"""
Authentication module for MATATAG AI Lesson Plan Generator.
MySQL-backed user auth with Flask sessions.
"""

import os
import functools
import pymysql
from flask import Blueprint, request, session, redirect, url_for, render_template, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

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
    """Create users table if it doesn't exist."""
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
    finally:
        conn.close()


def login_required(f):
    """Decorator that requires an authenticated, approved user."""
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login", next=request.url))
        return f(*args, **kwargs)
    return wrapped


def admin_required(f):
    """Decorator that requires an admin user."""
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login", next=request.url))
        if session.get("user_role") != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("generator"))
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

        # Login successful
        session["user_id"] = user["id"]
        session["user_email"] = user["email"]
        session["user_name"] = user["name"]
        session["user_role"] = user["role"]

        next_url = request.args.get("next") or request.form.get("next") or url_for("generator")
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
    return render_template("admin.html", users=users, stats=stats)


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
    return redirect(url_for("auth.admin_panel"))


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
    return redirect(url_for("auth.admin_panel"))


@auth_bp.route("/admin/toggle-role/<int:user_id>", methods=["POST"])
@admin_required
def admin_toggle_role(user_id):
    if user_id == session.get("user_id"):
        flash("You cannot change your own role.", "error")
        return redirect(url_for("auth.admin_panel"))

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
    return redirect(url_for("auth.admin_panel"))
