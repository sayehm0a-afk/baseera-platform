"""EmailSender: the same "clean interface now, no real gateway yet"
posture the billing layer (src/billing/) uses for payment providers.
No SMTP/SES/SendGrid credentials exist anywhere in this environment, so
the only implementation today logs the would-be email (including the
verification/reset link) rather than silently dropping it or, worse,
pretending an email was actually delivered. Swap in a real
`SmtpEmailSender`/`SesEmailSender` later by adding one more class here
and a branch in `get_email_sender()` -- nothing else in src/auth/ needs
to change, since callers only depend on this module's ABC.
"""

import logging
from abc import ABC, abstractmethod

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


def get_email_sender() -> EmailSender:
    """No real provider is configured in this codebase yet -- always
    returns the console implementation. This is the one seam a future
    SMTP/SES/SendGrid integration replaces."""
    return ConsoleEmailSender()
