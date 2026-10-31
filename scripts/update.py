#!/usr/bin/env python3
"""Récupère les flux RSS listés dans feeds.txt et écrit episodes.json
(épisodes triés du plus récent au plus ancien). Aucune dépendance externe."""
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEEDS_FILE = ROOT / "feeds.txt"
OUT_FILE = ROOT / "episodes.json"
PER_FEED = 30      # épisodes gardés par podcast
MAX_TOTAL = 300    # épisodes gardés au total

NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "atom": "http://www.w3.org/2005/Atom",
}


def text(el, path):
    found = el.find(path, NS)
    return (found.text or "").strip() if found is not None and found.text else ""


def parse_date(raw):
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def parse_duration(raw):
    """'1:02:03', '62:03' ou '3723' -> secondes."""
    if not raw:
        return None
    try:
        parts = [int(float(p)) for p in raw.split(":")]
    except ValueError:
        return None
    total = 0
    for p in parts:
        total = total * 60 + p
    return total


def parse_feed(xml_bytes, feed_url):
    root = ET.fromstring(xml_bytes)
    episodes = []
    channel = root.find("channel")
    if channel is not None:  # RSS 2.0 (le cas de presque tous les podcasts)
        show = text(channel, "title")
        img_el = channel.find("itunes:image", NS)
        show_img = img_el.get("href") if img_el is not None else text(channel, "image/url")
        for item in channel.findall("item")[:PER_FEED]:
            enc = item.find("enclosure")
            audio = enc.get("url") if enc is not None else ""
            ep_img_el = item.find("itunes:image", NS)
            episodes.append({
                "show": show,
                "title": text(item, "title"),
                "date": parse_date(text(item, "pubDate")),
                "audio": audio,
                "link": text(item, "link"),
                "duration": parse_duration(text(item, "itunes:duration")),
                "image": ep_img_el.get("href") if ep_img_el is not None else show_img,
                "id": text(item, "guid") or audio or text(item, "title"),
                "feed": feed_url,
            })
    else:  # Atom
        show = text(root, "atom:title")
        for entry in root.findall("atom:entry", NS)[:PER_FEED]:
            audio = ""
            link = ""
            for l in entry.findall("atom:link", NS):
                if l.get("rel") == "enclosure":
                    audio = l.get("href", "")
                elif not link:
                    link = l.get("href", "")
            episodes.append({
                "show": show,
                "title": text(entry, "atom:title"),
                "date": parse_date(text(entry, "atom:published") or text(entry, "atom:updated")),
                "audio": audio,
                "link": link,
                "duration": None,
                "image": "",
                "id": text(entry, "atom:id") or audio,
                "feed": feed_url,
            })
    return show, episodes


def read_feed_urls():
    urls = []
    for line in FEEDS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (podcast-updater)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main():
    all_eps, shows, errors = [], [], []
    for url in read_feed_urls():
        try:
            show, eps = parse_feed(fetch(url), url)
            shows.append({"title": show, "feed": url, "count": len(eps)})
            all_eps.extend(eps)
            print(f"OK  {show} ({len(eps)} épisodes)")
        except Exception as e:  # un flux cassé ne bloque pas les autres
            errors.append({"feed": url, "error": str(e)[:200]})
            print(f"ERR {url}: {e}", file=sys.stderr)

    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    all_eps.sort(key=lambda e: e["date"] or epoch, reverse=True)
    all_eps = all_eps[:MAX_TOTAL]
    for e in all_eps:
        e["date"] = e["date"].isoformat() if e["date"] else None

    OUT_FILE.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "shows": shows,
        "errors": errors,
        "episodes": all_eps,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(all_eps)} épisodes écrits dans episodes.json")


if __name__ == "__main__":
    main()
