"""
SKOOLED-AI Lesson Plan Generator - Standalone Web Application
DepEd-aligned lesson plan content generator based on MATATAG Curriculum.
"""

import os
import re
import json
import uuid
import zipfile
from io import BytesIO
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
    generate_lesson_plan, generate_lesson_plan_topic,
    generate_assessment, generate_assessment_topic,
    generate_quiz, generate_quiz_topic,
    convert_quiz_to_gift, convert_quiz_to_qti,
    get_template_sections, get_procedure_models,
    generate_rpms_ppst, regenerate_section,
    TEMPLATE_SECTIONS, PROCEDURE_MODELS, ASSESSMENT_TYPES, QUIZ_TYPES
)
from scorm_builder import build_scorm_package
from auth import auth_bp, login_required, init_db, verify_auth_token, generate_auth_token
from activities_generator import generate_activity_content as _gen_activity_content
from pptx_builder import build_pptx
from syllabus_generator import generate_syllabus as _gen_syllabus

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

# Fix external URL generation when behind Cloudways / Nginx reverse proxy.
# ProxyFix reads X-Forwarded-Proto/Host headers so url_for(_external=True)
# produces https://skooled-ai.webprvw.xyz/... instead of http://127.0.0.1:...
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

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
        # Session already populated (cookie worked or already restored).
        # Verify the URL token; if absent or expired, generate a fresh one
        # so AUTH_TOKEN in the page meta is always valid for API calls.
        token = request.args.get("_t", "")
        if token and verify_auth_token(token):
            g.auth_token = token
        else:
            g.auth_token = generate_auth_token(
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


# ── Activity Logging ────────────────────────────────────────

def _log_activity(action_type, detail="", subject="", grade=""):
    """Log a user activity silently — never blocks the main request."""
    try:
        from auth import get_db
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO activity_log
                       (user_id, user_name, action_type, detail, subject, grade)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (
                        session.get("user_id", 0),
                        session.get("user_name", "Unknown"),
                        action_type,
                        str(detail)[:500],
                        str(subject)[:255],
                        str(grade)[:100],
                    )
                )
        finally:
            conn.close()
    except Exception:
        pass  # Logging must never break user-facing functionality


