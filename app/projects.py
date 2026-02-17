from flask import Blueprint, request, jsonify, g
from .auth_middleware import require_auth, require_role
from .supabase_client import get_supabase

bp = Blueprint("projects", __name__)

MIN_BUDGET = 1000

@bp.route("", methods=["GET"])
def list_projects():
    supabase = get_supabase(service_role=True)
    q = supabase.table("projects").select("*, profiles!client_id(full_name, company_name, username)", count="exact").eq("status", "open").order("created_at", desc=True)
    skills = request.args.getlist("skills") or (request.args.get("skills") or "").split(",")
    skills = [s.strip() for s in skills if s.strip()]
    budget_min = request.args.get("budget_min", type=int)
    budget_max = request.args.get("budget_max", type=int)
    search = (request.args.get("q") or "").strip()
    r = q.limit(50).execute()
    items = r.data or []
    if search:
        search_lower = search.lower()
        items = [p for p in items if search_lower in (p.get("title") or "").lower() or search_lower in (p.get("description") or "").lower()]
    if skills:
        items = [p for p in items if p.get("skills") and any(s in (p.get("skills") or []) for s in skills)]
    if budget_min is not None:
        items = [p for p in items if (p.get("budget") or 0) >= budget_min]
    if budget_max is not None:
        items = [p for p in items if (p.get("budget") or 0) <= budget_max]
    return jsonify({"items": items, "total": len(items)})

@bp.route("/<project_id>", methods=["GET"])
def get_project(project_id):
    supabase = get_supabase(service_role=True)
    r = supabase.table("projects").select("*, profiles!client_id(full_name, company_name, username)").eq("id", project_id).maybe_single().execute()
    if not r.data:
        return jsonify({"error": "Not found"}), 404
    return jsonify(r.data)

@bp.route("", methods=["POST"])
@require_auth
@require_role("client")
def create_project():
    data = request.get_json() or {}
    title = data.get("title") or ""
    description = data.get("description") or ""
    skills = data.get("skills") or []
    budget = data.get("budget")
    timeline = data.get("timeline")
    deliverables = data.get("deliverables") or []
    if len(description) < 100:
        return jsonify({"error": "Description must be at least 100 characters"}), 400
    if not isinstance(skills, list) or len(skills) < 1 or len(skills) > 10:
        return jsonify({"error": "Select 1-10 required skills"}), 400
    if budget is None or int(budget) < MIN_BUDGET:
        return jsonify({"error": f"Budget must be at least ${MIN_BUDGET}"}), 400
    supabase = get_supabase(service_role=True)
    payload = {
        "client_id": g.user_id,
        "title": title.strip(),
        "description": description.strip(),
        "skills": skills,
        "budget": int(budget),
        "timeline": timeline,
        "deliverables": deliverables,
        "status": "open",
    }
    r = supabase.table("projects").insert(payload).execute()
    return jsonify(r.data[0] if r.data else {}), 201

@bp.route("/<project_id>", methods=["PATCH"])
@require_auth
@require_role("client")
def update_project(project_id):
    supabase = get_supabase(service_role=True)
    existing = supabase.table("projects").select("client_id, status").eq("id", project_id).maybe_single().execute()
    if not existing.data or existing.data["client_id"] != g.user_id:
        return jsonify({"error": "Forbidden"}), 403
    if existing.data.get("status") != "open":
        return jsonify({"error": "Only open projects can be edited"}), 400
    data = request.get_json() or {}
    allowed = {"title", "description", "skills", "budget", "timeline", "deliverables"}
    payload = {k: v for k, v in data.items() if k in allowed}
    if "budget" in payload and int(payload["budget"]) < MIN_BUDGET:
        return jsonify({"error": f"Budget must be at least ${MIN_BUDGET}"}), 400
    if not payload:
        return jsonify({"error": "No valid fields"}), 400
    r = supabase.table("projects").update(payload).eq("id", project_id).execute()
    return jsonify(r.data[0] if r.data else {})

@bp.route("/<project_id>", methods=["DELETE"])
@require_auth
@require_role("client")
def delete_project(project_id):
    supabase = get_supabase(service_role=True)
    existing = supabase.table("projects").select("client_id").eq("id", project_id).maybe_single().execute()
    if not existing.data or existing.data["client_id"] != g.user_id:
        return jsonify({"error": "Forbidden"}), 403
    proposals = supabase.table("proposals").select("id").eq("project_id", project_id).execute()
    if proposals.data and len(proposals.data) > 0:
        return jsonify({"error": "Cannot delete project with proposals"}), 400
    supabase.table("projects").delete().eq("id", project_id).execute()
    return jsonify({"ok": True}), 200

@bp.route("/<project_id>/close", methods=["POST"])
@require_auth
@require_role("client")
def close_project(project_id):
    supabase = get_supabase(service_role=True)
    existing = supabase.table("projects").select("client_id").eq("id", project_id).maybe_single().execute()
    if not existing.data or existing.data["client_id"] != g.user_id:
        return jsonify({"error": "Forbidden"}), 403
    r = supabase.table("projects").update({"status": "closed"}).eq("id", project_id).execute()
    return jsonify(r.data[0] if r.data else {})

@bp.route("/my", methods=["GET"])
@require_auth
@require_role("client")
def my_projects():
    supabase = get_supabase(service_role=True)
    r = supabase.table("projects").select("*").eq("client_id", g.user_id).order("created_at", desc=True).execute()
    return jsonify({"items": r.data or []})
