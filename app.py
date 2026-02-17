"""
MATATAG AI Lesson Plan Generator - Standalone Web Application
DepEd-aligned lesson plan content generator based on MATATAG Curriculum.
"""

import os
import re
import json
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, session, send_file, redirect, url_for, g

load_dotenv()
from curriculum_loader import (
    get_subjects, get_grades_for_subject, get_quarters_for_subject_grade,
    get_competencies, get_competency_by_id, get_pedagogical_approaches,
    get_21st_century_skills, get_crosscutting_concepts, load_all_curriculum_data,
    DB_PATH, SUBJECT_DISPLAY
)
from lesson_generator import (
    generate_lesson_plan, generate_assessment, generate_quiz,
    get_template_sections, get_procedure_models,
    TEMPLATE_SECTIONS, PROCEDURE_MODELS, ASSESSMENT_TYPES, QUIZ_TYPES
)
from scorm_builder import build_scorm_package
from auth import auth_bp, login_required, init_db, verify_auth_token, generate_auth_token

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

# Register auth blueprint
app.register_blueprint(auth_bp)

# Initialize MySQL users table
try:
    init_db()
except Exception as e:
    print(f"Warning: Could not initialize auth database: {e}")

# Ensure curriculum database is loaded on startup
if not os.path.exists(DB_PATH):
    print("First run: loading curriculum data from Excel files...")
    load_all_curriculum_data()


# ── Token-based Session (Cloudways Nginx strips cookies) ──

@app.before_request
def restore_session_from_token():
    """Restore session from URL auth token since cookies are stripped by Nginx."""
    if "user_id" in session:
        # Session already populated (cookie worked or already restored)
        token = request.args.get("_t", "")
        g.auth_token = token if token else generate_auth_token(
            session["user_id"], session.get("user_email", ""),
            session.get("user_name", ""), session.get("user_role", ""))
        return
    token = request.args.get("_t", "")
    if not token:
        g.auth_token = ""
        return
    data = verify_auth_token(token)
    if data:
        session["user_id"] = data["uid"]
        session["user_email"] = data["email"]
        session["user_name"] = data["name"]
        session["user_role"] = data["role"]
        g.auth_token = token
    else:
        g.auth_token = ""


@app.context_processor
def inject_auth_token():
    """Make auth_token available in all templates."""
    return {"auth_token": getattr(g, "auth_token", "")}


@app.template_global()
def turl(endpoint, **kwargs):
    """Generate URL with auth token appended."""
    url = url_for(endpoint, **kwargs)
    token = getattr(g, "auth_token", "")
    if token:
        url += ("&" if "?" in url else "?") + f"_t={token}"
    return url


# ── Security Headers ────────────────────────────────────────

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'"
    )
    # Prevent Varnish from caching/stripping cookies
    response.headers["Cache-Control"] = "private, no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Cookie"
    return response


# ── Routes ──────────────────────────────────────────────────

@app.route("/")
def landing():
    """Public marketing landing page."""
    return render_template("landing.html")


@app.route("/generator")
@login_required
def generator():
    """Lesson plan generator (requires login)."""
    subjects = get_subjects()
    return render_template("generator.html",
                           subjects=subjects,
                           template_sections=TEMPLATE_SECTIONS,
                           procedure_models=PROCEDURE_MODELS)


# ── API Routes (require login) ─────────────────────────────

@app.route("/api/grades/<subject_id>")
@login_required
def api_grades(subject_id):
    """Get grades for a subject."""
    grades = get_grades_for_subject(subject_id)
    return jsonify(grades)


@app.route("/api/quarters/<subject_id>/<grade>")
@login_required
def api_quarters(subject_id, grade):
    """Get quarters for a subject and grade."""
    quarters = get_quarters_for_subject_grade(subject_id, grade)
    return jsonify(quarters)


@app.route("/api/competencies/<subject_id>")
@login_required
def api_competencies(subject_id):
    """Get competencies filtered by subject, grade, quarter."""
    grade = request.args.get("grade", "")
    quarter = request.args.get("quarter", "")
    comps = get_competencies(subject_id, grade or None, quarter or None)
    return jsonify(comps)


