"""Find songs on Spotify and build the playlist."""
from __future__ import annotations

import difflib
import re

import spotipy
from spotipy.cache_handler import CacheFileHandler, CacheHandler
from spotipy.oauth2 import SpotifyOAuth

from apple_music import Track

SCOPES = "user-read-private playlist-modify-private playlist-modify-public"
TOKEN_FILE = ".spotify_token"


class SessionCacheHandler(CacheHandler):
    """Keeps the Spotify token in this browser session only (safe on a shared server)."""

    def __init__(self, store: dict, key: str = "spotify_token"):
        self.store, self.key = store, key

    def get_cached_token(self):
        return self.store.get(self.key)

    def save_token_to_cache(self, token_info):
        self.store[self.key] = token_info


def make_oauth(client_id: str, client_secret: str, redirect_uri: str, store: dict | None = None) -> SpotifyOAuth:
    cache = SessionCacheHandler(store) if store is not None else CacheFileHandler(cache_path=TOKEN_FILE)
    return SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPES,
        cache_handler=cache,
        open_browser=False,
    )


_FEAT = re.compile(r"\s*[\(\[](feat\.?|ft\.?|with|prod\.?)\s[^\)\]]*[\)\]]", re.I)
_TAIL = re.compile(r"\s+-\s+(\d{4}\s+)?(remaster(ed)?|live|radio edit|mono|stereo|single|.*version|.*mix)\b.*$", re.I)


def clean_title(s: str) -> str:
    return _TAIL.sub("", _FEAT.sub("", s)).strip()


def lead_artist(s: str) -> str:
    return re.split(r",|&| x | X |\bfeat\.?|\bft\.?", s)[0].strip()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def score(track: Track, cand: dict) -> float:
    t = difflib.SequenceMatcher(None, _norm(clean_title(track.title)), _norm(clean_title(cand["name"]))).ratio()
    if not track.artist:
        a = 0.7
    else:
        want = _norm(lead_artist(track.artist))
        a = max(
            (1.0 if want and (want in _norm(x["name"]) or _norm(x["name"]) in want)
             else difflib.SequenceMatcher(None, want, _norm(x["name"])).ratio())
            for x in cand["artists"]
        ) if cand.get("artists") else 0.0
    s = 0.6 * t + 0.4 * a
    if track.duration_ms and cand.get("duration_ms"):
        gap = abs(track.duration_ms - cand["duration_ms"]) / 1000
        if gap > 20:
            s -= min(0.15, gap / 600)
    return round(max(s, 0.0), 3)


class RateLimited(Exception):
    def __init__(self, wait_s: int):
        super().__init__(f"Spotify rate limit, retry after {wait_s}s")
        self.wait_s = wait_s


def make_client(oauth: SpotifyOAuth) -> spotipy.Spotify:
    # No automatic retries: spotipy would otherwise sleep through a long Retry-After
    # (Spotify can ask for 24h) and the app would just look frozen.
    return spotipy.Spotify(auth_manager=oauth, retries=0, status_retries=0, requests_timeout=15)


def _search(sp: spotipy.Spotify, q: str, limit: int) -> list[dict]:
    try:
        return sp.search(q=q, type="track", limit=limit, market="from_token")["tracks"]["items"]
    except spotipy.SpotifyException as e:
        if e.http_status == 429:
            wait = int((e.headers or {}).get("Retry-After", 60))
            raise RateLimited(wait) from e
        raise


def match_track(sp: spotipy.Spotify, track: Track) -> tuple[dict | None, float, str]:
    if track.isrc:
        items = _search(sp, f"isrc:{track.isrc}", 1)
        if items:
            return items[0], 1.0, "ISRC"

    title = clean_title(track.title)
    artist = lead_artist(track.artist)
    # one precise query; only fall back to a loose one when it finds nothing at all
    items = _search(sp, f'track:"{title}" artist:"{artist}"' if artist else title, 5)
    if not items and artist:
        items = _search(sp, f"{title} {artist}", 5)

    best, best_s = None, 0.0
    for c in items:
        sc = score(track, c)
        if sc > best_s:
            best, best_s = c, sc
    return best, best_s, ("search" if best else "not found")


def create_playlist(sp: spotipy.Spotify, name: str, description: str, public: bool, uris: list[str]) -> dict:
    me = sp.current_user()
    payload = {"name": name, "public": public, "description": description}
    try:
        pl = sp.user_playlist_create(me["id"], name, public=public, description=description)
    except spotipy.SpotifyException:
        # newer accounts/apps may only allow the /me endpoint
        pl = sp._post("me/playlists", payload=payload)
    for i in range(0, len(uris), 100):
        sp.playlist_add_items(pl["id"], uris[i:i + 100])
    return pl
