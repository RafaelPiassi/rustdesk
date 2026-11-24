"""Customer brands and the white-label installer builds made from them.

A brand is the name set and artwork a customer's build carries instead of
Boa Safra's. Building one asks GitHub Actions to run `brand-build.yml`, which
downloads the brand pack from here, rewrites the client with
`res/branding/apply_brand.py` and publishes the installer as a release.
"""

import io
import json
import re
import secrets
import zipfile
from datetime import datetime

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from . import db, github, keys
from .web import actor, login_required

bp = Blueprint("brands", __name__)

APP_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{2,29}$")
# Display names land in XML, .rc, .desktop, plist and JSON files, so nothing
# any of those would need escaped.
TEXT_RE = re.compile(r"^[\w .,()\-]{2,60}$")
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
RESERVED = {"rustdesk", "boasafra"}
PACK_TTL = 72 * 60 * 60
IMAGE_FIELDS = ("logo_light", "logo_dark", "emblem")
MAX_IMAGE = 2 * 1024 * 1024


def _image(upload):
    """Return (bytes, type) for an accepted upload, None for no upload, or
    raise ValueError with the reason it was refused."""
    if upload is None or not upload.filename:
        return None
    data = upload.read(MAX_IMAGE + 1)
    if len(data) > MAX_IMAGE:
        raise ValueError("imagem maior que 2 MB")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return data, "png"
    text = data.decode("utf-8", errors="replace")
    if "<svg" not in text:
        raise ValueError("envie SVG ou PNG")
    lowered = text.lower()
    # The build renders these with cairosvg, which follows external references.
    if "<script" in lowered or "<!entity" in lowered or re.search(r"href\s*=\s*[\"']\s*(https?|file):", lowered):
        raise ValueError("o SVG não pode ter scripts nem referências externas")
    return data, "svg"


def _get(bid):
    row = db.get().execute("SELECT * FROM brands WHERE id = ?", (bid,)).fetchone()
    if row is None:
        abort(404)
    return row


def _form(existing=None):
    f = request.form
    values = {
        "app_name": f.get("app_name", "").strip(),
        "display_name": f.get("display_name", "").strip(),
        "company": f.get("company", "").strip(),
        "color_dark": f.get("color_dark", "#304929").strip(),
    }
    errors = []
    if not APP_NAME_RE.match(values["app_name"]):
        errors.append("Identificador: só letras e números, começando por letra, de 3 a 30 caracteres.")
    elif values["app_name"].lower() in RESERVED:
        errors.append("Identificador reservado; escolha outro.")
    else:
        clash = db.get().execute(
            "SELECT id FROM brands WHERE lower(app_name) = lower(?) AND id != ?",
            (values["app_name"], existing["id"] if existing else 0),
        ).fetchone()
        if clash:
            errors.append("Já existe uma marca com esse identificador.")
    for key, label in (("display_name", "Nome exibido"), ("company", "Empresa")):
        if not TEXT_RE.match(values[key]):
            errors.append(f"{label}: de 2 a 60 caracteres, sem & < > \" ' ou símbolos.")
    if not COLOR_RE.match(values["color_dark"]):
        errors.append("Cor: use o formato #RRGGBB.")
    images = {}
    for field in IMAGE_FIELDS:
        try:
            images[field] = _image(request.files.get(field))
        except ValueError as exc:
            errors.append(f"{field}: {exc}")
    return values, images, errors


@bp.get("/brands")
@login_required
def brands():
    rows = db.get().execute(
        "SELECT b.*, (SELECT COUNT(*) FROM customers c WHERE c.brand_id = b.id) AS customers"
        " FROM brands b ORDER BY b.display_name"
    ).fetchall()
    return render_template("brands.html", brands=rows)


@bp.get("/brands/new")
@login_required
def brand_new():
    return render_template("brand.html", brand=None, builds=[], customers=[])


@bp.post("/brands")
@login_required
def brand_create():
    values, images, errors = _form()
    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("brand.html", brand=None, form=values, builds=[], customers=[]), 400
    conn = db.get()
    now = db.now()
    cur = conn.execute(
        "INSERT INTO brands (app_name, display_name, company, color_dark, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (values["app_name"], values["display_name"], values["company"], values["color_dark"], now, now),
    )
    _store_images(cur.lastrowid, images)
    db.log_event("brand_created", values["app_name"], actor=actor())
    conn.commit()
    flash("Marca cadastrada.", "ok")
    return redirect(url_for("brands.brand", bid=cur.lastrowid))


def _store_images(bid, images):
    for field, value in images.items():
        if value:
            db.get().execute(
                f"UPDATE brands SET {field} = ?, {field}_type = ? WHERE id = ?", (*value, bid)
            )


@bp.get("/brands/<int:bid>")
@login_required
def brand(bid):
    b = _get(bid)
    _refresh_builds(bid)
    builds = db.get().execute(
        "SELECT * FROM builds WHERE brand_id = ? ORDER BY requested_at DESC LIMIT 20", (bid,)
    ).fetchall()
    customers = db.get().execute(
        "SELECT id, name FROM customers WHERE brand_id = ? ORDER BY name", (bid,)
    ).fetchall()
    return render_template(
        "brand.html", brand=b, builds=builds, customers=customers,
        github_ready=github.configured(), repo=current_app.config["GITHUB_REPO"],
    )


