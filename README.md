## Mindsrot.app

Turn text + background footage into short vertical videos with TikTok-style TTS, captions/karaoke, and optional split-screen. This repo runs as a Flask web app (`web_app_multiuser.py`) with user accounts + per-user storage under `user_data/`.

## Features

- **Web UI**: register/login, upload background video(s), paste text or batch-upload CSV/TXT, generate, download
- **TTS**: TikTok (unofficial) voices via `app/tts/tiktok.py`
- **Captions**: timed caption spans + optional per-word karaoke timing (uses `faster-whisper` if installed)
- **Video**: auto-crops to 9:16, optional split-screen, optional background music mix
- **Storage cleanup**: uploaded source videos and generated outputs are deleted automatically to save disk

## Requirements

- **Python**: 3.10+
- **FFmpeg**: required by MoviePy (must be on your `PATH`)
- **Optional**: `faster-whisper` for better word-level timestamps (otherwise it falls back to heuristic timing)

## Install

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Optional: better karaoke timing

```powershell
pip install faster-whisper
```

## Run (local)

```powershell
python web_app_multiuser.py
```

Then open `http://localhost:5000`.

### First run

- **Database**: defaults to SQLite at `tts_saas.db` in the project directory.
- **Test account**: if there are no users yet, the app creates `test@example.com` with password `password`.

## Configuration (environment variables)

The app loads environment variables from a local `.env` (via `python-dotenv`) if present.

- **SECRET_KEY**: Flask secret key (default: `dev-secret-key-change-in-production`)
- **DATABASE_URL**: SQLAlchemy DB URL (default: `sqlite:///tts_saas.db`)
- **PORT**: server port (default: `5000`)
- **FLASK_ENV**: set to `production` to disable debug mode
- **ADMIN_EMAILS**: comma-separated list of emails that should be marked as admins
- **GAM_REWARDED_AD_UNIT_PATH**: (optional) Google Ad Manager rewarded ad unit path used by the UI
- **STRIPE_SECRET_KEY**: (optional) enable Stripe webhook handling
- **STRIPE_WEBHOOK_SECRET**: (optional) Stripe webhook signature secret

Example `.env`:

```env
SECRET_KEY=change-me
DATABASE_URL=sqlite:///tts_saas.db
FLASK_ENV=development
ADMIN_EMAILS=you@example.com
```

## Usage

- **Single**: paste text → upload a background video → generate → download from the queue
- **Batch**: upload a `.csv` or `.txt` (one item per line or first column) → upload video(s) → generate
- **Split screen**: enable split screen and upload **two** background videos

## Background music (optional)

To enable background music mixing, create `assets/background_music/` and drop in audio files (mp3/wav/m4a/aac/ogg/flac). If the folder doesn’t exist (or is empty), videos are generated with TTS audio only.

## Captions / karaoke timing

The app generates:

- **Caption spans**: chunked text with timings based on TTS duration
- **Karaoke word spans**:
  - **Preferred**: `faster-whisper` word timestamps (if installed)
  - **Fallback**: heuristic per-word timing based on TTS duration

## YouTube upload (standalone)

`app/youtube_uploader.py` implements a queued uploader with rate limiting (default: 10 uploads / 24h). It is not currently wired into the Flask UI routes in `web_app_multiuser.py`, but you can use the scripts to set up and test the uploader:

```powershell
python scripts/setup_youtube_credentials.py
python scripts/test_youtube_integration.py
python scripts/reset_youtube_integration.py
```

## Deployment

- **Procfile**: `gunicorn web_app_multiuser:app --bind 0.0.0.0:$PORT --workers 1 --timeout 300`
- **VPS guide**: see `VPS_DEPLOYMENT.md`

## Notes

- **TikTok TTS** uses unofficial endpoints and can break if upstream changes.
- **Uploaded background videos** are deleted after processing to avoid accumulating large files.
- **Downloads expire**: completed outputs are removed after download; job artifacts are periodically cleaned up.

## License

MIT (see `LICENSE`).
