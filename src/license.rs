//! Boa Safra per-machine licensing.
//!
//! A license is a serial issued by the license panel (`license-panel/`). The
//! panel binds it to one machine on first activation and keeps it valid for
//! the period it was issued with (one year by default).
//!
//! The client never decides validity on its own. It asks the panel, which
//! answers with a status signed by the panel's Ed25519 key, and the client only
//! trusts a status that verifies against the public key compiled into this
//! build and names this machine and this serial. Without a fresh, signed,
//! active status the machine neither accepts nor makes remote connections.
//!
//! Validation is online only: the process that accepts connections asks the
//! panel again every [`CHECK_INTERVAL_SECS`], and a status older than
//! [`GRACE_SECS`] stops counting, so a machine that cannot reach the panel is
//! blocked once the grace period runs out.

use crate::branding;
use hbb_common::{
    anyhow::anyhow, bail, config::Config, log, sodiumoxide::crypto::sign, ResultType,
};
use serde_derive::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

const OPTION_SERIAL: &str = "license-serial";
const OPTION_STATUS: &str = "license-status";
const OPTION_SERVER: &str = "license-server";

const CHECK_INTERVAL_SECS: u64 = 60 * 60;
const RETRY_INTERVAL_SECS: u64 = 5 * 60;
/// How long a signed status keeps counting when the panel cannot be reached.
const GRACE_SECS: i64 = 24 * 60 * 60;
/// A status stamped this far in the future means the clock was turned back.
const CLOCK_SKEW_SECS: i64 = 10 * 60;
const EXPIRING_SOON_DAYS: i64 = 30;
const REQUEST_TIMEOUT_SECS: u64 = 15;

pub const REASON_NONE: &str = "license-none-tip";
pub const REASON_EXPIRED: &str = "license-expired-tip";
pub const REASON_REVOKED: &str = "license-revoked-tip";
pub const REASON_OTHER_MACHINE: &str = "license-other-machine-tip";
pub const REASON_INVALID: &str = "license-invalid-tip";
pub const REASON_OFFLINE: &str = "license-offline-tip";
pub const REASON_MISCONFIGURED: &str = "license-misconfigured-tip";
/// What a peer that tries to connect to an unlicensed machine is told.
pub const REASON_REMOTE: &str = "license-remote-tip";

/// The status the panel signs. Field names are the panel's wire format.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
pub struct Status {
    pub serial: String,
    pub machine: String,
    pub state: String,
    #[serde(default)]
    pub customer: String,
    #[serde(default)]
    pub expires_at: i64,
    pub checked_at: i64,
}

#[derive(Deserialize, Default)]
struct Response {
    #[serde(default)]
    token: String,
    #[serde(default)]
    error: String,
}

/// Whether this process may accept a connection, judged from its own config.
///
/// Meant for the process that accepts connections, which owns the config.
pub fn check() -> Result<(), &'static str> {
    evaluate_options(|k| Config::get_option(k)).map(|_| ())
}

/// Whether this machine may make an outgoing connection.
pub async fn ensure_licensed() -> ResultType<()> {
    // The UI process's copy of the config can lag behind the service's, so ask
    // the service, which is the one that revalidates.
    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    let options = crate::ipc::get_options_async().await;
    #[cfg(any(target_os = "android", target_os = "ios"))]
    let options = Config::get_options();
    evaluate_options(|k| options.get(k).cloned().unwrap_or_default())
        .map(|_| ())
        .map_err(|reason| anyhow!(reason))
}

/// The license state for the UI, as JSON.
pub fn status_json() -> String {
    status_json_with(|k| crate::ui_interface::get_option(k))
}

/// The license state as the service sees it, as JSON, for the command line.
#[cfg(not(any(target_os = "android", target_os = "ios")))]
pub fn service_status_json() -> String {
    let options = crate::ipc::get_options();
    status_json_with(|k| options.get(k).cloned().unwrap_or_default())
}

fn status_json_with(get: impl Fn(&str) -> String) -> String {
    let serial = get(OPTION_SERIAL);
    let now = hbb_common::get_time() / 1000;
    let status = load_status(&get(OPTION_STATUS), &serial);
    let result = evaluate(&serial, status.as_ref(), now);
    let (customer, expires_at) = status
        .as_ref()
        .map(|s| (s.customer.clone(), s.expires_at))
        .unwrap_or_default();
    let days_left = if expires_at > 0 {
        (expires_at - now).div_euclid(24 * 60 * 60)
    } else {
        0
    };
    serde_json::json!({
        "licensed": result.is_ok(),
        "reason": result.err().unwrap_or_default(),
        "serial": serial,
        "customer": customer,
        "expires_at": expires_at,
        "days_left": days_left,
        "expiring_soon": result.is_ok() && days_left < EXPIRING_SOON_DAYS,
        "machine": machine_fingerprint(),
    })
    .to_string()
}

