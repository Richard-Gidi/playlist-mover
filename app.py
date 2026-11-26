"""Playlist Mover: copy playlists between Apple Music, Spotify, Deezer, YouTube Music and more.

Run locally:  streamlit run app.py --server.address 127.0.0.1 --server.port 8501
"""
from __future__ import annotations

import time

import pandas as pd
import spotipy
import streamlit as st

import store
import targets as T
import ui
from core import PLATFORMS, Candidate, RateLimited, best_of, colour, label, split_artists
from sources import SourceError, detect, parse_text, read_url

st.set_page_config(page_title="Playlist Mover", page_icon="🎧", layout="wide")
ui.inject()

cfg = store.config()
ss = st.session_state

# ---------- Spotify login round trip ----------
qp = st.query_params
if "state" in qp and ("code" in qp or "error" in qp):
    if store.adopt(qp["state"]):
        j = store.job()
        if "code" in qp:
            try:
                T.spotify_oauth(cfg, j).get_access_token(qp["code"], as_dict=False, check_cache=False)
                j.pop("me", None)
                ss.flash = ("ok", "Spotify connected.")
            except Exception as ex:  # noqa: BLE001
                ss.flash = ("err", f"Spotify login failed: {ex}")
        else:
            ss.flash = ("err", "Spotify login was cancelled.")
    st.query_params.clear()

job = store.job()
SPOTIFY_READY = bool(cfg["spotify_id"] and cfg["spotify_secret"])
GOOGLE_READY = bool(cfg["google_id"] and cfg["google_secret"])


def sp_client():
    return T.spotify_client(cfg, job) if SPOTIFY_READY else None


def sp_me(sp):
    if sp is None:
        return None
    if "me" not in job:
        try:
            job["me"] = sp.current_user()
        except spotipy.SpotifyException:
            job.pop("spotify_token", None)
            return None
    return job["me"]


def flash():
    msg = ss.pop("flash", None)
    if msg:
        (st.success if msg[0] == "ok" else st.error)(msg[1])


def go(page):
    st.switch_page(PAGES[page])


def paused_banner(platform="spotify"):
    left = store.paused_for(platform)
    if left:
        st.warning(f"{label(platform)} has asked this app to slow down. Searching there resumes in about "
                   f"{left / 3600:.1f} h. Reading playlists and exports still work.")
    return left


# =====================================================================
# Home
# =====================================================================

def page_home():
    flash()
    ui.hero()
    c1, c2, _ = st.columns([1.4, 1, 1.6])
    if c1.button("Start a transfer →", type="primary", width="stretch"):
        go("source")
    if job.get("playlist") and c2.button("Resume", width="stretch"):
        go("match" if job.get("target") else "destination")
    st.write("")
    ui.features()
    st.markdown("#### Where can it go?")
    ui.matrix()
    st.caption("Apple Music and Deezer only let large, approved apps create playlists. For those, "
               "use the link sheet: one tap per song opens it in the app of your choice.")


# =====================================================================
# 1 · Source
# =====================================================================

def page_source():
    ui.steps(1)
    st.markdown("## Where is the playlist now?")
    mode = st.radio("Source", ["Paste a link", "Upload or paste a song list"], horizontal=True,
                    label_visibility="collapsed")

    if mode == "Paste a link":
        url = st.text_input("Playlist link", placeholder="https://music.apple.com/…  ·  open.spotify.com/playlist/…  ·  "
                            "deezer.com/playlist/…  ·  youtube.com/playlist?list=…")
        kind = detect(url)
        if url and kind:
            st.markdown(f"Detected {ui.chip(kind)}", unsafe_allow_html=True)
        elif url:
            st.caption("I don't recognise that link yet. Apple Music, Spotify, Deezer and YouTube playlists work.")
        if st.button("Read playlist", type="primary", disabled=not kind):
            with st.spinner(f"Reading {label(kind)}…"):
                try:
                    pl = read_url(url, sp_client() if kind == "spotify" else None)
                    _set_playlist(pl)
                except SourceError as ex:
                    st.error(str(ex))
                except Exception as ex:  # noqa: BLE001
                    st.error(f"Something went wrong reading that link: {ex}")
    else:
        up = st.file_uploader("A .txt or .csv file", type=["txt", "csv"])
        text = st.text_area("Or paste songs, one per line: Title - Artist", height=200,
                            value=up.getvalue().decode("utf-8-sig", errors="replace") if up else "",
                            placeholder="Essence - Wizkid\nBlinding Lights - The Weeknd")
        name = st.text_input("Name it", value="My playlist")
        if st.button("Use this list", type="primary", disabled=not text.strip()):
            tracks = parse_text(text)
            if tracks:
                from core import Playlist
                _set_playlist(Playlist(name=name.strip() or "My playlist", tracks=tracks, platform="text"))
            else:
                st.error("I couldn't find any songs in that text.")

    pl = job.get("playlist")
    if pl:
        st.write("")
        ui.playlist_card(pl)
        if pl.note:
            st.info(pl.note)
        ui.dna_card(pl)
        with st.expander(f"See all {len(pl.tracks)} songs"):
            st.dataframe(pd.DataFrame([{"#": i + 1, "Title": t.title, "Artist": t.artist, "Album": t.album}
                                       for i, t in enumerate(pl.tracks)]),
                         hide_index=True, width="stretch", height=360)
        if st.button("Next: choose where it goes →", type="primary"):
            go("destination")


