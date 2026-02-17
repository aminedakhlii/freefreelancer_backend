import json
import os
import re
import requests
from openai import OpenAI
from flask import Blueprint, request, jsonify, g
from .auth_middleware import require_auth, require_role
from .supabase_client import get_supabase

bp = Blueprint("profiles", __name__)
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
MAX_PAGE_BYTES = 120_000
USER_AGENT = "Mozilla/5.0 (compatible; FreeFreelancer/1.0; +https://freefreelancer.us)"

@bp.route("/me", methods=["GET", "PATCH"])
@require_auth
def me():
    supabase = get_supabase(service_role=True)
    if request.method == "GET":
        r = supabase.table("profiles").select("*").eq("id", g.user_id).maybe_single().execute()
        if not r.data:
            return jsonify({"error": "Profile not found"}), 404
        return jsonify(r.data)
    data = request.get_json() or {}
    allowed = {"full_name", "title", "company_name", "bio", "industry", "address", "phone", "website", "hourly_rate", "avatar_url", "skills", "profile_complete"}
    payload = {k: v for k, v in data.items() if k in allowed}
    if not payload:
        return jsonify({"error": "No valid fields"}), 400
    r = supabase.table("profiles").update(payload).eq("id", g.user_id).execute()
    return jsonify(r.data[0] if r.data else {})

@bp.route("/freelancer/<username>", methods=["GET"])
def get_freelancer_by_username(username):
    supabase = get_supabase(service_role=True)
    r = supabase.table("profiles").select("id, full_name, title, bio, skills, hourly_rate, avatar_url, username, created_at").eq("username", username).eq("role", "freelancer").maybe_single().execute()
    if not r.data:
        return jsonify({"error": "Not found"}), 404
    portfolio = supabase.table("portfolio_items").select("*").eq("user_id", r.data["id"]).order("created_at", desc=True).execute()
    return jsonify({**r.data, "portfolio": portfolio.data or []})

@bp.route("/client/<username>", methods=["GET"])
def get_client_by_username(username):
    supabase = get_supabase(service_role=True)
    r = supabase.table("profiles").select("id, full_name, company_name, industry, bio, avatar_url, username, website, created_at").eq("username", username).eq("role", "client").maybe_single().execute()
    if not r.data:
        return jsonify({"error": "Not found"}), 404
    return jsonify(r.data)

@bp.route("/freelancers", methods=["GET"])
def list_freelancers():
    supabase = get_supabase(service_role=True)
    skills = request.args.getlist("skills") or request.args.get("skills", "").split(",")
    skills = [s.strip() for s in skills if s.strip()]
    q = supabase.table("profiles").select("id, full_name, title, skills, hourly_rate, avatar_url, username").eq("role", "freelancer")
    r = q.order("created_at", desc=True).limit(50).execute()
    data = (r.data if r and hasattr(r, "data") else []) or []
    if skills:
        data = [p for p in data if p.get("skills") and any(s in (p.get("skills") or []) for s in skills)]
    return jsonify({"items": data})


@bp.route("/me/portfolio", methods=["GET", "POST"])
@require_auth
@require_role("freelancer")
def my_portfolio():
    supabase = get_supabase(service_role=True)
    if request.method == "GET":
        r = supabase.table("portfolio_items").select("*").eq("user_id", g.user_id).order("created_at", desc=True).execute()
        return jsonify({"items": r.data or []})
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400
    payload = {
        "user_id": g.user_id,
        "title": title,
        "description": (data.get("description") or "").strip() or None,
        "link": (data.get("link") or "").strip() or None,
        "skills": data.get("skills") if isinstance(data.get("skills"), list) else None,
        "image_urls": data.get("image_urls") if isinstance(data.get("image_urls"), list) else [],
    }
    r = supabase.table("portfolio_items").insert(payload).execute()
    return jsonify(r.data[0] if r.data else {})


@bp.route("/me/portfolio/<item_id>", methods=["PATCH", "DELETE"])
@require_auth
@require_role("freelancer")
def my_portfolio_item(item_id):
    supabase = get_supabase(service_role=True)
    r = supabase.table("portfolio_items").select("id").eq("id", item_id).eq("user_id", g.user_id).maybe_single().execute()
    if not r.data:
        return jsonify({"error": "Not found"}), 404
    if request.method == "DELETE":
        supabase.table("portfolio_items").delete().eq("id", item_id).eq("user_id", g.user_id).execute()
        return jsonify({"ok": True})
    data = request.get_json() or {}
    allowed = {"title", "description", "link", "skills", "image_urls"}
    payload = {k: v for k, v in data.items() if k in allowed}
    if "title" in payload and isinstance(payload["title"], str):
        payload["title"] = payload["title"].strip() or None
    if "description" in payload and isinstance(payload["description"], str):
        payload["description"] = payload["description"].strip() or None
    if "link" in payload and isinstance(payload["link"], str):
        payload["link"] = payload["link"].strip() or None
    if not payload:
        return jsonify({"error": "No valid fields"}), 400
    r = supabase.table("portfolio_items").update(payload).eq("id", item_id).eq("user_id", g.user_id).execute()
    return jsonify(r.data[0] if r.data else {})


def _fetch_page_content(url: str) -> str:
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=15,
        allow_redirects=True,
    )
    resp.raise_for_status()
    text = resp.text
    if len(text) > MAX_PAGE_BYTES:
        text = text[:MAX_PAGE_BYTES] + "\n...[truncated]"
    return text


def _extract_profile_with_openai(page_content: str) -> dict:
    if not OPENAI_API_KEY:
        return {"bio": "", "portfolio": []}
    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = """Extract from this freelancer profile page (HTML or text from Upwork, Fiverr, LinkedIn, GitHub, etc.):

1) bio: A single string with the person's professional bio/summary. Use empty string if none found.
2) portfolio: A JSON array of projects. Each project has: title (string), description (string), link (string URL or null), image (string image URL or null). Omit projects with no title.

Return only valid JSON, no markdown or explanation. Format:
{"bio": "...", "portfolio": [{"title": "...", "description": "...", "link": "..." or null, "image": "..." or null}]}
"""
    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You output only valid JSON."},
                {"role": "user", "content": prompt + "\n\n---\n\n" + page_content[:80_000]},
            ],
            temperature=0.1,
        )
        raw = (completion.choices[0].message.content or "").strip()
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
        out = json.loads(raw)
        bio = out.get("bio") or ""
        portfolio = out.get("portfolio")
        if not isinstance(portfolio, list):
            portfolio = []
        return {"bio": bio, "portfolio": portfolio}
    except Exception:
        return {"bio": "", "portfolio": []}


@bp.route("/import-from-link", methods=["POST"])
@require_auth
@require_role("freelancer")
def import_from_link():
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    if not url.startswith("http://") and not url.startswith("https://"):
        return jsonify({"error": "Invalid url"}), 400
    try:
        content = _fetch_page_content(url)
    except requests.RequestException as e:
        print(e)
        return jsonify({"error": "Could not fetch URL", "detail": str(e)}), 400
    result = _extract_profile_with_openai(content)
    return jsonify(result)
