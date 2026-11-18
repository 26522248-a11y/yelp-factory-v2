use std::net::ToSocketAddrs;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Manager, WindowEvent};

#[tauri::command]
fn app_info() -> serde_json::Value {
    serde_json::json!({
        "name": "YFCP",
        "version": env!("CARGO_PKG_VERSION"),
        "engine": "yelp-factory-v2"
    })
}

#[derive(serde::Serialize)]
struct AdminResponse {
    status: u16,
    body: serde_json::Value,
}

/// Hard limits for the relay. The admin API only serves small JSON payloads.
const MAX_BODY_BYTES: usize = 2 * 1024 * 1024;
const MAX_RESPONSE_BYTES: usize = 8 * 1024 * 1024;
const CONNECT_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(3);
const TOTAL_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(10);

fn is_loopback_ip(ip: std::net::IpAddr) -> bool {
    match ip {
        std::net::IpAddr::V4(v4) => v4.is_loopback(),
        std::net::IpAddr::V6(v6) => v6.is_loopback(),
    }
}

/// RFC1918 / link-local / CGNAT (Tailscale) / IPv6 ULA — safe enough for plain
/// HTTP inside a LAN or VPN, never for the public internet.
fn is_private_ip(ip: std::net::IpAddr) -> bool {
    match ip {
        std::net::IpAddr::V4(v4) => {
            v4.is_private()
                || v4.is_link_local()
                || v4.octets()[0] == 100 && (64..128).contains(&v4.octets()[1])
        }
        std::net::IpAddr::V6(v6) => {
            let first = v6.segments()[0];
            (first & 0xfe00) == 0xfc00 || (first & 0xffc0) == 0xfe80
        }
    }
}

fn resolve_addrs(host: &str, port: u16) -> Result<Vec<std::net::SocketAddr>, String> {
    (host, port)
        .to_socket_addrs()
        .map(|iter| iter.collect())
        .map_err(|e| format!("cannot resolve {host}: {e}"))
}

fn same_origin(a: &reqwest::Url, b: &reqwest::Url) -> bool {
    a.scheme() == b.scheme()
        && a.host_str().map(str::to_ascii_lowercase) == b.host_str().map(str::to_ascii_lowercase)
        && a.port_or_known_default() == b.port_or_known_default()
}

fn clean_host(url: &reqwest::Url) -> String {
    url.host_str()
        .unwrap_or_default()
        .trim_start_matches('[')
        .trim_end_matches(']')
        .to_string()
}

/// Validate an endpoint the operator wants to use for a remote engine.
/// Stores only the origin (`scheme://host:port`); public hosts must be HTTPS.
fn validate_remote_endpoint(raw: &str) -> Result<reqwest::Url, String> {
    let mut url = reqwest::Url::parse(raw).map_err(|e| format!("invalid url: {e}"))?;
    match url.scheme() {
        "http" | "https" => {}
        other => return Err(format!("scheme not allowed: {other}")),
    }
    if !url.username().is_empty() || url.password().is_some() {
        return Err("credentials in URL are not allowed".into());
    }
    let path = url.path();
    if !(path.is_empty() || path == "/") || url.query().is_some() || url.fragment().is_some() {
        return Err("endpoint must be scheme://host:port only (no path/query)".into());
    }

    let host = clean_host(&url);
    let port = url
        .port_or_known_default()
        .unwrap_or(if url.scheme() == "https" { 443 } else { 80 });

    if let Ok(ip) = host.parse::<std::net::IpAddr>() {
        if !is_loopback_ip(ip) && url.scheme() == "http" && !is_private_ip(ip) {
            return Err(
                "plain HTTP is only allowed for loopback or private/LAN addresses; use https"
                    .into(),
            );
        }
    } else if !host.eq_ignore_ascii_case("localhost") && url.scheme() == "http" {
        let addrs = resolve_addrs(&host, port)?;
        if addrs.is_empty()
            || !addrs
                .iter()
                .all(|addr| is_private_ip(addr.ip()) || is_loopback_ip(addr.ip()))
        {
            return Err(
                "plain HTTP is only allowed for loopback or private/LAN addresses; use https"
                    .into(),
            );
        }
    }

    url.set_path("");
    url.set_query(None);
    url.set_fragment(None);
    Ok(url)
}