# ── Error handlers: always return JSON for /api/* routes ────
@app.errorhandler(404)
def err_404(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return str(e), 404

@app.errorhandler(405)
def err_405(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Method not allowed"}), 405
    return str(e), 405

@app.errorhandler(500)
def err_500(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error"}), 500
    return str(e), 500


# ── Routes ──────────────────────────────────────────────────

@app.route("/")
def landing():
    """Public marketing landing page."""
    recent_syllabi = []
    try:
        from auth import get_db as _get_auth_db
        conn = _get_auth_db()
        with conn.cursor() as cur:
            cur.execute(
                """SELECT token, course_title, owner_name, created_at, syllabus_json
                   FROM syllabi ORDER BY created_at DESC LIMIT 6"""
            )
            rows = cur.fetchall()
        conn.close()
        for r in rows:
            syl = json.loads(r["syllabus_json"]) if r["syllabus_json"] else {}
            recent_syllabi.append({
                "token": r["token"],
                "course_title": r["course_title"] or "Untitled",
                "owner_name": r["owner_name"] or "Anonymous",
                "created_at": r["created_at"].strftime("%b %d, %Y") if r["created_at"] else "",
                "institution_type": syl.get("institution_type", "College"),
                "school_name": syl.get("school_name", ""),
            })
    except Exception:
        pass
    return render_template("landing.html", recent_syllabi=recent_syllabi)


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

    _log_activity("lesson_generate", subject_id, subject=subject_id)
    return jsonify({"content": content})


@app.route("/api/generate-topic", methods=["POST"])
@login_required
def api_generate_topic():
    """Generate a topic-based lesson plan."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    topic = data.get("topic", "").strip()
    subject_name = data.get("subject_name", "").strip()
    grade = data.get("grade", "").strip()
    competencies_text = data.get("competencies_text", "").strip()
    template_config = data.get("template_config", TEMPLATE_SECTIONS)
    use_ai = data.get("use_ai", False)
    api_key = data.get("api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    ai_provider = data.get("ai_provider", "anthropic")

    if not topic:
        return jsonify({"error": "Topic is required"}), 400
    if not subject_name:
        return jsonify({"error": "Subject is required"}), 400

    topic_context = {
        "topic": topic,
        "subject_name": subject_name,
        "grade": grade,
        "competencies_text": competencies_text,
    }

    content, error = generate_lesson_plan_topic(
        topic_context, template_config,
        use_ai=use_ai, api_key=api_key, ai_provider=ai_provider
    )

    if error:
        return jsonify({"error": error}), 400

    _log_activity("topic_generate", topic, subject=subject_name, grade=grade)
    return jsonify({"content": content})


@app.route("/api/generate-assessment-topic", methods=["POST"])
@login_required
def api_generate_assessment_topic():
    """Generate authentic assessment for a topic-based lesson plan."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    topic = data.get("topic", "").strip()
    subject_name = data.get("subject_name", "").strip()
    if not topic:
        return jsonify({"error": "Topic is required"}), 400
    if not subject_name:
        return jsonify({"error": "Subject is required"}), 400

    topic_context = {
        "topic": topic,
        "subject_name": subject_name,
        "grade": data.get("grade", "").strip(),
        "competencies_text": data.get("competencies_text", "").strip(),
    }
    assessment_config = data.get("assessment_config", {})
    use_ai = data.get("use_ai", False)
    api_key = data.get("api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    ai_provider = data.get("ai_provider", "anthropic")

    content, error = generate_assessment_topic(
        topic_context, assessment_config,
        use_ai=use_ai, api_key=api_key, ai_provider=ai_provider
    )
    if error:
        return jsonify({"error": error}), 400
    _log_activity("assessment_generate", topic, subject=subject_name,
                  grade=topic_context.get("grade", ""))
    return jsonify({"content": content})


@app.route("/api/generate-quiz-topic", methods=["POST"])
@login_required
def api_generate_quiz_topic():
    """Generate a standalone quiz for a topic-based lesson plan."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    topic = data.get("topic", "").strip()
    subject_name = data.get("subject_name", "").strip()
    if not topic:
        return jsonify({"error": "Topic is required"}), 400
    if not subject_name:
        return jsonify({"error": "Subject is required"}), 400

    topic_context = {
        "topic": topic,
        "subject_name": subject_name,
        "grade": data.get("grade", "").strip(),
        "competencies_text": data.get("competencies_text", "").strip(),
    }
    quiz_config = data.get("quiz_config", {})
    use_ai = data.get("use_ai", False)
    api_key = data.get("api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    ai_provider = data.get("ai_provider", "anthropic")

    content, error = generate_quiz_topic(
        topic_context, quiz_config,
        use_ai=use_ai, api_key=api_key, ai_provider=ai_provider
    )
    if error:
        return jsonify({"error": error}), 400
    _log_activity("quiz_generate", topic, subject=subject_name,
                  grade=topic_context.get("grade", ""))
    return jsonify({"content": content})


@app.route("/api/rate-lesson", methods=["POST"])
@login_required
def api_rate_lesson():
    """Save a lesson plan rating and optional comment."""
    from auth import get_db
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    rating = data.get("rating")
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        return jsonify({"error": "Rating must be an integer between 1 and 5"}), 400

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO lesson_ratings
                   (user_id, user_name, rating, comment, subject, grade, quarter, lesson_title, gen_mode)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    session["user_id"],
                    session.get("user_name", ""),
                    rating,
                    data.get("comment", ""),
                    data.get("subject", ""),
                    data.get("grade", ""),
                    data.get("quarter", ""),
                    data.get("lesson_title", ""),
                    data.get("gen_mode", "curriculum"),
                )
            )
    finally:
        conn.close()

    return jsonify({"message": "Rating saved. Thank you for your feedback!"})


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


def _build_qti_zip(title, qti_xml):
    """Wrap QTI XML in an IMS Content Package ZIP (required by Canvas/Brightspace)."""
    safe_title = title.replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    manifest = f'''<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="quiz_manifest"
    xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <metadata>
    <schema>IMS Content</schema>
    <schemaversion>1.1.3</schemaversion>
  </metadata>
  <organizations/>
  <resources>
    <resource identifier="quiz_resource" type="imsqti_xmlv1p2" href="quiz.xml">
      <file href="quiz.xml"/>
    </resource>
  </resources>
</manifest>'''
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("imsmanifest.xml", manifest.encode("utf-8"))
        zf.writestr("quiz.xml", qti_xml.encode("utf-8") if isinstance(qti_xml, str) else qti_xml)
    buf.seek(0)
    return buf


@app.route("/api/export-quiz-gift", methods=["POST"])
@login_required
def api_export_quiz_gift():
    """Convert generated quiz markdown to Moodle GIFT format and return as .txt download."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    quiz_md = data.get("quiz_md", "").strip()
    if not quiz_md:
        return jsonify({"error": "No quiz content provided"}), 400

    api_key = data.get("api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    ai_provider = data.get("ai_provider", "anthropic")

    content, error = convert_quiz_to_gift(quiz_md, api_key=api_key, ai_provider=ai_provider)
    if error:
        return jsonify({"error": error}), 400

    title = data.get("title", "quiz")
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", title)[:50]
    buf = BytesIO(content.encode("utf-8"))
    buf.seek(0)
    _log_activity("download_gift", data.get("title", "quiz"))
    return send_file(buf, mimetype="text/plain", as_attachment=True,
                     download_name=f"Quiz_{safe}_GIFT.txt")


@app.route("/api/export-quiz-qti", methods=["POST"])
@login_required
def api_export_quiz_qti():
    """Convert generated quiz markdown to IMS QTI 1.2 ZIP package for Canvas/Brightspace."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    quiz_md = data.get("quiz_md", "").strip()
    if not quiz_md:
        return jsonify({"error": "No quiz content provided"}), 400

    title = data.get("title", "Quiz")
    api_key = data.get("api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    ai_provider = data.get("ai_provider", "anthropic")

    qti_xml, error = convert_quiz_to_qti(title, quiz_md, api_key=api_key, ai_provider=ai_provider)
    if error:
        return jsonify({"error": error}), 400

    buf = _build_qti_zip(title, qti_xml)
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", title)[:50]
    _log_activity("download_qti", title)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"Quiz_{safe}_QTI.zip")


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

    if not lesson_plan_md and not assessment_md:
        return jsonify({"error": "No content to package"}), 400

    # Quiz is a standalone LMS activity — not included in the SCORM package
    pkg = build_scorm_package(title, lesson_plan_md or None, assessment_md or None, None)
    safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title)[:50]

    _log_activity("download_scorm", title)
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


@app.route("/api/generate-rpms-ppst", methods=["POST"])
@login_required
def api_generate_rpms_ppst():
    """Generate RPMS-PPST alignment evidence for a lesson plan."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    lesson_plan = data.get("lesson_plan", "").strip()
    if not lesson_plan:
        return jsonify({"error": "Lesson plan content is required"}), 400

    lesson_context = {
        "subject": data.get("subject", ""),
        "grade": data.get("grade", ""),
        "competencies_summary": data.get("competencies_summary", ""),
    }
    api_key = data.get("api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    ai_provider = data.get("ai_provider", "anthropic")

    content, error = generate_rpms_ppst(lesson_plan, lesson_context, api_key, ai_provider)
    if error:
        return jsonify({"error": error}), 400

    return jsonify({"content": content})


@app.route("/api/regenerate-section", methods=["POST"])
@login_required
def api_regenerate_section():
    """Regenerate a single section of a lesson plan."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    section_title = data.get("section_title", "").strip()
    section_content = data.get("section_content", "").strip()
    if not section_title or not section_content:
        return jsonify({"error": "section_title and section_content are required"}), 400

    lesson_context = data.get("lesson_context", {})
    instruction = data.get("instruction", "").strip() or "Improve this section"
    api_key = data.get("api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    ai_provider = data.get("ai_provider", "anthropic")

    content, error = regenerate_section(
        section_title, section_content, lesson_context, instruction, api_key, ai_provider
    )
    if error:
        return jsonify({"error": error}), 400

    return jsonify({"content": content})


@app.route("/activities")
@login_required
def activities():
    """Interactive activities page."""
    return render_template("activities.html")


@app.route("/api/generate-activity-content", methods=["POST"])
@login_required
def api_generate_activity_content():
    """Extract structured game content from lesson/quiz markdown."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    lesson_md = data.get("lesson_md", "").strip()
    quiz_md = data.get("quiz_md", "").strip()
    if not lesson_md:
        return jsonify({"error": "lesson_md is required"}), 400

    api_key = data.get("api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    ai_provider = data.get("ai_provider", "anthropic")

    content, error = _gen_activity_content(lesson_md, quiz_md, api_key, ai_provider)
    if error:
        return jsonify({"error": error}), 400

    return jsonify(content)


@app.route("/api/download-pptx", methods=["POST"])
@login_required
def api_download_pptx():
    """Generate and download a SKOOLED-AI branded .pptx lesson plan."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    lesson_md = data.get("lesson_md", "").strip()
    if not lesson_md:
        return jsonify({"error": "lesson_md is required"}), 400

    title = data.get("title", "Lesson Plan")
    safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", title)[:50]

    buf = build_pptx(lesson_md)
    _log_activity("download_pptx", title)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        as_attachment=True,
        download_name=f"LessonPlan_{safe_title}.pptx",
    )


@app.route("/syllabus")
@login_required
def syllabus():
    """Syllabus generator page for SHS and College level."""
    return render_template("syllabus.html")


@app.route("/syllabi")
@login_required
def syllabi_dashboard():
    """Dashboard: shows current user's syllabi (admin sees all)."""
    is_admin = session.get("user_role") == "admin"
    return render_template("syllabi_dashboard.html", is_admin=is_admin)


@app.route("/api/generate-syllabus", methods=["POST"])
@login_required
def api_generate_syllabus():
    """Generate an OBE-aligned course syllabus."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    course_title = data.get("course_title", "").strip()
    if not course_title:
        return jsonify({"error": "Course title is required"}), 400

    config = {
        "institution_type": data.get("institution_type", "college"),
        "school_name": data.get("school_name", ""),
        "college_dept": data.get("college_dept", ""),
        "program": data.get("program", ""),
        "course_code": data.get("course_code", ""),
        "course_title": course_title,
        "credits": data.get("credits", "3 units"),
        "prerequisites": data.get("prerequisites", "None"),
        "course_type": data.get("course_type", "Core"),
        "semester": data.get("semester", ""),
        "num_weeks": int(data.get("num_weeks", 14)),
        "course_description": data.get("course_description", ""),
        "program_outcomes": data.get("program_outcomes", ""),
        "course_outcomes": data.get("course_outcomes", ""),
        "grading": data.get("grading", {"Activities": 30, "Projects": 30, "Final Project": 40}),
    }

    use_ai = data.get("use_ai", False)
    api_key = data.get("api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
    ai_provider = data.get("ai_provider", "anthropic")

    syllabus_dict, warning = _gen_syllabus(
        config,
        api_key=api_key if use_ai else "",
        ai_provider=ai_provider,
    )

    if syllabus_dict is None:
        return jsonify({"error": warning or "Syllabus generation failed"}), 500

    _log_activity(
        "syllabus_generate",
        course_title,
        subject=data.get("program", ""),
        grade=data.get("institution_type", "college"),
    )

    response = {"syllabus": syllabus_dict}
    if warning:
        response["warning"] = warning
    return jsonify(response)


@app.route("/api/save-lesson-plan", methods=["POST"])
@login_required
def api_save_lesson_plan():
    """Save a lesson plan to the DB and return a token."""
    from auth import get_db
    data = request.get_json()
    if not data or not data.get("lesson_md"):
        return jsonify({"error": "No lesson plan content provided"}), 400

    token = uuid.uuid4().hex
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO lesson_plans
                   (token, owner_id, owner_name, title, subject, grade, quarter,
                    gen_mode, lesson_md, quiz_md, assessment_md)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    token,
                    session["user_id"],
                    session.get("user_name", ""),
                    data.get("title", "Untitled Lesson Plan"),
                    data.get("subject", ""),
                    data.get("grade", ""),
                    data.get("quarter", ""),
                    data.get("gen_mode", ""),
                    data["lesson_md"],
                    data.get("quiz_md", ""),
                    data.get("assessment_md", ""),
                ),
            )
    finally:
        conn.close()

    _log_activity("lesson_plan_save", data.get("title", ""), subject=data.get("subject", ""), grade=data.get("grade", ""))
    return jsonify({"token": token})


@app.route("/api/my-lesson-plans")
@login_required
def api_my_lesson_plans():
    """Return the current user's saved lesson plans (admin sees all)."""
    from auth import get_db
    conn = get_db()
    is_admin = session.get("user_role") == "admin"
    try:
        with conn.cursor() as cur:
            if is_admin:
                cur.execute(
                    """SELECT token, title, subject, grade, quarter, gen_mode,
                              created_at, updated_at, owner_name, owner_id
                       FROM lesson_plans
                       ORDER BY COALESCE(updated_at, created_at) DESC
                       LIMIT 200"""
                )
            else:
                cur.execute(
                    """SELECT token, title, subject, grade, quarter, gen_mode,
                              created_at, updated_at, owner_name, owner_id
                       FROM lesson_plans
                       WHERE owner_id = %s
                       ORDER BY COALESCE(updated_at, created_at) DESC
                       LIMIT 50""",
                    (session["user_id"],),
                )
            rows = cur.fetchall()
    finally:
        conn.close()

    current_uid = session["user_id"]
    result = []
    for r in rows:
        result.append({
            "token":      r["token"],
            "title":      r["title"] or "Untitled",
            "subject":    r["subject"] or "",
            "grade":      r["grade"] or "",
            "quarter":    r["quarter"] or "",
            "gen_mode":   r["gen_mode"] or "",
            "owner_name": r["owner_name"] or "",
            "is_owner":   r["owner_id"] == current_uid,
            "created_at": r["created_at"].isoformat() if r["created_at"] else "",
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else "",
        })
    return jsonify(result)


@app.route("/api/load-lesson-plan/<token>")
@login_required
def api_load_lesson_plan(token):
    """Load a saved lesson plan. Owner or admin only."""
    from auth import get_db
    conn = get_db()
    is_admin = session.get("user_role") == "admin"
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM lesson_plans WHERE token = %s", (token,)
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return jsonify({"error": "Not found"}), 404
    if not is_admin and row["owner_id"] != session["user_id"]:
        return jsonify({"error": "Access denied"}), 403

    return jsonify({
        "token":          row["token"],
        "title":          row["title"] or "",
        "subject":        row["subject"] or "",
        "grade":          row["grade"] or "",
        "quarter":        row["quarter"] or "",
        "gen_mode":       row["gen_mode"] or "",
        "lesson_md":      row["lesson_md"] or "",
        "quiz_md":        row["quiz_md"] or "",
        "assessment_md":  row["assessment_md"] or "",
        "created_at":     row["created_at"].isoformat() if row["created_at"] else "",
    })


@app.route("/api/delete-lesson-plan/<token>", methods=["DELETE"])
@login_required
def api_delete_lesson_plan(token):
    """Delete a saved lesson plan. Owner or admin only."""
    from auth import get_db
    conn = get_db()
    is_admin = session.get("user_role") == "admin"
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT owner_id FROM lesson_plans WHERE token = %s", (token,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Not found"}), 404
            if not is_admin and row["owner_id"] != session["user_id"]:
                return jsonify({"error": "Access denied"}), 403
            cur.execute("DELETE FROM lesson_plans WHERE token = %s", (token,))
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/save-syllabus", methods=["POST"])
@login_required
def api_save_syllabus():
    """Save a syllabus to the DB and return a public shareable URL."""
    from auth import get_db
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    syllabus = data.get("syllabus")
    if not syllabus:
        return jsonify({"error": "No syllabus content provided"}), 400

    token = uuid.uuid4().hex
    course_title = syllabus.get("course_title", "Untitled Syllabus")

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO syllabi (token, owner_id, owner_name, course_title, syllabus_json, revision, revision_comment)
                   VALUES (%s, %s, %s, %s, %s, 1, '')""",
                (
                    token,
                    session.get("user_id", 0),
                    session.get("user_name", ""),
                    course_title,
                    json.dumps(syllabus),
                ),
            )
    finally:
        conn.close()

    share_url = url_for("syllabus_view", token=token, _external=True)
    _log_activity("syllabus_share", course_title, subject=syllabus.get("program", ""))
    return jsonify({"token": token, "url": share_url})


@app.route("/api/my-syllabi")
@login_required
def api_my_syllabi():
    """Return syllabi: current user's own, or all (admin)."""
    from auth import get_db
    conn = get_db()
    is_admin = session.get("user_role") == "admin"
    try:
        with conn.cursor() as cur:
            if is_admin:
                cur.execute(
                    """SELECT token, course_title, revision, revision_comment,
                              created_at, updated_at, owner_name, owner_id
                       FROM syllabi
                       ORDER BY COALESCE(updated_at, created_at) DESC
                       LIMIT 200"""
                )
            else:
                cur.execute(
                    """SELECT token, course_title, revision, revision_comment,
                              created_at, updated_at, owner_name, owner_id
                       FROM syllabi
                       WHERE owner_id = %s
                       ORDER BY COALESCE(updated_at, created_at) DESC
                       LIMIT 50""",
                    (session["user_id"],),
                )
            rows = cur.fetchall()
    finally:
        conn.close()

    current_uid = session["user_id"]
    result = []
    for r in rows:
        result.append({
            "token": r["token"],
            "course_title": r["course_title"] or "Untitled",
            "revision": r["revision"] or 1,
            "revision_comment": r["revision_comment"] or "",
            "owner_name": r["owner_name"] or "",
            "is_owner": r["owner_id"] == current_uid,
            "created_at": r["created_at"].isoformat() if r["created_at"] else "",
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else "",
        })
    return jsonify(result)


@app.route("/api/load-syllabus/<token>")
@login_required
def api_load_syllabus(token):
    """Load a syllabus for editing (owner or admin)."""
    from auth import get_db
    conn = get_db()
    is_admin = session.get("user_role") == "admin"
    try:
        with conn.cursor() as cur:
            if is_admin:
                cur.execute(
                    """SELECT token, syllabus_json, revision, revision_comment, updated_at
                       FROM syllabi WHERE token = %s""",
                    (token,),
                )
            else:
                cur.execute(
                    """SELECT token, syllabus_json, revision, revision_comment, updated_at
                       FROM syllabi WHERE token = %s AND owner_id = %s""",
                    (token, session["user_id"]),
                )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return jsonify({"error": "Not found or not authorized"}), 404

    return jsonify({
        "token": row["token"],
        "syllabus": json.loads(row["syllabus_json"]),
        "revision": row["revision"] or 1,
        "revision_comment": row["revision_comment"] or "",
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else "",
    })


@app.route("/api/update-syllabus/<token>", methods=["POST"])
@login_required
def api_update_syllabus(token):
    """Update an existing syllabus and archive the previous version."""
    from auth import get_db
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    syllabus = data.get("syllabus")
    comment = data.get("comment", "")
    if not syllabus:
        return jsonify({"error": "No syllabus content provided"}), 400

    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Verify ownership (admin can edit any)
            is_admin = session.get("user_role") == "admin"
            if is_admin:
                cur.execute(
                    "SELECT id, syllabus_json, revision FROM syllabi WHERE token = %s",
                    (token,),
                )
            else:
                cur.execute(
                    "SELECT id, syllabus_json, revision FROM syllabi WHERE token = %s AND owner_id = %s",
                    (token, session["user_id"]),
                )
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Not found or not authorized"}), 404

            old_revision = row["revision"] or 1
            old_json = row["syllabus_json"]

            # Archive the old version
            cur.execute(
                """INSERT INTO syllabus_revisions
                   (syllabus_token, revision, syllabus_json, comment, revised_by)
                   VALUES (%s, %s, %s, %s, %s)""",
                (token, old_revision, old_json, comment, session.get("user_name", "")),
            )

            # Update the current record
            course_title = syllabus.get("course_title", "Untitled Syllabus")
            new_revision = old_revision + 1
            cur.execute(
                """UPDATE syllabi
                   SET syllabus_json = %s, course_title = %s,
                       revision = %s, revision_comment = %s,
                       updated_at = NOW()
                   WHERE token = %s""",
                (
                    json.dumps(syllabus), course_title,
                    new_revision, comment,
                    token,
                ),
            )
    finally:
        conn.close()

    share_url = url_for("syllabus_view", token=token, _external=True)
    _log_activity("syllabus_update", f"Rev {new_revision}: {comment or '(no comment)'}",
                  subject=syllabus.get("program", ""))
    return jsonify({"token": token, "url": share_url, "revision": new_revision})


@app.route("/api/delete-syllabus/<token>", methods=["DELETE"])
@login_required
def api_delete_syllabus(token):
    """Delete a syllabus (owner or admin only)."""
    from auth import get_db
    conn = get_db()
    is_admin = session.get("user_role") == "admin"
    try:
        with conn.cursor() as cur:
            if is_admin:
                cur.execute("DELETE FROM syllabi WHERE token = %s", (token,))
            else:
                cur.execute(
                    "DELETE FROM syllabi WHERE token = %s AND owner_id = %s",
                    (token, session["user_id"]),
                )
            deleted = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    if not deleted:
        return jsonify({"error": "Not found or not authorized"}), 404
    return jsonify({"ok": True})


@app.route("/syllabus/view/<token>")
@login_required
def syllabus_view(token):
    """Restricted syllabus view: owner, admin, or explicitly invited email only."""
    from auth import get_db
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT syllabus_json, course_title, owner_id FROM syllabi WHERE token = %s",
                (token,),
            )
            row = cur.fetchone()
            if not row:
                return render_template("syllabus_view.html", syllabus=None,
                                       course_title=None, can_edit=False,
                                       can_manage=False, syllabus_token=None,
                                       error="Syllabus not found or link has expired.")

            uid        = session.get("user_id")
            user_email = session.get("user_email", "").lower().strip()
            is_admin   = session.get("user_role") == "admin"
            is_owner   = uid == row["owner_id"]
            can_edit   = is_owner or is_admin
            can_manage = can_edit  # only owner/admin can manage shares

            if not can_edit:
                # Check if this user's email was explicitly invited
                cur.execute(
                    "SELECT id FROM syllabus_shares WHERE syllabus_token = %s AND shared_email = %s",
                    (token, user_email),
                )
                can_view = bool(cur.fetchone())
            else:
                can_view = True
    finally:
        conn.close()

    if not can_view:
        return render_template("syllabus_view.html", syllabus=None,
                               course_title=None, can_edit=False,
                               can_manage=False, syllabus_token=None,
                               error="You don't have access to this syllabus. Ask the owner to share it with your email address.")

    syllabus = json.loads(row["syllabus_json"])
    return render_template("syllabus_view.html", syllabus=syllabus,
                           course_title=row["course_title"], error=None,
                           can_edit=can_edit, can_manage=can_manage,
                           syllabus_token=token)


# ── Syllabus share management ──────────────────────────────

@app.route("/api/syllabus-shares/<token>")
@login_required
def api_list_syllabus_shares(token):
    """List emails that have been granted access to a syllabus."""
    from auth import get_db
    conn = get_db()
    is_admin = session.get("user_role") == "admin"
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT owner_id FROM syllabi WHERE token = %s", (token,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Not found"}), 404
            if not is_admin and row["owner_id"] != session["user_id"]:
                return jsonify({"error": "Access denied"}), 403
            cur.execute(
                "SELECT shared_email, created_at FROM syllabus_shares WHERE syllabus_token = %s ORDER BY created_at ASC",
                (token,),
            )
            shares = [{"email": r["shared_email"],
                       "created_at": r["created_at"].isoformat() if r["created_at"] else ""}
                      for r in cur.fetchall()]
    finally:
        conn.close()
    return jsonify(shares)


@app.route("/api/syllabus-shares/<token>", methods=["POST"])
@login_required
def api_add_syllabus_share(token):
    """Grant a specific email access to view a syllabus."""
    from auth import get_db
    data = request.get_json()
    email = (data or {}).get("email", "").lower().strip()
    if not email or "@" not in email:
        return jsonify({"error": "Valid email required"}), 400

    conn = get_db()
    is_admin = session.get("user_role") == "admin"
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT owner_id FROM syllabi WHERE token = %s", (token,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Not found"}), 404
            if not is_admin and row["owner_id"] != session["user_id"]:
                return jsonify({"error": "Access denied"}), 403
            cur.execute(
                "INSERT IGNORE INTO syllabus_shares (syllabus_token, shared_email, shared_by_id) VALUES (%s, %s, %s)",
                (token, email, session["user_id"]),
            )
    finally:
        conn.close()
    _log_activity("syllabus_share_add", email)
    return jsonify({"ok": True, "email": email})


