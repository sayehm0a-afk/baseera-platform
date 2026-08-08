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

    @abstractmethod
    def send_welcome_email(self, to_email: str, full_name: "str | None") -> None:
        ...

    @abstractmethod
    def send_security_alert_email(self, to_email: str, event_description_ar: str) -> None:
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

    def send_welcome_email(self, to_email: str, full_name: "str | None") -> None:
        logger.warning(
            "[ConsoleEmailSender] No real email provider configured -- "
            "welcome email NOT actually sent to %s (name=%s).",
            to_email,
            full_name,
        )

    def send_security_alert_email(self, to_email: str, event_description_ar: str) -> None:
        logger.warning(
            "[ConsoleEmailSender] No real email provider configured -- "
            "security alert email NOT actually sent to %s. Event: %s",
            to_email,
            event_description_ar,
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

    def _html(self, heading: str, body_html: str, cta_label: "str | None" = None, cta_link: "str | None" = None) -> str:
        """Basirah's brand shell (gold #d4af37 on navy #0a0e14, matching
        frontend/src/app/globals.css's --color-bsr-gold-500/navy-950)
        wrapped around plain body content, RTL Arabic. Kept intentionally
        simple (inline styles only, no external assets/fonts) since email
        clients strip <style> blocks and remote images unpredictably."""
        cta_html = ""
        if cta_label and cta_link:
            cta_html = (
                f'<p style="text-align:center;margin:28px 0;">'
                f'<a href="{cta_link}" '
                f'style="background:#d4af37;color:#0a0e14;padding:12px 28px;border-radius:8px;'
                f'text-decoration:none;font-weight:bold;display:inline-block;">{cta_label}</a></p>'
            )
        return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<body style="margin:0;padding:0;background:#0a0e14;font-family:Tahoma,Arial,sans-serif;">
  <table role="presentation" width="100%" style="background:#0a0e14;padding:32px 0;">
    <tr><td align="center">
      <table role="presentation" width="480" style="background:#111827;border-radius:12px;overflow:hidden;">
        <tr><td style="background:#d4af37;padding:20px 32px;">
          <span style="font-size:20px;font-weight:bold;color:#0a0e14;">بصيرة AI</span>
        </td></tr>
        <tr><td style="padding:32px;color:#e5e7eb;">
          <h1 style="font-size:18px;color:#ffffff;margin:0 0 16px;">{heading}</h1>
          <div style="font-size:14px;line-height:1.8;color:#d1d5db;">{body_html}</div>
          {cta_html}
        </td></tr>
        <tr><td style="padding:16px 32px;background:#0a0e14;color:#6b7280;font-size:11px;text-align:center;">
          بصيرة AI — منصة تحليل الأسهم السعودية بالذكاء الاصطناعي
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    def _send(self, to_email: str, subject: str, plain_body: str, html_body: "str | None" = None) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._from_email
        message["To"] = to_email
        message.set_content(plain_body)
        if html_body:
            message.add_alternative(html_body, subtype="html")
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
            self._html(
                "تأكيد بريدك الإلكتروني",
                "مرحباً، لإتمام إنشاء حسابك في بصيرة AI يرجى تأكيد بريدك الإلكتروني بالضغط على الزر أدناه. "
                "إذا لم تطلب إنشاء هذا الحساب، يمكنك تجاهل هذه الرسالة بأمان.",
                "تأكيد البريد الإلكتروني", link,
            ),
        )

    def send_password_reset_email(self, to_email: str, raw_token: str) -> None:
        link = f"{self._frontend_base_url}/reset-password?token={raw_token}"
        self._send(
            to_email, "إعادة تعيين كلمة المرور - بصيرة AI",
            f"لإعادة تعيين كلمة المرور، افتح الرابط التالي:\n\n{link}\n\nإذا لم تطلب هذا، تجاهل هذه الرسالة.",
            self._html(
                "إعادة تعيين كلمة المرور",
                "وصلنا طلب لإعادة تعيين كلمة المرور الخاصة بحسابك في بصيرة AI. اضغط الزر أدناه لتعيين كلمة مرور جديدة. "
                "إذا لم تطلب هذا، يمكنك تجاهل هذه الرسالة بأمان -- كلمة مرورك الحالية ستبقى كما هي.",
                "إعادة تعيين كلمة المرور", link,
            ),
        )

    def send_welcome_email(self, to_email: str, full_name: "str | None") -> None:
        greeting = f"مرحباً {full_name}،" if full_name else "مرحباً،"
        link = f"{self._frontend_base_url}/dashboard"
        self._send(
            to_email, "مرحباً بك في بصيرة AI",
            f"{greeting}\n\nتم تأكيد بريدك الإلكتروني بنجاح، وحسابك في بصيرة AI جاهز الآن.\n\n{link}",
            self._html(
                "مرحباً بك في بصيرة AI",
                f"{greeting} تم تأكيد بريدك الإلكتروني بنجاح، وحسابك في بصيرة AI جاهز الآن للاستخدام. "
                "يمكنك البدء بمسح السوق السعودي، متابعة الأسهم التي تهمك، والاطلاع على تحليلات الذكاء الاصطناعي "
                "لكل سهم مع سجل أداء حقيقي لكل توصية.",
                "الانتقال إلى لوحة التحكم", link,
            ),
        )

    def send_security_alert_email(self, to_email: str, event_description_ar: str) -> None:
        self._send(
            to_email, "تنبيه أمني - بصيرة AI",
            f"{event_description_ar}\n\nإذا لم تكن أنت من قام بهذا الإجراء، يرجى التواصل معنا فوراً وإعادة تعيين كلمة المرور.",
            self._html(
                "تنبيه أمني على حسابك",
                f"{event_description_ar}<br><br>إذا لم تكن أنت من قام بهذا الإجراء، يرجى التواصل معنا فوراً "
                "وإعادة تعيين كلمة المرور من صفحة نسيت كلمة المرور.",
            ),
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