def _set_playlist(pl):
    job["playlist"] = pl
    for k in ("rows", "result", "fix"):
        job.pop(k, None)
    job["editor_v"] = job.get("editor_v", 0) + 1


# =====================================================================
# 2 · Destination
# =====================================================================

def page_destination():
    flash()
    ui.steps(2)
    pl = job.get("playlist")
    if not pl:
        st.info("Start by loading a playlist.")
        if st.button("Go to Source", type="primary"):
            go("source")
        return
    st.markdown("## Where should it go?")
    options = ["spotify", "youtube", "export"]
    if ss.get("dest_pick") not in options:
        ss.dest_pick = job.get("target") if job.get("target") in options else "spotify"
    pick = st.radio("Destination", options, key="dest_pick",
                    format_func=lambda k: {"spotify": "Spotify", "youtube": "YouTube Music (beta)",
                                           "export": "Any other app (link sheet + CSV)"}[k],
                    horizontal=True, label_visibility="collapsed")
    if pick != job.get("target"):
        job["target"] = pick
        job.pop("rows", None)
        job.pop("result", None)
    ui.route(pl.platform, pick)

    ready = False
    if pick == "spotify":
        ready = _connect_spotify()
    elif pick == "youtube":
        ready = _connect_youtube()
    else:
        ui.card("<h4 style='margin-top:0'>No login needed</h4><div class='pm-meta'>You'll get a link sheet: a page "
                "with one button per song for Apple Music, Spotify, YouTube Music, Deezer, Tidal, Amazon Music, "
                "SoundCloud and Audiomack. You'll also get a CSV that importers such as TuneMyMusic and Soundiiz "
                "accept.</div>")
        ready = True

    if ready and st.button("Next: match the songs →" if pick != "export" else "Next: get the files →",
                           type="primary"):
        go("transfer" if pick == "export" else "match")


def _connect_spotify() -> bool:
    if not SPOTIFY_READY:
        st.error("Spotify isn't set up on this site yet." + ("" if store.HOSTED else " Open ⚙ Setup in the menu."))
        return False
    sp = sp_client()
    me = sp_me(sp)
    if me:
        img = (me.get("images") or [{}])[0].get("url", "")
        avatar = f'<img src="{ui.e(img)}" style="width:44px;height:44px;border-radius:50%;object-fit:cover">' if img else ""
        ui.card(f'<div style="display:flex;gap:14px;align-items:center">{avatar}<div><b>Connected as '
                f'{ui.e(me.get("display_name") or me["id"])}</b><div class="pm-meta">The new playlist will be '
                f'created in this account.</div></div></div>')
        if st.button("Use a different Spotify account"):
            for k in ("spotify_token", "me"):
                job.pop(k, None)
            st.rerun()
        return True
    url = T.spotify_oauth(cfg, job).get_authorize_url(state=job["id"])
    st.markdown(
        f'<div class="pm-card"><h4 style="margin-top:0">Connect your Spotify</h4><div class="pm-meta" '
        f'style="margin-bottom:16px">You\'ll approve access on Spotify\'s own page, then come straight back here.</div>'
        f'<a href="{ui.e(url)}" target="_self" style="display:inline-block;padding:11px 22px;border-radius:999px;'
        f'background:#1ED760;color:#0b0b12;font-weight:700;text-decoration:none">Log in with Spotify</a></div>',
        unsafe_allow_html=True)
    st.caption("Spotify only lets accounts the site owner has added under User Management use this app "
               "(up to 5 people).")
    return False


