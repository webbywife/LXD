"""
Authentication module for SKOOLED-AI Lesson Plan Generator.
MySQL-backed user auth with signed URL tokens.
Cloudways Nginx strips Cookie headers, so we pass auth via URL tokens.
"""

import os
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
    """Decorator that requires an authenticated, approved user."""
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
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

                cur.execute(
                    "INSERT INTO users (email, name, password_hash, role, status) VALUES (%s, %s, %s, %s, %s)",
                    (email, name, generate_password_hash(password), role, status),
                )
        finally:
            conn.close()

        if status == "approved":
            flash("Admin account created! You can now log in.", "success")
        else:
            flash("Account created! Please wait for admin approval.", "success")
        return redirect(url_for("auth.login"))

    return render_template("signup.html")


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
                    'assessment_generate','quiz_generate')""")
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
                        'assessment_generate','quiz_generate')) AS generations,
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
