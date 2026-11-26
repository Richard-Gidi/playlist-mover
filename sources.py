"""Read playlists from public links (Apple Music, Spotify, Deezer, YouTube) or from a pasted/uploaded list."""
from __future__ import annotations

import csv
import io
import json
import re
from urllib.parse import parse_qs, urlparse

import requests

from core import Playlist, Track

UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}


class SourceError(Exception):
    pass


def detect(url: str) -> str | None:
    u = (url or "").strip().lower()
    if not u:
        return None
    if "music.apple.com" in u:
        return "apple"
    if "open.spotify.com" in u or u.startswith("spotify:"):
        return "spotify"
    if "deezer.com" in u or "deezer.page.link" in u:
        return "deezer"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    return None


def read_url(url: str, spotify_client=None) -> Playlist:
    kind = detect(url)
    if kind == "apple":
        return read_apple(url)
    if kind == "spotify":
        return read_spotify(url, spotify_client)
    if kind == "deezer":
        return read_deezer(url)
    if kind == "youtube":
        return read_youtube(url)
    raise SourceError("That link isn't from Apple Music, Spotify, Deezer or YouTube.")


def _get(url: str, **kw) -> requests.Response:
    try:
        r = requests.get(url, headers=UA, timeout=30, **kw)
    except requests.RequestException as e:
        raise SourceError(f"Couldn't reach {urlparse(url).netloc}: {e}") from e
    if r.status_code != 200:
        raise SourceError(f"{urlparse(url).netloc} answered {r.status_code}. Is the playlist public?")
    if not r.encoding or r.encoding.lower() in ("iso-8859-1", "latin-1", "ascii"):
        r.encoding = "utf-8"  # pages that omit a charset are UTF-8 in practice (emoji in titles)
    return r


# ---------------- Apple Music ----------------

def _apple_art(art: dict | None, size: int = 300) -> str:
    try:
        u = art["dictionary"]["url"]
    except (TypeError, KeyError):
        return ""
    return u.replace("{w}", str(size)).replace("{h}", str(size)).replace("{f}", "jpg")


def read_apple(url: str) -> Playlist:
    if "/playlist/" not in url:
        raise SourceError("Only Apple Music playlist links are supported.")
    html = _get(url.strip()).text
    name, owner, cover, tracks = "", "", "", []

    m = re.search(r'<script[^>]*id="serialized-server-data"[^>]*>(.*?)</script>', html, re.S)
    if m:
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            data = None

        def walk(n):
            nonlocal name, owner, cover
            if isinstance(n, dict):
                nid = str(n.get("id", ""))
                if nid.startswith("playlist-detail-header") and not name:
                    name = n.get("title", "") or ""
                    subs = n.get("subtitleLinks") or []
                    owner = subs[0].get("title", "") if subs else ""
                    cover = _apple_art(n.get("artwork"), 600)
                if isinstance(n.get("title"), str) and isinstance(n.get("artistName"), str):
                    tert = n.get("tertiaryLinks") or []
                    dur = n.get("duration")
                    tracks.append(Track(
                        title=n["title"], artist=n["artistName"],
                        album=tert[0].get("title", "") if tert else "",
                        duration_ms=int(dur) if isinstance(dur, (int, float)) else 0,
                        art=_apple_art(n.get("artwork")),
                    ))
                    return
                for v in n.values():
                    walk(v)
            elif isinstance(n, list):
                for v in n:
                    walk(v)

        if data is not None:
            walk(data)

    if not tracks:  # schema.org fallback
        for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
            try:
                d = json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
            for t in (d.get("track") or []) if isinstance(d, dict) else []:
                by = t.get("byArtist") or {}
                artist = (", ".join(b.get("name", "") for b in by) if isinstance(by, list)
                          else by.get("name", "") if isinstance(by, dict) else str(by))
                if t.get("name"):
                    tracks.append(Track(title=t["name"], artist=artist))

    if not name:
        og = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', html)
        name = re.sub(r"\s+(by\s.+)?\s*on Apple Music$", "", og.group(1)).strip() if og else "Apple Music playlist"
    if not tracks:
        raise SourceError("Apple Music didn't show any songs for that link.")
    return Playlist(name=name, owner=owner, cover=cover, tracks=tracks, platform="apple", url=url)


