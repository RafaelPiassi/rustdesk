"""The administration pages."""

import csv
import functools
import hmac
import io
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, keys, licensing
from .api import RateLimiter, client_ip

bp = Blueprint("web", __name__)
login_limiter = RateLimiter(limit=10, window=15 * 60)


# --- auth and CSRF ----------------------------------------------------------

def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            return redirect(url_for("web.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


@bp.before_app_request
def load_user_and_check_csrf():
    g.user = None
    uid = session.get("uid")
    if uid is not None:
        g.user = db.get().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    exempt = request.blueprint == "api" or (request.endpoint or "").endswith("build_pack")
    if request.method == "POST" and not exempt:
        sent = request.form.get("csrf", "")
        if not sent or not hmac.compare_digest(sent, session.get("csrf", "")):
            abort(400, "CSRF token inválido. Recarregue a página e tente novamente.")


def actor() -> str:
    return g.user["username"] if g.get("user") else ""


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if not login_limiter.allow(client_ip()):
            flash("Muitas tentativas. Aguarde alguns minutos.", "error")
            return render_template("login.html"), 429
        user = db.get().execute(
            "SELECT * FROM users WHERE username = ?", (request.form.get("username", ""),)
        ).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["uid"] = user["id"]
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("web.dashboard"))
        flash("Usuário ou senha incorretos.", "error")
    return render_template("login.html")


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("web.login"))


# --- dashboard --------------------------------------------------------------

def _licenses(where="1=1", params=()):
    rows = db.get().execute(
        "SELECT l.*, c.name AS customer FROM licenses l JOIN customers c ON c.id = l.customer_id"
        f" WHERE {where} ORDER BY l.created_at DESC",
        params,
    ).fetchall()
    now = db.now()
    return [dict(r, state=licensing.state(r, now)) for r in rows]


@bp.get("/")
@login_required
def dashboard():
    licenses = _licenses()
    counts = {k: 0 for k in licensing.STATE_LABELS}
    for lic in licenses:
        counts[lic["state"]] += 1
    expiring = sorted(
        (l for l in licenses if l["state"] in ("expiring", "expired")),
        key=lambda l: l["expires_at"] or 0,
    )[:15]
    events = db.get().execute(
        "SELECT e.*, l.serial FROM events e LEFT JOIN licenses l ON l.id = e.license_id"
        " ORDER BY e.at DESC LIMIT 15"
    ).fetchall()
    customers = db.get().execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    return render_template(
        "dashboard.html", counts=counts, expiring=expiring, events=events, customers=customers
    )


# --- customers --------------------------------------------------------------

def _brands():
    return db.get().execute("SELECT id, display_name FROM brands ORDER BY display_name").fetchall()


def _customer_form():
    f = request.form
    name = f.get("name", "").strip()
    if not name:
        flash("Informe o nome do cliente.", "error")
        return None
    brand_id = f.get("brand_id") or None
    return (
        name[:200],
        f.get("document", "").strip()[:40],
        f.get("email", "").strip()[:200],
        f.get("phone", "").strip()[:40],
        f.get("notes", "").strip()[:2000],
        int(brand_id) if brand_id else None,
    )


@bp.get("/customers")
@login_required
def customers():
    q = request.args.get("q", "").strip()
    rows = db.get().execute(
        "SELECT c.*, b.display_name AS brand,"
        " (SELECT COUNT(*) FROM licenses l WHERE l.customer_id = c.id) AS total"
        " FROM customers c LEFT JOIN brands b ON b.id = c.brand_id"
        " WHERE c.name LIKE ? OR c.document LIKE ? OR c.email LIKE ? ORDER BY c.name",
        (f"%{q}%", f"%{q}%", f"%{q}%"),
    ).fetchall()
    return render_template("customers.html", customers=rows, q=q, brands=_brands())


@bp.post("/customers")
@login_required
def customer_create():
    values = _customer_form()
    if values is None:
        return redirect(url_for("web.customers"))
    conn = db.get()
    cur = conn.execute(
        "INSERT INTO customers (name, document, email, phone, notes, brand_id, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (*values, db.now()),
    )
    db.log_event("customer_created", values[0], actor=actor())
    conn.commit()
    flash("Cliente cadastrado.", "ok")
    return redirect(url_for("web.customer", cid=cur.lastrowid))


def _get_customer(cid):
    row = db.get().execute(
        "SELECT c.*, b.display_name AS brand FROM customers c LEFT JOIN brands b ON b.id = c.brand_id"
        " WHERE c.id = ?",
        (cid,),
    ).fetchone()
    if row is None:
        abort(404)
    return row


