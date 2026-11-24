"""The panel's Ed25519 signing key.

Clients trust a status only if it verifies against the public half, which is
compiled into every build. Losing the private key means rebuilding and
reinstalling every client, so back up the data volume.
"""

import base64
import json
import os
from pathlib import Path

from flask import current_app
from nacl.signing import SigningKey

KEY_FILE = "license_signing_key"


def init_app(app):
    path = Path(app.config["DATA_DIR"]) / KEY_FILE
    env = os.environ.get("PANEL_SIGNING_KEY", "").strip()
    if env:
        seed = base64.b64decode(env)
    elif path.exists():
        seed = base64.b64decode(path.read_text().strip())
    else:
        seed = bytes(SigningKey.generate())
        path.write_text(base64.b64encode(seed).decode())
        path.chmod(0o600)
    app.extensions["signing_key"] = SigningKey(seed)


def signing_key() -> SigningKey:
    return current_app.extensions["signing_key"]


def public_key_b64() -> str:
    return base64.b64encode(bytes(signing_key().verify_key)).decode()


def sign_status(status: dict) -> str:
    """The token the client stores: base64 of signature || JSON, which is the
    layout sodiumoxide's `sign::verify` expects."""
    message = json.dumps(status, separators=(",", ":"), ensure_ascii=False).encode()
    return base64.b64encode(signing_key().sign(message)).decode()
