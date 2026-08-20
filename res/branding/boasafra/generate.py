#!/usr/bin/env python3
"""Regenerate every Boa Safra brand asset shipped with this client.

Two files are the source of truth, and they are the official artwork:

    logo-light.svg    the full lockup, for light backgrounds
    logo-dark.svg     the full lockup, for dark backgrounds

Everything else is derived. The square emblem that becomes the application
icon is cropped out of the lockup at build time rather than kept as its own
file, so there is no second copy to drift: the crop is measured from the
rendered artwork, not hardcoded, and it follows the logo if the logo changes.

    python3 res/branding/boasafra/generate.py

Requires cairosvg, Pillow and numpy.
"""

import io
import os
import re
import shutil
import sys

try:
    import cairosvg
    import numpy as np
    from PIL import Image
except ImportError as exc:  # pragma: no cover - developer convenience
    sys.exit("missing dependency (%s); run: pip install cairosvg pillow numpy" % exc)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

LOGO_LIGHT = os.path.join(HERE, "logo-light.svg")
LOGO_DARK = os.path.join(HERE, "logo-dark.svg")

# Boa Safra's palette, as it appears in the official artwork.
DARK = "#304929"
LIGHT = "#9DAF40"
WHITE = "#FFFFFF"

MEASURE_SCALE = 16  # px per viewBox unit when measuring the artwork


# --- reading the official artwork -----------------------------------------

def view_box(svg):
    m = re.search(r'viewBox\s*=\s*"([-\d.eE]+)\s+([-\d.eE]+)\s+([-\d.eE]+)\s+([-\d.eE]+)"', svg)
    if not m:
        raise SystemExit("no viewBox in the source artwork")
    return tuple(float(v) for v in m.groups())


def with_view_box(svg, box):
    """The same drawing, cropped to `box`. The sources carry no width/height,
    so replacing the viewBox is enough to reframe them."""
    return re.sub(r'viewBox\s*=\s*"[^"]*"',
                  'viewBox="%.4f %.4f %.4f %.4f"' % box, svg, count=1)


