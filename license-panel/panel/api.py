"""The endpoints the clients call."""

import threading
import time
from collections import defaultdict, deque

from flask import Blueprint, jsonify, request

from . import licensing

bp = Blueprint("api", __name__, url_prefix="/api/v1")


class RateLimiter:
    """A sliding window per key. In memory, so per worker process; the panel
    runs one worker, which keeps this exact."""

    def __init__(self, limit, window):
        self.limit, self.window = limit, window
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


limiter = RateLimiter(limit=30, window=60)


def client_ip() -> str:
    return request.remote_addr or ""


def _handle(activate: bool):
    ip = client_ip()
    if not limiter.allow(ip):
        return jsonify(error="too many requests"), 429
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="expected a JSON object"), 400
    reply = licensing.answer(payload, activate, ip)
    return jsonify(reply), (400 if "error" in reply else 200)


@bp.post("/activate")
def activate():
    return _handle(True)


@bp.post("/validate")
def validate():
    return _handle(False)


@bp.get("/health")
def health():
    return jsonify(ok=True)
