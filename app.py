"""Playlist Mover: Apple Music link -> Spotify playlist.

Run:  streamlit run app.py --server.address 127.0.0.1 --server.port 8501
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import spotipy
import streamlit as st

from apple_music import AppleMusicError, get_playlist, parse_pasted
from spotify_tools import TOKEN_FILE, create_playlist, make_oauth, match_track

st.set_page_config(page_title="Playlist Mover", page_icon="🎧", layout="wide")

CONFIG = Path("spotify_config.json")
# On a server (Render sets RENDER), credentials come only from env vars and each visitor
# keeps their own Spotify login in their session instead of a shared token file.
HOSTED = bool(os.getenv("RENDER") or os.getenv("HOSTED"))
DEFAULT_REDIRECT = "http://127.0.0.1:8501/"


# ---------- config & login ----------

def load_config() -> dict:
    cfg = {"client_id": os.getenv("SPOTIFY_CLIENT_ID", ""),
           "client_secret": os.getenv("SPOTIFY_CLIENT_SECRET", ""),
           "redirect_uri": os.getenv("SPOTIFY_REDIRECT_URI", DEFAULT_REDIRECT)}
    if CONFIG.exists() and not HOSTED:
        try:
            cfg.update({k: v for k, v in json.loads(CONFIG.read_text()).items() if v})
        except json.JSONDecodeError:
            pass
    return cfg


cfg = load_config()
have_creds = bool(cfg["client_id"] and cfg["client_secret"])
oauth = (make_oauth(cfg["client_id"], cfg["client_secret"], cfg["redirect_uri"],
                    store=st.session_state if HOSTED else None) if have_creds else None)

# Spotify sends the user back here with ?code=...
if oauth and "code" in st.query_params:
    try:
        oauth.get_access_token(st.query_params["code"], as_dict=False, check_cache=False)
        st.query_params.clear()
        st.toast("Spotify connected ✅")
    except Exception as e:  # noqa: BLE001
        st.error(f"Spotify login failed: {e}")


def spotify_client() -> spotipy.Spotify | None:
    if not oauth:
        return None
    tok = oauth.validate_token(oauth.cache_handler.get_cached_token())
    return spotipy.Spotify(auth_manager=oauth) if tok else None


sp = spotify_client()
me = None
if sp:
    try:
        me = sp.current_user()
    except spotipy.SpotifyException:
        sp = None

ss = st.session_state
ss.setdefault("tracks", [])
ss.setdefault("source_name", "")
ss.setdefault("results", None)

# ---------- navigation ----------

st.sidebar.title("🎧 Playlist Mover")
page = st.sidebar.radio("Steps", ["1 · Connect Spotify", "2 · Load playlist", "3 · Match & build"],
                        label_visibility="collapsed")
st.sidebar.divider()
st.sidebar.write("Spotify:", f"✅ {me['display_name'] or me['id']}" if me else "❌ not connected")
st.sidebar.write("Songs loaded:", len(ss.tracks))


# ---------- page 1 ----------

if page.startswith("1"):
    st.header("Connect Spotify")

    if HOSTED:
        if not have_creds:
            st.error("Server is missing SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET / SPOTIFY_REDIRECT_URI.")
    else:
        with st.expander("Spotify app credentials", expanded=not have_creds):
            st.markdown(
                "Make a free app at **developer.spotify.com/dashboard** → *Create app*. "
                f"Set the Redirect URI to exactly `{cfg['redirect_uri']}` and tick *Web API*. "
                "Then copy the Client ID and Client Secret here."
            )
            cid = st.text_input("Client ID", value=cfg["client_id"])
            sec = st.text_input("Client Secret", value=cfg["client_secret"], type="password")
            red = st.text_input("Redirect URI", value=cfg["redirect_uri"])
            if st.button("Save credentials"):
                CONFIG.write_text(json.dumps({"client_id": cid.strip(), "client_secret": sec.strip(),
                                              "redirect_uri": red.strip()}, indent=2))
                st.success("Saved. Reloading…")
                st.rerun()

    if not have_creds:
        st.info("Spotify isn't set up yet." if HOSTED else "Add your Spotify app credentials above first.")
    elif me:
        st.success(f"Connected as **{me['display_name'] or me['id']}**.")
        if st.button("Log out"):
            if HOSTED:
                ss.pop("spotify_token", None)
            else:
                Path(TOKEN_FILE).unlink(missing_ok=True)
            st.rerun()
    else:
        st.link_button("Log in with Spotify", oauth.get_authorize_url(), type="primary")
        if HOSTED:
            st.caption("Only Spotify accounts added under *User Management* in the Spotify app can log in.")
        st.caption("After you approve, Spotify brings you back to this app, already logged in.")


# ---------- page 2 ----------

elif page.startswith("2"):
    st.header("Load the playlist you want to move")
    source = st.radio("Source", ["Apple Music link", "Paste a song list"], horizontal=True)

    if source == "Apple Music link":
        url = st.text_input("Apple Music playlist link",
                            placeholder="https://music.apple.com/gh/playlist/…/pl.u-…")
        if st.button("Read playlist", type="primary", disabled=not url):
            with st.spinner("Reading the playlist…"):
                try:
                    name, tracks, how = get_playlist(url)
                    ss.tracks, ss.source_name, ss.results = tracks, name, None
                    st.success(f"**{name}**: {len(tracks)} songs, read from the {how}.")
                    st.caption("If that's fewer than the playlist has, Apple only showed part of it "
                               "on the page. Use *Paste a song list* to add the rest.")
                except AppleMusicError as e:
                    st.error(str(e))
                except Exception as e:  # noqa: BLE001
                    st.error(f"Something went wrong reading that link: {e}")
    else:
        name = st.text_input("Playlist name", value=ss.source_name or "Imported playlist")
        up = st.file_uploader("…or upload a .txt list (e.g. just_vibes_tracks.txt)", type=["txt", "csv"])
        text = st.text_area("One song per line: Title - Artist", height=260,
                            value=up.getvalue().decode("utf-8-sig") if up else "",
                            placeholder="Blinding Lights - The Weeknd\nEssence - Wizkid")
        append = st.checkbox("Add to the songs already loaded (e.g. the rest of a long playlist)",
                             value=bool(ss.tracks))
        if st.button("Load list", type="primary", disabled=not text.strip()):
            new = parse_pasted(text)
            ss.tracks = (ss.tracks + new) if append else new
            ss.source_name, ss.results = name, None
            st.success(f"{len(new)} songs added — {len(ss.tracks)} in total.")

    if ss.tracks:
        st.dataframe(pd.DataFrame([{"#": i + 1, "Title": t.title, "Artist": t.artist, "Album": t.album}
                                   for i, t in enumerate(ss.tracks)]),
                     hide_index=True, width="stretch", height=380)
        st.caption("Next: open **3 · Match & build** in the sidebar.")


# ---------- page 3 ----------

else:
    st.header("Match songs on Spotify and build the playlist")
    if not sp:
        st.warning("Connect Spotify first (step 1).")
        st.stop()
    if not ss.tracks:
        st.warning("Load a playlist first (step 2).")
        st.stop()

    c1, c2 = st.columns([3, 1])
    pl_name = c1.text_input("New Spotify playlist name", value=ss.source_name or "Imported playlist")
    min_score = c2.number_input("Minimum match score (0–1)", min_value=0.0, max_value=1.0,
                                value=0.60, step=0.05, format="%.2f")
    public = st.checkbox("Make the playlist public", value=False)

    if st.button(f"Find {len(ss.tracks)} songs on Spotify", type="primary"):
        bar = st.progress(0.0, text="Searching…")
        rows = []
        for i, t in enumerate(ss.tracks):
            try:
                hit, s, how = match_track(sp, t)
            except spotipy.SpotifyException as e:
                hit, s, how = None, 0.0, f"error {e.http_status}: {e.msg}"
                if i < 5 and all(r["How"].startswith("error") for r in rows) :
                    bar.empty()
                    st.error(f"Spotify is refusing searches ({e.http_status}: {e.msg}). "
                             "Log out on page 1 and log in again, then retry.")
                    st.stop()
            rows.append({
                "#": i + 1, "Title": t.title, "Artist": t.artist,
                "Spotify match": f"{hit['name']} — {', '.join(a['name'] for a in hit['artists'])}" if hit else "",
                "Score": s, "How": how, "uri": hit["uri"] if hit else "",
            })
            bar.progress((i + 1) / len(ss.tracks), text=f"Searching… {i + 1}/{len(ss.tracks)}")
        bar.empty()
        ss.results = pd.DataFrame(rows)

    if ss.results is not None:
        df = ss.results.copy()
        df["Add?"] = (df["Score"] >= min_score) & (df["uri"] != "")
        df = st.data_editor(
            df, hide_index=True, width="stretch", height=420,
            column_order=["Add?", "#", "Title", "Artist", "Spotify match", "Score", "How"],
            disabled=["#", "Title", "Artist", "Spotify match", "Score", "How"],
        )
        chosen = df[df["Add?"] & (df["uri"] != "")]
        missing = df[~df["Add?"]]

        m1, m2, m3 = st.columns(3)
        m1.metric("Will be added", len(chosen))
        m2.metric("Left out", len(missing))
        m3.metric("Match rate", f"{len(chosen) / len(df):.0%}")
        st.caption("Untick a row to drop a wrong match. Low scores are worth a quick look.")

        b1, b2 = st.columns(2)
        if b1.button("Create playlist on Spotify", type="primary", disabled=chosen.empty):
            # keep original order, drop exact duplicate URIs
            uris = list(dict.fromkeys(chosen.sort_values("#")["uri"]))
            with st.spinner("Creating playlist…"):
                try:
                    pl = create_playlist(sp, pl_name, f"Moved from Apple Music · {len(uris)} songs",
                                         public, uris)
                    st.success(f"Done: **{pl_name}** with {len(uris)} songs.")
                    st.link_button("Open in Spotify", pl["external_urls"]["spotify"])
                except spotipy.SpotifyException as e:
                    st.error(f"Spotify refused: {e.msg}")
        b2.download_button("Download left-out songs (CSV)",
                           missing[["#", "Title", "Artist"]].to_csv(index=False),
                           file_name="not_added.csv", disabled=missing.empty)
