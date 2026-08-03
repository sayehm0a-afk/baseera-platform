"""EmailSender: the same "clean interface now, no real gateway yet"
posture the billing layer (src/billing/) uses for payment providers.

`SmtpEmailSender` is a real implementation -- opt-in via the SMTP_HOST
env var (matching this codebase's existing auto-detect-from-env-vars
convention, e.g. src/market_data/provider_factory.py choosing SAHMK vs
Dev by whether SAHMK_API_KEY is set). Until SMTP_HOST is set,
`get_email_sender()` keeps returning `ConsoleEmailSender`, which logs
the would-be email (including the verification/reset link) rather than
silently dropping it or, worse, pretending an email was actually
delivered.
"""

import logging
import os
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage

logger = logging.getLogger(__name__)


class EmailSender(ABC):
    @abstractmethod
    def send_verification_email(self, to_email: str, raw_token: str) -> None:
        ...

    @abstractmethod
    def send_password_reset_email(self, to_email: str, raw_token: str) -> None:
        ...


class ConsoleEmailSender(EmailSender):
    """Logs the email instead of sending it. The only implementation
    today -- explicitly NOT for production use once a real mail
    provider is configured; nothing about this class contacts a real
    inbox, and it says so loudly rather than silently."""

    def send_verification_email(self, to_email: str, raw_token: str) -> None:
        logger.warning(
            "[ConsoleEmailSender] No real email provider configured -- "
            "verification email NOT actually sent to %s. Token: %s",
            to_email,
            raw_token,
        )

    def send_password_reset_email(self, to_email: str, raw_token: str) -> None:
        logger.warning(
            "[ConsoleEmailSender] No real email provider configured -- "
            "password reset email NOT actually sent to %s. Token: %s",
            to_email,
            raw_token,
        )


class SmtpEmailSender(EmailSender):
    """A real implementation -- sends over SMTP (works with any
    provider that speaks it: Gmail app passwords, SendGrid, Postmark,
    Resend's SMTP relay, AWS SES's SMTP interface, etc.), building the
    same `<frontend>/verify-email?token=...` /
    `<frontend>/reset-password?token=...` links the frontend's
    VerifyEmailClient/ResetPasswordClient already read (see
    frontend/src/app/verify-email/VerifyEmailClient.tsx,
    frontend/src/app/reset-password/ResetPasswordClient.tsx).
    Connection failures are logged, never raised -- a real mail outage
    must not turn into a 500 on registration/password-reset, matching
    this module's "never silently pretend, never crash the caller"
    posture."""

    def __init__(self, host: str, port: int, username: str, password: str, from_email: str, frontend_base_url: str, use_tls: bool):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_email = from_email
        self._frontend_base_url = frontend_base_url.rstrip("/")
        self._use_tls = use_tls

    def _send(self, to_email: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._from_email
        message["To"] = to_email
        message.set_content(body)
        try:
            with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
                if self._use_tls:
                    smtp.starttls()
                if self._username:
                    smtp.login(self._username, self._password)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            logger.error("[SmtpEmailSender] Failed to send email to %s: %s", to_email, exc)

    def send_verification_email(self, to_email: str, raw_token: str) -> None:
        link = f"{self._frontend_base_url}/verify-email?token={raw_token}"
        self._send(
            to_email, "تأكيد بريدك الإلكتروني - بصيرة AI",
            f"لتأكيد بريدك الإلكتروني، افتح الرابط التالي:\n\n{link}\n\nإذا لم تطلب هذا، تجاهل هذه الرسالة.",
        )

    def send_password_reset_email(self, to_email: str, raw_token: str) -> None:
        link = f"{self._frontend_base_url}/reset-password?token={raw_token}"
        self._send(
            to_email, "إعادة تعيين كلمة المرور - بصيرة AI",
            f"لإعادة تعيين كلمة المرور، افتح الرابط التالي:\n\n{link}\n\nإذا لم تطلب هذا، تجاهل هذه الرسالة.",
        )


def get_email_sender() -> EmailSender:
    """Auto-selects like src/market_data/provider_factory.py does for
    SAHMK vs Dev: SMTP_HOST set -> real SmtpEmailSender; unset -> the
    honest ConsoleEmailSender fallback. FRONTEND_BASE_URL is required
    alongside SMTP_HOST (there's no safe default frontend origin to
    guess), so a misconfiguration falls back to Console rather than
    emailing a broken link."""
    host = os.getenv("SMTP_HOST", "").strip()
    frontend_base_url = os.getenv("FRONTEND_BASE_URL", "").strip()
    if not host or not frontend_base_url:
        return ConsoleEmailSender()
    return SmtpEmailSender(
        host=host,
        port=int(os.getenv("SMTP_PORT", "587")),
        username=os.getenv("SMTP_USERNAME", ""),
        password=os.getenv("SMTP_PASSWORD", ""),
        from_email=os.getenv("SMTP_FROM_EMAIL", "no-reply@basirah.ai"),
        frontend_base_url=frontend_base_url,
        use_tls=os.getenv("SMTP_USE_TLS", "true").strip().lower() in ("true", "1", "yes"),
    )
