from flask import Blueprint, request, jsonify, g
from .auth_middleware import require_auth, get_current_user_id
from .supabase_client import get_supabase

bp = Blueprint("auth", __name__)


def _get_profile(supabase, user_id):
    """Fetch profile by id. Returns profile dict or None. Uses limit(1) to avoid 204 from maybe_single()."""
    r = supabase.table("profiles").select("*").eq("id", user_id).limit(1).execute()
    data = getattr(r, "data", None) if r else None
    if not data or not isinstance(data, list) or len(data) == 0:
        return None
    return data[0]


@bp.route("/me", methods=["GET"])
@require_auth
def me():
    supabase = get_supabase(service_role=True)
    data = _get_profile(supabase, g.user_id)
    if not data:
        return jsonify({"error": "Profile not found"}), 404
    return jsonify(data)

@bp.route("/profile", methods=["POST"])
@require_auth
def create_profile():
    data = request.get_json() or {}
    role = data.get("role")
    if role not in ("freelancer", "client"):
        return jsonify({"error": "Invalid role"}), 400
    supabase = get_supabase(service_role=True)
    existing = _get_profile(supabase, g.user_id)
    if existing:
        supabase.table("profiles").update({"role": role}).eq("id", g.user_id).execute()
        r2 = supabase.table("profiles").select("*").eq("id", g.user_id).single().execute()
        return jsonify(r2.data if r2 and hasattr(r2, "data") and r2.data else {})
    username = f"user_{g.user_id[:8]}"
    payload = {"id": g.user_id, "role": role, "username": username}
    supabase.table("profiles").insert(payload).execute()
    r2 = supabase.table("profiles").select("*").eq("id", g.user_id).single().execute()
    return jsonify(r2.data if r2 and hasattr(r2, "data") and r2.data else payload), 201

@bp.route("/session", methods=["GET"])
def session():
    uid = get_current_user_id()
    if not uid:
        return jsonify({"user": None}), 200
    supabase = get_supabase(service_role=True)
    data = _get_profile(supabase, uid)
    return jsonify({"user": data, "user_id": uid}), 200
