"""Serials and the activation / validation rules."""

import re
import secrets

from . import db, keys

# Crockford base32: no I, L, O or U, so a serial read over the phone survives.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
GROUPS, GROUP_LEN = 5, 4
DAY = 24 * 60 * 60
EXPIRING_SOON_DAYS = 30
MACHINE_RE = re.compile(r"^[0-9a-f]{64}$")

STATE_LABELS = {
    "unused": "Não ativada",
    "active": "Ativa",
    "expiring": "Vencendo",
    "expired": "Vencida",
    "revoked": "Revogada",
}


def new_serial() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(GROUPS * GROUP_LEN))
    return format_serial(raw)


def serial_key(serial: str) -> str:
    """The comparable form: what a person may type, reduced to its symbols."""
    key = re.sub(r"[^0-9A-Za-z]", "", serial or "").upper()
    return key.translate(str.maketrans({"O": "0", "I": "1", "L": "1"}))


def format_serial(key: str) -> str:
    return "-".join(key[i:i + GROUP_LEN] for i in range(0, len(key), GROUP_LEN))


def state(lic, now=None) -> str:
    now = db.now() if now is None else now
    if lic["revoked_at"]:
        return "revoked"
    if not lic["activated_at"] or not lic["machine"]:
        return "unused"
    if lic["expires_at"] is not None and lic["expires_at"] <= now:
        return "expired"
    if lic["expires_at"] is not None and lic["expires_at"] - now < EXPIRING_SOON_DAYS * DAY:
        return "expiring"
    return "active"


def create_licenses(customer_id, count, validity_days, start_now, notes, actor):
    conn = db.get()
    now = db.now()
    created = []
    for _ in range(count):
        while True:
            serial = new_serial()
            key = serial_key(serial)
            if not conn.execute("SELECT 1 FROM licenses WHERE serial_key = ?", (key,)).fetchone():
                break
        expires_at = now + validity_days * DAY if start_now else None
        cur = conn.execute(
            "INSERT INTO licenses (serial, serial_key, customer_id, validity_days, expires_at, notes, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (serial, key, customer_id, validity_days, expires_at, notes, now),
        )
        db.log_event("issued", serial, cur.lastrowid, actor)
        created.append(serial)
    conn.commit()
    return created


def answer(payload: dict, activate: bool, ip: str) -> dict:
    """Decide a client's request and return the signed reply.

    Every decision is signed, refusals included, so a client cannot be talked
    into anything by a reply that did not come from here.
    """
    conn = db.get()
    now = db.now()
    typed = str(payload.get("serial", ""))[:64]
    machine = str(payload.get("machine", "")).lower()
    if not MACHINE_RE.match(machine):
        return {"error": "invalid machine"}

    lic = conn.execute(
        "SELECT l.*, c.name AS customer FROM licenses l JOIN customers c ON c.id = l.customer_id"
        " WHERE l.serial_key = ?",
        (serial_key(typed),),
    ).fetchone()

    serial = lic["serial"] if lic else typed.strip().upper()
    customer = lic["customer"] if lic else ""
    expires_at = 0
    if lic is None:
        result = "invalid"
    elif lic["revoked_at"]:
        result = "revoked"
    elif lic["machine"] and lic["machine"] != machine:
        result = "bound_elsewhere"
    elif not lic["machine"] and not activate:
        # Unbound (never activated, or its binding was reset): only an
        # explicit activation may claim it.
        result = "invalid"
    else:
        if not lic["machine"]:
            expires_at = lic["expires_at"] or now + lic["validity_days"] * DAY
            conn.execute(
                "UPDATE licenses SET machine = ?, activated_at = ?, expires_at = ? WHERE id = ?",
                (machine, now, expires_at, lic["id"]),
            )
            db.log_event("activated", _describe(payload), lic["id"], ip=ip)
        else:
            expires_at = lic["expires_at"] or 0
        conn.execute(
            "UPDATE licenses SET peer_id = ?, hostname = ?, platform = ?, version = ?, app = ?,"
            " last_ip = ?, last_seen_at = ? WHERE id = ?",
            (
                str(payload.get("id", ""))[:32],
                str(payload.get("hostname", ""))[:128],
                str(payload.get("platform", ""))[:32],
                str(payload.get("version", ""))[:32],
                str(payload.get("app", ""))[:64],
                ip,
                now,
                lic["id"],
            ),
        )
        result = "active" if expires_at > now else "expired"

    if lic is not None and result != "active":
        db.log_event("refused" if activate else "check_failed", f"{result} — {_describe(payload)}", lic["id"], ip=ip)
    conn.commit()

    status = {
        "serial": serial,
        "machine": machine,
        "state": result,
        "customer": customer,
        "expires_at": expires_at,
        "checked_at": now,
    }
    return {"state": result, "token": keys.sign_status(status)}


def _describe(payload):
    parts = [str(payload.get(k, ""))[:64] for k in ("hostname", "id", "platform", "app")]
    return " · ".join(p for p in parts if p)