# ---------------- Spotify ----------------

def _spotify_id(url: str) -> str:
    m = re.search(r"playlist[/:]([A-Za-z0-9]{22})", url)
    if not m:
        raise SourceError("That isn't a Spotify playlist link.")
    return m.group(1)


def read_spotify(url: str, sp=None) -> Playlist:
    pid = _spotify_id(url)
    if sp is not None:  # full list through the API when the user is logged in
        try:
            meta = sp.playlist(pid, fields="name,owner(display_name),images")
            page = sp.playlist_items(pid, limit=100, additional_types=("track",))
            tracks = []
            while page:
                for it in page.get("items", []):
                    t = it.get("track") or it.get("item")
                    if not t or not t.get("name") or t.get("type", "track") != "track":
                        continue
                    imgs = (t.get("album") or {}).get("images") or []
                    tracks.append(Track(
                        title=t["name"], artist=", ".join(a["name"] for a in t.get("artists", [])),
                        album=(t.get("album") or {}).get("name", ""),
                        isrc=(t.get("external_ids") or {}).get("isrc", ""),
                        duration_ms=t.get("duration_ms") or 0,
                        art=imgs[-1]["url"] if imgs else "",
                        ids={"spotify": t.get("uri", "")},
                    ))
                page = sp.next(page) if page.get("next") else None
            if tracks:
                imgs = meta.get("images") or []
                return Playlist(name=meta.get("name", "Spotify playlist"),
                                owner=(meta.get("owner") or {}).get("display_name", ""),
                                cover=imgs[0]["url"] if imgs else "", tracks=tracks,
                                platform="spotify", url=url)
        except Exception:  # noqa: BLE001 - fall back to the public embed below
            pass

    html = _get(f"https://open.spotify.com/embed/playlist/{pid}").text
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise SourceError("Spotify didn't return that playlist. Is it public?")
    ent = (json.loads(m.group(1)).get("props", {}).get("pageProps", {})
           .get("state", {}).get("data", {}).get("entity", {}))
    tracks = [
        Track(title=t.get("title", ""), artist=t.get("subtitle", ""),
              duration_ms=int(t.get("duration") or 0), ids={"spotify": t.get("uri", "")})
        for t in ent.get("trackList", []) if t.get("title")
    ]
    if not tracks:
        raise SourceError("That Spotify playlist looks empty or private.")
    srcs = (ent.get("coverArt") or {}).get("sources") or []
    note = ("Spotify's public view may stop at 100 songs. Connect Spotify on the Destination page "
            "and read the link again to get the full list.") if len(tracks) >= 100 and sp is None else ""
    return Playlist(name=ent.get("name") or ent.get("title") or "Spotify playlist",
                    owner=ent.get("subtitle", ""), cover=srcs[0]["url"] if srcs else "",
                    tracks=tracks, platform="spotify", url=url, note=note)


# ---------------- Deezer ----------------

