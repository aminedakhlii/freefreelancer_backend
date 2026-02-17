from flask import Blueprint, request, jsonify, g
from .auth_middleware import require_auth, require_role
from .supabase_client import get_supabase

bp = Blueprint("proposals", __name__)

@bp.route("", methods=["POST"])
@require_auth
@require_role("freelancer")
def create():
    data = request.get_json() or {}
    project_id = data.get("project_id")
    cover_letter = (data.get("cover_letter") or "").strip()
    proposed_budget = data.get("proposed_budget")
    timeline = data.get("timeline")
    portfolio_item_ids = data.get("portfolio_item_ids") or []
    if not project_id or len(cover_letter) < 200 or len(cover_letter) > 1000:
        return jsonify({"error": "Cover letter 200-1000 characters required"}), 400
    if proposed_budget is None or int(proposed_budget) < 0:
        return jsonify({"error": "Valid proposed budget required"}), 400
    supabase = get_supabase(service_role=True)
    # Must have passed interview for this project
    interview = supabase.table("interviews").select("id, score, passed").eq("project_id", project_id).eq("freelancer_id", g.user_id).order("created_at", desc=True).limit(1).execute()
    if not interview.data or not interview.data[0].get("passed"):
        return jsonify({"error": "You must pass the AI interview before submitting a proposal"}), 400
    existing = supabase.table("proposals").select("id").eq("project_id", project_id).eq("freelancer_id", g.user_id).execute()
    if existing.data:
        return jsonify({"error": "You already submitted a proposal for this project"}), 400
    payload = {
        "project_id": project_id,
        "freelancer_id": g.user_id,
        "cover_letter": cover_letter,
        "proposed_budget": int(proposed_budget),
        "timeline": timeline,
        "portfolio_item_ids": portfolio_item_ids,
        "interview_id": interview.data[0]["id"],
        "status": "active",
    }
    r = supabase.table("proposals").insert(payload).execute()
    return jsonify(r.data[0] if r.data else {}), 201

@bp.route("/my", methods=["GET"])
@require_auth
@require_role("freelancer")
def my_proposals():
    supabase = get_supabase(service_role=True)
    status = request.args.get("status")
    q = supabase.table("proposals").select("*, projects(id, title, status), interviews(score, passed)").eq("freelancer_id", g.user_id).order("created_at", desc=True)
    if status:
        q = q.eq("status", status)
    r = q.execute()
    return jsonify({"items": r.data or []})

@bp.route("/<proposal_id>", methods=["GET"])
@require_auth
def get_proposal(proposal_id):
    supabase = get_supabase(service_role=True)
    r = supabase.table("proposals").select("*, projects(*), interviews(*), profiles!freelancer_id(full_name, title, username, avatar_url, skills)").eq("id", proposal_id).maybe_single().execute()
    if not r.data:
        return jsonify({"error": "Not found"}), 404
    p = r.data
    if p["freelancer_id"] != g.user_id:
        profile = supabase.table("profiles").select("role").eq("id", g.user_id).maybe_single().execute()
        if not profile.data or profile.data.get("role") != "client" or p["projects"]["client_id"] != g.user_id:
            return jsonify({"error": "Forbidden"}), 403
    return jsonify(p)

@bp.route("/<proposal_id>/accept", methods=["POST"])
@require_auth
@require_role("client")
def accept(proposal_id):
    supabase = get_supabase(service_role=True)
    prop = supabase.table("proposals").select("*, projects(client_id)").eq("id", proposal_id).maybe_single().execute()
    if not prop.data or prop.data["projects"]["client_id"] != g.user_id:
        return jsonify({"error": "Forbidden"}), 403
    if prop.data.get("status") != "active":
        return jsonify({"error": "Proposal no longer active"}), 400
    supabase.table("proposals").update({"status": "accepted"}).eq("id", proposal_id).execute()
    supabase.table("projects").update({"status": "in_progress"}).eq("id", prop.data["project_id"]).execute()
    return jsonify({"ok": True})

@bp.route("/<proposal_id>/decline", methods=["POST"])
@require_auth
@require_role("client")
def decline(proposal_id):
    supabase = get_supabase(service_role=True)
    prop = supabase.table("proposals").select("*, projects(client_id)").eq("id", proposal_id).maybe_single().execute()
    if not prop.data or prop.data["projects"]["client_id"] != g.user_id:
        return jsonify({"error": "Forbidden"}), 403
    if prop.data.get("status") != "active":
        return jsonify({"error": "Proposal no longer active"}), 400
    supabase.table("proposals").update({"status": "declined"}).eq("id", proposal_id).execute()
    return jsonify({"ok": True})

@bp.route("/project/<project_id>", methods=["GET"])
@require_auth
@require_role("client")
def list_by_project(project_id):
    supabase = get_supabase(service_role=True)
    proj = supabase.table("projects").select("client_id").eq("id", project_id).maybe_single().execute()
    if not proj.data or proj.data["client_id"] != g.user_id:
        return jsonify({"error": "Forbidden"}), 403
    r = supabase.table("proposals").select("*, profiles!freelancer_id(full_name, title, username, avatar_url), interviews(score, passed, transcript)").eq("project_id", project_id).order("created_at", desc=True).execute()
    return jsonify({"items": r.data or []})