def _connect_youtube() -> bool:
    if not GOOGLE_READY:
        ui.card("<h4 style='margin-top:0'>YouTube Music isn't switched on here yet</h4><div class='pm-meta'>"
                "The site owner needs to add a Google sign-in app: set GOOGLE_CLIENT_ID and "
                "GOOGLE_CLIENT_SECRET for an OAuth client of type <i>TVs and Limited Input devices</i>, "
                "with the YouTube Data API v3 turned on. Until then, use <b>Any other app</b>.</div>")
        return False
    if job.get("yt_token"):
        ui.card("<b>YouTube Music connected.</b><div class='pm-meta'>The playlist will be created in the Google "
                "account you approved.</div>")
        if st.button("Disconnect YouTube Music"):
            for k in ("yt_token", "yt_client", "yt_device"):
                job.pop(k, None)
            st.rerun()
        return True
    dev = job.get("yt_device")
    if not dev or time.time() > dev["_t"] + int(dev.get("expires_in", 1800)):
        st.markdown("YouTube Music uses Google's TV-style sign-in: you get a short code, enter it on Google's "
                    "page, and you're connected.")
        if st.button("Get my sign-in code", type="primary"):
            try:
                dev = T.yt_start_device_login(cfg)
                dev["_t"] = time.time()
                job["yt_device"] = dev
                st.rerun()
            except Exception as ex:  # noqa: BLE001
                st.error(f"Google didn't give a code: {ex}")
        return False
    st.markdown(f'<div class="pm-card"><div class="pm-meta">1. Open <b>{ui.e(dev["verification_url"])}</b>'
                f'&nbsp;&nbsp;2. Enter this code&nbsp;&nbsp;3. Allow access</div><div style="margin:16px 0">'
                f'<span class="pm-code">{ui.e(dev["user_code"])}</span></div></div>', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 3])
    c1.link_button("Open Google", dev["verification_url"])
    if c2.button("I've allowed it", type="primary"):
        tok, msg = T.yt_finish_device_login(cfg, dev["device_code"])
        if tok:
            job["yt_token"], job["yt_client"] = tok, None
            job.pop("yt_device", None)
            st.rerun()
        else:
            st.warning(msg)
    return False


# =====================================================================
# 3 · Match
# =====================================================================

def _client_for(target):
    if target == "spotify":
        return sp_client()
    if target == "youtube":
        return T.yt_client(cfg, job) if GOOGLE_READY else None
    return None


def _search(target, client, track, query=None):
    if target == "spotify":
        return T.spotify_search(client, track, query)
    return T.yt_search(client, track, query)


