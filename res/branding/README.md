# Boa Safra branding

Every icon, logo and installer bitmap in this repository is generated from two
files, and those two files are the official Boa Safra artwork:

| File | What it is |
| --- | --- |
| [`boasafra/logo-light.svg`](boasafra/logo-light.svg) | the full lockup, for light backgrounds |
| [`boasafra/logo-dark.svg`](boasafra/logo-dark.svg) | the full lockup reversed, for dark backgrounds |

There is deliberately no third file for the square mark. The generator crops it
out of the lockup by measuring the rendered drawing — it finds the widest empty
column between the mark and the wordmark — so the crop follows the artwork
instead of being a second copy that can drift from it.

## Regenerating

```sh
pip install cairosvg pillow numpy
python3 res/branding/boasafra/generate.py
```

That rewrites roughly fifty files: the Linux icon set, the Windows `.ico`, the
macOS `.icns`, the Android launcher, adaptive and status-bar icons across five
densities, the full iOS icon set, the tray icons, the in-app logo for both
themes, the README banner, and the two WiX installer bitmaps. It is
deterministic and safe to re-run.

To update the brand, replace the two SVGs and run it again. Nothing else needs
editing.

## How the two lockups are used

Both draw the mark on **transparency**, so anything square has to supply its own
ground. That is what decides which source feeds which asset:

- **Application icons** take the mark from `logo-light.svg` — dark green and
  olive — and set it on white, inset slightly so it does not read as a crop.
- **Anything on a dark ground** — the macOS menu bar, the Android status bar,
  the installer's side panel — takes the mark from `logo-dark.svg`, which is
  already the reversed, white version. The light-theme tray icon is that same
  silhouette painted black.
- **The in-app logo** uses each lockup whole, picked by theme: `loadLogo()` in
  `flutter/lib/common.dart` resolves `assets/logo_light.png` or
  `assets/logo_dark.png` from `Theme.of(context).brightness`.

The Illustrator `<style>` block is inlined into presentation attributes on every
SVG that ships, because `flutter_svg` and some icon loaders ignore CSS.

## Colours

| Token | Hex | Where |
| --- | --- | --- |
| dark green | `#304929` | the mark, "SAFRA", the installer's side panel |
| light green | `#9DAF40` | the seed, "BOA" |
| white | `#FFFFFF` | the icon ground, the reversed lockup |

Both greens are read straight from the artwork; the generator does not invent
them. The one place a colour is written by hand is
`flutter/android/app/src/main/res/values/ic_launcher_background.xml`, which is
white to match the icon ground.

## Naming

The identity (`BoaSafra`), the display name (`Boa Safra Acesso Remoto`) and the
binary/package name (`boasafra`) are documented in
[`BOASAFRA.md`](../../BOASAFRA.md), together with the version scheme and how to
build the Windows installer. This file covers the artwork only.
