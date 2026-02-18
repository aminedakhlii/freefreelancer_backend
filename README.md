# Backend

Flask API for USFreelancer (auth, profiles, projects, proposals, interviews, messages).

## Environment setup

`.env` is not committed. After cloning, create it from the example:

```bash
cp .env.example .env
```

Then edit `.env` and set Supabase (DB), OpenAI, and **Firebase** (auth): `GOOGLE_APPLICATION_CREDENTIALS` or `FIREBASE_SERVICE_ACCOUNT_JSON` for token verification. See `docs/FIREBASE_AUTH.md`.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python run.py
```

API runs at `http://localhost:5001` (or the port in `run.py`).