@app.route("/api/syllabus-shares/<token>/<path:email>", methods=["DELETE"])
@login_required
def api_remove_syllabus_share(token, email):
    """Remove a specific email's access to a syllabus."""
    from auth import get_db
    email = email.lower().strip()
    conn = get_db()
    is_admin = session.get("user_role") == "admin"
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT owner_id FROM syllabi WHERE token = %s", (token,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Not found"}), 404
            if not is_admin and row["owner_id"] != session["user_id"]:
                return jsonify({"error": "Access denied"}), 403
            cur.execute(
                "DELETE FROM syllabus_shares WHERE syllabus_token = %s AND shared_email = %s",
                (token, email),
            )
    finally:
        conn.close()
    return jsonify({"ok": True})


# ── Rubric library routes ──────────────────────────────

@app.route("/api/rubrics")
@login_required
def api_list_rubrics():
    """List all rubrics (community library — all users see all)."""
    from auth import get_db
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT token, owner_name, name, description, rubric_json
                FROM rubrics
                ORDER BY created_at DESC
                LIMIT 100
            """)
            rows = cur.fetchall()
    finally:
        conn.close()
    results = []
    for r in rows:
        try:
            rj = json.loads(r["rubric_json"])
        except Exception:
            rj = {}
        results.append({
            "token": r["token"],
            "owner_name": r["owner_name"],
            "name": r["name"],
            "description": r["description"] or "",
            "criteria_count": len(rj.get("criteria", [])),
            "level_count": len(rj.get("levels", [])),
        })
    return jsonify(results)


@app.route("/api/rubrics", methods=["POST"])
@login_required
def api_save_rubric():
    """Save a rubric to the shared library."""
    import secrets as _sec
    from auth import get_db
    data = request.get_json()
    rub = data.get("rubric", {})
    name = (rub.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Rubric name is required"}), 400
    description = (rub.get("description") or "").strip()
    owner_id = session["user_id"]
    owner_name = session.get("user_name") or session.get("user_email", "")
    token = _sec.token_hex(16)
    rubric_json = json.dumps(rub)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO rubrics (token, owner_id, owner_name, name, description, rubric_json)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (token, owner_id, owner_name, name, description, rubric_json))
        conn.commit()
    finally:
        conn.close()
    _log_activity("rubric_save", name)
    return jsonify({"token": token, "name": name})


@app.route("/api/rubrics/<token>")
@login_required
def api_get_rubric(token):
    """Get full rubric data by token."""
    from auth import get_db
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT token, owner_name, name, description, rubric_json FROM rubrics WHERE token = %s",
                (token,)
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    try:
        rj = json.loads(row["rubric_json"])
    except Exception:
        rj = {}
    return jsonify({
        "token": row["token"],
        "name": row["name"],
        "description": row["description"] or "",
        "owner_name": row["owner_name"],
        "rubric": rj,
    })


@app.route("/api/rubrics/<token>", methods=["DELETE"])
@login_required
def api_delete_rubric(token):
    """Delete a rubric (owner or admin only)."""
    from auth import get_db
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT owner_id FROM rubrics WHERE token = %s", (token,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Not found"}), 404
            if row["owner_id"] != session["user_id"] and not session.get("is_admin"):
                return jsonify({"error": "Access denied"}), 403
            cur.execute("DELETE FROM rubrics WHERE token = %s", (token,))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8080)
