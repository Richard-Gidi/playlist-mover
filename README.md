# Playlist Mover

Moves an Apple Music playlist into Spotify. You log in to Spotify only; no Apple account is needed.

## Use
1. **Connect Spotify**: log in.
2. **Load playlist**: paste a public Apple Music link, or upload or paste a song list (`Title - Artist` or `Title<TAB>Artist`, one per line).
3. **Match & build**: find the songs on Spotify, untick any wrong matches, then create the playlist.

## Deploy on Render
`render.yaml` sets up a free Python web service. Set these environment variables:
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`: from your app at developer.spotify.com/dashboard
- `SPOTIFY_REDIRECT_URI`: `https://<your-service>.onrender.com/` (add the same value to the Spotify app's Redirect URIs)

Spotify apps in development mode only allow accounts listed under *User Management*.

## Run locally
Double-click `run_app.bat`, or run `streamlit run app.py --server.address 127.0.0.1 --server.port 8501`,
then paste your Spotify credentials on page 1 (redirect URI `http://127.0.0.1:8501/`).
