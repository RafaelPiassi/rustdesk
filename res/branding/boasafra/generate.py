#!/usr/bin/env python3
"""Regenerate every Boa Safra brand asset shipped with this client.

The brand lives in three SVG sources next to this script:

    emblem.svg        the square mark, used for every application icon
    logo-light.svg    the full lockup, for light backgrounds
    logo-dark.svg     the full lockup, for dark backgrounds

Replace those files with the official artwork (SVG, or a PNG with the same
base name) and re-run this script to push the new art into every platform:

    python3 res/branding/boasafra/generate.py

Passing --rebuild-sources redraws the three SVGs from the vector definition
below, discarding any artwork that was dropped in. Requires cairosvg,
Pillow and fonttools.
"""

import argparse
import os
import shutil
import sys

try:
    import cairosvg
    from PIL import Image
except ImportError as exc:  # pragma: no cover - developer convenience
    sys.exit("missing dependency (%s); run: pip install cairosvg pillow fonttools" % exc)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

DARK = "#1B5632"   # Boa Safra dark green
LIGHT = "#8CBB2E"  # Boa Safra light green
WHITE = "#FFFFFF"

# --- the mark -------------------------------------------------------------
# A 512x512 grid. The "S" is a single stroked curve; the seed is a disc set
# into the upper counter, held off the stroke by a halo of background colour.
S_PATH = ("M 352 148 C 352 96, 276 74, 220 104 C 156 138, 160 212, 244 246 "
          "C 336 284, 342 350, 288 388 C 232 428, 152 408, 144 358")
S_WIDTH = 86
SEED = (190, 206, 66)  # cx, cy, r
SEED_HALO = 16

# --- the wordmark ---------------------------------------------------------
WORDMARK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
WORDMARK_TRACKING = 0.02   # em
WORDMARK_WEIGHT = 90       # font units of extra stroke, to reach a black weight


def mark(stroke_color, seed_color, halo_color, uid="a"):
    """The S and its seed, on a transparent 512x512 canvas.

    The seed never touches the S. On a solid background the gap is painted in
    the background colour; on a transparent one it is masked out of the stroke.
    """
    cx, cy, r = SEED
    stroke = ('<path d="%s" fill="none" stroke="%s" stroke-width="%d" '
              'stroke-linecap="round"%%s/>' % (S_PATH, stroke_color, S_WIDTH))
    seed = '<circle cx="%d" cy="%d" r="%d" fill="%s"/>' % (cx, cy, r, seed_color)
    if halo_color is None:
        mask_id = "seed-gap-" + uid
        return ('<mask id="%s" maskUnits="userSpaceOnUse" x="0" y="0" width="512" height="512">'
                '<rect width="512" height="512" fill="#fff"/>'
                '<circle cx="%d" cy="%d" r="%d" fill="#000"/></mask>\n%s\n%s'
                % (mask_id, cx, cy, r + SEED_HALO,
                   stroke % (' mask="url(#%s)"' % mask_id), seed))
    halo = ('<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" stroke-width="%d"/>'
            % (cx, cy, r + SEED_HALO // 2, halo_color, SEED_HALO))
    return "%s\n%s\n%s" % (stroke % "", halo, seed)


def emblem_svg(radius=96):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" '
            'width="512" height="512">\n'
            '<rect width="512" height="512" rx="%d" ry="%d" fill="%s"/>\n%s\n</svg>\n'
            % (radius, radius, DARK, mark(WHITE, LIGHT, DARK)))


def mark_svg(stroke_color=WHITE, seed_color=LIGHT):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" '
            'width="512" height="512">\n%s\n</svg>\n'
            % mark(stroke_color, seed_color, None))


def wordmark_path(text):
    """Outline `text` as an SVG path, plus its tight bounds, in font units."""
    from fontTools.ttLib import TTFont
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.misc.transform import Identity

    font = TTFont(WORDMARK_FONT)
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    upem = font["head"].unitsPerEm

    def run(pen):
        x = 0.0
        for ch in text:
            glyph = glyphs[cmap[ord(ch)]]
            glyph.draw(TransformPen(pen, Identity.translate(x, 0)))
            x += glyph.width + WORDMARK_TRACKING * upem

    out = SVGPathPen(glyphs)
    run(out)
    bounds = BoundsPen(glyphs)
    run(bounds)
    x0, y0, x1, y1 = bounds.bounds
    half = WORDMARK_WEIGHT / 2.0
    return out.getCommands(), (x0 - half, y0 - half, x1 + half, y1 + half)