def page_match():
    ui.steps(3)
    pl, target = job.get("playlist"), job.get("target")
    if not pl or not target:
        st.info("Pick a playlist and a destination first.")
        if st.button("Back to the start", type="primary"):
            go("source" if not pl else "destination")
        return
    if target == "export":
        go("transfer")
    client = _client_for(target)
    if client is None:
        st.warning(f"Connect {label(target)} first.")
        if st.button("Go to Destination", type="primary"):
            go("destination")
        return

    st.markdown(f"## Finding your songs on {label(target)}")
    ui.route(pl.platform, target)
    left = paused_banner(target)

    rows = job.setdefault("rows", [])
    n, done = len(pl.tracks), len(rows)
    if done < n:
        msg = f"Find {n} songs on {label(target)}" if done == 0 else f"Continue ({done}/{n} done)"
        st.caption("Takes about a second for every 3 songs. You can leave this page open while it works.")
        if st.button(msg, type="primary", disabled=bool(left)):
            _run_search(pl, target, client)
            st.rerun()
    if not rows:
        return

    thr = st.number_input("Auto-tick matches scoring at least", min_value=0.0, max_value=1.0,
                          value=float(job.get("thr", 0.70)), step=0.05, format="%.2f")
    job["thr"] = thr
    for r in rows:
        if not r.get("touched"):
            r["add"] = bool(r["cand"]) and r["score"] >= thr
    matched = sum(1 for r in rows if r["cand"] and r["score"] >= thr)
    review = sum(1 for r in rows if r["cand"] and r["score"] < thr)
    missing = sum(1 for r in rows if not r["cand"])
    ui.rings(matched, review, missing)

    view = st.radio("Show", ["All", "Check these", "Not found", "Ticked"], horizontal=True)
    sel = [r for r in rows if view == "All"
           or (view == "Check these" and r["cand"] and r["score"] < thr)
           or (view == "Not found" and not r["cand"])
           or (view == "Ticked" and r["add"])]
    df = pd.DataFrame([{
        "Add": r["add"], "Art": (r["cand"].art if r["cand"] else "") or pl.tracks[r["i"]].art,
        "#": r["i"] + 1, "Song": pl.tracks[r["i"]].title, "Artist": pl.tracks[r["i"]].artist,
        f"On {label(target)}": (f'{r["cand"].title} — {", ".join(r["cand"].artists)}' if r["cand"] else "not found"),
        "Score": r["score"], "How": r["how"],
    } for r in sel])
    key = f"ed_{job.get('editor_v', 0)}"
    if not df.empty:
        st.data_editor(
            df, key=key, hide_index=True, width="stretch", height=460,
            disabled=[c for c in df.columns if c != "Add"],
            column_config={
                "Add": st.column_config.CheckboxColumn(width="small"),
                "Art": st.column_config.ImageColumn("", width="small"),
                "#": st.column_config.NumberColumn(width="small"),
                "Score": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="%.2f", width="small"),
            },
            on_change=_apply_edits, args=(key, [r["i"] for r in sel]),
        )
    else:
        st.caption("Nothing in this view.")

    with st.expander("🔎 Fix a song yourself"):
        _fixer(pl, target, client)

    ticked = sum(1 for r in rows if r["add"] and r["cand"])
    if len(rows) == n and st.button(f"Next: create the playlist with {ticked} songs →", type="primary",
                                    disabled=ticked == 0):
        go("transfer")


def _apply_edits(key, idx_map):
    edits = (st.session_state.get(key) or {}).get("edited_rows", {})
    rows = job.get("rows", [])
    for pos, change in edits.items():
        if "Add" in change and pos < len(idx_map):
            r = rows[idx_map[pos]]
            r["add"], r["touched"] = bool(change["Add"]) and r["cand"] is not None, True
    job["editor_v"] = job.get("editor_v", 0) + 1


def _run_search(pl, target, client):
    rows = job["rows"]
    bar = st.progress(len(rows) / len(pl.tracks), text="Starting…")
    errors = 0
    for i in range(len(rows), len(pl.tracks)):
        t = pl.tracks[i]
        own = t.ids.get(target)
        try:
            if own:  # same platform on both sides: copy the exact song
                cand = Candidate(id=own, title=t.title, artists=split_artists(t.artist), art=t.art)
                rows.append({"i": i, "cand": cand, "score": 1.0, "how": "exact", "add": True})
                continue
            cands, how = _search(target, client, t)
            cand, sc = best_of(t, cands)
            if how == "ISRC" and cand:
                sc = 1.0
            rows.append({"i": i, "cand": cand, "score": sc, "how": how if cand else "not found", "add": False})
            errors = 0
        except RateLimited as ex:
            store.pause(target, ex.wait_s)
            st.error(f"{label(target)} paused searches for about {ex.wait_s / 3600:.1f} h. "
                     f"{len(rows)} songs are done and kept. Come back and press Continue.")
            break
        except Exception as ex:  # noqa: BLE001
            errors += 1
            rows.append({"i": i, "cand": None, "score": 0.0, "how": f"error: {str(ex)[:60]}", "add": False})
            if errors >= 5:
                del rows[-5:]
                st.error(f"{label(target)} keeps refusing searches ({ex}). Reconnect on the Destination page, "
                         "then press Continue.")
                break
        bar.progress((i + 1) / len(pl.tracks), text=f"{i + 1}/{len(pl.tracks)} · {t.artist} — {t.title}")
        time.sleep(0.25 if target == "spotify" else 0.35)
    bar.empty()
    job["editor_v"] = job.get("editor_v", 0) + 1


