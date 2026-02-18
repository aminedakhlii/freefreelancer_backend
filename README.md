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

## Deploy backend to Vercel (service account)

`service-account.json` is gitignored. On Vercel you provide Firebase credentials via an **environment variable** instead of a file.

1. **Create a single-line JSON value**  
   Use the contents of `service-account.json` as **one line** (no real newlines), so it’s safe to paste into Vercel:
   ```bash
   cat service-account.json | jq -c .
   ```
   (Or minify the JSON in an editor and copy the result.)

2. **In Vercel → Project → Settings → Environment Variables** add:
   - **Name:** `FIREBASE_SERVICE_ACCOUNT_JSON`
   - **Value:** the minified JSON string (entire object: `{"type":"service_account","project_id":"...", ...}`)
   - **Environment:** Production (and Preview if you use it)

3. **Other backend env vars**  
   Set the same ones you use locally: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`, `OPENAI_API_KEY` (if used), `CORS_ORIGINS` (e.g. `https://your-frontend.vercel.app,https://freefreelancer.com`).

The app already reads `FIREBASE_SERVICE_ACCOUNT_JSON` and uses it with `credentials.Certificate(cred_dict)`; no file is written on the server.