#[derive(Debug)]
struct Target {
    url: reqwest::Url,
    /// Preserved Host header when the URL host was replaced by a pinned IP.
    host_header: Option<String>,
}

/// Validate and canonicalise a target URL.
///
/// Loopback (`127.0.0.0/8`, `::1`, `localhost`) is always allowed — this is the
/// single-machine mode. Any other host must exactly match the remote endpoint
/// stored by the operator (see `remote_endpoint_set`), which makes the webview's
/// reach a deliberate, persistent decision rather than an arbitrary SSRF.
///
/// Additional rules: redirects are disabled by the caller, paths cannot contain
/// `..`, remote plain HTTP must resolve to private/LAN addresses only, and
/// private HTTP hosts are resolved once and pinned to an IP (DNS rebinding).
fn resolve_target(raw: &str, remote: Option<&reqwest::Url>) -> Result<Target, String> {
    let lower_raw = raw.to_ascii_lowercase();
    if lower_raw.contains("/../") || lower_raw.ends_with("/..") || lower_raw.contains("%2e%2e") {
        return Err("path traversal is not allowed".into());
    }

    let url = reqwest::Url::parse(raw).map_err(|e| format!("invalid url: {e}"))?;
    let scheme = url.scheme();
    if scheme != "http" && scheme != "https" {
        return Err(format!("scheme not allowed: {scheme}"));
    }
    if !url.username().is_empty() || url.password().is_some() {
        return Err("credentials in URL are not allowed".into());
    }
    if url.path().is_empty() || !url.path().starts_with('/') {
        return Err("path must be absolute".into());
    }
    if url.path().to_ascii_lowercase().contains("..") {
        return Err("path traversal is not allowed".into());
    }

    let host = clean_host(&url);
    let port = url
        .port_or_known_default()
        .unwrap_or(if scheme == "https" { 443 } else { 80 });
    let remote_ok = remote.map(|r| same_origin(&url, r)).unwrap_or(false);
    let not_configured = || {
        "remote endpoint not configured — add it in Workspace settings → Console connection"
            .to_string()
    };

    if let Ok(ip) = host.parse::<std::net::IpAddr>() {
        if is_loopback_ip(ip) {
            return Ok(Target {
                url,
                host_header: None,
            });
        }
        if !remote_ok {
            return Err(not_configured());
        }
        if scheme == "http" && !is_private_ip(ip) {
            return Err("plain HTTP is only allowed for private/LAN addresses".into());
        }
        return Ok(Target {
            url,
            host_header: None,
        });
    }

    if host.eq_ignore_ascii_case("localhost") {
        if scheme != "http" {
            return Err("localhost only supports http".into());
        }
        let addrs = resolve_addrs(&host, port)?;
        if addrs.is_empty() || !addrs.iter().all(|addr| is_loopback_ip(addr.ip())) {
            return Err("localhost does not resolve to loopback".into());
        }
        let ip = addrs
            .iter()
            .map(|addr| addr.ip())
            .find(|ip| matches!(ip, std::net::IpAddr::V4(v4) if v4.is_loopback()))
            .or_else(|| {
                addrs
                    .iter()
                    .map(|addr| addr.ip())
                    .find(|ip| is_loopback_ip(*ip))
            })
            .ok_or_else(|| "localhost has no loopback address".to_string())?;
        let mut url = url;
        url.set_ip_host(ip)
            .map_err(|_| "cannot pin host to a loopback IP".to_string())?;
        return Ok(Target {
            url,
            host_header: None,
        });
    }

    // Remote host name.
    if !remote_ok {
        return Err(not_configured());
    }
    let addrs = resolve_addrs(&host, port)?;
    if addrs.is_empty() {
        return Err(format!("cannot resolve {host}"));
    }
    if addrs.iter().any(|addr| is_loopback_ip(addr.ip())) {
        return Err("remote endpoint must not resolve to loopback".into());
    }

    if scheme == "http" {
        if !addrs.iter().all(|addr| is_private_ip(addr.ip())) {
            return Err("plain HTTP is only allowed for private/LAN addresses; use https".into());
        }
        let ip = addrs
            .iter()
            .map(|addr| addr.ip())
            .find(|ip| matches!(ip, std::net::IpAddr::V4(_)))
            .unwrap_or_else(|| addrs[0].ip());
        let mut url = url;
        url.set_ip_host(ip)
            .map_err(|_| "cannot pin remote host to an IP".to_string())?;
        return Ok(Target {
            url,
            host_header: Some(format!("{host}:{port}")),
        });
    }

    // HTTPS keeps the hostname so certificate/SNI validation still applies.
    Ok(Target {
        url,
        host_header: None,
    })
}

