import os
import json
from functools import wraps
from flask import request, g, jsonify

_firebase_app = None


def _get_firebase_app():
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app
    import firebase_admin
    from firebase_admin import credentials
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and os.path.isfile(cred_path):
        cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        return _firebase_app
    sa_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        try:
            cred_dict = json.loads(sa_json)
            cred = credentials.Certificate(cred_dict)
            _firebase_app = firebase_admin.initialize_app(cred)
            return _firebase_app
        except (json.JSONDecodeError, ValueError):
            pass
    try:
        _firebase_app = firebase_admin.initialize_app()
    except Exception:
        _firebase_app = None
    return _firebase_app


def _verify_firebase_token(token: str):
    """Verify Firebase ID token and return uid, or None."""
    try:
        from firebase_admin import auth as firebase_auth
        _get_firebase_app()
        decoded = firebase_auth.verify_id_token(token)
        return decoded.get("uid")
    except Exception:
        return None


def get_current_user_id():
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return None
    token = auth[7:].strip()
    if not token:
        return None
    return _verify_firebase_token(token)


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
