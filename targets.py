"""Destinations: Spotify, YouTube Music, and file/link exports for every other app."""
from __future__ import annotations

import base64
import csv
import html
import io
import time
from urllib.parse import quote, quote_plus

import requests
import spotipy
from spotipy.cache_handler import CacheHandler
from spotipy.oauth2 import SpotifyOAuth

from core import Candidate, RateLimited, Track, clean_title, lead_artist

# ======================= Spotify =======================

SPOTIFY_SCOPES = ("user-read-private playlist-read-private playlist-modify-private "
                  "playlist-modify-public ugc-image-upload")


class JobCache(CacheHandler):
    """Keeps a user's Spotify token inside their own job (never shared between visitors)."""

    def __init__(self, job: dict):
        self.job = job

    def get_cached_token(self):
        return self.job.get("spotify_token")

    def save_token_to_cache(self, token_info):
        self.job["spotify_token"] = token_info


def spotify_oauth(cfg: dict, job: dict) -> SpotifyOAuth:
    return SpotifyOAuth(client_id=cfg["spotify_id"], client_secret=cfg["spotify_secret"],
                        redirect_uri=cfg["redirect_uri"], scope=SPOTIFY_SCOPES,
                        cache_handler=JobCache(job), open_browser=False)


def spotify_client(cfg: dict, job: dict) -> spotipy.Spotify | None:
    if not (cfg.get("spotify_id") and cfg.get("spotify_secret")):
        return None
    oauth = spotify_oauth(cfg, job)
    try:
        tok = oauth.validate_token(oauth.cache_handler.get_cached_token())
    except Exception:  # noqa: BLE001
        tok = None
    if not tok:
        return None
    # no automatic retries: a long Retry-After must surface, not freeze the app
    return spotipy.Spotify(auth_manager=oauth, retries=0, status_retries=0, requests_timeout=15)


def _sp_call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except spotipy.SpotifyException as e:
        if e.http_status == 429:
            raise RateLimited(int((e.headers or {}).get("Retry-After", 60))) from e
        raise


def _sp_cand(t: dict) -> Candidate:
    imgs = (t.get("album") or {}).get("images") or []
    return Candidate(
        id=t["uri"], title=t.get("name", ""), artists=[a["name"] for a in t.get("artists", [])],
        album=(t.get("album") or {}).get("name", ""), duration_ms=t.get("duration_ms") or 0,
        art=(imgs[-1] if imgs else {}).get("url", ""), url=(t.get("external_urls") or {}).get("spotify", ""),
    )


def spotify_search(sp, track: Track, query: str | None = None) -> tuple[list[Candidate], str]:
    if query:
        items = _sp_call(sp.search, q=query, type="track", limit=8, market="from_token")["tracks"]["items"]
        return [_sp_cand(t) for t in items], "manual"
    if track.isrc:
        items = _sp_call(sp.search, q=f"isrc:{track.isrc}", type="track", limit=1, market="from_token")["tracks"]["items"]
        if items:
            return [_sp_cand(items[0])], "ISRC"
    title, artist = clean_title(track.title), lead_artist(track.artist)
    q = f'track:"{title}" artist:"{artist}"' if artist else title
    items = _sp_call(sp.search, q=q, type="track", limit=5, market="from_token")["tracks"]["items"]
    if not items and artist:
        items = _sp_call(sp.search, q=f"{title} {artist}", type="track", limit=5, market="from_token")["tracks"]["items"]
    return [_sp_cand(t) for t in items], "search"


def _cover_b64(url: str) -> str | None:
    try:
        from PIL import Image
        raw = requests.get(url, timeout=20).content
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        img.thumbnail((640, 640))
        for q in (90, 80, 70, 60):
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=q)
            b = base64.b64encode(buf.getvalue()).decode()
            if len(b) < 250_000:
                return b
    except Exception:  # noqa: BLE001
        return None
    return None


def spotify_create(sp, name: str, description: str, public: bool, uris: list[str],
                   cover_url: str = "") -> tuple[str, str]:
    payload = {"name": name, "public": public, "description": description[:290]}
    try:
        me = _sp_call(sp.current_user)
        pl = _sp_call(sp.user_playlist_create, me["id"], name, public=public, description=payload["description"])
    except spotipy.SpotifyException:
        pl = _sp_call(sp._post, "me/playlists", payload=payload)
    for i in range(0, len(uris), 100):
        _sp_call(sp.playlist_add_items, pl["id"], uris[i:i + 100])
    note = ""
    if cover_url:
        b64 = _cover_b64(cover_url)
        try:
            if b64:
                sp.playlist_upload_cover_image(pl["id"], b64)
                note = "Cover art copied."
        except Exception:  # noqa: BLE001
            note = "Spotify didn't accept the cover image, so it kept its own."
    return pl["external_urls"]["spotify"], note


# ======================= YouTube Music (beta) =======================

def yt_start_device_login(cfg: dict) -> dict:
    from ytmusicapi import OAuthCredentials
    return dict(OAuthCredentials(cfg["google_id"], cfg["google_secret"]).get_code())


