# Playlist Mover

Copy playlists between music apps: paste a link, check the matches, and send it.

| Platform | Copy from | Create playlist in |
|---|---|---|
| Apple Music | ✓ public playlist links | ✓ via TuneMyMusic hand-off |
| Spotify | ✓ public links; full list when logged in | ✓ |
| YouTube / YouTube Music | ✓ public or unlisted playlists | ✓ beta |
| Deezer | ✓ public playlists (with ISRC codes) | ✓ via TuneMyMusic hand-off |
| Boomplay, Audiomack, TIDAL, Amazon Music, SoundCloud | — | ✓ via TuneMyMusic hand-off |
| Text / CSV list | ✓ | — |
| Any other app | — | Link sheet (one button per song for 8 services) + CSV |

Apple Music, Deezer and the others only let large, approved apps create playlists. For those, Playlist Mover
prepares a CSV and opens TuneMyMusic's matching "CSV to <app>" page. You upload the file and sign in to the
destination app there. TuneMyMusic can't be embedded, because its site forbids framing.

## How it works
1. **Source**: paste a link or upload a list. You get a playlist card, its "DNA" (top artists, running time) and a cover wall.
2. **Destination**: Spotify, YouTube Music or Any other app. Connect your account.
3. **Match**: every song is searched. ISRC codes or same-app IDs give exact matches; otherwise title and artist are scored.
   Untick wrong ones, or use **Fix a song yourself** to pick the right version.
4. **Transfer**: create the playlist (Spotify can also copy the original cover), or download the link sheet and CSV.

## Deploy on Render
`render.yaml` sets up a free Python web service. Environment variables:
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI` (`https://<service>.onrender.com/`)
- Optional, for YouTube Music: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`. In Google Cloud, create a project,
  enable **YouTube Data API v3**, and make an OAuth client of type **TVs and Limited Input devices**. While the
  consent screen is in Testing, add each Google account under Test users.

Spotify development-mode apps allow up to 5 users, added under *User Management*, and the app owner needs
Premium. The request quota is shared by everyone using the app, so the app slows its searches down and pauses
cleanly if Spotify asks it to.

## Run locally
Double-click `run_app.bat`, or run `streamlit run app.py --server.address 127.0.0.1 --server.port 8501`.
Then open **Setup** in the menu to enter your keys (redirect URI `http://127.0.0.1:8501/`).

## Files
`app.py` pages and flow · `sources.py` readers · `targets.py` Spotify, YouTube Music and exports ·
`core.py` matching · `ui.py` design · `store.py` per-visitor state