@bp.get("/customers/<int:cid>")
@login_required
def customer(cid):
    return render_template(
        "customer.html",
        customer=_get_customer(cid),
        licenses=_licenses("l.customer_id = ?", (cid,)),
        brands=_brands(),
        default_days=current_app.config["DEFAULT_VALIDITY_DAYS"],
    )


@bp.post("/customers/<int:cid>")
@login_required
def customer_update(cid):
    _get_customer(cid)
    values = _customer_form()
    if values is not None:
        conn = db.get()
        conn.execute(
            "UPDATE customers SET name = ?, document = ?, email = ?, phone = ?, notes = ?, brand_id = ?"
            " WHERE id = ?",
            (*values, cid),
        )
        db.log_event("customer_updated", values[0], actor=actor())
        conn.commit()
        flash("Cliente atualizado.", "ok")
    return redirect(url_for("web.customer", cid=cid))


@bp.post("/customers/<int:cid>/delete")
@login_required
def customer_delete(cid):
    c = _get_customer(cid)
    conn = db.get()
    if conn.execute("SELECT 1 FROM licenses WHERE customer_id = ?", (cid,)).fetchone():
        flash("Exclua ou transfira as licenças do cliente antes de excluí-lo.", "error")
        return redirect(url_for("web.customer", cid=cid))
    conn.execute("DELETE FROM customers WHERE id = ?", (cid,))
    db.log_event("customer_deleted", c["name"], actor=actor())
    conn.commit()
    flash("Cliente excluído.", "ok")
    return redirect(url_for("web.customers"))


@bp.post("/customers/<int:cid>/licenses")
@login_required
def licenses_create(cid):
    _get_customer(cid)
    try:
        count = max(1, min(500, int(request.form.get("count", "1"))))
        days = max(1, min(3650, int(request.form.get("validity_days", "365"))))
    except ValueError:
        flash("Quantidade e validade devem ser números.", "error")
        return redirect(url_for("web.customer", cid=cid))
    start_now = request.form.get("start") == "now"
    serials = licensing.create_licenses(
        cid, count, days, start_now, request.form.get("notes", "").strip()[:500], actor()
    )
    flash(f"{len(serials)} serial(is) gerado(s): " + ", ".join(serials), "ok")
    return redirect(url_for("web.customer", cid=cid))


# --- licenses ---------------------------------------------------------------

@bp.get("/licenses")
@login_required
def licenses():
    q = request.args.get("q", "").strip()
    wanted = request.args.get("state", "")
    rows = _licenses(
        "(l.serial LIKE ? OR c.name LIKE ? OR l.hostname LIKE ? OR l.peer_id LIKE ?)",
        (f"%{q}%",) * 4,
    )
    if wanted:
        rows = [r for r in rows if r["state"] == wanted]
    if request.args.get("format") == "csv":
        return _csv(rows)
    return render_template("licenses.html", licenses=rows, q=q, wanted=wanted)


def _csv(rows):
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["serial", "cliente", "situacao", "ativada_em", "vence_em", "id", "computador",
                "sistema", "versao", "app", "ultimo_contato"])
    for r in rows:
        w.writerow([
            r["serial"], r["customer"], licensing.STATE_LABELS[r["state"]],
            fmt_time(r["activated_at"]), fmt_time(r["expires_at"]), r["peer_id"], r["hostname"],
            r["platform"], r["version"], r["app"], fmt_time(r["last_seen_at"]),
        ])
    return Response(
        "﻿" + out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=licencas.csv"},
    )


def _get_license(lid):
    rows = _licenses("l.id = ?", (lid,))
    if not rows:
        abort(404)
    return rows[0]


@bp.get("/licenses/<int:lid>")
@login_required
def license(lid):
    lic = _get_license(lid)
    events = db.get().execute(
        "SELECT * FROM events WHERE license_id = ? ORDER BY at DESC LIMIT 100", (lid,)
    ).fetchall()
    brand = db.get().execute(
        "SELECT b.app_name FROM customers c JOIN brands b ON b.id = c.brand_id WHERE c.id = ?",
        (lic["customer_id"],),
    ).fetchone()
    return render_template("license.html", lic=lic, events=events, brand=brand,
                           default_days=current_app.config["DEFAULT_VALIDITY_DAYS"])


