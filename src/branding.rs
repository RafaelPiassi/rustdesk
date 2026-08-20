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

/// Install the brand name into the global configuration.
///
/// Must run before anything reads the configuration, since the config
/// directory is derived from the name. A signed custom-client config loaded
/// afterwards still wins, which is why callers apply this first.
pub fn apply() {
    *hbb_common::config::APP_NAME.write().unwrap() = APP_NAME.to_owned();
}
