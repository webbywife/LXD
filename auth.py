"""
Authentication module for SKOOLED-AI Lesson Plan Generator.
MySQL-backed user auth with signed URL tokens.
Cloudways Nginx strips Cookie headers, so we pass auth via URL tokens.
"""

import os
import secrets
import functools
import pymysql
from flask import Blueprint, request, session, redirect, url_for, render_template, flash, jsonify, g, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer

auth_bp = Blueprint("auth", __name__)

# MySQL connection settings from environment
DB_HOST = os.environ.get("MYSQL_HOST", "localhost")
DB_USER = os.environ.get("MYSQL_USER", "muwrnbjezq")
DB_PASS = os.environ.get("MYSQL_PASS", "")
DB_NAME = os.environ.get("MYSQL_DB", "muwrnbjezq")


def get_db():
    """Get a MySQL database connection."""
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def init_db():
    """Create database tables if they don't exist."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    name VARCHAR(255) NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role ENUM('user', 'admin') DEFAULT 'user',
                    status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS lesson_ratings (
                    id           INT AUTO_INCREMENT PRIMARY KEY,
                    user_id      INT NOT NULL,
                    user_name    VARCHAR(255) NOT NULL,
                    rating       TINYINT NOT NULL,
                    comment      TEXT,
                    subject      VARCHAR(255),
                    grade        VARCHAR(100),
                    quarter      VARCHAR(100),
                    lesson_title VARCHAR(500),
                    gen_mode     ENUM('curriculum','topic') DEFAULT 'curriculum',
                    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS syllabi (
                    id            INT AUTO_INCREMENT PRIMARY KEY,
                    token         VARCHAR(64) NOT NULL UNIQUE,
                    owner_id      INT NOT NULL,
                    owner_name    VARCHAR(255),
                    course_title  VARCHAR(500),
                    syllabus_json LONGTEXT NOT NULL,
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_syl_token (token),
                    INDEX idx_syl_owner (owner_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # Migrate syllabi — add new columns if not exist
            for sql in [
                "ALTER TABLE syllabi ADD COLUMN revision INT NOT NULL DEFAULT 1",
                "ALTER TABLE syllabi ADD COLUMN revision_comment TEXT",
                "ALTER TABLE syllabi ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
            ]:
                try: cur.execute(sql)
                except Exception: pass  # already exists

            # Revision history table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS syllabus_revisions (
                    id             INT AUTO_INCREMENT PRIMARY KEY,
                    syllabus_token VARCHAR(64) NOT NULL,
                    revision       INT NOT NULL,
                    syllabus_json  LONGTEXT NOT NULL,
                    comment        TEXT,
                    revised_by     VARCHAR(255),
                    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_srev_token (syllabus_token)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS syllabus_shares (
                    id             INT AUTO_INCREMENT PRIMARY KEY,
                    syllabus_token VARCHAR(64) NOT NULL,
                    shared_email   VARCHAR(255) NOT NULL,
                    shared_by_id   INT NOT NULL,
                    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_share (syllabus_token, shared_email),
                    INDEX idx_share_token (syllabus_token),
                    INDEX idx_share_email (shared_email)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS rubrics (
                    id           INT AUTO_INCREMENT PRIMARY KEY,
                    token        VARCHAR(64) NOT NULL UNIQUE,
                    owner_id     INT NOT NULL,
                    owner_name   VARCHAR(255),
                    name         VARCHAR(500) NOT NULL,
                    description  TEXT,
                    rubric_json  LONGTEXT NOT NULL,
                    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_rub_token (token),
                    INDEX idx_rub_owner (owner_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS saved_activities (
                    id            INT AUTO_INCREMENT PRIMARY KEY,
                    token         VARCHAR(64) NOT NULL UNIQUE,
                    owner_id      INT NOT NULL,
                    owner_name    VARCHAR(255),
                    title         VARCHAR(500),
                    subject       VARCHAR(255),
                    grade         VARCHAR(50),
                    activity_json LONGTEXT NOT NULL,
                    lesson_md     LONGTEXT,
                    quiz_md       LONGTEXT,
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_act_token (token),
                    INDEX idx_act_owner (owner_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # Patch existing installs — add verification_token if missing
            try:
                cur.execute(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                    "verification_token VARCHAR(64) DEFAULT NULL"
                )
            except Exception:
                pass
            # Patch existing installs — add password reset columns if missing
            for sql in [
                "ALTER TABLE users ADD COLUMN reset_token VARCHAR(64) DEFAULT NULL",
                "ALTER TABLE users ADD COLUMN reset_token_expires DATETIME DEFAULT NULL",
            ]:
                try:
                    cur.execute(sql)
                except Exception:
                    pass  # already exists

            cur.execute("""
                CREATE TABLE IF NOT EXISTS lesson_plans (
                    id            INT AUTO_INCREMENT PRIMARY KEY,
                    token         VARCHAR(64) NOT NULL UNIQUE,
                    owner_id      INT NOT NULL,
                    owner_name    VARCHAR(255),
                    title         VARCHAR(500),
                    subject       VARCHAR(255),
                    grade         VARCHAR(50),
                    quarter       VARCHAR(50),
                    gen_mode      VARCHAR(50),
                    lesson_md     LONGTEXT NOT NULL,
                    quiz_md       LONGTEXT,
                    assessment_md LONGTEXT,
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_lp_token (token),
                    INDEX idx_lp_owner (owner_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS activity_log (
                    id          INT AUTO_INCREMENT PRIMARY KEY,
                    user_id     INT NOT NULL,
                    user_name   VARCHAR(255) NOT NULL,
                    action_type VARCHAR(60) NOT NULL,
                    detail      VARCHAR(500),
                    subject     VARCHAR(255),
                    grade       VARCHAR(100),
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_al_user (user_id),
                    INDEX idx_al_action (action_type),
                    INDEX idx_al_created (created_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
    finally:
        conn.close()


def _get_serializer():
    """Get the URL-safe timed serializer for auth tokens."""
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generate_auth_token(user_id, email, name, role):
    """Generate a signed auth token encoding user info (valid 24h)."""
    s = _get_serializer()
    return s.dumps({"uid": user_id, "email": email, "name": name, "role": role})


def verify_auth_token(token, max_age=86400):
    """Verify and decode an auth token. Returns user dict or None."""
    s = _get_serializer()
    try:
        return s.loads(token, max_age=max_age)
    except Exception:
        return None


def _token_redirect(endpoint, **kwargs):
    """Redirect to endpoint, carrying forward the auth token."""
    token = request.args.get("_t", "")
    url = url_for(endpoint, **kwargs)
    if token:
        url += ("&" if "?" in url else "?") + f"_t={token}"
    return redirect(url)


def login_required(f):
    """Decorator that requires an authenticated, approved user.
    API routes (/api/*) return JSON 401; page routes redirect to login.
    """
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required", "login": "/login"}), 401
            return redirect(url_for("auth.login", next=request.path))
        return f(*args, **kwargs)
    return wrapped


def admin_required(f):
    """Decorator that requires an admin user."""
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login", next=request.path))
        if session.get("user_role") != "admin":
            flash("Admin access required.", "error")
            return _token_redirect("generator")
        return f(*args, **kwargs)
    return wrapped


def send_email(to_email, subject, html_body):
    """Send a transactional email via SMTP. Silently skips if SMTP not configured."""
    import smtplib, ssl
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    server   = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    port     = int(os.environ.get("MAIL_PORT", "587"))
    username = os.environ.get("MAIL_USERNAME", "")
    password = os.environ.get("MAIL_PASSWORD", "")
    frm      = os.environ.get("MAIL_FROM", f"SKOOLED-AI <{username}>")
    if not username or not password:
        print(f"[email] SMTP not configured — skipping to {to_email}")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = frm
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(server, port) as s:
            s.ehlo(); s.starttls(context=ctx); s.login(username, password)
            s.sendmail(username, to_email, msg.as_string())
    except Exception as e:
        print(f"[email] Failed to send to {to_email}: {e}")


# ── Routes ──────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("generator"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("login.html")

        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE email = %s", (email,))
                user = cur.fetchone()
        finally:
            conn.close()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        if user.get("verification_token"):
            flash("Please verify your email first. Check your inbox.", "warning")
            return render_template("login.html")

        if user["status"] == "pending":
            flash("Your account is pending admin approval.", "warning")
            return render_template("login.html")

        if user["status"] == "rejected":
            flash("Your account has been rejected.", "error")
            return render_template("login.html")

        # Login successful — generate auth token for URL-based session
        session["user_id"] = user["id"]
        session["user_email"] = user["email"]
        session["user_name"] = user["name"]
        session["user_role"] = user["role"]

        token = generate_auth_token(user["id"], user["email"], user["name"], user["role"])
        next_url = request.args.get("next") or request.form.get("next") or url_for("generator")
        next_url += ("&" if "?" in next_url else "?") + f"_t={token}"
        return redirect(next_url)

    return render_template("login.html")


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return redirect(url_for("generator"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        errors = []
        if not name:
            errors.append("Name is required.")
        if not email:
            errors.append("Email is required.")
        if not password or len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("signup.html", name=name, email=email)

        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE email = %s", (email,))
                if cur.fetchone():
                    flash("An account with this email already exists.", "error")
                    return render_template("signup.html", name=name, email=email)

                # Check if this is the first user — make them admin + approved
                cur.execute("SELECT COUNT(*) AS cnt FROM users")
                count = cur.fetchone()["cnt"]

                role = "admin" if count == 0 else "user"
                status = "approved" if count == 0 else "pending"
                vtok = None if count == 0 else secrets.token_urlsafe(32)

                cur.execute(
                    "INSERT INTO users (email, name, password_hash, role, status, verification_token) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (email, name, generate_password_hash(password), role, status, vtok),
                )
        finally:
            conn.close()

        if status == "approved":
            flash("Admin account created! You can now log in.", "success")
        else:
            # Send verification email
            verify_url = url_for("auth.verify_email", token=vtok, _external=True)
            send_email(
                email,
                "Verify your email — SKOOLED-AI",
                f"""
                <div style="font-family:sans-serif;max-width:560px;margin:auto;padding:32px;">
                  <h2 style="color:#1e293b;margin-bottom:8px;">Welcome to SKOOLED-AI, {name}!</h2>
                  <p style="color:#475569;">Please verify your email address to continue.</p>
                  <p style="color:#475569;">After verifying, an admin will review and approve your account.</p>
                  <a href="{verify_url}"
                     style="display:inline-block;margin:24px 0;padding:12px 28px;
                            background:#4f46e5;color:#fff;text-decoration:none;
                            border-radius:6px;font-weight:600;">
                    Verify My Email
                  </a>
                  <p style="color:#94a3b8;font-size:12px;">
                    If you didn't create an account, you can ignore this email.<br>
                    This link will remain valid until used.
                  </p>
                </div>
                """,
            )
            flash("Account created! Please check your email to verify your address.", "success")
        return redirect(url_for("auth.login"))

    return render_template("signup.html")


@auth_bp.route("/verify-email/<token>")
def verify_email(token):
    """Confirm a user's email address via the token sent at signup."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE verification_token = %s", (token,))
            user = cur.fetchone()
            if not user:
                flash("Invalid or expired verification link.", "error")
                return redirect(url_for("auth.login"))
            cur.execute(
                "UPDATE users SET verification_token = NULL WHERE id = %s",
                (user["id"],),
            )
    finally:
        conn.close()
    flash("Email verified! Your account is pending admin approval.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        from datetime import datetime, timedelta
        email = request.form.get("email", "").strip().lower()
        if email:
            conn = get_db()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, name FROM users WHERE email=%s AND status='approved'",
                        (email,),
                    )
                    user = cur.fetchone()
                    if user:
                        token = secrets.token_urlsafe(32)
                        expires = datetime.utcnow() + timedelta(hours=1)
                        cur.execute(
                            "UPDATE users SET reset_token=%s, reset_token_expires=%s WHERE id=%s",
                            (token, expires, user["id"]),
                        )
                        reset_url = url_for("auth.reset_password", token=token, _external=True)
                        send_email(
                            email,
                            "Reset your password — SKOOLED-AI",
                            f"""
                            <div style="font-family:sans-serif;max-width:560px;margin:auto;padding:32px;">
                              <h2 style="color:#1e293b;margin-bottom:8px;">Reset your password</h2>
                              <p style="color:#475569;">Hi {user['name']}, we received a request to reset your SKOOLED-AI password.</p>
                              <p style="color:#475569;">Click the button below to choose a new password. This link expires in 1 hour.</p>
                              <a href="{reset_url}"
                                 style="display:inline-block;margin:24px 0;padding:12px 28px;
                                        background:#4f46e5;color:#fff;text-decoration:none;
                                        border-radius:6px;font-weight:600;">
                                Reset My Password
                              </a>
                              <p style="color:#94a3b8;font-size:12px;">
                                If you didn't request a password reset, you can safely ignore this email.<br>
                                Your password will not change until you click the link above.
                              </p>
                            </div>
                            """,
                        )
            finally:
                conn.close()
        # Always show same message to prevent email enumeration
        flash("If that email is registered and active, we've sent a reset link. Check your inbox.", "success")
        return redirect(url_for("auth.forgot_password"))
    return render_template("forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    from datetime import datetime
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, reset_token_expires FROM users WHERE reset_token=%s",
                (token,),
            )
            user = cur.fetchone()
    finally:
        conn.close()

    if not user or not user["reset_token_expires"] or user["reset_token_expires"] < datetime.utcnow():
        flash("This reset link has expired or is invalid. Please request a new one.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("reset_password.html", token=token)
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html", token=token)
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash=%s, reset_token=NULL, reset_token_expires=NULL WHERE id=%s",
                    (generate_password_hash(password), user["id"]),
                )
        finally:
            conn.close()
        flash("Password updated successfully. Please sign in with your new password.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html", token=token)


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))


# ── Admin Routes ────────────────────────────────────────────

@auth_bp.route("/admin")
@admin_required
def admin_panel():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, email, name, role, status, created_at FROM users ORDER BY created_at DESC")
            users = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS total FROM users")
            total = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) AS pending FROM users WHERE status = 'pending'")
            pending = cur.fetchone()["pending"]
            cur.execute("SELECT COUNT(*) AS approved FROM users WHERE status = 'approved'")
            approved = cur.fetchone()["approved"]
            cur.execute("SELECT COUNT(*) AS admins FROM users WHERE role = 'admin'")
            admins = cur.fetchone()["admins"]
    finally:
        conn.close()

    stats = {"total": total, "pending": pending, "approved": approved, "admins": admins}

    rating_stats = {"total_ratings": 0, "avg_rating": 0}
    ratings = []
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM lesson_ratings")
            rating_stats["total_ratings"] = cur.fetchone()["cnt"]
            cur.execute("SELECT AVG(rating) AS avg FROM lesson_ratings")
            avg = cur.fetchone()["avg"]
            rating_stats["avg_rating"] = round(float(avg), 1) if avg else 0
            cur.execute(
                "SELECT id, user_name, rating, comment, subject, grade, quarter, "
                "lesson_title, gen_mode, created_at FROM lesson_ratings "
                "ORDER BY created_at DESC LIMIT 100"
            )
            ratings = cur.fetchall()
        conn.close()
    except Exception:
        pass

    activity_stats = {"total": 0, "generations": 0, "downloads": 0, "by_type": {}}
    activity_log = []
    user_activity = []
    try:
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM activity_log")
            activity_stats["total"] = cur.fetchone()["cnt"]
            cur.execute("""SELECT COUNT(*) AS cnt FROM activity_log
                WHERE action_type IN ('lesson_generate','topic_generate',
                    'assessment_generate','quiz_generate','syllabus_generate')""")
            activity_stats["generations"] = cur.fetchone()["cnt"]
            cur.execute("""SELECT COUNT(*) AS cnt FROM activity_log
                WHERE action_type IN ('download_pptx','download_scorm',
                    'download_gift','download_qti')""")
            activity_stats["downloads"] = cur.fetchone()["cnt"]
            cur.execute("""SELECT action_type, COUNT(*) AS cnt
                FROM activity_log GROUP BY action_type ORDER BY cnt DESC""")
            activity_stats["by_type"] = {r["action_type"]: r["cnt"] for r in cur.fetchall()}
            cur.execute("""
                SELECT al.user_name, al.action_type, al.detail, al.subject, al.grade, al.created_at
                FROM activity_log al ORDER BY al.created_at DESC LIMIT 100
            """)
            activity_log = cur.fetchall()
            cur.execute("""
                SELECT user_name,
                    SUM(action_type IN ('lesson_generate','topic_generate',
                        'assessment_generate','quiz_generate','syllabus_generate')) AS generations,
                    SUM(action_type IN ('download_pptx','download_scorm',
                        'download_gift','download_qti')) AS downloads,
                    COUNT(*) AS total,
                    MAX(created_at) AS last_active
                FROM activity_log GROUP BY user_name ORDER BY total DESC LIMIT 30
            """)
            user_activity = cur.fetchall()
        conn.close()
    except Exception:
        pass

    return render_template("admin.html", users=users, stats=stats,
                           rating_stats=rating_stats, ratings=ratings,
                           activity_stats=activity_stats, activity_log=activity_log,
                           user_activity=user_activity)


@auth_bp.route("/admin/approve/<int:user_id>", methods=["POST"])
@admin_required
def admin_approve(user_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET status = 'approved' WHERE id = %s", (user_id,))
    finally:
        conn.close()
    flash("User approved.", "success")
    return _token_redirect("auth.admin_panel")


@auth_bp.route("/admin/reject/<int:user_id>", methods=["POST"])
@admin_required
def admin_reject(user_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET status = 'rejected' WHERE id = %s", (user_id,))
    finally:
        conn.close()
    flash("User rejected.", "success")
    return _token_redirect("auth.admin_panel")


@auth_bp.route("/admin/toggle-role/<int:user_id>", methods=["POST"])
@admin_required
def admin_toggle_role(user_id):
    if user_id == session.get("user_id"):
        flash("You cannot change your own role.", "error")
        return _token_redirect("auth.admin_panel")

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if user:
                new_role = "admin" if user["role"] == "user" else "user"
                cur.execute("UPDATE users SET role = %s WHERE id = %s", (new_role, user_id))
                flash(f"User role changed to {new_role}.", "success")
    finally:
        conn.close()
    return _token_redirect("auth.admin_panel")