fn allowed_method(method: &str) -> Result<reqwest::Method, String> {
    match method.to_ascii_uppercase().as_str() {
        "GET" => Ok(reqwest::Method::GET),
        "POST" => Ok(reqwest::Method::POST),
        other => Err(format!("method not allowed: {other}")),
    }
}

/// Relay one request to the engine admin API.
///
/// The engine binds to 127.0.0.1 and does not send CORS headers, so a webview
/// fetch from `tauri://localhost` is blocked. Doing the call in Rust sidesteps
/// that without changing the engine.
///
/// This is a security boundary: it is the only place the webview can ask the
/// shell to make a network request. Redirects are never followed, the method
/// and target are whitelisted, and the body/response sizes are capped.
#[tauri::command]
async fn admin_request(
    app: tauri::AppHandle,
    url: String,
    method: String,
    token: Option<String>,
    body: Option<serde_json::Value>,
) -> Result<AdminResponse, String> {
    let remote = read_remote_endpoint(&app);
    let target = resolve_target(&url, remote.as_ref())?;
    let http_method = allowed_method(&method)?;

    let payload = match body {
        Some(value) => {
            let bytes = serde_json::to_vec(&value).map_err(|e| format!("invalid body: {e}"))?;
            if bytes.len() > MAX_BODY_BYTES {
                return Err(format!(
                    "request body too large (max {MAX_BODY_BYTES} bytes)"
                ));
            }
            Some(bytes)
        }
        None => None,
    };

    let client = reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(CONNECT_TIMEOUT)
        .timeout(TOTAL_TIMEOUT)
        .build()
        .map_err(|e| e.to_string())?;

    let mut request = client.request(http_method, target.url);
    if let Some(host) = target.host_header {
        request = request.header(reqwest::header::HOST, host);
    }
    // The target was validated (loopback or the operator's stored remote
    // endpoint), so the token can never be forwarded to another host; redirects
    // are not followed either.
    if let Some(token) = token.filter(|t| !t.is_empty()) {
        request = request.bearer_auth(token);
    }
    if let Some(bytes) = payload {
        request = request
            .header(reqwest::header::CONTENT_TYPE, "application/json")
            .body(bytes);
    }

    let mut response = request.send().await.map_err(|e| e.to_string())?;
    let status = response.status().as_u16();

    if let Some(length) = response.content_length() {
        if length as usize > MAX_RESPONSE_BYTES {
            return Err("response too large".into());
        }
    }

    let mut buffer: Vec<u8> = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|e| e.to_string())? {
        if buffer.len() + chunk.len() > MAX_RESPONSE_BYTES {
            return Err("response too large".into());
        }
        buffer.extend_from_slice(&chunk);
    }

    let text = String::from_utf8_lossy(&buffer);
    let body =
        serde_json::from_str(&text).unwrap_or_else(|_| serde_json::Value::String(text.into()));

    Ok(AdminResponse { status, body })
}

const REMOTE_ENDPOINT_FILE: &str = "remote-endpoint.txt";

fn remote_endpoint_path(app: &tauri::AppHandle) -> Result<std::path::PathBuf, String> {
    let dir = app.path().app_config_dir().map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir.join(REMOTE_ENDPOINT_FILE))
}

fn read_remote_endpoint(app: &tauri::AppHandle) -> Option<reqwest::Url> {
    let path = remote_endpoint_path(app).ok()?;
    let raw = std::fs::read_to_string(path).ok()?;
    reqwest::Url::parse(raw.trim()).ok()
}

fn write_remote_endpoint(app: &tauri::AppHandle, url: &reqwest::Url) -> Result<(), String> {
    let path = remote_endpoint_path(app)?;
    std::fs::write(path, url.origin().ascii_serialization()).map_err(|e| e.to_string())
}

