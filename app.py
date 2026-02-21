"""
SKOOLED-AI Lesson Plan Generator - Standalone Web Application
DepEd-aligned lesson plan content generator based on MATATAG Curriculum.
"""

import os
import re
import json
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
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        as_attachment=True,
        download_name=f"LessonPlan_{safe_title}.pptx",
    )


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8080)
