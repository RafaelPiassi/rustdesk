# Boa Safra Acesso Remoto

This repository is the Boa Safra build of RustDesk. It is a full rebrand: the
application installs as `boasafra`, stores its configuration under its own
name, registers the `boasafra://` URL scheme, and carries the Boa Safra logo on
every platform and in the Windows installer.

Everything below the branding is upstream RustDesk — see [README.md](README.md)
for the project documentation.

## Names

The rebrand uses two names, and the difference matters.

| | Value | Where it comes from | What it drives |
| --- | --- | --- | --- |
| Identity | `BoaSafra` | [`src/branding.rs`](src/branding.rs) | the configuration directory, the Windows service and registry keys, the `boasafra://` scheme, the window title, the tray tooltip, and every UI string — `lang::translate` substitutes it wherever the upstream text says "RustDesk" |
| Display name | `Boa Safra Acesso Remoto` | the platform packaging | the Linux launcher, the Android label, the Windows executable properties and installer title, the macOS `CFBundleDisplayName` |
| Binary / package | `boasafra` | `Cargo.toml`, `BINARY_NAME`, `build.py` | the executable, the `.deb`/`.rpm`/AppImage/Flatpak package names, the install directories |

The identity is a single alphanumeric token on purpose: `get_uri_prefix()`
lowercases it into a URL scheme, and the MSI derives its registry key root from
it the same way. Both land on `boasafra`, which is what makes the client and
the installer agree about `boasafra://` links.

To change the identity, edit `src/branding.rs` and the `--app-name` default in
`res/msi/preprocess.py` together.

## Versioning

`version` in `Cargo.toml` is **the upstream RustDesk version this build is
based on**, not a marketing number. It goes on the wire during the handshake,
and peers gate features on it (`get_version_number(&peer.version) >= …`), so
lowering it would make other clients treat this one as old and silently
disable features. Leave it tracking upstream.

Boa Safra releases are identified by a git tag instead:

```
boasafra-v<upstream version>-<release>
```

so the first release off RustDesk 1.4.9 is `boasafra-v1.4.9-1`, the next
rebuild of the same base is `boasafra-v1.4.9-2`, and rebasing onto RustDesk
1.5.0 starts `boasafra-v1.5.0-1`.

Two things follow from this:

- The MSI declares `AllowSameVersionUpgrades="yes"`, so installing a newer
  build of the same upstream version upgrades in place rather than refusing.
  Its `ProductVersion` also carries a generated fourth component
  (`--revision-version`, minutes since the epoch) so each build is distinct.
- CI reads `VERSION` out of `Cargo.toml`, so a version bump is a one-line
  change and every published artifact follows it.

## Building the Windows installer

Two artifacts come out of a Windows build, both usable as installers:

| File | What it is |
| --- | --- |
| `boasafra-<version>-x86_64.msi` | the MSI. Installs per-machine, registers the service, the `boasafra://` handler and the shortcuts. Use this for a managed rollout. |
| `boasafra-<version>-x86_64.exe` | the self-extracting installer. Single file, no MSI engine, convenient for sending to one machine. |

### Through GitHub Actions (recommended)

The repository's own pipeline builds both. It has never run on this fork, so
Actions has to be enabled once:

1. Open the repository on GitHub → **Actions** tab. If it shows
   "Workflows aren't being run on this forked repository", click
   **I understand my workflows, go ahead and enable them**.
2. In the left sidebar pick **Flutter Nightly Build** → **Run workflow** →
   choose the branch → **Run workflow**.
3. Wait. The Windows jobs are `x86_64-pc-windows-msvc` (and
   `aarch64-pc-windows-msvc` for Windows on ARM). A cold run takes roughly an
   hour, mostly vcpkg.
4. Collect the result:
   - **Releases → the `nightly` pre-release**: `boasafra-1.4.9-x86_64.msi` and
     `boasafra-1.4.9-x86_64.exe`.
   - **The workflow run → Artifacts**: `boasafra-unsigned-windows-x86_64`, a
     zip of the built application folder. That is the portable form — no
     installer, just unzip and run `boasafra.exe`.

Two things to expect on a fork:

- The jobs for the other platforms may fail (they need secrets this fork does
  not have). `fail-fast` is off, so the Windows jobs still finish and publish.
- The signing steps are skipped without the `SIGN_BASE_URL` secret, so the
  binaries are unsigned and Windows SmartScreen will warn on first run. To
  avoid that, sign the MSI and the exe with your own code-signing certificate,
  or distribute through Group Policy / Intune where SmartScreen does not apply.

### Locally on Windows

Mirrors what the CI job does. You need Visual Studio 2022 Build Tools (Desktop
development with C++), Rust 1.75 (msvc), Python 3, Flutter 3.24.5, LLVM 15.0.6,
nasm, and vcpkg.

```powershell
git clone --recursive https://github.com/RafaelPiassi/rustdesk
cd rustdesk

# native dependencies
$env:VCPKG_ROOT = "C:\vcpkg"
vcpkg install --triplet x64-windows-static --x-install-root="$env:VCPKG_ROOT/installed"

# the dart <-> rust bridge
cargo install flutter_rust_bridge_codegen --version 1.80.1 --features uuid --locked
flutter_rust_bridge_codegen --rust-input ./src/flutter_ffi.rs --dart-output ./flutter/lib/generated_bridge.dart

# the application, plus the self-extracting installer
python build.py --flutter --hwcodec --vram
```

That leaves `boasafra-1.4.9-install.exe` in the repository root and the
application in `flutter/build/windows/x64/runner/Release`.

For the MSI, point the preprocessor at that folder and build the WiX solution
(WiX v4, restored through nuget):

```powershell
Move-Item .\flutter\build\windows\x64\runner\Release .\boasafra
cd res\msi
python preprocess.py --arp -d ..\..\boasafra
nuget restore msi.sln
msbuild msi.sln -p:Configuration=Release -p:Platform=x64 /p:TargetVersion=Windows10
```

The MSI lands in `res\msi\Package\bin\x64\Release\en-us\Package.msi`.

`preprocess.py` already defaults to the Boa Safra identity, so no `--app-name`
is needed. It also copies the branded installer artwork from
`res/branding/boasafra/msi` into the generated `Package/Resources`.

## What is deliberately not rebranded

- **The Rust crate and library names** (`rustdesk`, `librustdesk`). They are
  internal, and the Dart FFI loads the library by filename.
- **The mobile bundle identifiers** — Android `applicationId` and the iOS
  `PRODUCT_BUNDLE_IDENTIFIER` are still `com.carriez.*`. Changing them means
  new provisioning profiles and a new store listing, and breaks the upgrade
  path for anything already installed. Change them only when you are ready to
  publish to the stores; the visible app name and icons are already Boa Safra.
- **Third-party component names** — the RustDesk printer driver, the IDD
  virtual display driver and the top-most-window helper keep the names their
  signed binaries actually have.
- **Internal identifiers** — the D-Bus name, the named pipes, the temporary
  file prefixes and the virtual-display driver id. They are invisible to users,
  they only have to agree between our own processes, and some of them must
  match a signed driver.
- **Upstream URLs** in comments and in the build scripts' download steps, which
  still point at the RustDesk project where the artefacts genuinely come from.

## Branding assets

The logo, icons and installer artwork all come from a handful of SVG sources
and one script — see [`res/branding/README.md`](res/branding/README.md) for how
to regenerate them or drop in the official artwork.