def inline_styles(svg):
    """Turn the `<style>` class rules Illustrator emits into presentation
    attributes. flutter_svg and several icon loaders ignore CSS, and these
    files are shipped as SVG, not only rasterised."""
    rules = {}
    for block in re.findall(r"<style[^>]*>(.*?)</style>", svg, re.S):
        for name, body in re.findall(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", block):
            attrs = {}
            for decl in body.split(";"):
                if ":" in decl:
                    prop, value = decl.split(":", 1)
                    attrs[prop.strip()] = value.strip()
            rules[name] = attrs

    def replace(match):
        attrs = rules.get(match.group(1))
        if attrs is None:
            return match.group(0)
        return " ".join('%s="%s"' % kv for kv in attrs.items())

    svg = re.sub(r'class="([A-Za-z0-9_-]+)"', replace, svg)
    return re.sub(r"<style[^>]*>.*?</style>", "", svg, flags=re.S)


def on_white(svg):
    """The same drawing over an opaque white rectangle covering its viewBox."""
    x, y, w, h = view_box(svg)
    rect = '<rect x="%.4f" y="%.4f" width="%.4f" height="%.4f" fill="%s"/>' % (x, y, w, h, WHITE)
    return re.sub(r"(<svg\b[^>]*>)", r"\1" + rect, svg, count=1)


def rasterise(svg, width, height=None):
    data = cairosvg.svg2png(bytestring=svg.encode(), output_width=width,
                            output_height=height)
    return Image.open(io.BytesIO(data)).convert("RGBA")


def mark_box(svg):
    """Where the square mark sits inside the lockup.

    Measured by rendering: the mark is whatever comes before the widest empty
    column between it and the wordmark.
    """
    vx, vy, vw, vh = view_box(svg)
    img = rasterise(svg, int(vw * MEASURE_SCALE), int(vh * MEASURE_SCALE))
    ink = np.array(img)[..., 3] > 8
    columns = ink.any(axis=0)
    drawn = np.where(columns)[0]

    gutters, start = [], None
    for i, empty in enumerate(~columns):
        if empty and start is None:
            start = i
        elif not empty and start is not None:
            gutters.append((start, i))
            start = None
    interior = [g for g in gutters if g[0] > drawn[0] and g[1] < drawn[-1]]
    if not interior:
        raise SystemExit("cannot tell the mark from the wordmark in the lockup")
    split = max(interior, key=lambda g: g[1] - g[0])[0]

    region = ink[:, :split]
    xs, ys = np.where(region.any(axis=0))[0], np.where(region.any(axis=1))[0]
    x0, x1 = xs[0] / MEASURE_SCALE, (xs[-1] + 1) / MEASURE_SCALE
    y0, y1 = ys[0] / MEASURE_SCALE, (ys[-1] + 1) / MEASURE_SCALE
    return vx + x0, vy + y0, x1 - x0, y1 - y0


def square(box):
    """Grow a box to a square about its centre. The mark is a filled block, so
    the padding is the same colour as its field and the seam does not show."""
    x, y, w, h = box
    side = max(w, h)
    return x - (side - w) / 2, y - (side - h) / 2, side, side


def emblem_svg(source_svg):
    return inline_styles(with_view_box(source_svg, square(mark_box(source_svg))))


# --- writing the assets ---------------------------------------------------

def out(*parts):
    path = os.path.join(ROOT, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def save(img, *parts, **kw):
    path = out(*parts)
    img.save(path, **kw)
    print("asset   %s  %dx%d" % (os.path.relpath(path, ROOT), img.width, img.height))


def write_text(text, *parts):
    path = out(*parts)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("asset   %s  (svg)" % os.path.relpath(path, ROOT))


def opaque(img, background=WHITE):
    return Image.alpha_composite(Image.new("RGBA", img.size, background), img).convert("RGB")


def crop_alpha(img):
    box = img.getchannel("A").getbbox()
    return img.crop(box) if box else img


def inset(img, canvas, ratio):
    """Centre `img` at `ratio` of a transparent canvas x canvas square."""
    limit = max(1, round(canvas * ratio))
    scale = min(limit / img.width, limit / img.height)
    size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    out_img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    out_img.paste(img.resize(size, Image.LANCZOS),
                  ((canvas - size[0]) // 2, (canvas - size[1]) // 2))
    return out_img


def recolour(shape, color):
    """Keep a mark's silhouette, paint it a single colour."""
    solid = Image.new("RGBA", shape.size, tuple(color) + (255,))
    solid.putalpha(shape.getchannel("A"))
    return solid


def on_ground(mark, canvas, ratio, background):
    """The mark centred on a filled square. Both lockups draw the mark on
    transparency, so every icon has to supply the ground itself."""
    square_img = Image.new("RGBA", (canvas, canvas), background)
    square_img.alpha_composite(inset(crop_alpha(mark), canvas, ratio))
    return square_img


LOCKUP_BOX = (1200, 300)  # loadLogo() draws into 300x60; ship it at 4x

IOS_ICONS = [
    (20, 1), (20, 2), (20, 3), (29, 1), (29, 2), (29, 3), (40, 1), (40, 2),
    (40, 3), (60, 2), (60, 3), (76, 1), (76, 2), (83.5, 2), (1024, 1),
]

ANDROID_DENSITIES = {
    "mdpi": (48, 108, 24),
    "hdpi": (72, 162, 36),
    "xhdpi": (96, 216, 48),
    "xxhdpi": (144, 324, 72),
    "xxxhdpi": (192, 432, 96),
}

MSI_BANNER = (493, 58)
MSI_DIALOG = (493, 312)
MSI_DIALOG_ART_W = 164


def fit(svg, box_w, box_h):
    _, _, vw, vh = view_box(svg)
    scale = min(box_w / vw, box_h / vh)
    return rasterise(svg, max(1, round(vw * scale)), max(1, round(vh * scale)))


def main():
    for path in (LOGO_LIGHT, LOGO_DARK):
        if not os.path.exists(path):
            sys.exit("missing source artwork: %s" % os.path.relpath(path, ROOT))

    light = open(LOGO_LIGHT, encoding="utf-8").read()
    dark = open(LOGO_DARK, encoding="utf-8").read()

    emblem = emblem_svg(light)
    reversed_emblem = emblem_svg(dark)
    ICON_INSET = 0.88
    icon = on_ground(rasterise(emblem, 1024), 1024, ICON_INSET, WHITE)
    # The reversed mark, white on transparency, for anything drawn on a dark
    # ground: the menu bar, the status bar and the installer's side panel.
    figure = crop_alpha(rasterise(reversed_emblem, 512))
    print("emblem  cropped from logo-light.svg at %s" %
          ("%.2f %.2f %.2f %.2f" % square(mark_box(light))))

    # --- shared / Linux ---------------------------------------------------
    save(icon, "res", "icon.png")
    save(icon, "res", "mac-icon.png")
    for size in (32, 64, 128):
        save(icon.resize((size, size), Image.LANCZOS), "res", "%dx%d.png" % (size, size))
    save(icon.resize((256, 256), Image.LANCZOS), "res", "128x128@2x.png")
    save(icon, "res", "icon.ico", format="ICO",
         sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    write_text(emblem, "res", "scalable.svg")
    write_text(emblem, "res", "logo.svg")

    # --- trays ------------------------------------------------------------
    save(inset(figure, 48, 0.92), "res", "mac-tray-dark-x2.png")
    save(inset(recolour(figure, (0, 0, 0)), 48, 0.92), "res", "mac-tray-light-x2.png")
    save(icon, "res", "tray-icon.ico", format="ICO",
         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)])

    # --- Flutter ----------------------------------------------------------
    write_text(emblem, "flutter", "assets", "icon.svg")
    save(icon.resize((512, 512), Image.LANCZOS), "flutter", "assets", "icon.png")
    save(fit(light, *LOCKUP_BOX), "flutter", "assets", "logo_light.png")
    save(fit(dark, *LOCKUP_BOX), "flutter", "assets", "logo_dark.png")
    # The README banner needs its own ground: the lockup is drawn on
    # transparency, and the dark green would be unreadable on GitHub's dark theme.
    write_text(on_white(inline_styles(light)), "res", "logo-header.svg")

    # --- Windows ----------------------------------------------------------
    save(icon, "flutter", "windows", "runner", "resources", "app_icon.ico", format="ICO",
         sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    # --- macOS ------------------------------------------------------------
    save(icon, "flutter", "macos", "Runner", "AppIcon.icns", format="ICNS")

    # --- Android ----------------------------------------------------------
    for density, (launcher, foreground, stat) in ANDROID_DENSITIES.items():
        base = ("flutter", "android", "app", "src", "main", "res", "mipmap-" + density)
        block = icon.resize((launcher, launcher), Image.LANCZOS)
        save(block, *base, "ic_launcher.png")
        save(block, *base, "ic_launcher_round.png")
        # Adaptive icons only keep the inner 72/108 of the canvas; the mark is
        # a block, so it is inset rather than bled to the edges.
        save(inset(crop_alpha(rasterise(emblem, 512)), foreground, 72 / 108 * 0.86),
             *base, "ic_launcher_foreground.png")
        save(inset(figure, stat, 0.92), *base, "ic_stat_logo.png")
    save(icon.resize((256, 256), Image.LANCZOS),
         "fastlane", "metadata", "android", "en-US", "images", "icon.png")

    # --- Windows installer ------------------------------------------------
    target = os.path.join(HERE, "msi")
    os.makedirs(target, exist_ok=True)

    def store(img, name):
        path = os.path.join(target, name)
        img.save(path, format="BMP")
        print("asset   %s  %dx%d" % (os.path.relpath(path, ROOT), img.width, img.height))

    w, h = MSI_BANNER
    banner = Image.new("RGBA", MSI_BANNER, WHITE)
    logo = fit(light, round(w * 0.46), h - 16)
    banner.alpha_composite(logo, (w - logo.width - 14, (h - logo.height) // 2))
    store(banner.convert("RGB"), "WixUIBannerBmp.bmp")

    w, h = MSI_DIALOG
    dialog = Image.new("RGBA", MSI_DIALOG, WHITE)
    dialog.alpha_composite(Image.new("RGBA", (MSI_DIALOG_ART_W, h), DARK))
    art = inset(figure, MSI_DIALOG_ART_W, 0.55)
    dialog.alpha_composite(art, (0, (h - art.height) // 2))
    store(dialog.convert("RGB"), "WixUIDialogBmp.bmp")

    # --- iOS (no alpha channel allowed) -----------------------------------
    for size, scale in IOS_ICONS:
        px = int(round(size * scale))
        name = "Icon-App-%gx%g@%dx.png" % (size, size, scale)
        save(opaque(icon.resize((px, px), Image.LANCZOS)),
             "flutter", "ios", "Runner", "Assets.xcassets", "AppIcon.appiconset", name)


if __name__ == "__main__":
    main()
