"""Look and feel: global styles and small HTML components."""
from __future__ import annotations

import html

import streamlit as st

from core import PLATFORMS, colour, dna, fmt_ms, label

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&display=swap');
:root{--violet:#7C5CFF;--pink:#FF4D8D;--cyan:#22D3EE;--card:rgba(255,255,255,.035);--line:rgba(255,255,255,.08);--muted:#9a9ab0}
.stApp,.stApp p,.stApp li,.stApp label,.stApp input,.stApp textarea,.stApp button,.stApp td,.stApp th,
.stMarkdown,.stMarkdown div{font-family:'Inter',system-ui,sans-serif}
h1,h2,h3,h4,.pm-display{font-family:'Space Grotesk',system-ui,sans-serif!important;letter-spacing:-.02em}
[data-testid="stAppViewContainer"]{background:
  radial-gradient(1100px 560px at 8% -12%,rgba(124,92,255,.20),transparent 60%),
  radial-gradient(900px 520px at 105% 0%,rgba(255,77,141,.13),transparent 60%),
  radial-gradient(900px 700px at 50% 125%,rgba(34,211,238,.10),transparent 60%),#0B0B12}
[data-testid="stHeader"]{background:transparent}
[data-testid="stSidebar"]{background:rgba(13,13,22,.88);border-right:1px solid var(--line);backdrop-filter:blur(14px)}
.block-container{padding-top:2rem;max-width:1160px}
.stButton>button,.stDownloadButton>button,[data-testid="stLinkButton"] a{border-radius:999px!important;font-weight:600;
  border:1px solid var(--line)!important;transition:transform .15s ease,box-shadow .2s ease}
.stButton>button:hover,.stDownloadButton>button:hover,[data-testid="stLinkButton"] a:hover{transform:translateY(-1px)}
.stButton>button[kind="primary"],[data-testid="stLinkButton"] a[kind="primary"],.stDownloadButton>button[kind="primary"]{
  background:linear-gradient(135deg,var(--violet),var(--pink))!important;border:0!important;color:#fff!important;
  box-shadow:0 10px 28px -10px rgba(124,92,255,.75)}
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,textarea{border-radius:14px!important}
[data-testid="stExpander"]{border:1px solid var(--line);border-radius:16px;background:var(--card)}
.pm-card{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:22px 24px;margin:6px 0 14px;
  backdrop-filter:blur(10px)}
.pm-eyebrow{text-transform:uppercase;letter-spacing:.18em;font-size:.72rem;color:#b9a9ff;font-weight:600}
.pm-hero h1{font-size:clamp(2.4rem,5.5vw,4.1rem);line-height:1.02;margin:.35rem 0 .6rem}
.pm-grad{background:linear-gradient(92deg,#fff 0%,#d6caff 35%,#ff9cc2 65%,#86ecff 100%);-webkit-background-clip:text;
  background-clip:text;color:transparent}
.pm-sub{color:var(--muted);font-size:1.08rem;max-width:620px}
.pm-route{display:flex;align-items:center;gap:12px;margin:22px 0 8px}
.pm-hero .pm-route{display:grid;grid-template-columns:auto minmax(18px,1fr) auto minmax(18px,1fr) auto;gap:10px}
@media (max-width:640px){.pm-hero .pm-route{grid-template-columns:1fr}.pm-hero .pm-route .pm-line{display:none}}
.pm-stack{display:flex;flex-direction:column;gap:8px}
.pm-chip{display:inline-flex;align-items:center;gap:8px;padding:7px 14px;border-radius:999px;background:rgba(255,255,255,.05);
  border:1px solid var(--line);font-weight:600;font-size:.9rem;white-space:nowrap}
.pm-dot{width:9px;height:9px;border-radius:50%;background:var(--c);box-shadow:0 0 12px var(--c)}
.pm-line{flex:1;min-width:18px;height:2px;border-radius:2px;position:relative;overflow:hidden;
  background:linear-gradient(90deg,var(--a),var(--b))}
.pm-line::after{content:"";position:absolute;top:-3px;left:-10%;width:8px;height:8px;border-radius:50%;background:#fff;
  box-shadow:0 0 14px #fff;animation:pm-travel 2.4s linear infinite}
@keyframes pm-travel{to{left:110%}}
.pm-steps{display:flex;gap:8px;margin:0 0 20px;flex-wrap:wrap}
.pm-step{padding:6px 13px;border-radius:999px;font-size:.8rem;border:1px solid var(--line);color:#8d8da5}
.pm-step.done{color:#d2c8ff;border-color:rgba(124,92,255,.45)}
.pm-step.now{background:linear-gradient(135deg,var(--violet),var(--pink));color:#fff;border-color:transparent}
.pm-pl{display:flex;gap:22px;align-items:center}
.pm-pl img,.pm-pl .pm-noart{width:140px;height:140px;border-radius:18px;object-fit:cover;flex:none;
  box-shadow:0 24px 44px -16px rgba(0,0,0,.7)}
.pm-noart{background:linear-gradient(135deg,var(--violet),var(--pink));display:grid;place-items:center;font-size:3rem}
.pm-pl h2{margin:.25rem 0 .35rem;font-size:1.9rem}
.pm-meta{color:var(--muted);font-size:.93rem}
.pm-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-top:6px}
.pm-stat{background:rgba(255,255,255,.03);border:1px solid var(--line);border-radius:16px;padding:12px 14px}
.pm-stat b{display:block;font-family:'Space Grotesk';font-size:1.45rem}
.pm-stat span{color:var(--muted);font-size:.8rem}
.pm-bar-row{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(60px,1fr) 22px;gap:10px;align-items:center;margin:7px 0;font-size:.88rem}
.pm-bar{height:8px;border-radius:8px;background:rgba(255,255,255,.06);overflow:hidden}
.pm-bar>span{display:block;height:100%;border-radius:8px;background:linear-gradient(90deg,var(--violet),var(--pink))}
.pm-mosaic{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.pm-mosaic img{width:100%;aspect-ratio:1;border-radius:9px;object-fit:cover;opacity:.92}
.pm-rings{display:flex;gap:26px;flex-wrap:wrap;align-items:center}
.pm-ring{width:112px;height:112px;border-radius:50%;display:grid;place-items:center;
  background:conic-gradient(var(--c) calc(var(--p)*1%),rgba(255,255,255,.07) 0)}
.pm-ring>div{width:88px;height:88px;border-radius:50%;background:#10101a;display:grid;place-items:center;text-align:center}
.pm-ring b{font-family:'Space Grotesk';font-size:1.4rem;line-height:1}
.pm-ring span{font-size:.72rem;color:var(--muted)}
.pm-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.pm-feature h4{margin:.2rem 0 .3rem}.pm-feature p{color:var(--muted);margin:0;font-size:.92rem}
.pm-num{font-family:'Space Grotesk';font-size:.8rem;color:#b9a9ff}
.pm-matrix{width:100%;border-collapse:collapse;font-size:.9rem}
.pm-matrix td,.pm-matrix th{padding:9px 6px;border-bottom:1px solid var(--line);text-align:left}
.pm-matrix th{color:var(--muted);font-weight:500}
.pm-yes{color:#4ade80;font-weight:700}.pm-no{color:#5b5b70}.pm-beta{color:#fbbf24;font-weight:700}
.pm-code{font-family:'Space Grotesk';font-size:2.2rem;letter-spacing:.18em;padding:10px 18px;border-radius:14px;
  background:rgba(124,92,255,.15);border:1px dashed rgba(124,92,255,.6);display:inline-block}
.pm-side{font-size:.85rem;color:var(--muted)}
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)


def e(s) -> str:
    return html.escape(str(s or ""))


def chip(key: str, text: str | None = None) -> str:
    return f'<span class="pm-chip"><span class="pm-dot" style="--c:{colour(key)}"></span>{e(text or label(key))}</span>'


def steps(now: int):
    names = ["Source", "Destination", "Match", "Transfer"]
    out = []
    for i, n in enumerate(names, 1):
        cls = "now" if i == now else ("done" if i < now else "")
        out.append(f'<span class="pm-step {cls}">{i} · {n}</span>')
    st.markdown(f'<div class="pm-steps">{"".join(out)}</div>', unsafe_allow_html=True)


def route(src: str, dst: str):
    st.markdown(
        f'<div class="pm-route">{chip(src)}<div class="pm-line" style="--a:{colour(src)};--b:{colour(dst)}"></div>'
        f'{chip(dst)}</div>', unsafe_allow_html=True)


def hero():
    sources = "".join(chip(k) for k in ("apple", "spotify", "youtube", "deezer"))
    dests = "".join(chip(k) for k in ("spotify", "youtube", "export"))
    st.markdown(f"""
<div class="pm-hero">
  <div class="pm-eyebrow">Playlist Mover</div>
  <h1 class="pm-display"><span class="pm-grad">Your music,<br>wherever you listen.</span></h1>
  <div class="pm-sub">Paste a playlist link from one app and rebuild it in another. Every song is matched,
  scored and shown to you before anything is created.</div>
  <div class="pm-route"><div class="pm-stack">{sources}</div>
    <div class="pm-line" style="--a:#FA2D48;--b:#7C5CFF"></div>
    <span class="pm-chip" style="padding:12px 18px">✦ match &amp; review</span>
    <div class="pm-line" style="--a:#7C5CFF;--b:#1ED760"></div>
    <div class="pm-stack">{dests}</div></div>
</div>""", unsafe_allow_html=True)


def features():
    items = [
        ("01", "Paste a link", "Apple Music, Spotify, Deezer or YouTube. Or drop in a song list or CSV."),
        ("02", "Every song, matched", "Exact ISRC codes when the source has them, smart title and artist matching when not."),
        ("03", "You stay in control", "Untick a wrong match, or search a song yourself, before the playlist is made."),
    ]
    cards = "".join(f'<div class="pm-card pm-feature"><span class="pm-num">{n}</span><h4>{e(t)}</h4><p>{e(d)}</p></div>'
                    for n, t, d in items)
    st.markdown(f'<div class="pm-grid">{cards}</div>', unsafe_allow_html=True)


def matrix():
    rows = []
    for k, (name, c, can_read, can_write) in PLATFORMS.items():
        if k in ("text",):
            continue
        r = '<span class="pm-yes">✓</span>' if can_read else '<span class="pm-no">—</span>'
        if k == "youtube":
            w = '<span class="pm-beta">beta</span>'
        elif k == "export":
            w = '<span class="pm-yes">✓</span> link sheet + CSV'
        else:
            w = '<span class="pm-yes">✓</span>' if can_write else '<span class="pm-no">— use the link sheet</span>'
        rows.append(f"<tr><td>{chip(k)}</td><td>{r}</td><td>{w}</td></tr>")
    st.markdown(f'<div class="pm-card"><table class="pm-matrix"><tr><th>Platform</th><th>Copy from</th>'
                f'<th>Create playlist in</th></tr>{"".join(rows)}</table></div>', unsafe_allow_html=True)


def playlist_card(pl):
    d = dna(pl.tracks)
    art = f'<img src="{e(pl.cover)}" alt="">' if pl.cover else '<div class="pm-noart">♫</div>'
    owner = f" · by {e(pl.owner)}" if pl.owner else ""
    stats = [
        (d["count"], "songs"),
        (d["unique_artists"], "artists"),
        (fmt_ms(d["total_ms"]) if d["total_ms"] else "—", "running time"),
        (fmt_ms(d["avg_ms"]) if d["avg_ms"] else "—", "average song"),
    ]
    stat_html = "".join(f'<div class="pm-stat"><b>{e(v)}</b><span>{e(k)}</span></div>' for v, k in stats)
    st.markdown(f"""
<div class="pm-card"><div class="pm-pl">{art}<div style="flex:1">
  {chip(pl.platform)}<h2 class="pm-display">{e(pl.name)}</h2>
  <div class="pm-meta">{d['count']} songs{owner}</div>
  <div class="pm-stats" style="margin-top:14px">{stat_html}</div></div></div></div>""", unsafe_allow_html=True)


def dna_card(pl):
    d = dna(pl.tracks)
    if not d["top"]:
        return
    mx = d["top"][0][1]
    bars = "".join(
        f'<div class="pm-bar-row"><span>{e(a)}</span><div class="pm-bar"><span style="width:{n / mx * 100:.0f}%">&#8203;</span>'
        f'</div><span class="pm-meta">{n}</span></div>' for a, n in d["top"])
    longest = ""
    if d["longest"] is not None and d["longest"].duration_ms:
        t = d["longest"]
        longest = f'<div class="pm-meta" style="margin-top:10px">Longest song: <b>{e(t.title)}</b> by {e(t.artist)} ({fmt_ms(t.duration_ms)})</div>'
    arts = list(dict.fromkeys(t.art for t in pl.tracks if t.art))[:12]
    mosaic = ('<div class="pm-mosaic" style="margin-top:4px">' + "".join(f'<img src="{e(a)}" alt="">' for a in arts)
              + "</div>") if len(arts) >= 4 else ""
    c1, c2 = st.columns([1.15, 1]) if mosaic else (st.container(), None)
    with c1:
        st.markdown(f'<div class="pm-card"><div class="pm-eyebrow">Playlist DNA · most played artists</div>'
                    f'<div style="margin-top:10px">{bars}</div>{longest}</div>', unsafe_allow_html=True)
    if c2 is not None:
        with c2:
            st.markdown(f'<div class="pm-card"><div class="pm-eyebrow">Cover wall</div>'
                        f'<div style="margin-top:12px">{mosaic}</div></div>', unsafe_allow_html=True)


def rings(matched: int, review: int, missing: int):
    total = max(matched + review + missing, 1)

    def ring(n, word, c):
        return (f'<div class="pm-ring" style="--c:{c};--p:{n / total * 100:.1f}"><div><div><b>{n}</b><br>'
                f'<span>{word}</span></div></div></div>')

    st.markdown(f'<div class="pm-card"><div class="pm-rings">{ring(matched, "matched", "#4ade80")}'
                f'{ring(review, "check these", "#fbbf24")}{ring(missing, "not found", "#f87171")}'
                f'<div class="pm-meta" style="max-width:340px">Matched songs are ticked for you. '
                f'"Check these" means a song was found but the title or artist differs a bit: '
                f'have a quick look before you transfer.</div></div></div>', unsafe_allow_html=True)


def card(body_html: str):
    st.markdown(f'<div class="pm-card">{body_html}</div>', unsafe_allow_html=True)
