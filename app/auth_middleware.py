import jwt
import os
import urllib.request
import json
from functools import wraps
from flask import request, g, jsonify

JWT_SECRET = (os.getenv("JWT_SECRET") or "").strip()
JWT_ALGORITHM = "HS256"
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")


def _verify_via_supabase_api(token: str):
    """Fallback: validate token by calling Supabase Auth (works with any signing key)."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": SUPABASE_ANON_KEY,
                "Content-Type": "application/json",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode())
            return data.get("id")
    except Exception:
        return None


def get_current_user_id():
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    if JWT_SECRET:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload.get("sub")
        except Exception:
            pass
    return _verify_via_supabase_api(token)

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        uid = get_current_user_id()
        if not uid:
            return jsonify({"error": "Unauthorized"}), 401
        g.user_id = uid
        return f(*args, **kwargs)
    return decorated

def require_role(role: str):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            uid = get_current_user_id()
            if not uid:
                return jsonify({"error": "Unauthorized"}), 401
            g.user_id = uid
            supabase = __import__("app.supabase_client", fromlist=["get_supabase"]).get_supabase(service_role=True)
            r = supabase.table("profiles").select("role").eq("id", uid).maybe_single().execute()
            if not r.data or r.data.get("role") != role:
                return jsonify({"error": "Forbidden"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
