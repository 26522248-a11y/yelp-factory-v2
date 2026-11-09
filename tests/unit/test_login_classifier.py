"""Challenge classifier: the four submit outcomes (T-2, spec v3.0 section 4)."""

from __future__ import annotations

from flows.login_flow import classify_login_outcome


def test_logged_in_wins_over_every_text():
    assert classify_login_outcome("sent an email with a login link", logged_in=True) == "logged_in"


def test_email_link_challenge_detected():
    text = "We need to confirm it's really you. We've sent an email with a login link to a@b.com."
    assert classify_login_outcome(text, logged_in=False) == "email_link"
    assert classify_login_outcome("We need to confirm it's really you", logged_in=False) == "email_link"


def test_bad_credentials_beats_toast():
    text = "The email or password you entered doesn't look right. Unable to log you in right now."
    assert classify_login_outcome(text, logged_in=False) == "bad_credentials"


def test_error_toast_is_transient():
    assert classify_login_outcome("We're unable to log you in right now. Please try again later.", logged_in=False) == "error_toast"


def test_captcha_widget_detected():
    assert classify_login_outcome("Please verify you are a human with hcaptcha", logged_in=False) == "captcha"


def test_silent_submit_stays_pending():
    assert classify_login_outcome("", logged_in=False) == "pending"
    assert classify_login_outcome(None, logged_in=False) == "pending"


def test_bool_page_text_does_not_crash():
    # FakePage.evaluate returns True for unknown scripts (regression guard).
    assert classify_login_outcome(True, logged_in=False) == "pending"
