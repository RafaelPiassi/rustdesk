//! Boa Safra brand identity.
//!
//! Everything the running application calls itself derives from [`APP_NAME`]:
//! the configuration directory, the Windows service and registry keys, the
//! `boasafra://` URI scheme, the window title, the tray tooltip, and — through
//! [`crate::lang`], which rewrites "RustDesk" in every translated string once
//! [`crate::is_rustdesk`] is false — the whole user interface.
//!
//! That is why the name is a single alphanumeric token rather than the longer
//! marketing name: `crate::get_uri_prefix` lowercases it into a URI scheme, and
//! `lang::translate` substitutes it into running text. The marketing name is
//! [`DISPLAY_NAME`], and it is applied by the platform packaging — the Linux
//! desktop entry, the Android label, the Windows executable properties and the
//! macOS `CFBundleDisplayName` — not from here.
//!
//! The build and packaging scripts carry the same names independently; see
//! `BOASAFRA.md` for the full map and what to change together.

/// The name the application answers to. Alphanumeric, no spaces.
pub const APP_NAME: &str = "BoaSafra";

/// The full product name, for anywhere a human reads it outside the app.
pub const DISPLAY_NAME: &str = "Boa Safra Acesso Remoto";

/// The vendor, for executable metadata and installer properties.
pub const COMPANY: &str = "Boa Safra";

/// The license panel clients activate and revalidate against, e.g.
/// `https://licencas.example.com`. A `BOASAFRA_LICENSE_SERVER` build
/// environment variable overrides it, and the `license-server` option
/// overrides both at run time.
pub const LICENSE_SERVER: &str = "http://Rafael-PC:8000";

/// The license panel's Ed25519 public key, base64. The panel shows it on its
/// "Chave pública" page. A `BOASAFRA_LICENSE_PUBLIC_KEY` build environment
/// variable overrides it. Without one, every license check fails.
pub const LICENSE_PUBLIC_KEY: &str = "2WTuf0KVCCJkt/mjRiE2PmkR0SJs8BXYq0V4ceFH3Ok=";

/// The ID server (hbbs) a fresh install uses, e.g. `192.168.0.10`. The relay
/// is derived from it. A `BOASAFRA_RENDEZVOUS_SERVER` build environment
/// variable overrides it. Empty means the public RustDesk servers.
pub const RENDEZVOUS_SERVER: &str = "Rafael-PC";

/// That server's public key (the contents of hbbs's `id_ed25519.pub`). A
/// `BOASAFRA_RS_PUB_KEY` build environment variable overrides it.
pub const RS_PUB_KEY: &str = "cacP1iQMtqW6mRLyjAGs2ir2M6S8ZDnB8m69uFHasKU=";

/// Install the brand name into the global configuration.
///
/// Must run before anything reads the configuration, since the config
/// directory is derived from the name. A signed custom-client config loaded
/// afterwards still wins, which is why callers apply this first.
pub fn apply() {
    *hbb_common::config::APP_NAME.write().unwrap() = APP_NAME.to_owned();
    apply_default_server();
}

/// Point a fresh install at the build's own server. These are defaults, so a
/// server set in the settings, or by a custom-client config, still wins.
fn apply_default_server() {
    use hbb_common::config::{keys, DEFAULT_SETTINGS};
    let defaults = [
        (
            keys::OPTION_CUSTOM_RENDEZVOUS_SERVER,
            option_env!("BOASAFRA_RENDEZVOUS_SERVER").unwrap_or(""),
            RENDEZVOUS_SERVER,
        ),
        (
            keys::OPTION_KEY,
            option_env!("BOASAFRA_RS_PUB_KEY").unwrap_or(""),
            RS_PUB_KEY,
        ),
    ];
    let mut settings = DEFAULT_SETTINGS.write().unwrap();
    for (key, build_env, constant) in defaults {
        let value = Some(build_env.trim())
            .filter(|v| !v.is_empty())
            .unwrap_or(constant);
        if !value.is_empty() {
            settings.insert(key.to_owned(), value.to_owned());
        }
    }
}
