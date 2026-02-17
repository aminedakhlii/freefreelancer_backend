from flask import Blueprint, request, jsonify, g
from .auth_middleware import require_auth
from .supabase_client import get_supabase

bp = Blueprint("messages", __name__)

@bp.route("/threads", methods=["GET"])
@require_auth
def list_threads():
    supabase = get_supabase(service_role=True)
    r = supabase.table("message_threads").select("*, projects(title)").or_(f"client_id.eq.{g.user_id},freelancer_id.eq.{g.user_id}").order("updated_at", desc=True).execute()
    data = (r.data if r and hasattr(r, "data") else []) or []
    other_ids = list({(t["freelancer_id"] if t["client_id"] == g.user_id else t["client_id"]) for t in data})
    profiles = {}
    if other_ids:
        for uid in other_ids:
            p = supabase.table("profiles").select("full_name, username").eq("id", uid).maybe_single().execute()
            if p and getattr(p, "data", None) and p.data:
                profiles[str(uid)] = p.data
    for t in data:
        oid = t["freelancer_id"] if t["client_id"] == g.user_id else t["client_id"]
        t["other_participant"] = profiles.get(str(oid))
    return jsonify({"items": data})

@bp.route("/thread/<thread_id>", methods=["GET"])
@require_auth
def get_thread(thread_id):
    supabase = get_supabase(service_role=True)
    thread = supabase.table("message_threads").select("*").eq("id", thread_id).maybe_single().execute()
    if not thread.data:
        return jsonify({"error": "Not found"}), 404
    t = thread.data
    if t["client_id"] != g.user_id and t["freelancer_id"] != g.user_id:
        return jsonify({"error": "Forbidden"}), 403
    messages = supabase.table("messages").select("*").eq("thread_id", thread_id).order("created_at", desc=False).execute()
    proj = supabase.table("projects").select("title").eq("id", t["project_id"]).maybe_single().execute()
    other_id = t["freelancer_id"] if t["client_id"] == g.user_id else t["client_id"]
    other = supabase.table("profiles").select("full_name, username").eq("id", other_id).maybe_single().execute()
    payload = {
        **t,
        "messages": messages.data or [],
        "project_title": proj.data.get("title") if proj and getattr(proj, "data", None) and proj.data else None,
        "other_participant": other.data if other and getattr(other, "data", None) else None,
    }
    return jsonify(payload)

@bp.route("/thread", methods=["POST"])
@require_auth
def create_thread():
    data = request.get_json() or {}
    project_id = data.get("project_id")
    freelancer_id = data.get("freelancer_id") or data.get("other_user_id")
    if not project_id or not freelancer_id:
        return jsonify({"error": "project_id and freelancer_id required"}), 400
    supabase = get_supabase(service_role=True)
    proj = supabase.table("projects").select("client_id").eq("id", project_id).maybe_single().execute()
    if not proj or not getattr(proj, "data", None) or not proj.data:
        return jsonify({"error": "Project not found"}), 404
    client_id = proj.data["client_id"]
    if str(client_id) != str(g.user_id):
        return jsonify({"error": "You can only start a conversation for your own project"}), 403
    existing = supabase.table("message_threads").select("id").eq("project_id", project_id).eq("client_id", client_id).eq("freelancer_id", freelancer_id).maybe_single().execute()
    if existing and getattr(existing, "data", None) and existing.data:
        ex = supabase.table("message_threads").select("*").eq("id", existing.data["id"]).single().execute()
        return jsonify(ex.data if ex and getattr(ex, "data", None) else existing.data), 200
    payload = {"project_id": project_id, "client_id": client_id, "freelancer_id": freelancer_id}
    r = supabase.table("message_threads").insert(payload).execute()
    return jsonify(r.data[0] if r.data else {}), 201

@bp.route("/thread/<thread_id>/messages", methods=["GET"])
@require_auth
def list_messages(thread_id):
    supabase = get_supabase(service_role=True)
    thread = supabase.table("message_threads").select("*").eq("id", thread_id).maybe_single().execute()
    if not thread.data or (thread.data["client_id"] != g.user_id and thread.data["freelancer_id"] != g.user_id):
        return jsonify({"error": "Forbidden"}), 403
    r = supabase.table("messages").select("*").eq("thread_id", thread_id).order("created_at", desc=False).execute()
    return jsonify({"items": r.data or []})

@bp.route("/thread/<thread_id>/messages", methods=["POST"])
@require_auth
def send_message(thread_id):
    data = request.get_json() or {}
    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"error": "Message body required"}), 400
    supabase = get_supabase(service_role=True)
    thread = supabase.table("message_threads").select("*").eq("id", thread_id).maybe_single().execute()
    if not thread.data or (thread.data["client_id"] != g.user_id and thread.data["freelancer_id"] != g.user_id):
        return jsonify({"error": "Forbidden"}), 403
    payload = {"thread_id": thread_id, "sender_id": g.user_id, "body": body}
    r = supabase.table("messages").insert(payload).execute()
    from datetime import datetime, timezone
    supabase.table("message_threads").update({"updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", thread_id).execute()
    return jsonify(r.data[0] if r.data else {}), 201
