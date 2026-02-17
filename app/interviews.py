import os
from flask import Blueprint, request, jsonify, g
from .auth_middleware import require_auth, require_role
from .supabase_client import get_supabase

bp = Blueprint("interviews", __name__)

PASS_THRESHOLD = 70
MAX_RETAKES = 2
COOLDOWN_HOURS = 24

def _get_openai():
    try:
        from openai import OpenAI
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            return None
        return OpenAI(api_key=key)
    except Exception:
        return None

@bp.route("/start/<project_id>", methods=["POST"])
@require_auth
@require_role("freelancer")
def start_interview(project_id):
    supabase = get_supabase(service_role=True)
    project = supabase.table("projects").select("id, skills, title").eq("id", project_id).maybe_single().execute()
    if not project.data:
        return jsonify({"error": "Project not found"}), 404
    # Check existing completed interviews for this freelancer + project
    existing = supabase.table("interviews").select("id, passed, created_at").eq("project_id", project_id).eq("freelancer_id", g.user_id).order("created_at", desc=True).execute()
    if existing.data and existing.data[0].get("passed"):
        return jsonify({"error": "You already passed the interview", "interview_id": existing.data[0]["id"]}), 400
    attempts = [e for e in (existing.data or [])]
    if len(attempts) >= MAX_RETAKES + 1:
        return jsonify({"error": "Max retakes reached"}), 400
    if attempts:
        from datetime import datetime, timezone, timedelta
        last = datetime.fromisoformat(attempts[0]["created_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - last < timedelta(hours=COOLDOWN_HOURS):
            return jsonify({"error": "Cooldown active", "retry_after": COOLDOWN_HOURS}), 429
    # Create interview and generate questions
    skills = project.data.get("skills") or []
    profile = supabase.table("profiles").select("skills").eq("id", g.user_id).maybe_single().execute()
    freelancer_skills = (profile.data or {}).get("skills") or []
    client = _get_openai()
    questions = []
    if client:
        prompt = f"Generate exactly 5 short interview questions (one per line, no numbering) for a freelancer applying to a project. Project skills: {skills}. Freelancer skills: {freelancer_skills}. Mix: 40% technical, 40% scenario, 20% problem-solving. Each question one line."
        try:
            resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=400)
            text = (resp.choices[0].message.content or "").strip()
            questions = [q.strip() for q in text.split("\n") if q.strip()][:5]
        except Exception:
            pass
    if not questions:
        questions = [
            "Describe your experience with the required skills for this project.",
            "Tell us about a similar project you completed and the outcome.",
            "How do you approach deadlines and scope changes?",
            "What tools do you use for this type of work?",
            "Why are you a good fit for this project?",
        ]
    payload = {
        "project_id": project_id,
        "freelancer_id": g.user_id,
        "questions": questions,
        "answers": [],
        "transcript": [],
        "score": None,
        "passed": None,
        "status": "in_progress",
    }
    r = supabase.table("interviews").insert(payload).execute()
    return jsonify(r.data[0] if r.data else {}), 201

@bp.route("/<interview_id>", methods=["GET"])
@require_auth
def get_interview(interview_id):
    supabase = get_supabase(service_role=True)
    r = supabase.table("interviews").select("*").eq("id", interview_id).maybe_single().execute()
    if not r.data:
        return jsonify({"error": "Not found"}), 404
    if r.data["freelancer_id"] != g.user_id:
        proj = supabase.table("projects").select("client_id").eq("id", r.data["project_id"]).maybe_single().execute()
        if not proj.data or proj.data["client_id"] != g.user_id:
            return jsonify({"error": "Forbidden"}), 403
    return jsonify(r.data)

@bp.route("/<interview_id>/answer", methods=["POST"])
@require_auth
@require_role("freelancer")
def submit_answer(interview_id):
    data = request.get_json() or {}
    answer = (data.get("answer") or "").strip()
    if not answer:
        return jsonify({"error": "Answer required"}), 400
    supabase = get_supabase(service_role=True)
    r = supabase.table("interviews").select("*").eq("id", interview_id).eq("freelancer_id", g.user_id).maybe_single().execute()
    if not r.data or r.data.get("status") != "in_progress":
        return jsonify({"error": "Interview not found or not in progress"}), 400
    inv = r.data
    questions = inv.get("questions") or []
    answers = list(inv.get("answers") or [])
    transcript = list(inv.get("transcript") or [])
    idx = len(answers)
    if idx >= len(questions):
        return jsonify({"error": "All questions answered"}), 400
    transcript.append({"q": questions[idx], "a": answer})
    answers.append(answer)
    if len(answers) >= len(questions):
        # Score with OpenAI if available
        score = 75
        client = _get_openai()
        if client and transcript:
            try:
                prompt = f"Score this freelancer interview (0-100 integer only, one number). Be fair. Transcript: {transcript}. Reply with only the number."
                resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], max_tokens=10)
                t = (resp.choices[0].message.content or "75").strip()
                score = min(100, max(0, int("".join(c for c in t if c.isdigit()) or "75")))
            except Exception:
                pass
        passed = score >= PASS_THRESHOLD
        supabase.table("interviews").update({
            "answers": answers,
            "transcript": transcript,
            "score": score,
            "passed": passed,
            "status": "completed",
        }).eq("id", interview_id).execute()
        return jsonify({"completed": True, "score": score, "passed": passed})
    supabase.table("interviews").update({"answers": answers, "transcript": transcript}).eq("id", interview_id).execute()
    return jsonify({"next_index": len(answers), "total": len(questions)})
