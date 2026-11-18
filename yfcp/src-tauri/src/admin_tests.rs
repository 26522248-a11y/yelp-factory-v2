//! Security tests for the `admin_request` relay (the app's only network surface).
//! Kept in its own module so Clippy's `items_after_test_module` lint stays happy.

use super::*;

fn allow(raw: &str) -> reqwest::Url {
    validate_remote_endpoint(raw).expect("endpoint should be accepted")
}

#[test]
fn accepts_ipv4_loopback() {
    assert!(resolve_target("http://127.0.0.1:8787/health", None).is_ok());
    assert!(resolve_target("http://127.10.20.30:8787/report?since=24h", None).is_ok());
}

#[test]
fn accepts_ipv6_loopback() {
    assert!(resolve_target("http://[::1]:8787/health", None).is_ok());
}

#[test]
fn accepts_localhost_and_pins_it() {
    let target =
        resolve_target("http://localhost:8787/health", None).expect("localhost should resolve");
    let host = target.url.host_str().unwrap_or_default();
    // The engine binds IPv4, so localhost must prefer 127.0.0.1 on dual-stack.
    assert_eq!(host, "127.0.0.1", "localhost pinned to {host}");
}

#[test]
fn rejects_public_ip_without_approval() {
    assert!(resolve_target("http://8.8.8.8/health", None).is_err());
    assert!(resolve_target("http://[2001:4860:4860::8888]/", None).is_err());
}

#[test]
fn rejects_dns_rebinding_hostnames() {
    assert!(resolve_target("http://127.0.0.1.nip.io:8787/health", None).is_err());
    assert!(resolve_target("http://localhost.evil.com:8787/health", None).is_err());
}

#[test]
fn rejects_non_http_schemes() {
    assert!(resolve_target("file:///etc/passwd", None).is_err());
    assert!(resolve_target("data:text/plain,hello", None).is_err());
    // https is allowed (loopback with TLS, or an approved https remote).
    assert!(resolve_target("https://127.0.0.1:8787/health", None).is_ok());
}

#[test]
fn rejects_credentials_in_url() {
    assert!(resolve_target("http://user:pass@127.0.0.1:8787/health", None).is_err());
}

#[test]
fn rejects_path_traversal() {
    assert!(resolve_target("http://127.0.0.1:8787/api/../admin", None).is_err());
    assert!(resolve_target("http://127.0.0.1:8787/../secret", None).is_err());
    assert!(resolve_target("http://127.0.0.1:8787/%2e%2e/admin", None).is_err());
}

#[test]
fn restricts_methods() {
    assert!(allowed_method("GET").is_ok());
    assert!(allowed_method("post").is_ok());
    assert!(allowed_method("TRACE").is_err());
    assert!(allowed_method("PUT").is_err());
    assert!(allowed_method("CONNECT").is_err());
}

#[test]
fn classifies_private_addresses() {
    for raw in [
        "10.1.2.3",
        "172.16.5.5",
        "192.168.1.20",
        "169.254.1.1",
        "100.64.0.1",
    ] {
        assert!(
            is_private_ip(raw.parse().unwrap()),
            "{raw} should be private"
        );
    }
    for raw in ["8.8.8.8", "1.1.1.1", "172.32.0.1"] {
        assert!(
            !is_private_ip(raw.parse().unwrap()),
            "{raw} should be public"
        );
    }
    assert!(is_private_ip("fd00::1".parse().unwrap()));
    assert!(is_private_ip("fe80::1".parse().unwrap()));
}

#[test]
fn remote_endpoint_policy() {
    // LAN / VPN over plain HTTP is allowed.
    assert!(validate_remote_endpoint("http://192.168.1.20:8787").is_ok());
    assert!(validate_remote_endpoint("http://10.0.0.5:8787").is_ok());
    assert!(validate_remote_endpoint("http://100.101.102.103:8787").is_ok());
    // Public plain HTTP is not.
    assert!(validate_remote_endpoint("http://8.8.8.8:8787").is_err());
    // Public hosts must use https.
    assert!(validate_remote_endpoint("https://engine.example.com").is_ok());
    // Endpoint must be an origin only.
    assert!(validate_remote_endpoint("https://engine.example.com/api").is_err());
    assert!(validate_remote_endpoint("https://engine.example.com?x=1").is_err());
    // Other schemes and credentials stay banned.
    assert!(validate_remote_endpoint("file:///tmp/x").is_err());
    assert!(validate_remote_endpoint("http://u:p@192.168.1.20:8787").is_err());
}

#[test]
fn remote_targets_require_approval() {
    let raw = "http://192.168.1.20:8787/health";
    assert!(
        resolve_target(raw, None).is_err(),
        "unapproved remote host must be refused"
    );

    let approved = allow("http://192.168.1.20:8787");
    let target = resolve_target(raw, Some(&approved)).expect("approved remote should work");
    assert_eq!(target.url.host_str(), Some("192.168.1.20"));

    let other = allow("http://192.168.1.21:8787");
    assert!(
        resolve_target(raw, Some(&other)).is_err(),
        "a different approved host must not unlock this one"
    );
}

#[test]
fn approved_remote_keeps_redirects_and_paths_safe() {
    let approved = allow("http://192.168.1.20:8787");
    assert!(resolve_target("http://192.168.1.20:8787/api/../admin", Some(&approved)).is_err());
    assert!(resolve_target("http://192.168.1.20:8787/%2e%2e/admin", Some(&approved)).is_err());
}