def yt_finish_device_login(cfg: dict, device_code: str) -> tuple[dict | None, str]:
    from ytmusicapi import OAuthCredentials
    tok = dict(OAuthCredentials(cfg["google_id"], cfg["google_secret"]).token_from_code(device_code))
    if "error" in tok:
        err = tok.get("error")
        if err in ("authorization_pending", "slow_down"):
            return None, "Not approved yet. Finish the Google step, then press the button again."
        return None, f"Google said: {err}. Start again."
    tok["expires_at"] = int(time.time()) + int(tok.get("expires_in", 3600))
    return tok, ""


def yt_client(cfg: dict, job: dict):
    if not job.get("yt_token"):
        return None
    if job.get("yt_client") is None:
        from ytmusicapi import OAuthCredentials, YTMusic
        job["yt_client"] = YTMusic(auth=job["yt_token"],
                                   oauth_credentials=OAuthCredentials(cfg["google_id"], cfg["google_secret"]))
    return job["yt_client"]


def _yt_cand(r: dict) -> Candidate:
    thumbs = r.get("thumbnails") or []
    return Candidate(
        id=r.get("videoId", ""), title=r.get("title", ""),
        artists=[a.get("name", "") for a in (r.get("artists") or [])],
        album=(r.get("album") or {}).get("name", "") if r.get("album") else "",
        duration_ms=int(r.get("duration_seconds") or 0) * 1000,
        art=thumbs[0]["url"] if thumbs else "",
        url=f"https://music.youtube.com/watch?v={r.get('videoId', '')}",
    )


def yt_search(yt, track: Track, query: str | None = None) -> tuple[list[Candidate], str]:
    q = query or f"{clean_title(track.title)} {lead_artist(track.artist)}".strip()
    res = yt.search(q, filter="songs", limit=8 if query else 5)
    return [_yt_cand(r) for r in res if r.get("videoId")][: 8 if query else 5], ("manual" if query else "search")


def yt_create(yt, name: str, description: str, public: bool, video_ids: list[str]) -> tuple[str, str]:
    pid = yt.create_playlist(name, description[:4900], privacy_status="PUBLIC" if public else "PRIVATE")
    if not isinstance(pid, str):
        raise RuntimeError(f"YouTube Music refused to create the playlist: {pid}")
    for i in range(0, len(video_ids), 50):
        yt.add_playlist_items(pid, video_ids[i:i + 50], duplicates=False)
        time.sleep(0.5)
    return f"https://music.youtube.com/playlist?list={pid}", ""


# ======================= exports (every other app) =======================

SEARCH_LINKS = {
    "Apple Music": "https://music.apple.com/search?term={q}",
    "Spotify": "https://open.spotify.com/search/{p}",
    "YouTube Music": "https://music.youtube.com/search?q={q}",
    "Deezer": "https://www.deezer.com/search/{p}",
    "Tidal": "https://listen.tidal.com/search?q={q}",
    "Amazon Music": "https://music.amazon.com/search/{p}",
    "SoundCloud": "https://soundcloud.com/search?q={q}",
    "Audiomack": "https://audiomack.com/search?q={q}",
}


def export_csv(tracks: list[Track]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Title", "Artist", "Album", "ISRC"])
    for t in tracks:
        w.writerow([t.title, t.artist, t.album, t.isrc])
    return buf.getvalue()


def link_sheet(name: str, tracks: list[Track]) -> str:
    rows = []
    for i, t in enumerate(tracks, 1):
        q = f"{clean_title(t.title)} {lead_artist(t.artist)}".strip()
        links = " ".join(
            f'<a href="{html.escape(tpl.format(q=quote_plus(q), p=quote(q)))}" target="_blank">{html.escape(n)}</a>'
            for n, tpl in SEARCH_LINKS.items())
        rows.append(f"<tr><td>{i}</td><td><b>{html.escape(t.title)}</b><br><span>{html.escape(t.artist)}</span></td>"
                    f"<td class=l>{links}</td></tr>")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{html.escape(name)} · link sheet</title>
<style>body{{font-family:Inter,system-ui,sans-serif;background:#0b0b12;color:#ececf4;margin:0;padding:32px}}
h1{{font-family:'Space Grotesk',system-ui;margin:0 0 4px}}p{{color:#9a9ab0;margin:0 0 24px}}
table{{width:100%;border-collapse:collapse}}td{{padding:10px 8px;border-bottom:1px solid #22222f;vertical-align:top}}
td span{{color:#9a9ab0;font-size:.9em}}td.l a{{display:inline-block;margin:2px 4px 2px 0;padding:4px 10px;border-radius:999px;
background:#1a1a28;color:#cfc4ff;text-decoration:none;font-size:.82em}}td.l a:hover{{background:#7c5cff;color:#fff}}</style>
</head><body><h1>{html.escape(name)}</h1><p>{len(tracks)} songs · tap a service to find each song there</p>
<table>{''.join(rows)}</table></body></html>"""
