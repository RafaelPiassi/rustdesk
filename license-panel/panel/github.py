"""The little of the GitHub REST API the brand builds need."""

import json
import re
import urllib.error
import urllib.request

from flask import current_app

API = "https://api.github.com"
BUILD_ID_RE = re.compile(r"\(build (\d+)\)")


class GitHubError(Exception):
    pass


def configured() -> bool:
    return bool(current_app.config["GITHUB_REPO"] and current_app.config["GITHUB_TOKEN"])


def _request(method, path, body=None):
    cfg = current_app.config
    req = urllib.request.Request(
        f"{API}/repos/{cfg['GITHUB_REPO']}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {cfg['GITHUB_TOKEN']}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "license-panel",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise GitHubError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GitHubError(str(exc.reason)) from exc
    return json.loads(raw) if raw else None


def dispatch(inputs: dict):
    cfg = current_app.config
    _request(
        "POST",
        f"/actions/workflows/{cfg['GITHUB_WORKFLOW']}/dispatches",
        {"ref": cfg["GITHUB_REF"], "inputs": inputs},
    )


def runs() -> dict:
    """Recent brand build runs, by the panel build id in their run name."""
    cfg = current_app.config
    data = _request(
        "GET", f"/actions/workflows/{cfg['GITHUB_WORKFLOW']}/runs?event=workflow_dispatch&per_page=50"
    )
    found = {}
    for run in (data or {}).get("workflow_runs", []):
        m = BUILD_ID_RE.search(run.get("display_title") or run.get("name") or "")
        if m and int(m.group(1)) not in found:
            found[int(m.group(1))] = run
    return found