/// Activate `serial` on this machine. Blocking; returns JSON for the UI.
///
/// Must not run on a Tokio thread: it uses the blocking HTTP client and, on
/// desktop, the blocking IPC helpers.
pub fn activate(serial: &str) -> String {
    let result = request("/api/v1/activate", serial).and_then(|(status, token)| {
        let reason = evaluate(&status.serial, Some(&status), hbb_common::get_time() / 1000).err();
        if reason.is_none() {
            store(OPTION_SERIAL, &status.serial);
            store(OPTION_STATUS, &token);
        }
        Ok(reason)
    });
    let reason = match result {
        Ok(reason) => reason.unwrap_or_default().to_owned(),
        Err(err) => {
            log::warn!("license activation failed: {err}");
            err.to_string()
        }
    };
    serde_json::json!({ "ok": reason.is_empty(), "reason": reason }).to_string()
}

/// Save an option where the process that owns the config will see it.
fn store(key: &str, value: &str) {
    // Through the service, one key at a time: it merges into the service's
    // options rather than replacing them with this process's copy.
    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    crate::ipc::set_option(key, value);
    #[cfg(any(target_os = "android", target_os = "ios"))]
    Config::set_option(key.to_owned(), value.to_owned());
}

/// Revalidate the stored serial with the panel, periodically, for good.
///
/// Runs in the process that owns the config: the service on desktop, the app
/// itself on mobile.
pub fn start_check_thread() {
    static ONCE: std::sync::Once = std::sync::Once::new();
    ONCE.call_once(|| {
        std::thread::spawn(check_loop);
    });
}

fn check_loop() {
    loop {
        let serial = Config::get_option(OPTION_SERIAL);
        let wait = if serial.is_empty() {
            RETRY_INTERVAL_SECS
        } else {
            match request("/api/v1/validate", &serial) {
                // A different serial means it was replaced while we asked.
                Ok((status, token)) if Config::get_option(OPTION_SERIAL) == status.serial => {
                    if status.state != "active" {
                        log::warn!("license {}: {}", status.serial, status.state);
                    }
                    Config::set_option(OPTION_STATUS.to_owned(), token);
                    CHECK_INTERVAL_SECS
                }
                Ok(_) => RETRY_INTERVAL_SECS,
                Err(err) => {
                    log::warn!("license check failed: {err}");
                    RETRY_INTERVAL_SECS
                }
            }
        };
        std::thread::sleep(std::time::Duration::from_secs(wait));
    }
}

fn evaluate_options(get: impl Fn(&str) -> String) -> Result<Status, &'static str> {
    let serial = get(OPTION_SERIAL);
    let status = load_status(&get(OPTION_STATUS), &serial);
    evaluate(&serial, status.as_ref(), hbb_common::get_time() / 1000).cloned()
}

fn load_status(token: &str, serial: &str) -> Option<Status> {
    let pk = public_key()?;
    if token.is_empty() || serial.is_empty() {
        return None;
    }
    decode(token, &pk, serial, &machine_fingerprint())
}

fn evaluate<'a>(
    serial: &str,
    status: Option<&'a Status>,
    now: i64,
) -> Result<&'a Status, &'static str> {
    if public_key().is_none() || server_url().is_empty() {
        return Err(REASON_MISCONFIGURED);
    }
    if serial.is_empty() {
        return Err(REASON_NONE);
    }
    let Some(status) = status else {
        return Err(REASON_OFFLINE);
    };
    judge(status, now)
}

fn judge(status: &Status, now: i64) -> Result<&Status, &'static str> {
    match status.state.as_str() {
        "active" => {}
        "expired" => return Err(REASON_EXPIRED),
        "revoked" => return Err(REASON_REVOKED),
        "bound_elsewhere" => return Err(REASON_OTHER_MACHINE),
        _ => return Err(REASON_INVALID),
    }
    if status.expires_at <= now {
        return Err(REASON_EXPIRED);
    }
    if status.checked_at > now + CLOCK_SKEW_SECS || now - status.checked_at > GRACE_SECS {
        return Err(REASON_OFFLINE);
    }
    Ok(status)
}

/// Verify a signed status and check it is about this serial on this machine.
fn decode(token: &str, pk: &sign::PublicKey, serial: &str, machine: &str) -> Option<Status> {
    let signed = crate::decode64(token).ok()?;
    let data = sign::verify(&signed, pk).ok()?;
    let status: Status = serde_json::from_slice(&data).ok()?;
    (normalize(&status.serial) == normalize(serial) && status.machine == machine).then_some(status)
}