@bp.post("/brands/<int:bid>")
@login_required
def brand_update(bid):
    b = _get(bid)
    values, images, errors = _form(b)
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("brands.brand", bid=bid))
    conn = db.get()
    conn.execute(
        "UPDATE brands SET app_name = ?, display_name = ?, company = ?, color_dark = ?, updated_at = ?"
        " WHERE id = ?",
        (values["app_name"], values["display_name"], values["company"], values["color_dark"], db.now(), bid),
    )
    _store_images(bid, images)
    if request.form.get("remove_emblem"):
        conn.execute("UPDATE brands SET emblem = NULL, emblem_type = NULL WHERE id = ?", (bid,))
    db.log_event("brand_updated", values["app_name"], actor=actor())
    conn.commit()
    flash("Marca atualizada. Gere um novo instalador para aplicar as mudanças.", "ok")
    return redirect(url_for("brands.brand", bid=bid))


@bp.post("/brands/<int:bid>/delete")
@login_required
def brand_delete(bid):
    b = _get(bid)
    conn = db.get()
    conn.execute("DELETE FROM brands WHERE id = ?", (bid,))
    db.log_event("brand_deleted", b["app_name"], actor=actor())
    conn.commit()
    flash("Marca excluída. Os clientes que a usavam voltam para a marca padrão.", "ok")
    return redirect(url_for("brands.brands"))


@bp.get("/brands/<int:bid>/image/<field>")
@login_required
def brand_image(bid, field):
    if field not in IMAGE_FIELDS:
        abort(404)
    b = _get(bid)
    if not b[field]:
        abort(404)
    mime = "image/png" if b[f"{field}_type"] == "png" else "image/svg+xml"
    return Response(b[field], mimetype=mime, headers={
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
        "X-Content-Type-Options": "nosniff",
    })


# --- builds -----------------------------------------------------------------

@bp.post("/brands/<int:bid>/build")
@login_required
def brand_build(bid):
    b = _get(bid)
    public_url = current_app.config["PUBLIC_URL"]
    problems = []
    if not public_url.startswith("https://"):
        problems.append("Configure PANEL_PUBLIC_URL com o endereço https do painel.")
    if not github.configured():
        problems.append("Configure GITHUB_REPO e GITHUB_TOKEN para disparar builds.")
    if not (b["logo_light"] and b["logo_dark"]):
        problems.append("Envie os logos para fundo claro e escuro.")
    if problems:
        for p in problems:
            flash(p, "error")
        return redirect(url_for("brands.brand", bid=bid))

    conn = db.get()
    token = secrets.token_urlsafe(32)
    tag = f"{b['app_name'].lower()}-{datetime.now():%Y%m%d-%H%M%S}"
    cur = conn.execute(
        "INSERT INTO builds (brand_id, token, release_tag, requested_by, requested_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (bid, token, tag, actor(), db.now()),
    )
    build_id = cur.lastrowid
    try:
        github.dispatch({
            "brand": b["app_name"],
            "build_id": str(build_id),
            "pack_url": f"{public_url}/build-pack/{token}.zip",
            "release_tag": tag,
        })
        conn.execute("UPDATE builds SET status = 'queued' WHERE id = ?", (build_id,))
        flash("Build solicitado ao GitHub Actions. Leva cerca de uma hora.", "ok")
    except github.GitHubError as exc:
        conn.execute("UPDATE builds SET status = 'failed', error = ? WHERE id = ?", (str(exc), build_id))
        flash(f"O GitHub recusou o build: {exc}", "error")
    db.log_event("build_requested", f"{b['app_name']} → {tag}", actor=actor())
    conn.commit()
    return redirect(url_for("brands.brand", bid=bid))


def _refresh_builds(bid):
    pending = db.get().execute(
        "SELECT * FROM builds WHERE brand_id = ? AND status IN ('queued', 'in_progress', 'downloaded')",
        (bid,),
    ).fetchall()
    if not pending or not github.configured():
        return
    try:
        runs = github.runs()
    except github.GitHubError:
        return
    conn = db.get()
    for build in pending:
        run = runs.get(build["id"])
        if not run:
            continue
        status = run["status"] if run["status"] != "completed" else (
            "success" if run["conclusion"] == "success" else "failed")
        conn.execute("UPDATE builds SET status = ?, run_url = ? WHERE id = ?",
                     (status, run["html_url"], build["id"]))
    conn.commit()


@bp.get("/build-pack/<token>.zip")
def build_pack(token):
    """What the build runner downloads. The token in the URL is the only
    credential: it is random, single-brand and expires."""
    build = db.get().execute("SELECT * FROM builds WHERE token = ?", (token,)).fetchone()
    if build is None or db.now() - build["requested_at"] > PACK_TTL:
        abort(404)
    b = _get(build["brand_id"])
    files = {}
    manifest = {
        "app_name": b["app_name"],
        "display_name": b["display_name"],
        "company": b["company"],
        "color_dark": b["color_dark"],
        "license_server": current_app.config["PUBLIC_URL"],
        "license_public_key": keys.public_key_b64(),
    }
    for field in IMAGE_FIELDS:
        if b[field]:
            name = f"{field.replace('_', '-')}.{b[field + '_type']}"
            files[name] = b[field]
            manifest[field] = name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("brand.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for name, data in files.items():
            zf.writestr(name, data)
    conn = db.get()
    if build["status"] == "queued":
        conn.execute("UPDATE builds SET status = 'downloaded' WHERE id = ?", (build["id"],))
        conn.commit()
    return Response(buf.getvalue(), mimetype="application/zip")
