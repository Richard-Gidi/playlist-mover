"""Shared data types, title cleaning and match scoring."""
from __future__ import annotations

import difflib
import re
from collections import Counter
from dataclasses import dataclass, field

# key -> (label, brand-ish colour, can_read, can_write)
PLATFORMS = {
    "apple":   ("Apple Music",   "#FA2D48", True,  False),
    "spotify": ("Spotify",       "#1ED760", True,  True),
    "youtube": ("YouTube Music", "#FF0033", True,  True),
    "deezer":  ("Deezer",        "#A238FF", True,  False),
    "text":    ("Song list",     "#9CA3AF", True,  False),
    "tmm":     ("Via TuneMyMusic", "#FFB020", False, True),
    "export":  ("Any other app", "#22D3EE", False, True),
}

# services reachable through TuneMyMusic's "upload a CSV" pages: label -> (url slug, colour)
TMM_SERVICES = {
    "Apple Music": ("apple-music", "#FA2D48"),
    "Deezer": ("deezer", "#A238FF"),
    "Boomplay": ("boomplay", "#2E7CF6"),
    "Audiomack": ("audiomack", "#FFA200"),
    "TIDAL": ("tidal", "#E5E7EB"),
    "Amazon Music": ("amazon-music", "#25D1DA"),
    "SoundCloud": ("soundcloud", "#FF5500"),
    "YouTube Music": ("youtube-music", "#FF0033"),
    "Spotify": ("spotify", "#1ED760"),
}


def tmm_url(service: str) -> str:
    return f"https://www.tunemymusic.com/transfer/csv-to-{TMM_SERVICES[service][0]}"


def label(key: str) -> str:
    return PLATFORMS.get(key, (key.title(),))[0]


def colour(key: str) -> str:
    return PLATFORMS.get(key, ("", "#888"))[1]


@dataclass
class Track:
    title: str
    artist: str
    album: str = ""
    isrc: str = ""
    duration_ms: int = 0
    art: str = ""
    ids: dict = field(default_factory=dict)   # platform key -> that platform's own id


@dataclass
class Playlist:
    name: str
    tracks: list[Track]
    platform: str
    owner: str = ""
    cover: str = ""
    url: str = ""
    note: str = ""


@dataclass
class Candidate:
    id: str
    title: str
    artists: list[str]
    album: str = ""
    duration_ms: int = 0
    art: str = ""
    url: str = ""


class RateLimited(Exception):
    def __init__(self, wait_s: int):
        super().__init__(f"rate limited for {wait_s}s")
        self.wait_s = wait_s


# ---------- cleaning ----------

_BRACKET = re.compile(
    r"\s*[\(\[][^\)\]]*\b(feat\.?|ft\.?|with|prod\.?|remaster(ed)?|radio edit|version|from|live|mono|stereo|"
    r"edit|explicit|clean)\b[^\)\]]*[\)\]]", re.I)
_TAIL = re.compile(r"\s+-\s+(\d{4}\s+)?(remaster(ed)?|live|radio edit|mono|stereo|single|.*version|.*mix)\b.*$", re.I)


def clean_title(s: str) -> str:
    out = _TAIL.sub("", _BRACKET.sub("", s or "")).strip()
    return out or (s or "").strip()


def split_artists(s: str) -> list[str]:
    parts = re.split(r",|&| x | X |\bfeat\.?|\bft\.?|\band\b", s or "")
    return [p.strip() for p in parts if p.strip()]


def lead_artist(s: str) -> str:
    a = split_artists(s)
    return a[0] if a else ""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def score(track: Track, cand: Candidate) -> float:
    t = difflib.SequenceMatcher(None, _norm(clean_title(track.title)), _norm(clean_title(cand.title))).ratio()
    want = _norm(lead_artist(track.artist))
    if not want:
        a = 0.7
    elif not cand.artists:
        a = 0.0
    else:
        a = max(
            1.0 if (want in _norm(x) or _norm(x) in want) and _norm(x) else
            difflib.SequenceMatcher(None, want, _norm(x)).ratio()
            for x in cand.artists
        )
    s = 0.6 * t + 0.4 * a
    if track.duration_ms and cand.duration_ms:
        gap = abs(track.duration_ms - cand.duration_ms) / 1000
        if gap > 20:
            s -= min(0.15, gap / 600)
    return round(max(s, 0.0), 3)


def best_of(track: Track, cands: list[Candidate]) -> tuple[Candidate | None, float]:
    best, best_s = None, 0.0
    for c in cands:
        s = score(track, c)
        if s > best_s:
            best, best_s = c, s
    return best, best_s


# ---------- playlist "DNA" ----------

def fmt_ms(ms: int) -> str:
    s = int(ms // 1000)
    h, m = divmod(s // 60, 60)
    return f"{h} h {m} min" if h else f"{m} min {s % 60:02d} s"


def dna(tracks: list[Track]) -> dict:
    artists = Counter()
    for t in tracks:
        for a in split_artists(t.artist)[:2]:
            artists[a] += 1
    durs = [t.duration_ms for t in tracks if t.duration_ms]
    longest = max(tracks, key=lambda t: t.duration_ms) if durs else None
    return {
        "count": len(tracks),
        "unique_artists": len(artists),
        "top": artists.most_common(6),
        "total_ms": sum(durs),
        "avg_ms": int(sum(durs) / len(durs)) if durs else 0,
        "longest": longest,
    }
