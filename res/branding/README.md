# Boa Safra branding

This client ships with the Boa Safra identity instead of the upstream RustDesk
one. Everything visual is derived from a handful of SVG sources in
[`boasafra/`](boasafra), so the whole application — desktop, mobile, tray and
the Windows installer — can be re-skinned by editing those sources and running
one script.

## Sources

| File | What it is | Where it ends up |
| --- | --- | --- |
| `emblem.svg` | the square mark on a rounded green tile | every application icon |
| `emblem-square.svg` | the same mark, hard-edged | reference / print |
| `mark.svg` | the S and its seed, transparent background | Android adaptive icon, installer panel |
| `mark-mono.svg` | the mark in a single colour | tray icons, Android status bar |
| `logo-light.svg` | full lockup for light backgrounds | the app's home screen in light theme |
| `logo-dark.svg` | full lockup for dark backgrounds | the app's home screen in dark theme |
| `logo-dark-mono.svg` | all-white lockup | alternative for `logo-dark.svg` |
| `logo-header.svg` | lockup on an opaque canvas | the README banner |
| `wordmark-light.svg` / `wordmark-mono.svg` | "BOA SAFRA" without the mark | installer side panel |
| `msi/*.bmp` | WiX banner and dialog artwork | the Windows installer |

## Regenerating everything

```sh
pip install cairosvg pillow fonttools
python3 res/branding/boasafra/generate.py
```

That rewrites every icon, logo and installer bitmap in the repository from the
sources above. It is safe to re-run: the outputs are deterministic.

## Dropping in the official artwork

The reconstruction in `generate.py` was drawn from the Boa Safra logo rather
than exported from the original files. To replace it with the official art:

1. Overwrite `boasafra/emblem.svg`, `boasafra/logo-light.svg` and
   `boasafra/logo-dark.svg` with the real files. A `.png` with the same base
   name is used in preference to the `.svg`, so bitmap artwork works too —
   supply it at 1024x1024 for the emblem.
2. Do the same for `mark.svg` and `mark-mono.svg` if you have transparent
   versions of the mark; otherwise leave them, they only feed the Android
   adaptive icon and the tray.
3. Run the command above.

Do **not** pass `--rebuild-sources` afterwards: that flag redraws the sources
from the vector definition in `generate.py` and would discard the real art.

## Brand colours

| Token | Hex | Used for |
| --- | --- | --- |
| dark green | `#1B5632` | icon background, "SAFRA", Android adaptive background |
| light green | `#8CBB2E` | the seed, "BOA" |
| white | `#FFFFFF` | the S, reversed lockups |

`#1B5632` is also set in
`flutter/android/app/src/main/res/values/ic_launcher_background.xml`; change it
there too if the palette moves.

## What is *not* rebranded

The binary, the Linux package and service names, the configuration directory
and the `rustdesk://` URI scheme are all still `rustdesk`. That keeps
`build.py` and every packaging recipe working unchanged. Only what the user
sees was renamed to "Boa Safra Acesso Remoto":

- `res/rustdesk.desktop`, `res/rustdesk-link.desktop` (Linux launcher)
- `flutter/android/app/src/main/AndroidManifest.xml` and `res/values/strings.xml`
- `flutter/windows/runner/Runner.rc` (executable properties)
- `flutter/macos/Runner/Info.plist` (`CFBundleDisplayName`)

Strings that come from the Rust side at runtime — the window title, the tray
tooltip, the About box — still read "RustDesk", because they resolve through
`hbb_common::config::APP_NAME`, which lives in the `libs/hbb_common` submodule.