@bp.post("/licenses/<int:lid>/<action>")
@login_required
def license_action(lid, action):
    lic = _get_license(lid)
    conn = db.get()
    now = db.now()
    f = request.form
    if action == "renew":
        try:
            days = max(1, min(3650, int(f.get("days", "365") or 365)))
        except ValueError:
            flash("Informe a quantidade de dias.", "error")
            return redirect(url_for("web.license", lid=lid))
        if lic["activated_at"]:
            base = max(lic["expires_at"] or now, now)
            conn.execute("UPDATE licenses SET expires_at = ? WHERE id = ?",
                         (base + days * licensing.DAY, lid))
        else:
            conn.execute("UPDATE licenses SET validity_days = validity_days + ? WHERE id = ?",
                         (days, lid))
        detail, msg = f"+{days} dias", f"Licença renovada por {days} dias."
    elif action == "expiry":
        try:
            tz = ZoneInfo(current_app.config["TIMEZONE"])
            day = datetime.strptime(f.get("date", ""), "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=tz)
        except ValueError:
            flash("Data inválida.", "error")
            return redirect(url_for("web.license", lid=lid))
        conn.execute("UPDATE licenses SET expires_at = ? WHERE id = ?", (int(day.timestamp()), lid))
        detail, msg = day.strftime("%d/%m/%Y"), "Data de vencimento alterada."
    elif action == "revoke":
        conn.execute("UPDATE licenses SET revoked_at = ? WHERE id = ?", (now, lid))
        detail, msg = "", "Licença revogada. O computador será bloqueado na próxima verificação."
    elif action == "unrevoke":
        conn.execute("UPDATE licenses SET revoked_at = NULL WHERE id = ?", (lid,))
        detail, msg = "", "Licença reativada."
    elif action == "unbind":
        conn.execute("UPDATE licenses SET machine = NULL WHERE id = ?", (lid,))
        detail = lic["hostname"] or lic["peer_id"]
        msg = "Vínculo removido. O serial pode ser ativado em outro computador."
    elif action == "notes":
        conn.execute("UPDATE licenses SET notes = ? WHERE id = ?", (f.get("notes", "")[:2000], lid))
        detail, msg = "", "Observações salvas."
    elif action == "delete":
        if lic["state"] not in ("unused", "revoked"):
            flash("Só é possível excluir licenças não ativadas ou revogadas.", "error")
            return redirect(url_for("web.license", lid=lid))
        conn.execute("DELETE FROM licenses WHERE id = ?", (lid,))
        db.log_event("deleted", lic["serial"], actor=actor())
        conn.commit()
        flash("Licença excluída.", "ok")
        return redirect(url_for("web.customer", cid=lic["customer_id"]))
    else:
        abort(404)
    db.log_event(action, detail, lid, actor=actor())
    conn.commit()
    flash(msg, "ok")
    return redirect(url_for("web.license", lid=lid))


# --- events and settings ----------------------------------------------------

@bp.get("/events")
@login_required
def events():
    rows = db.get().execute(
        "SELECT e.*, l.serial FROM events e LEFT JOIN licenses l ON l.id = e.license_id"
        " ORDER BY e.at DESC LIMIT 500"
    ).fetchall()
    return render_template("events.html", events=rows)


@bp.get("/settings")
@login_required
def settings():
    return render_template(
        "settings.html",
        public_key=keys.public_key_b64(),
        public_url=current_app.config["PUBLIC_URL"],
        github_repo=current_app.config["GITHUB_REPO"],
        github_ready=bool(current_app.config["GITHUB_REPO"] and current_app.config["GITHUB_TOKEN"]),
    )


@bp.post("/settings/password")
@login_required
def change_password():
    f = request.form
    if not check_password_hash(g.user["password_hash"], f.get("current", "")):
        flash("Senha atual incorreta.", "error")
    elif len(f.get("new", "")) < 10:
        flash("A nova senha precisa ter pelo menos 10 caracteres.", "error")
    elif f.get("new") != f.get("confirm"):
        flash("A confirmação não confere.", "error")
    else:
        conn = db.get()
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (generate_password_hash(f["new"]), g.user["id"]))
        db.log_event("password_changed", actor=actor())
        conn.commit()
        flash("Senha alterada.", "ok")
    return redirect(url_for("web.settings"))


# --- template helpers -------------------------------------------------------

def fmt_time(ts, with_time=False):
    if not ts:
        return ""
    tz = ZoneInfo(current_app.config["TIMEZONE"])
    return datetime.fromtimestamp(ts, tz).strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y")


def register_filters(app):
    app.jinja_env.filters["date"] = fmt_time
    app.jinja_env.filters["datetime"] = lambda ts: fmt_time(ts, True)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["STATE_LABELS"] = licensing.STATE_LABELS
