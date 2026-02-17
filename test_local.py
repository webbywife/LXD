"""
Local test runner - bypasses MySQL auth for local browser testing.
Run: python3 test_local.py
Then open: http://localhost:8080/generator
"""
import os
os.environ["FLASK_SECRET_KEY"] = "test-secret-key-local"

# Monkey-patch auth to skip MySQL
import auth
auth._SKIP_MYSQL = True

_original_init_db = auth.init_db
def _noop_init_db():
    print("  [test] Skipping MySQL init_db")
auth.init_db = _noop_init_db

_original_login_required = auth.login_required
def _bypass_login_required(f):
    import functools
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        from flask import session
        session["user_id"] = 1
        session["user_email"] = "test@test.com"
        session["user_name"] = "Test User"
        session["user_role"] = "admin"
        return f(*args, **kwargs)
    return wrapper
auth.login_required = _bypass_login_required

# Now import and run the app
from app import app
app.secret_key = "test-secret-key-local"

print("\n" + "=" * 60)
print("  LOCAL TEST SERVER")
print("  Open: http://localhost:8080/generator")
print("  Auth is BYPASSED - you're auto-logged in as Test User")
print("=" * 60 + "\n")

app.run(debug=True, host="0.0.0.0", port=8080)
