"""
AI Sales Agent - Ecommerce
Flask app initialization. Models live in models.py, routes in routes.py,
email helper in mailer.py.

Runs anywhere — Replit, VS Code, plain Python — provided you set the
DATABASE_URL env var (or it falls back to a local SQLite file).
"""

import os
import logging

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv

base_dir = os.path.dirname(__file__)
load_dotenv(os.path.join(base_dir, ".env"))
print("DEBUG: SMTP_HOST =", repr(os.environ.get("SMTP_HOST")))  # DEBUG
logging.basicConfig(level=logging.INFO)


class Base(DeclarativeBase):
    pass


app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-change-me")
# Required so url_for() generates HTTPS links behind Replit's proxy.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Database — Postgres if DATABASE_URL is set, otherwise local SQLite.
db_url = os.environ.get("DATABASE_URL")
if db_url is None:
    sqlite_path = os.path.join(app.root_path, "instance", "users.db")
    db_url = f"sqlite:///{sqlite_path}"
elif db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
elif db_url.startswith("sqlite:///"):
    sqlite_path = db_url.replace("sqlite:///", "", 1)
    if not os.path.isabs(sqlite_path):
        sqlite_path = os.path.join(app.root_path, sqlite_path)
    db_url = f"sqlite:///{sqlite_path}"

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

# Make sure the SQLite directory exists for local file-based databases.
if db_url.startswith("sqlite:///"):
    sqlite_path = db_url.replace("sqlite:///", "", 1)
    sqlite_dir = os.path.dirname(sqlite_path)
    if sqlite_dir:
        os.makedirs(sqlite_dir, exist_ok=True)

# File-upload config for product images.
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB
UPLOAD_FOLDER = os.path.join(app.static_folder, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

db = SQLAlchemy(app, model_class=Base)

# Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."


@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(user_id)


# OAuth with Flask-Dance
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.contrib.github import make_github_blueprint, github

google_client_id = os.environ.get("GOOGLE_CLIENT_ID")
google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
if google_client_id and google_client_secret:
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    google_bp = make_google_blueprint(
        client_id=google_client_id,
        client_secret=google_client_secret,
        scope=["profile", "email"],
        redirect_to="google_login"
    )
    app.register_blueprint(google_bp, url_prefix="/login")
else:
    google = None

github_client_id = os.environ.get("GITHUB_CLIENT_ID")
github_client_secret = os.environ.get("GITHUB_CLIENT_SECRET")
if github_client_id and github_client_secret:
    github_bp = make_github_blueprint(
        client_id=github_client_id,
        client_secret=github_client_secret,
        scope=["user:email"],
        redirect_to="github_login"
    )
    app.register_blueprint(github_bp, url_prefix="/login")
else:
    github = None



def _ensure_columns():
    """Tiny safety-net migration: add columns introduced after first deploy."""
    inspector = inspect(db.engine)
    if "products" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("products")}
        if "cost_price" not in cols:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE products ADD COLUMN cost_price FLOAT DEFAULT 0"))
            logging.info("Added products.cost_price column")


# Create tables and apply tiny migrations.
with app.app_context():
    import models  # noqa: F401
    db.create_all()
    _ensure_columns()
    logging.info("Database tables created")
