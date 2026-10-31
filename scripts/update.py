#!/usr/bin/env python3
"""Récupère les flux RSS listés dans feeds.txt et écrit episodes.json
(épisodes triés du plus récent au plus ancien). Aucune dépendance externe."""
import json
import re
import sys
import unicodedata
import urllib.parse
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


RESOLVED_FILE = ROOT / "feeds-resolved.json"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("€", " euros ")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def lookup(name, artist_hint=""):
    """Trouve le flux RSS d'un podcast à partir de son nom (annuaire Apple Podcasts)."""
    q = urllib.parse.urlencode({"term": name, "media": "podcast", "entity": "podcast",
                                "country": "FR", "limit": 15})
    results = json.loads(fetch("https://itunes.apple.com/search?" + q)).get("results", [])
    results = [r for r in results if r.get("feedUrl")]
    if artist_hint:
        # diffuseur précisé : on refuse un homonyme plutôt que de se tromper de podcast
        results = [r for r in results if norm(artist_hint) in norm(r.get("artistName"))]
    if not results:
        raise ValueError(f"podcast introuvable : {name}")
    n = norm(name)

    def score(r):
        t = norm(r.get("collectionName"))
        if t == n:
            return 0
        if t.startswith(n):
            return 1
        if n in t:
            return 2
        return 3

    best = min(results, key=score)   # à égalité, garde l'ordre de pertinence d'Apple
    return best["feedUrl"], best.get("collectionName", ""), best.get("artistName", "")


def read_feed_urls():
    """Chaque ligne de feeds.txt est soit une adresse de flux, soit un nom de podcast
    (éventuellement « Nom | Diffuseur » pour lever une ambiguïté)."""
    try:
        resolved = json.loads(RESOLVED_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        resolved = {}
    direct, urls, errors, used = [], [], [], {}
    for line in FEEDS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("http"):
            direct.append(line)
            continue
        if line not in resolved:
            name, _, hint = line.partition("|")
            try:
                url, title, artist = lookup(name.strip(), hint.strip())
                resolved[line] = {"feed": url, "title": title, "artist": artist}
                print(f"Trouvé : {line} -> {title} ({artist})")
            except Exception as e:
                errors.append({"feed": line, "error": str(e)[:200]})
                continue
        used[line] = resolved[line]
        urls.append(resolved[line]["feed"])
    RESOLVED_FILE.write_text(json.dumps(used, ensure_ascii=False, indent=1), encoding="utf-8")
    # Les adresses collées à la main passent en premier : elles priment sur une recherche par nom
    return direct + urls, errors


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (podcast-updater)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main():
    all_eps, shows = [], []
    urls, errors = read_feed_urls()
    for url in urls:
        try:
            show, eps = parse_feed(fetch(url), url)
            if norm(show) in {norm(s["title"]) for s in shows}:
                print(f"--  {show} déjà présent, flux ignoré : {url}")
                continue
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
