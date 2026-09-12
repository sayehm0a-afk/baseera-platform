"""Unit tests for src.auth.email_sender -- ConsoleEmailSender fallback,
SmtpEmailSender's real send path (mocked smtplib), ResendEmailSender's
real send path (mocked urllib), and get_email_sender's env-driven
auto-selection (including RESEND_API_KEY taking priority over
SMTP_HOST when both happen to be set)."""

import json
import urllib.error
from unittest.mock import MagicMock, patch

from src.auth.email_sender import (
    ConsoleEmailSender,
    ResendEmailSender,
    SmtpEmailSender,
    get_email_sender,
)


def test_console_sender_never_raises_and_logs_the_token(caplog):
    sender = ConsoleEmailSender()
    with caplog.at_level("WARNING"):
        sender.send_verification_email("user@example.com", "raw-token-123")
    assert "raw-token-123" in caplog.text
    assert "user@example.com" in caplog.text


def test_get_email_sender_defaults_to_console_when_smtp_host_unset(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert isinstance(get_email_sender(), ConsoleEmailSender)


def test_get_email_sender_defaults_to_console_when_frontend_base_url_unset(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)
    assert isinstance(get_email_sender(), ConsoleEmailSender)


def test_get_email_sender_returns_smtp_sender_when_both_set(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://app.basirah.ai")
    assert isinstance(get_email_sender(), SmtpEmailSender)


def test_get_email_sender_returns_resend_sender_when_key_and_frontend_set(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://app.basirah.ai")
    assert isinstance(get_email_sender(), ResendEmailSender)


def test_get_email_sender_prefers_resend_over_smtp_when_both_configured(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://app.basirah.ai")
    assert isinstance(get_email_sender(), ResendEmailSender)


def test_get_email_sender_defaults_to_console_when_resend_key_set_but_frontend_unset(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)
    assert isinstance(get_email_sender(), ConsoleEmailSender)


@patch("src.auth.email_sender.smtplib.SMTP")
def test_smtp_sender_builds_the_real_verify_email_link_and_sends(mock_smtp_cls):
    mock_smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

    sender = SmtpEmailSender(
        host="smtp.example.com", port=587, username="u", password="p",
        from_email="no-reply@basirah.ai", frontend_base_url="https://app.basirah.ai/", use_tls=True,
    )
    sender.send_verification_email("user@example.com", "tok-abc")

    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once_with("u", "p")
    assert mock_smtp.send_message.call_count == 1
    sent_message = mock_smtp.send_message.call_args[0][0]
    assert sent_message["To"] == "user@example.com"
    link = "https://app.basirah.ai/verify-email?token=tok-abc"
    assert link in sent_message.get_body(preferencelist=("plain",)).get_content()
    assert link in sent_message.get_body(preferencelist=("html",)).get_content()


@patch("src.auth.email_sender.smtplib.SMTP")
def test_smtp_sender_builds_the_real_reset_password_link(mock_smtp_cls):
    mock_smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

    sender = SmtpEmailSender(
        host="smtp.example.com", port=587, username="u", password="p",
        from_email="no-reply@basirah.ai", frontend_base_url="https://app.basirah.ai", use_tls=True,
    )
    sender.send_password_reset_email("user@example.com", "tok-xyz")

    sent_message = mock_smtp.send_message.call_args[0][0]
    link = "https://app.basirah.ai/reset-password?token=tok-xyz"
    assert link in sent_message.get_body(preferencelist=("plain",)).get_content()
    assert link in sent_message.get_body(preferencelist=("html",)).get_content()


@patch("src.auth.email_sender.smtplib.SMTP")
def test_smtp_sender_sends_a_branded_welcome_email(mock_smtp_cls):
    mock_smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

    sender = SmtpEmailSender(
        host="smtp.example.com", port=587, username="u", password="p",
        from_email="no-reply@basirah.ai", frontend_base_url="https://app.basirah.ai", use_tls=True,
    )
    sender.send_welcome_email("user@example.com", "أحمد")

    sent_message = mock_smtp.send_message.call_args[0][0]
    assert "أحمد" in sent_message.get_body(preferencelist=("plain",)).get_content()
    assert "أحمد" in sent_message.get_body(preferencelist=("html",)).get_content()


@patch("src.auth.email_sender.smtplib.SMTP")
def test_smtp_sender_sends_a_security_alert_email(mock_smtp_cls):
    mock_smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

    sender = SmtpEmailSender(
        host="smtp.example.com", port=587, username="u", password="p",
        from_email="no-reply@basirah.ai", frontend_base_url="https://app.basirah.ai", use_tls=True,
    )
    sender.send_security_alert_email("user@example.com", "تم تغيير كلمة المرور")

    sent_message = mock_smtp.send_message.call_args[0][0]
    assert "تم تغيير كلمة المرور" in sent_message.get_body(preferencelist=("plain",)).get_content()
    assert "تم تغيير كلمة المرور" in sent_message.get_body(preferencelist=("html",)).get_content()


def test_console_sender_never_raises_for_welcome_and_security_alert(caplog):
    sender = ConsoleEmailSender()
    with caplog.at_level("WARNING"):
        sender.send_welcome_email("user@example.com", "أحمد")
        sender.send_security_alert_email("user@example.com", "تنبيه أمني")
    assert "user@example.com" in caplog.text
    assert "تنبيه أمني" in caplog.text


@patch("src.auth.email_sender.smtplib.SMTP")
def test_smtp_sender_swallows_connection_errors_instead_of_raising(mock_smtp_cls):
    mock_smtp_cls.side_effect = OSError("connection refused")
    sender = SmtpEmailSender(
        host="smtp.example.com", port=587, username="u", password="p",
        from_email="no-reply@basirah.ai", frontend_base_url="https://app.basirah.ai", use_tls=True,
    )
    # Must not raise -- a mail outage cannot become a 500 on registration.
    sender.send_verification_email("user@example.com", "tok-abc")


@patch("src.auth.email_sender.smtplib.SMTP")
def test_smtp_sender_skips_login_when_no_username_configured(mock_smtp_cls):
    mock_smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
    sender = SmtpEmailSender(
        host="smtp.example.com", port=25, username="", password="",
        from_email="no-reply@basirah.ai", frontend_base_url="https://app.basirah.ai", use_tls=False,
    )
    sender.send_verification_email("user@example.com", "tok-abc")
    mock_smtp.login.assert_not_called()
    mock_smtp.starttls.assert_not_called()


@patch("src.auth.email_sender.urllib.request.urlopen")
def test_resend_sender_builds_the_real_verify_email_link_and_sends(mock_urlopen):
    mock_urlopen.return_value.__enter__.return_value = MagicMock()

    sender = ResendEmailSender(
        api_key="re_test_key", from_email="no-reply@basirah.ai",
        frontend_base_url="https://app.basirah.ai/",
    )
    sender.send_verification_email("user@example.com", "tok-abc")

    mock_urlopen.assert_called_once()
    sent_request = mock_urlopen.call_args[0][0]
    assert sent_request.full_url == "https://api.resend.com/emails"
    assert sent_request.get_method() == "POST"
    assert sent_request.get_header("Authorization") == "Bearer re_test_key"
    assert sent_request.get_header("Content-type") == "application/json"
    # Resend's Cloudflare front door 403s (error code 1010) requests
    # carrying urllib's default "Python-urllib/x.y" User-Agent -- must
    # not regress back to relying on that default.
    assert sent_request.get_header("User-agent") == "Basirah-Backend/1.0"

    payload = json.loads(sent_request.data.decode("utf-8"))
    assert payload["from"] == "no-reply@basirah.ai"
    assert payload["to"] == ["user@example.com"]
    link = "https://app.basirah.ai/verify-email?token=tok-abc"
    assert link in payload["text"]
    assert link in payload["html"]


@patch("src.auth.email_sender.urllib.request.urlopen")
def test_resend_sender_sends_a_branded_welcome_email(mock_urlopen):
    mock_urlopen.return_value.__enter__.return_value = MagicMock()

    sender = ResendEmailSender(
        api_key="re_test_key", from_email="no-reply@basirah.ai",
        frontend_base_url="https://app.basirah.ai",
    )
    sender.send_welcome_email("user@example.com", "أحمد")

    payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
    assert "أحمد" in payload["text"]
    assert "أحمد" in payload["html"]


@patch("src.auth.email_sender.urllib.request.urlopen")
def test_resend_sender_swallows_http_error_instead_of_raising(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.HTTPError(
        url="https://api.resend.com/emails", code=422, msg="Unprocessable",
        hdrs=None, fp=MagicMock(read=lambda: b'{"message": "invalid from"}'),
    )
    sender = ResendEmailSender(
        api_key="re_test_key", from_email="no-reply@basirah.ai",
        frontend_base_url="https://app.basirah.ai",
    )
    # Must not raise -- a mail-provider outage/misconfig cannot become a 500
    # on registration/password-reset.
    sender.send_verification_email("user@example.com", "tok-abc")


@patch("src.auth.email_sender.urllib.request.urlopen")
def test_resend_sender_swallows_network_errors_instead_of_raising(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.URLError("Network is unreachable")
    sender = ResendEmailSender(
        api_key="re_test_key", from_email="no-reply@basirah.ai",
        frontend_base_url="https://app.basirah.ai",
    )
    sender.send_verification_email("user@example.com", "tok-abc")