fn request(path: &str, serial: &str) -> ResultType<(Status, String)> {
    let server = server_url();
    let Some(pk) = public_key() else {
        bail!(REASON_MISCONFIGURED);
    };
    if server.is_empty() {
        bail!(REASON_MISCONFIGURED);
    }
    let machine = machine_fingerprint();
    let url = format!("{server}{path}");
    let body = serde_json::json!({
        "serial": serial.trim(),
        "machine": machine,
        "id": Config::get_id(),
        "hostname": crate::common::hostname(),
        "platform": std::env::consts::OS,
        "version": crate::VERSION,
        "app": branding::APP_NAME,
    });
    let response: Response = crate::hbbs_http::create_http_client_with_url(&url)
        .post(&url)
        .timeout(std::time::Duration::from_secs(REQUEST_TIMEOUT_SECS))
        .json(&body)
        .send()
        .map_err(|err| {
            log::warn!("license server {url} unreachable: {err}");
            anyhow!(REASON_OFFLINE)
        })?
        .json()
        .unwrap_or_default();
    if response.token.is_empty() {
        log::warn!(
            "license server {url} refused the request: {}",
            response.error
        );
        bail!(REASON_OFFLINE);
    }
    let Some(status) = decode(&response.token, &pk, serial, &machine) else {
        log::warn!("license server {url} answered with a status that does not verify");
        bail!(REASON_OFFLINE);
    };
    Ok((status, response.token))
}

/// What the panel knows this machine by. Stable across reinstalls, and not the
/// raw machine id, which the panel has no use for.
fn machine_fingerprint() -> String {
    let mut hasher = Sha256::new();
    hasher.update(b"BoaSafra-license:");
    hasher.update(hbb_common::get_uuid());
    hex::encode(hasher.finalize())
}

/// The panel's comparable form of a serial; must match `serial_key` there.
fn normalize(serial: &str) -> String {
    serial
        .chars()
        .filter(char::is_ascii_alphanumeric)
        .map(|c| match c.to_ascii_uppercase() {
            'O' => '0',
            'I' | 'L' => '1',
            c => c,
        })
        .collect()
}

/// A build-time override, so CI can inject the deployment's values.
fn configured(build_env: Option<&'static str>, default: &'static str) -> &'static str {
    build_env
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .unwrap_or(default)
}

fn public_key() -> Option<sign::PublicKey> {
    let pk = configured(
        option_env!("BOASAFRA_LICENSE_PUBLIC_KEY"),
        branding::LICENSE_PUBLIC_KEY,
    );
    sign::PublicKey::from_slice(&crate::decode64(pk).ok()?)
}

fn server_url() -> String {
    let custom = Config::get_option(OPTION_SERVER);
    let url = if custom.trim().is_empty() {
        configured(
            option_env!("BOASAFRA_LICENSE_SERVER"),
            branding::LICENSE_SERVER,
        )
    } else {
        custom.trim()
    };
    url.trim_end_matches('/').to_owned()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn status(state: &str, expires_at: i64, checked_at: i64) -> Status {
        Status {
            serial: "BSAF-AAAA-BBBB-CCCC-DDDD".to_owned(),
            machine: "m1".to_owned(),
            state: state.to_owned(),
            customer: "Cliente".to_owned(),
            expires_at,
            checked_at,
        }
    }

    #[test]
    fn decode_requires_signature_serial_and_machine() {
        let (pk, sk) = sign::gen_keypair();
        let s = status("active", 2_000, 1_000);
        let token = crate::encode64(sign::sign(&serde_json::to_vec(&s).unwrap(), &sk));
        assert_eq!(
            decode(&token, &pk, "bsaf aaaa bbbb cccc dddd", "m1"),
            Some(s)
        );
        assert_eq!(decode(&token, &pk, "BSAF-AAAA-BBBB-CCCC-EEEE", "m1"), None);
        assert_eq!(decode(&token, &pk, "BSAF-AAAA-BBBB-CCCC-DDDD", "m2"), None);
        let (other_pk, _) = sign::gen_keypair();
        assert_eq!(
            decode(&token, &other_pk, "BSAF-AAAA-BBBB-CCCC-DDDD", "m1"),
            None
        );
    }

    #[test]
    fn judge_states_and_times() {
        let day = 24 * 60 * 60;
        let now = 100 * day;
        assert!(judge(&status("active", now + day, now - 60), now).is_ok());
        assert_eq!(
            judge(&status("active", now - 1, now - 60), now),
            Err(REASON_EXPIRED)
        );
        assert_eq!(
            judge(&status("active", now + day, now - GRACE_SECS - 1), now),
            Err(REASON_OFFLINE)
        );
        assert_eq!(
            judge(&status("active", now + day, now + CLOCK_SKEW_SECS + 1), now),
            Err(REASON_OFFLINE)
        );
        assert_eq!(
            judge(&status("revoked", now + day, now), now),
            Err(REASON_REVOKED)
        );
        assert_eq!(
            judge(&status("bound_elsewhere", now + day, now), now),
            Err(REASON_OTHER_MACHINE)
        );
        assert_eq!(
            judge(&status("expired", now + day, now), now),
            Err(REASON_EXPIRED)
        );
        assert_eq!(
            judge(&status("invalid", now + day, now), now),
            Err(REASON_INVALID)
        );
    }
}