/// Read the remote engine origin the operator has approved for this machine.
#[tauri::command]
fn remote_endpoint_get(app: tauri::AppHandle) -> Result<Option<String>, String> {
    Ok(read_remote_endpoint(&app).map(|url| url.origin().ascii_serialization()))
}

/// Approve (and persist) a remote engine origin. Plain HTTP is only accepted for
/// loopback/private addresses; public hosts must use HTTPS.
#[tauri::command]
fn remote_endpoint_set(app: tauri::AppHandle, url: String) -> Result<String, String> {
    let parsed = validate_remote_endpoint(&url)?;
    write_remote_endpoint(&app, &parsed)?;
    Ok(parsed.origin().ascii_serialization())
}

#[tauri::command]
fn remote_endpoint_clear(app: tauri::AppHandle) -> Result<(), String> {
    let path = remote_endpoint_path(&app)?;
    match std::fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.to_string()),
    }
}

const KEYCHAIN_SERVICE: &str = "com.yfcp.console";
const KEYCHAIN_ACCOUNT: &str = "admin-api-token";

/// OS credential storage for the admin bearer token. On Windows this is the
/// Credential Manager (DPAPI-protected), so `settings.json` only keeps the URL.
mod token_store {
    #[cfg(windows)]
    fn entry() -> Result<keyring::Entry, String> {
        keyring::Entry::new(super::KEYCHAIN_SERVICE, super::KEYCHAIN_ACCOUNT)
            .map_err(|error| error.to_string())
    }

    #[cfg(windows)]
    pub fn get() -> Result<Option<String>, String> {
        match entry()?.get_password() {
            Ok(secret) => Ok(Some(secret)),
            Err(keyring::Error::NoEntry) => Ok(None),
            Err(error) => Err(error.to_string()),
        }
    }

    #[cfg(windows)]
    pub fn set(value: &str) -> Result<(), String> {
        entry()?
            .set_password(value)
            .map_err(|error| error.to_string())
    }

    #[cfg(windows)]
    pub fn delete() -> Result<(), String> {
        match entry()?.delete_credential() {
            Ok(()) => Ok(()),
            Err(keyring::Error::NoEntry) => Ok(()),
            Err(error) => Err(error.to_string()),
        }
    }

    #[cfg(not(windows))]
    pub fn get() -> Result<Option<String>, String> {
        Err("OS keychain is only implemented for Windows in this build".into())
    }

    #[cfg(not(windows))]
    pub fn set(_value: &str) -> Result<(), String> {
        Err("OS keychain is only implemented for Windows in this build".into())
    }

    #[cfg(not(windows))]
    pub fn delete() -> Result<(), String> {
        Ok(())
    }
}

#[tauri::command]
fn secret_get() -> Result<Option<String>, String> {
    token_store::get()
}

#[tauri::command]
fn secret_set(value: String) -> Result<(), String> {
    token_store::set(&value)
}

#[tauri::command]
fn secret_delete() -> Result<(), String> {
    token_store::delete()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_store::Builder::default().build())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_process::init())
        .invoke_handler(tauri::generate_handler![
            app_info,
            admin_request,
            remote_endpoint_get,
            remote_endpoint_set,
            remote_endpoint_clear,
            secret_get,
            secret_set,
            secret_delete
        ])
        .setup(|app| {
            let show = MenuItem::with_id(app, "show", "Show console", true, None::<&str>)?;
            let hide = MenuItem::with_id(app, "hide", "Hide to tray", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &hide, &quit])?;

            let _tray = TrayIconBuilder::with_id("main")
                .tooltip("YFCP — Yelp Factory Control Panel")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.unminimize();
                            let _ = w.set_focus();
                        }
                    }
                    "hide" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.hide();
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.unminimize();
                            let _ = w.set_focus();
                        }
                    }
                })
                .icon(app.default_window_icon().unwrap().clone())
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                // Keep the console in the tray unless the user explicitly quits.
                if window.label() == "main" {
                    let _ = window.hide();
                    api.prevent_close();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running YFCP");
}

#[cfg(test)]
mod admin_tests;