def wordmark_group(text, color, box):
    """Fit `text` into box=(x, y, w, h) of the lockup's coordinate system."""
    d, (x0, y0, x1, y1) = wordmark_path(text)
    x, y, w, h = box
    sx = w / (x1 - x0)
    sy = h / (y1 - y0)
    # The glyph outlines are y-up; the lockup is y-down.
    return ('<g transform="translate(%.3f,%.3f) scale(%.6f,%.6f) translate(%.3f,%.3f)">'
            '<path d="%s" fill="%s" stroke="%s" stroke-width="%d" stroke-linejoin="round"/>'
            '</g>' % (x, y + h, sx, -sy, -x0, -y0, d, color, color, WORDMARK_WEIGHT))


# Lockup geometry, in a 1104x415 box that matches the official proportions.
LOCKUP_W, LOCKUP_H = 1104, 415
EMBLEM_BOX = (0, 12, 390, 390)
BOA_BOX = (432, 4, 672, 246)
SAFRA_BOX = (432, 266, 672, 146)


def lockup_svg(emblem_fill, s_color, seed_color, boa_color, safra_color):
    x, y, w, h = EMBLEM_BOX
    body = ""
    if emblem_fill:
        body += '<rect x="%d" y="%d" width="%d" height="%d" fill="%s"/>\n' % (x, y, w, h, emblem_fill)
    body += ('<g transform="translate(%d,%d) scale(%.6f)">%s</g>\n'
             % (x, y, w / 512.0, mark(s_color, seed_color, emblem_fill, uid="lockup")))
    body += wordmark_group("BOA", boa_color, BOA_BOX) + "\n"
    body += wordmark_group("SAFRA", safra_color, SAFRA_BOX) + "\n"
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
            'width="%d" height="%d">\n%s</svg>\n'
            % (LOCKUP_W, LOCKUP_H, LOCKUP_W, LOCKUP_H, body))


WORDMARK_W, WORDMARK_H = 672, 412


def wordmark_svg(boa_color, safra_color):
    body = wordmark_group("BOA", boa_color, (0, 0, WORDMARK_W, 246)) + "\n"
    body += wordmark_group("SAFRA", safra_color, (0, 262, WORDMARK_W, 146)) + "\n"
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
            'width="%d" height="%d">\n%s</svg>\n'
            % (WORDMARK_W, WORDMARK_H, WORDMARK_W, WORDMARK_H, body))


HEADER_W, HEADER_H = 1200, 420


def header_svg():
    scale = 0.78
    w, h = LOCKUP_W * scale, LOCKUP_H * scale
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
            'width="%d" height="%d">\n'
            '<rect width="%d" height="%d" fill="%s"/>\n'
            '<g transform="translate(%.2f,%.2f) scale(%s)">%s</g>\n</svg>\n'
            % (HEADER_W, HEADER_H, HEADER_W, HEADER_H, HEADER_W, HEADER_H, WHITE,
               (HEADER_W - w) / 2, (HEADER_H - h) / 2, scale,
               lockup_svg(DARK, WHITE, LIGHT, LIGHT, DARK)
               .split(">\n", 1)[1].rsplit("</svg>", 1)[0]))


SOURCES = {
    "emblem.svg": lambda: emblem_svg(),
    "emblem-square.svg": lambda: emblem_svg(radius=0),
    "mark.svg": lambda: mark_svg(),
    "mark-mono.svg": lambda: mark_svg(WHITE, WHITE),
    "logo-light.svg": lambda: lockup_svg(DARK, WHITE, LIGHT, LIGHT, DARK),
    "logo-dark.svg": lambda: lockup_svg(None, WHITE, LIGHT, LIGHT, WHITE),
    "logo-dark-mono.svg": lambda: lockup_svg(None, WHITE, WHITE, WHITE, WHITE),
    "wordmark-light.svg": lambda: wordmark_svg(LIGHT, DARK),
    "wordmark-mono.svg": lambda: wordmark_svg(WHITE, WHITE),
    "logo-header.svg": lambda: header_svg(),
}