def read_deezer(url: str) -> Playlist:
    if "page.link" in url or "link.deezer.com" in url:
        try:
            url = requests.get(url, headers=UA, timeout=20, allow_redirects=True).url
        except requests.RequestException as e:
            raise SourceError(f"Couldn't open that Deezer short link: {e}") from e
    m = re.search(r"playlist/(\d+)", url)
    if not m:
        raise SourceError("That isn't a Deezer playlist link.")
    pid = m.group(1)
    meta = _get(f"https://api.deezer.com/playlist/{pid}").json()
    if "error" in meta:
        raise SourceError(f"Deezer: {meta['error'].get('message', 'playlist not found')}")
    tracks, nxt = [], f"https://api.deezer.com/playlist/{pid}/tracks?limit=100"
    while nxt and len(tracks) < 10000:
        page = _get(nxt).json()
        for t in page.get("data", []):
            tracks.append(Track(
                title=t.get("title", ""), artist=(t.get("artist") or {}).get("name", ""),
                album=(t.get("album") or {}).get("title", ""), isrc=t.get("isrc", "") or "",
                duration_ms=int(t.get("duration") or 0) * 1000,
                art=(t.get("album") or {}).get("cover_medium", ""),
                ids={"deezer": str(t.get("id", ""))},
            ))
        nxt = page.get("next")
    return Playlist(name=meta.get("title", "Deezer playlist"),
                    owner=(meta.get("creator") or {}).get("name", ""),
                    cover=meta.get("picture_xl") or meta.get("picture_big", ""),
                    tracks=tracks, platform="deezer", url=url)


# ---------------- YouTube / YouTube Music ----------------

def read_youtube(url: str) -> Playlist:
    q = parse_qs(urlparse(url).query)
    pid = (q.get("list") or [""])[0]
    if not pid:
        raise SourceError("That YouTube link has no playlist in it (look for ?list= in the link).")
    try:
        from ytmusicapi import YTMusic
        pl = YTMusic().get_playlist(pid, limit=None)
    except Exception as e:  # noqa: BLE001
        raise SourceError(f"YouTube didn't return that playlist ({e}). Is it public or unlisted?") from e
    tracks = []
    for t in pl.get("tracks", []):
        if not t.get("title"):
            continue
        thumbs = t.get("thumbnails") or []
        tracks.append(Track(
            title=t["title"], artist=", ".join(a.get("name", "") for a in (t.get("artists") or [])),
            album=(t.get("album") or {}).get("name", "") if t.get("album") else "",
            duration_ms=int(t.get("duration_seconds") or 0) * 1000,
            art=thumbs[0]["url"] if thumbs else "",
            ids={"youtube": t.get("videoId", "")},
        ))
    if not tracks:
        raise SourceError("That YouTube playlist looks empty or private.")
    author = pl.get("author")
    thumbs = pl.get("thumbnails") or []
    return Playlist(name=pl.get("title", "YouTube playlist"),
                    owner=author.get("name", "") if isinstance(author, dict) else (author or ""),
                    cover=thumbs[-1]["url"] if thumbs else "", tracks=tracks, platform="youtube", url=url)


# ---------------- pasted / uploaded list ----------------

def parse_text(text: str) -> list[Track]:
    text = (text or "").lstrip("﻿")
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return []
    head = lines[0].lower()
    if "," in head and any(k in head for k in ("title", "track", "song", "name")) and "artist" in head:
        rows = list(csv.DictReader(io.StringIO("\n".join(lines))))
        cols = {k.lower().strip(): k for k in rows[0].keys()} if rows else {}
        tk = next((cols[k] for k in ("title", "track", "track name", "song", "name") if k in cols), None)
        ak = next((cols[k] for k in ("artist", "artists", "artist name", "artist name(s)") if k in cols), None)
        bk = next((cols[k] for k in ("album", "album name") if k in cols), None)
        ik = cols.get("isrc")
        return [Track(title=r[tk].strip(), artist=(r.get(ak) or "").strip() if ak else "",
                      album=(r.get(bk) or "").strip() if bk else "",
                      isrc=(r.get(ik) or "").strip() if ik else "")
                for r in rows if tk and (r.get(tk) or "").strip()]
    out = []
    for line in lines:
        line = re.sub(r"^\s*\d+[\.\)]\s*", "", line).strip()
        for sep in ("\t", " - ", " – ", " — ", " by "):
            if sep in line:
                title, artist = line.split(sep, 1)
                out.append(Track(title=title.strip(), artist=artist.strip()))
                break
        else:
            out.append(Track(title=line, artist=""))
    return out
