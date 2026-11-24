"""Boa Safra license panel.

Issues per-machine serials, answers the clients' activation and validation
requests with statuses signed by the panel's Ed25519 key, and keeps the
customers' brands, from which it can start a white-label installer build.
"""

import os
import secrets
from pathlib import Path

from flask import Flask

from . import db, keys


def _secret_key(data_dir: Path) -> str:
    env = os.environ.get("PANEL_SECRET_KEY", "").strip()
    if env:
        return env
    path = data_dir / "secret_key"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48))
        path.chmod(0o600)
    return path.read_text().strip()


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    data_dir = Path(os.environ.get("PANEL_DATA_DIR", "/data"))
    app.config.update(
        DATA_DIR=data_dir,
        DATABASE=str(data_dir / "panel.sqlite3"),
        # The address clients and the build runners reach the panel at, e.g.
        # https://licencas.example.com. Baked into brand builds.
        PUBLIC_URL=os.environ.get("PANEL_PUBLIC_URL", "").rstrip("/"),
        ADMIN_USER=os.environ.get("PANEL_ADMIN_USER", "admin"),
        ADMIN_PASSWORD=os.environ.get("PANEL_ADMIN_PASSWORD", ""),
        TIMEZONE=os.environ.get("PANEL_TZ", "America/Sao_Paulo"),
        DEFAULT_VALIDITY_DAYS=int(os.environ.get("PANEL_VALIDITY_DAYS", "365")),
        GITHUB_REPO=os.environ.get("GITHUB_REPO", ""),
        GITHUB_TOKEN=os.environ.get("GITHUB_TOKEN", ""),
        GITHUB_REF=os.environ.get("GITHUB_REF", "master"),
        GITHUB_WORKFLOW=os.environ.get("GITHUB_WORKFLOW", "brand-build.yml"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("PANEL_SECURE_COOKIES", "1") == "1",
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    )
    if config:
        app.config.update(config)
    proxies = int(os.environ.get("PANEL_TRUSTED_PROXIES", "0"))
    if proxies:
        # Behind a reverse proxy, the client address the rate limits and the
        # logs use comes from X-Forwarded-For.
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies, x_host=proxies)
    data_dir = Path(app.config["DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    app.config.setdefault("SECRET_KEY", None)
    if not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = _secret_key(data_dir)

    db.init_app(app)
    keys.init_app(app)

    from . import api, brands, web

    app.register_blueprint(api.bp)
    app.register_blueprint(web.bp)
    app.register_blueprint(brands.bp)
    web.register_filters(app)
    return app