def write_sources(force):
    for name, build in SOURCES.items():
        path = os.path.join(HERE, name)
        if os.path.exists(path) and not force:
            continue
        with open(path, "w") as fh:
            fh.write(build())
        print("source  %s" % os.path.relpath(path, ROOT))


def render(source, width, height=None):
    """Rasterise a brand source to an RGBA image."""
    height = height or width
    svg = os.path.join(HERE, source)
    png = os.path.splitext(svg)[0] + ".png"
    if os.path.exists(png):  # official artwork dropped in as a bitmap
        img = Image.open(png).convert("RGBA")
        return img.resize((width, height), Image.LANCZOS)
    data = cairosvg.svg2png(url=svg, output_width=width, output_height=height)
    import io
    return Image.open(io.BytesIO(data)).convert("RGBA")


def render_fit(source, box_w, box_h):
    """Rasterise a lockup so it fits box_w x box_h without distortion."""
    scale = min(box_w / LOCKUP_W, box_h / LOCKUP_H)
    return render(source, max(1, round(LOCKUP_W * scale)), max(1, round(LOCKUP_H * scale)))


def out(*parts):
    path = os.path.join(ROOT, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def save(img, *parts, **kw):
    path = out(*parts)
    img.save(path, **kw)
    print("asset   %s  %dx%d" % (os.path.relpath(path, ROOT), img.width, img.height))


def opaque(img, background=DARK):
    bg = Image.new("RGBA", img.size, background)
    return Image.alpha_composite(bg, img).convert("RGB")


def silhouette(img, color=(255, 255, 255)):
    """Keep the alpha channel, flatten every colour to `color`."""
    solid = Image.new("RGBA", img.size, color + (255,))
    solid.putalpha(img.getchannel("A"))
    return solid


def crop_alpha(img):
    """Trim fully transparent margins, so the art can be sized deliberately."""
    box = img.getchannel("A").getbbox()
    return img.crop(box) if box else img


def inset(img, canvas, ratio):
    """Centre `img` scaled to `ratio` of a transparent canvas x canvas square."""
    box = max(1, round(canvas * ratio))
    scale = min(box / img.width, box / img.height)
    size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    out_img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    out_img.paste(img.resize(size, Image.LANCZOS),
                  ((canvas - size[0]) // 2, (canvas - size[1]) // 2))
    return out_img


def copy_source(source, *parts):
    path = out(*parts)
    shutil.copyfile(os.path.join(HERE, source), path)
    print("asset   %s  (svg)" % os.path.relpath(path, ROOT))


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


def build_assets():
    icon = render("emblem.svg", 1024)

    # --- shared / Linux ---------------------------------------------------
    save(icon, "res", "icon.png")
    save(icon, "res", "mac-icon.png")
    for size in (32, 64, 128):
        save(icon.resize((size, size), Image.LANCZOS), "res", "%dx%d.png" % (size, size))
    save(icon.resize((256, 256), Image.LANCZOS), "res", "128x128@2x.png")
    save(icon, "res", "icon.ico", format="ICO",
         sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    copy_source("emblem.svg", "res", "scalable.svg")
    copy_source("emblem.svg", "res", "logo.svg")

    # --- trays ------------------------------------------------------------
    mono = crop_alpha(render("mark-mono.svg", 512))
    save(inset(silhouette(mono), 48, 0.86), "res", "mac-tray-dark-x2.png")
    save(inset(silhouette(mono, (0, 0, 0)), 48, 0.86), "res", "mac-tray-light-x2.png")
    save(icon, "res", "tray-icon.ico", format="ICO",
         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)])

    # --- Flutter ----------------------------------------------------------
    copy_source("emblem.svg", "flutter", "assets", "icon.svg")
    save(icon.resize((512, 512), Image.LANCZOS), "flutter", "assets", "icon.png")
    # loadLogo() renders inside a 300x60 box; ship it at 4x for hidpi screens.
    save(render_fit("logo-light.svg", 1200, 240), "flutter", "assets", "logo_light.png")
    save(render_fit("logo-dark.svg", 1200, 240), "flutter", "assets", "logo_dark.png")
    copy_source("logo-header.svg", "res", "logo-header.svg")

    # --- Windows ----------------------------------------------------------
    save(icon, "flutter", "windows", "runner", "resources", "app_icon.ico", format="ICO",
         sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    # --- macOS ------------------------------------------------------------
    save(icon, "flutter", "macos", "Runner", "AppIcon.icns", format="ICNS")

    # --- Android ----------------------------------------------------------
    mark_img = crop_alpha(render("mark.svg", 1024))
    for density, (launcher, foreground, stat) in ANDROID_DENSITIES.items():
        base = ("flutter", "android", "app", "src", "main", "res", "mipmap-" + density)
        square = icon.resize((launcher, launcher), Image.LANCZOS)
        save(square, *base, "ic_launcher.png")
        save(square, *base, "ic_launcher_round.png")
        # Adaptive icons keep only the inner 72/108 of the canvas visible.
        save(inset(mark_img, foreground, 72 / 108), *base, "ic_launcher_foreground.png")
        save(inset(silhouette(mono), stat, 0.92), *base, "ic_stat_logo.png")
    save(icon.resize((256, 256), Image.LANCZOS),
         "fastlane", "metadata", "android", "en-US", "images", "icon.png")

    # --- Windows installer (WiX pulls these in via res/msi/preprocess.py) --
    build_msi_bitmaps()

    # --- iOS (no alpha channel allowed) -----------------------------------
    for size, scale in IOS_ICONS:
        px = int(round(size * scale))
        name = "Icon-App-%gx%g@%dx.png" % (size, size, scale)
        save(opaque(icon.resize((px, px), Image.LANCZOS)),
             "flutter", "ios", "Runner", "Assets.xcassets", "AppIcon.appiconset", name)


# WiX fixes the size of both dialog bitmaps; the left MSI_DIALOG_ART_W pixels
# of the large one are artwork, the rest sits behind the installer's text.
MSI_BANNER = (493, 58)
MSI_DIALOG = (493, 312)
MSI_DIALOG_ART_W = 164


def build_msi_bitmaps():
    target = os.path.join(HERE, "msi")
    os.makedirs(target, exist_ok=True)

    def store(img, name):
        path = os.path.join(target, name)
        img.save(path, format="BMP")
        print("asset   %s  %dx%d" % (os.path.relpath(path, ROOT), img.width, img.height))

    w, h = MSI_BANNER
    banner = Image.new("RGBA", MSI_BANNER, WHITE)
    logo = render_fit("logo-light.svg", round(w * 0.46), h - 16)
    banner.alpha_composite(logo, (w - logo.width - 14, (h - logo.height) // 2))
    store(banner.convert("RGB"), "WixUIBannerBmp.bmp")

    w, h = MSI_DIALOG
    dialog = Image.new("RGBA", MSI_DIALOG, WHITE)
    dialog.alpha_composite(Image.new("RGBA", (MSI_DIALOG_ART_W, h), DARK))
    mark_art = inset(crop_alpha(render("mark.svg", 512)), MSI_DIALOG_ART_W, 0.56)
    word_w = round(MSI_DIALOG_ART_W * 0.62)
    word = render("wordmark-mono.svg", word_w, round(word_w * WORDMARK_H / WORDMARK_W))
    top = (h - (mark_art.height + word.height)) // 2
    dialog.alpha_composite(mark_art, (0, top))
    dialog.alpha_composite(word, ((MSI_DIALOG_ART_W - word.width) // 2, top + mark_art.height))
    store(dialog.convert("RGB"), "WixUIDialogBmp.bmp")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild-sources", action="store_true",
                        help="redraw the SVG sources, discarding dropped-in artwork")
    args = parser.parse_args()
    write_sources(force=args.rebuild_sources)
    build_assets()


if __name__ == "__main__":
    main()
