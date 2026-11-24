#!/usr/bin/env python3
"""Rebrand this checkout for a customer.

Takes a brand pack — the zip the license panel serves for a build, or a
directory with the same files — and rewrites the client so that it installs,
runs and presents itself as that brand instead of Boa Safra:

    brand.json        the names, the installer colour and the license panel
    logo-light.*      the lockup for light backgrounds (SVG or PNG)
    logo-dark.*       the lockup for dark backgrounds (SVG or PNG)
    emblem.*          optional: the square icon, if it cannot be cropped
                      out of the lockup

    python3 res/branding/apply_brand.py pack.zip

It replaces the four Boa Safra names wherever the client and its packaging
carry them (see BOASAFRA.md for what each one drives), renames the files
named after the brand, points the licensing at the panel that issued the
pack, and regenerates every icon from the new artwork with
res/branding/boasafra/generate.py.

It edits the working tree in place and is meant for a throwaway checkout: CI
runs it, turns the result into a patch, and builds from that.
"""

import argparse
import base64
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ART_DIR = os.path.join(ROOT, "res", "branding", "boasafra")

# The current names and the brand field that replaces each.
CURRENT = [
    ("display_name", "Boa Safra Acesso Remoto"),
    ("company", "Boa Safra"),
    ("app_name", "BoaSafra"),
    ("slug", "boasafra"),
]

# Left alone: the brand sources themselves, the panel, CI (it is read from the
# commit that started the run, never from this checkout) and the docs about
# the Boa Safra build.
EXCLUDED_PREFIXES = (
    "res/branding/",
    "license-panel/",
    ".github/",
    "BOASAFRA.md",
)

# Paths that name the artwork directory. They must survive the rename of the
# slug, since the directory itself keeps its name.
PROTECTED = ["branding/boasafra"]

APP_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{2,29}$")
TEXT_RE = re.compile(r"^[\w .,()\-]{2,60}$")
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def fail(msg):
    sys.exit(f"apply_brand: {msg}")


def load_pack(path):
    if os.path.isdir(path):
        return path
    target = tempfile.mkdtemp(prefix="brand-")
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if "/" in name or "\\" in name or name.startswith("."):
                fail(f"unexpected entry in the pack: {name}")
        zf.extractall(target)
    return target


def read_manifest(pack):
    with open(os.path.join(pack, "brand.json"), encoding="utf-8") as fh:
        brand = json.load(fh)
    if not APP_NAME_RE.match(brand.get("app_name", "")):
        fail("app_name must be one word of letters and digits, starting with a letter")
    for key in ("display_name", "company"):
        if not TEXT_RE.match(brand.get(key, "")):
            fail(f"{key} has characters the packaging cannot carry")
    if not COLOR_RE.match(brand.get("color_dark", "#304929")):
        fail("color_dark must be #RRGGBB")
    for key in ("logo_light", "logo_dark"):
        if not brand.get(key):
            fail(f"the pack has no {key}")
    brand["slug"] = brand["app_name"].lower()
    if brand["slug"] in ("boasafra", "rustdesk"):
        fail("that identity is reserved")
    return brand


def tracked_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True,
                         capture_output=True).stdout
    return [p for p in out.decode().split("\0") if p and not p.startswith(EXCLUDED_PREFIXES)]


def rewrite(text, brand):
    """Replace every current name in one pass, so a new name that happens to
    contain an old one is never replaced again."""
    mapping = {keep: keep for keep in PROTECTED}
    mapping.update({old: brand[key] for key, old in CURRENT})
    pattern = re.compile("|".join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)))
    return pattern.sub(lambda m: mapping[m.group(0)], text)


def rewrite_files(brand):
    changed = 0
    for rel in tracked_files():
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path) or os.path.islink(path):
            continue
        with open(path, "rb") as fh:
            raw = fh.read()
        if b"\0" in raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        new = rewrite(text, brand)
        if new != text:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(new)
            changed += 1
    print(f"names   rewritten in {changed} files")


def rename_files(brand):
    for rel in tracked_files():
        new_rel = rewrite(rel, brand)
        if new_rel != rel and os.path.exists(os.path.join(ROOT, rel)):
            os.makedirs(os.path.dirname(os.path.join(ROOT, new_rel)) or ROOT, exist_ok=True)
            os.rename(os.path.join(ROOT, rel), os.path.join(ROOT, new_rel))
            print(f"rename  {rel} -> {new_rel}")


def set_licensing(brand):
    path = os.path.join(ROOT, "src", "branding.rs")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for const, value in (("LICENSE_SERVER", brand.get("license_server", "")),
                         ("LICENSE_PUBLIC_KEY", brand.get("license_public_key", ""))):
        if not re.fullmatch(r"[A-Za-z0-9+/=:._\-]*", value):
            fail(f"{const} has unexpected characters")
        text, n = re.subn(rf'(pub const {const}: &str = )"[^"]*";', rf'\1"{value}";', text)
        if n != 1:
            fail(f"could not find {const} in src/branding.rs")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("license " + (brand.get("license_server") or "(no panel)"))


def as_svg(path):
    """The artwork as SVG. A PNG is wrapped, so the generator can treat both
    the same way."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        width, height = struct.unpack(">II", data[16:24])
        b64 = base64.b64encode(data).decode()
        return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'
                f' viewBox="0 0 {width} {height}"><image width="{width}" height="{height}"'
                f' xlink:href="data:image/png;base64,{b64}"/></svg>')
    text = data.decode("utf-8")
    if "<svg" not in text:
        fail(f"{os.path.basename(path)} is neither SVG nor PNG")
    lowered = text.lower()
    if "<script" in lowered or "<!entity" in lowered or re.search(r"href\s*=\s*[\"']\s*(https?|file):", lowered):
        fail(f"{os.path.basename(path)} has scripts or external references")
    return text


def install_artwork(pack, brand):
    targets = {"logo_light": "logo-light.svg", "logo_dark": "logo-dark.svg", "emblem": "emblem.svg"}
    for key, name in targets.items():
        dest = os.path.join(ART_DIR, name)
        if brand.get(key):
            src = os.path.join(pack, os.path.basename(brand[key]))
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(as_svg(src))
        elif os.path.exists(dest):
            os.remove(dest)
    env = dict(os.environ, BRAND_COLOR_DARK=brand.get("color_dark", "#304929"))
    subprocess.run([sys.executable, os.path.join(ART_DIR, "generate.py")], check=True, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pack", help="brand pack: a zip from the license panel, or a directory")
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"),
                        help="where to write slug=..., for GitHub Actions")
    parser.add_argument("--skip-artwork", action="store_true",
                        help="rewrite names only, leave the icons alone")
    args = parser.parse_args()

    pack = load_pack(args.pack)
    brand = read_manifest(pack)
    print(f"brand   {brand['display_name']} ({brand['app_name']}, {brand['company']})")
    rewrite_files(brand)
    rename_files(brand)
    set_licensing(brand)
    if not args.skip_artwork:
        install_artwork(pack, brand)
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as fh:
            fh.write(f"slug={brand['slug']}\napp_name={brand['app_name']}\n")
    if pack != args.pack:
        shutil.rmtree(pack, ignore_errors=True)


if __name__ == "__main__":
    main()
