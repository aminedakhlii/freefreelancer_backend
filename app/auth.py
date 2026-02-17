from flask import Blueprint, request, jsonify, g
from .auth_middleware import require_auth, get_current_user_id
from .supabase_client import get_supabase

bp = Blueprint("auth", __name__)

@bp.route("/me", methods=["GET"])
@require_auth
def me():
    supabase = get_supabase(service_role=True)
    r = supabase.table("profiles").select("*").eq("id", g.user_id).maybe_single().execute()
    if not r or not getattr(r, "data", None):
        return jsonify({"error": "Profile not found"}), 404
    return jsonify(r.data)

@bp.route("/profile", methods=["POST"])
@require_auth
def create_profile():
    data = request.get_json() or {}
    role = data.get("role")
    if role not in ("freelancer", "client"):
        return jsonify({"error": "Invalid role"}), 400
    supabase = get_supabase(service_role=True)
    r = supabase.table("profiles").select("id").eq("id", g.user_id).maybe_single().execute()
    existing = r.data if (r is not None and hasattr(r, "data")) else None
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
    r = supabase.table("profiles").select("*").eq("id", uid).maybe_single().execute()
    return jsonify({"user": r.data if r and hasattr(r, "data") else None, "user_id": uid}), 200
