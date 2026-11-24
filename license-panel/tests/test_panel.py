import base64
import io
import json
import re
import zipfile

import pytest
from nacl.signing import VerifyKey

from panel import create_app, db, keys, licensing

M1 = "a" * 64
M2 = "b" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 4"><rect width="4" height="4"/><rect x="6" width="4" height="4"/></svg>'


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "DATA_DIR": tmp_path,
        "DATABASE": str(tmp_path / "t.sqlite3"),
        "ADMIN_PASSWORD": "senha-de-teste",
        "SECRET_KEY": "test",
        "SESSION_COOKIE_SECURE": False,
        "PUBLIC_URL": "https://licencas.test",
    })
    from panel import api, web
    api.limiter.hits.clear()
    web.login_limiter.hits.clear()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, path="/"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def login(client):
    token = csrf(client, "/login")
    r = client.post("/login", data={"username": "admin", "password": "senha-de-teste", "csrf": token})
    assert r.status_code == 302


def make_license(app, **kw):
    with app.app_context():
        conn = db.get()
        cid = conn.execute(
            "INSERT INTO customers (name, created_at) VALUES ('Fazenda Teste', 0)"
        ).lastrowid
        conn.commit()
        serial = licensing.create_licenses(cid, 1, kw.get("days", 365), kw.get("start_now", False), "", "t")[0]
        return serial


def decode(app, token):
    with app.app_context():
        vk = VerifyKey(base64.b64decode(keys.public_key_b64()))
    return json.loads(vk.verify(base64.b64decode(token)))


def call(client, path, serial, machine=M1):
    return client.post(path, json={"serial": serial, "machine": machine, "id": "123456789",
                                   "hostname": "PC-01", "platform": "windows", "app": "BoaSafra"})


def test_serial_format_and_normalisation():
    s = licensing.new_serial()
    assert re.fullmatch(r"([0-9A-HJKMNP-TV-Z]{4}-){4}[0-9A-HJKMNP-TV-Z]{4}", s)
    assert licensing.serial_key(s.lower().replace("-", " ")) == s.replace("-", "")


def test_activate_binds_and_starts_one_year(app, client):
    serial = make_license(app)
    r = call(client, "/api/v1/activate", serial.lower())
    assert r.status_code == 200
    status = decode(app, r.json["token"])
    assert status["state"] == "active"
    assert status["serial"] == serial and status["machine"] == M1
    assert status["customer"] == "Fazenda Teste"
    days = (status["expires_at"] - status["checked_at"]) / licensing.DAY
    assert 364.9 < days <= 365

    again = decode(app, call(client, "/api/v1/validate", serial).json["token"])
    assert again["state"] == "active" and again["expires_at"] == status["expires_at"]


def test_other_machine_is_refused(app, client):
    serial = make_license(app)
    call(client, "/api/v1/activate", serial)
    for path in ("/api/v1/activate", "/api/v1/validate"):
        status = decode(app, call(client, path, serial, M2).json["token"])
        assert status["state"] == "bound_elsewhere" and status["machine"] == M2


def test_validate_does_not_activate(app, client):
    serial = make_license(app)
    assert decode(app, call(client, "/api/v1/validate", serial).json["token"])["state"] == "invalid"
    assert decode(app, call(client, "/api/v1/activate", serial).json["token"])["state"] == "active"


def test_unknown_serial_and_bad_machine(app, client):
    assert decode(app, call(client, "/api/v1/activate", "XXXX").json["token"])["state"] == "invalid"
    assert call(client, "/api/v1/activate", "XXXX", "nothex").status_code == 400


def test_expired_and_revoked(app, client):
    serial = make_license(app)
    call(client, "/api/v1/activate", serial)
    with app.app_context():
        conn = db.get()
        conn.execute("UPDATE licenses SET expires_at = 1")
        conn.commit()
    assert decode(app, call(client, "/api/v1/validate", serial).json["token"])["state"] == "expired"
    with app.app_context():
        conn = db.get()
        conn.execute("UPDATE licenses SET revoked_at = 1")
        conn.commit()
    assert decode(app, call(client, "/api/v1/validate", serial).json["token"])["state"] == "revoked"