def _fixer(pl, target, client):
    rows = job["rows"]
    c1, c2 = st.columns([1, 3])
    num = c1.number_input("Song #", min_value=1, max_value=len(rows), value=1, step=1)
    r = rows[int(num) - 1]
    t = pl.tracks[r["i"]]
    q = c2.text_input("Search for", value=f"{t.title} {t.artist}".strip(), key=f"fixq_{num}")
    st.caption(f"Now: **{t.title}** by {t.artist} → "
               f"{(r['cand'].title + ' — ' + ', '.join(r['cand'].artists)) if r['cand'] else 'not found'}")
    if st.button("Search"):
        try:
            cands, _ = _search(target, client, t, q)
            job["fix"] = {"row": int(num) - 1, "cands": cands}
        except RateLimited as ex:
            store.pause(target, ex.wait_s)
            st.error("Paused by the platform. Try later.")
        except Exception as ex:  # noqa: BLE001
            st.error(str(ex))
    fix = job.get("fix")
    if fix and fix["row"] == int(num) - 1:
        if not fix["cands"]:
            st.caption("No results. Try fewer words.")
            return
        labels = [f'{c.title} — {", ".join(c.artists)}' + (f" · {c.album}" if c.album else "") for c in fix["cands"]]
        k = st.selectbox("Pick the right one", range(len(labels)), format_func=lambda x: labels[x])
        if st.button("Use this song", type="primary"):
            chosen = fix["cands"][k]
            r.update(cand=chosen, score=max(best_of(t, [chosen])[1], 0.01), how="you picked", add=True, touched=True)
            job.pop("fix", None)
            job["editor_v"] = job.get("editor_v", 0) + 1
            st.rerun()


# =====================================================================
# 4 · Transfer
# =====================================================================

def page_transfer():
    ui.steps(4)
    pl, target = job.get("playlist"), job.get("target")
    if not pl or not target:
        st.info("Pick a playlist and a destination first.")
        return
    st.markdown("## Make it yours")
    ui.route(pl.platform, target)

    res = job.get("result")
    if target in ("spotify", "youtube"):
        rows = job.get("rows", [])
        chosen = [r for r in sorted(rows, key=lambda r: r["i"]) if r["add"] and r["cand"]]
        if not chosen:
            st.info("No songs are ticked yet.")
            if st.button("Go to Match", type="primary"):
                go("match")
        elif res:
            st.balloons() if not res.get("shown") else None
            res["shown"] = True
            ui.card(f'<div class="pm-eyebrow">Done</div><h2 class="pm-display" style="margin:.3rem 0">'
                    f'{ui.e(res["name"])}</h2><div class="pm-meta">{res["count"]} songs are now on '
                    f'{label(target)}. {ui.e(res.get("note", ""))}</div>')
            st.link_button(f"Open in {label(target)}", res["url"], type="primary")
        else:
            c1, c2 = st.columns([2, 1])
            name = c1.text_input("Playlist name", value=pl.name)
            public = c2.checkbox("Public playlist", value=False)
            desc = st.text_input("Description",
                                 value=f"Moved from {label(pl.platform)} with Playlist Mover · {len(chosen)} songs")
            copy_cover = False
            if target == "spotify" and pl.cover:
                copy_cover = st.checkbox("Copy the original cover art", value=True)
            if st.button(f"Create on {label(target)} ({len(chosen)} songs)", type="primary"):
                ids = list(dict.fromkeys(r["cand"].id for r in chosen))
                with st.spinner("Creating your playlist…"):
                    try:
                        client = _client_for(target)
                        if target == "spotify":
                            url, note = T.spotify_create(client, name, desc, public, ids,
                                                         pl.cover if copy_cover else "")
                        else:
                            url, note = T.yt_create(client, name, desc, public, ids)
                        job["result"] = {"url": url, "note": note, "count": len(ids), "name": name}
                        st.rerun()
                    except RateLimited as ex:
                        store.pause(target, ex.wait_s)
                        st.error(f"{label(target)} paused this app for about {ex.wait_s / 3600:.1f} h. Try again later.")
                    except Exception as ex:  # noqa: BLE001
                        st.error(f"{label(target)} refused: {ex}")

    st.markdown("#### Take it anywhere")
    left_out = []
    if target in ("spotify", "youtube") and job.get("rows"):
        left_out = [pl.tracks[r["i"]] for r in job["rows"] if not (r["add"] and r["cand"])]
    c1, c2, c3 = st.columns(3)
    safe = "".join(ch for ch in pl.name if ch.isalnum() or ch in " -_").strip() or "playlist"
    c1.download_button("Link sheet (every app)", T.link_sheet(pl.name, pl.tracks), file_name=f"{safe} - links.html",
                       mime="text/html", width="stretch", type="primary" if target == "export" else "secondary")
    c2.download_button("CSV of all songs", T.export_csv(pl.tracks), file_name=f"{safe}.csv", mime="text/csv",
                       width="stretch")
    c3.download_button(f"Songs not added ({len(left_out)})", T.export_csv(left_out), file_name=f"{safe} - not added.csv",
                       mime="text/csv", width="stretch", disabled=not left_out)
    st.caption("The link sheet opens in any browser: each song gets a button for Apple Music, Spotify, YouTube Music, "
               "Deezer, Tidal, Amazon Music, SoundCloud and Audiomack.")
    st.write("")
    if st.button("Move another playlist"):
        for k in ("playlist", "rows", "result", "fix"):
            job.pop(k, None)
        go("source")


