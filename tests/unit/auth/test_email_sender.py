"""Unit tests for src.auth.email_sender -- ConsoleEmailSender fallback,
SmtpEmailSender's real send path (mocked smtplib), and get_email_sender's
env-driven auto-selection."""

from unittest.mock import MagicMock, patch

from src.auth.email_sender import ConsoleEmailSender, SmtpEmailSender, get_email_sender


def test_console_sender_never_raises_and_logs_the_token(caplog):
    sender = ConsoleEmailSender()
    with caplog.at_level("WARNING"):
        sender.send_verification_email("user@example.com", "raw-token-123")
    assert "raw-token-123" in caplog.text
    assert "user@example.com" in caplog.text


def test_get_email_sender_defaults_to_console_when_smtp_host_unset(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert isinstance(get_email_sender(), ConsoleEmailSender)


def test_get_email_sender_defaults_to_console_when_frontend_base_url_unset(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)
    assert isinstance(get_email_sender(), ConsoleEmailSender)


def test_get_email_sender_returns_smtp_sender_when_both_set(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://app.basirah.ai")
    assert isinstance(get_email_sender(), SmtpEmailSender)


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
    assert "https://app.basirah.ai/verify-email?token=tok-abc" in sent_message.get_content()


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
    assert "https://app.basirah.ai/reset-password?token=tok-xyz" in sent_message.get_content()


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