def test_start_now_fixes_expiry_at_issue(app, client):
    serial = make_license(app, days=10, start_now=True)
    with app.app_context():
        issued = db.get().execute("SELECT expires_at FROM licenses").fetchone()[0]
    status = decode(app, call(client, "/api/v1/activate", serial).json["token"])
    assert status["expires_at"] == issued


def test_admin_requires_login_and_csrf(app, client):
    assert client.get("/").status_code == 302
    login(client)
    assert client.get("/").status_code == 200
    assert client.post("/customers", data={"name": "X"}).status_code == 400


def test_admin_flow_issue_renew_unbind(app, client):
    login(client)
    token = csrf(client, "/customers")
    r = client.post("/customers", data={"name": "Agro Ltda", "csrf": token})
    cid = int(r.headers["Location"].rsplit("/", 1)[1])
    client.post(f"/customers/{cid}/licenses", data={"count": "3", "validity_days": "365", "csrf": token})
    with app.app_context():
        serials = [r[0] for r in db.get().execute("SELECT serial FROM licenses WHERE customer_id = ?", (cid,))]
    assert len(serials) == 3

    call(client, "/api/v1/activate", serials[0])
    with app.app_context():
        lid, before = db.get().execute("SELECT id, expires_at FROM licenses WHERE serial = ?", (serials[0],)).fetchone()
    client.post(f"/licenses/{lid}/renew", data={"days": "365", "csrf": token})
    with app.app_context():
        after = db.get().execute("SELECT expires_at FROM licenses WHERE id = ?", (lid,)).fetchone()[0]
    assert after - before == 365 * licensing.DAY

    client.post(f"/licenses/{lid}/unbind", data={"csrf": token})
    assert decode(app, call(client, "/api/v1/validate", serials[0]).json["token"])["state"] == "invalid"
    assert decode(app, call(client, "/api/v1/activate", serials[0], M2).json["token"])["state"] == "active"

    assert client.get("/licenses?format=csv").status_code == 200
    for page in ("/", "/licenses", f"/licenses/{lid}", f"/customers/{cid}", "/events", "/settings", "/brands"):
        assert client.get(page).status_code == 200, page


def test_brand_pack(app, client):
    login(client)
    token = csrf(client, "/brands/new")
    data = {"app_name": "AcmeRemoto", "display_name": "Acme Acesso Remoto", "company": "Acme Ltda",
            "color_dark": "#112233", "csrf": token,
            "logo_light": (io.BytesIO(SVG), "l.svg"), "logo_dark": (io.BytesIO(SVG), "d.svg")}
    r = client.post("/brands", data=data, content_type="multipart/form-data")
    assert r.status_code == 302
    bid = int(r.headers["Location"].rsplit("/", 1)[1])
    assert client.get(f"/brands/{bid}").status_code == 200
    assert client.get(f"/brands/{bid}/image/logo_light").mimetype == "image/svg+xml"

    bad = dict(data, app_name="Bad", display_name="<script>", logo_light=(io.BytesIO(b'<svg><script/></svg>'), "x.svg"),
               logo_dark=(io.BytesIO(SVG), "d.svg"))
    assert client.post("/brands", data=bad, content_type="multipart/form-data").status_code == 400

    with app.app_context():
        conn = db.get()
        conn.execute("INSERT INTO builds (brand_id, token, release_tag, requested_by, requested_at)"
                     " VALUES (?, 'tok', 'acmeremoto-x', 'admin', ?)", (bid, db.now()))
        conn.commit()
        pk = keys.public_key_b64()
    r = client.get("/build-pack/tok.zip")
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.data))
    manifest = json.loads(zf.read("brand.json"))
    assert manifest["app_name"] == "AcmeRemoto"
    assert manifest["license_public_key"] == pk
    assert manifest["license_server"] == "https://licencas.test"
    assert zf.read(manifest["logo_light"]) == SVG
    assert client.get("/build-pack/nope.zip").status_code == 404


def test_rate_limit(app, client):
    for _ in range(30):
        call(client, "/api/v1/validate", "X")
    assert call(client, "/api/v1/validate", "X").status_code == 429