# =====================================================================
# Setup (local only)
# =====================================================================

def page_setup():
    st.markdown("## ⚙ Setup")
    st.caption("Only shown when running on your own computer. On Render these come from environment variables.")
    with st.form("cfg"):
        st.markdown("**Spotify** · developer.spotify.com/dashboard → your app → Settings")
        a = st.text_input("Spotify Client ID", value=cfg["spotify_id"])
        b = st.text_input("Spotify Client Secret", value=cfg["spotify_secret"], type="password")
        c = st.text_input("Redirect URI (must match the Spotify app)", value=cfg["redirect_uri"])
        st.markdown("**YouTube Music (optional)** · Google Cloud → OAuth client, type *TVs and Limited Input devices*")
        d = st.text_input("Google Client ID", value=cfg["google_id"])
        f = st.text_input("Google Client Secret", value=cfg["google_secret"], type="password")
        if st.form_submit_button("Save", type="primary"):
            store.save_config({"spotify_id": a.strip(), "spotify_secret": b.strip(), "redirect_uri": c.strip(),
                               "google_id": d.strip(), "google_secret": f.strip()})
            st.success("Saved.")
            st.rerun()


# =====================================================================
# Navigation + sidebar
# =====================================================================

PAGES = {
    "home": st.Page(page_home, title="Home", icon=":material/home:", url_path="home", default=True),
    "source": st.Page(page_source, title="1 · Source", icon=":material/library_music:", url_path="source"),
    "destination": st.Page(page_destination, title="2 · Destination", icon=":material/output:", url_path="destination"),
    "match": st.Page(page_match, title="3 · Match", icon=":material/join_inner:", url_path="match"),
    "transfer": st.Page(page_transfer, title="4 · Transfer", icon=":material/rocket_launch:", url_path="transfer"),
}
nav = list(PAGES.values())
if not store.HOSTED:
    PAGES["setup"] = st.Page(page_setup, title="Setup", icon=":material/settings:", url_path="setup")
    nav.append(PAGES["setup"])

with st.sidebar:
    st.markdown('<div class="pm-display" style="font-size:1.35rem;font-weight:700;margin:4px 0 2px">'
                '<span class="pm-grad">Playlist Mover</span></div><div class="pm-side">Your music, wherever you '
                'listen.</div>', unsafe_allow_html=True)
    st.write("")

pg = st.navigation(nav)
pg.run()

# sidebar status is drawn after the page so it reflects what the page just did
with st.sidebar:
    st.divider()
    pl = job.get("playlist")
    if pl:
        thumb = f'<img src="{ui.e(pl.cover)}" style="width:42px;height:42px;border-radius:10px;object-fit:cover">' \
            if pl.cover else ""
        st.markdown(f'<div style="display:flex;gap:10px;align-items:center">{thumb}<div><b>{ui.e(pl.name)}</b>'
                    f'<div class="pm-side">{len(pl.tracks)} songs · {label(pl.platform)}</div></div></div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="pm-side">No playlist loaded yet.</div>', unsafe_allow_html=True)
    if job.get("target"):
        st.markdown(f'<div class="pm-side" style="margin-top:10px">Going to {ui.chip(job["target"])}</div>',
                    unsafe_allow_html=True)
    rows = job.get("rows") or []
    if rows and pl:
        st.progress(len(rows) / max(len(pl.tracks), 1), text=f"{len(rows)}/{len(pl.tracks)} searched")
