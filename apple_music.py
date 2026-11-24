"""Read a public Apple Music playlist from its share link. No Apple account needed.

Reads only what the public playlist page itself contains:
  1. the JSON embedded in the page, then
  2. the page's schema.org JSON-LD block.
Very long playlists may show only the first part on the page; paste the rest.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class Track:
    title: str
    artist: str
    album: str = ""
    isrc: str = ""
    duration_ms: int = 0


class AppleMusicError(Exception):
    pass


def parse_playlist_url(url: str) -> tuple[str, str]:
    """Return (storefront, playlist_id) from a music.apple.com playlist link."""
    p = urlparse(url.strip())
    if "music.apple.com" not in p.netloc:
        raise AppleMusicError("That isn't an Apple Music link.")
    parts = [x for x in p.path.split("/") if x]
    pid = next((x for x in parts if x.startswith("pl.")), None)
    if "playlist" not in parts or not pid:
        raise AppleMusicError("That link isn't a playlist link.")
    storefront = parts[0] if len(parts[0]) == 2 else "us"
    return storefront, pid


# ---------- reading the public page ----------

def _walk(node, out: list[Track]):
    if isinstance(node, dict):
        title, artist = node.get("title"), node.get("artistName")
        if isinstance(title, str) and isinstance(artist, str) and title:
            dur = node.get("duration") or node.get("durationInMillis") or 0
            out.append(Track(title=title, artist=artist,
                             duration_ms=int(dur) if isinstance(dur, (int, float)) else 0))
            return
        for v in node.values():
            _walk(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk(v, out)


def _from_page(html: str) -> list[Track]:
    tracks: list[Track] = []
    m = re.search(r'<script[^>]*id="serialized-server-data"[^>]*>(.*?)</script>', html, re.S)
    if m:
        try:
            _walk(json.loads(m.group(1)), tracks)
        except json.JSONDecodeError:
            pass

    if not tracks:
        for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
            try:
                d = json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
            items = d.get("track", []) if isinstance(d, dict) else []
            for t in items:
                by = t.get("byArtist") or {}
                if isinstance(by, list):
                    artist = ", ".join(b.get("name", "") for b in by if isinstance(b, dict))
                else:
                    artist = by.get("name", "") if isinstance(by, dict) else str(by)
                if t.get("name"):
                    tracks.append(Track(title=t["name"], artist=artist))

    # the embedded JSON can mention the same song twice (e.g. a "featured" shelf)
    seen, unique = set(), []
    for t in tracks:
        key = (t.title.lower(), t.artist.lower())
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


def _playlist_name(html: str) -> str:
    m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html)
    if not m:
        return "Imported playlist"
    name = m.group(1)
    # og:title looks like "Just vibes 😁 by Prince Semanhyia on Apple Music"
    name = re.sub(r"\s+on Apple Music$", "", name)
    name = re.sub(r"\s+by\s+[^\n]+$", "", name)
    return name.strip() or "Imported playlist"


def get_playlist(url: str) -> tuple[str, list[Track], str]:
    """Return (playlist_name, tracks, how_it_was_read)."""
    storefront, pid = parse_playlist_url(url)
    s = requests.Session()
    r = s.get(url.strip(), headers=HEADERS, timeout=30)
    if r.status_code != 200:
        raise AppleMusicError(f"Couldn't open the playlist page ({r.status_code}). Is it public?")
    html = r.text
    name = _playlist_name(html)

    tracks = _from_page(html)
    if tracks:
        return name, tracks, "public playlist page"
    raise AppleMusicError("Couldn't read any songs from that link.")


def parse_pasted(text: str) -> list[Track]:
    """One song per line: 'Title - Artist' (or 'Title by Artist', or tab-separated)."""
    out = []
    for line in text.splitlines():
        line = re.sub(r"^\s*\d+[\.\)]\s*", "", line).strip()
        if not line:
            continue
        for sep in ("\t", " - ", " – ", " — ", " by "):
            if sep in line:
                title, artist = line.split(sep, 1)
                out.append(Track(title=title.strip(), artist=artist.strip()))
                break
        else:
            out.append(Track(title=line, artist=""))
    return out
