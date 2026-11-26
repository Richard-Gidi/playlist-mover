"""Per-visitor job state that survives the Spotify login round trip, plus app-wide flags."""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import streamlit as st

JOB_TTL = 12 * 3600
CONFIG = Path("spotify_config.json")
HOSTED = bool(os.getenv("RENDER") or os.getenv("HOSTED"))


@st.cache_resource
def _jobs() -> dict:
    return {}


@st.cache_resource
def _flags() -> dict:
    return {}


def job() -> dict:
    jobs, ss = _jobs(), st.session_state
    now = time.time()
    for k in [k for k, v in jobs.items() if now - v.get("touched", 0) > JOB_TTL]:
        jobs.pop(k, None)
    jid = ss.get("job_id")
    if not jid or jid not in jobs:
        jid = uuid.uuid4().hex
        jobs[jid] = {"id": jid, "created": now}
        ss.job_id = jid
    jobs[jid]["touched"] = now
    return jobs[jid]


def adopt(jid: str) -> bool:
    """After an OAuth redirect (a fresh browser session), pick the visitor's job back up."""
    if jid in _jobs():
        st.session_state.job_id = jid
        return True
    return False


def pause(platform: str, seconds: int):
    _flags()[f"{platform}_paused_until"] = time.time() + seconds


def paused_for(platform: str) -> int:
    return max(0, int(_flags().get(f"{platform}_paused_until", 0) - time.time()))


def config() -> dict:
    cfg = {
        "spotify_id": os.getenv("SPOTIFY_CLIENT_ID", ""),
        "spotify_secret": os.getenv("SPOTIFY_CLIENT_SECRET", ""),
        "redirect_uri": os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8501/"),
        "google_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "google_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
    }
    if not HOSTED and CONFIG.exists():
        try:
            saved = json.loads(CONFIG.read_text())
            # older config files used client_id / client_secret
            saved.setdefault("spotify_id", saved.pop("client_id", ""))
            saved.setdefault("spotify_secret", saved.pop("client_secret", ""))
            cfg.update({k: v for k, v in saved.items() if v})
        except json.JSONDecodeError:
            pass
    return cfg


def save_config(values: dict):
    CONFIG.write_text(json.dumps(values, indent=2))