@app.route("/api/curriculum-context/<subject_id>")
@login_required
def api_curriculum_context(subject_id):
    """Get pedagogical approaches, 21st century skills, and crosscutting concepts."""
    approaches = get_pedagogical_approaches(subject_id)
    skills = get_21st_century_skills(subject_id)
    concepts = get_crosscutting_concepts(subject_id)
    return jsonify({
        "approaches": approaches,
        "skills": skills,
        "concepts": concepts,
    })


@app.route("/api/generate", methods=["POST"])
@login_required
def api_generate():
    """Generate a lesson plan."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    subject_id = data.get("subject_id")
    competency_ids = data.get("competency_ids", [])
    template_config = data.get("template_config", TEMPLATE_SECTIONS)
    use_ai = data.get("use_ai", False)
    api_key = data.get("api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    ai_provider = data.get("ai_provider", "anthropic")

    if not subject_id:
        return jsonify({"error": "Subject is required"}), 400
    if not competency_ids:
        return jsonify({"error": "Select at least one learning competency"}), 400

    # Convert string IDs to integers
    try:
        competency_ids = [int(cid) for cid in competency_ids]
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid competency IDs"}), 400

    content, error = generate_lesson_plan(
        subject_id, competency_ids, template_config,
        use_ai=use_ai, api_key=api_key, ai_provider=ai_provider
    )

    if error:
        return jsonify({"error": error}), 400

    return jsonify({"content": content})


@app.route("/api/generate-assessment", methods=["POST"])
@login_required
def api_generate_assessment():
    """Generate authentic assessment."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    subject_id = data.get("subject_id")
    competency_ids = data.get("competency_ids", [])
    assessment_config = data.get("assessment_config", {})
    use_ai = data.get("use_ai", False)
    api_key = data.get("api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    ai_provider = data.get("ai_provider", "anthropic")

    if not subject_id:
        return jsonify({"error": "Subject is required"}), 400
    if not competency_ids:
        return jsonify({"error": "Select at least one learning competency"}), 400

    try:
        competency_ids = [int(cid) for cid in competency_ids]
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid competency IDs"}), 400

    content, error = generate_assessment(
        subject_id, competency_ids, assessment_config,
        use_ai=use_ai, api_key=api_key, ai_provider=ai_provider
    )

    if error:
        return jsonify({"error": error}), 400

    return jsonify({"content": content})


@app.route("/api/generate-quiz", methods=["POST"])
@login_required
def api_generate_quiz():
    """Generate a quiz from competencies."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    subject_id = data.get("subject_id")
    competency_ids = data.get("competency_ids", [])
    quiz_config = data.get("quiz_config", {})
    use_ai = data.get("use_ai", False)
    api_key = data.get("api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    ai_provider = data.get("ai_provider", "anthropic")

    if not subject_id:
        return jsonify({"error": "Subject is required"}), 400
    if not competency_ids:
        return jsonify({"error": "Select at least one learning competency"}), 400

    try:
        competency_ids = [int(cid) for cid in competency_ids]
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid competency IDs"}), 400

    content, error = generate_quiz(
        subject_id, competency_ids, quiz_config,
        use_ai=use_ai, api_key=api_key, ai_provider=ai_provider
    )

    if error:
        return jsonify({"error": error}), 400

    return jsonify({"content": content})


@app.route("/api/download-scorm", methods=["POST"])
@login_required
def api_download_scorm():
    """Generate and download a SCORM 1.2 package."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    title = data.get("title", "MATATAG Lesson Plan")
    lesson_plan_md = data.get("lesson_plan", "")
    assessment_md = data.get("assessment", "")
    quiz_md = data.get("quiz", "")

    if not lesson_plan_md and not assessment_md and not quiz_md:
        return jsonify({"error": "No content to package"}), 400

    pkg = build_scorm_package(title, lesson_plan_md or None, assessment_md or None, quiz_md or None)
    safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title)[:50]

    return send_file(
        pkg,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'SCORM_{safe_title}.zip'
    )


@app.route("/api/reload-data", methods=["POST"])
@login_required
def api_reload_data():
    """Reload curriculum data from Excel files."""
    try:
        count = load_all_curriculum_data()
        return jsonify({"message": f"Reloaded {count} learning competencies."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8080)
