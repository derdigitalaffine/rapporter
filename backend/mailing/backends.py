from django.conf import settings
from django.core.mail import get_connection
from django.core.mail.backends.base import BaseEmailBackend

from .smtp_config import effective_mail_config


class ManagedRoutingEmailBackend(BaseEmailBackend):
    """Use managed SMTP when enabled, otherwise preserve the deployment backend."""

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        cfg = effective_mail_config()
        if cfg["source"] == "superadmin":
            connection = get_connection(
                backend="django.core.mail.backends.smtp.EmailBackend",
                host=cfg["host"], port=cfg["port"], username=cfg["username"], password=cfg["password"],
                use_tls=cfg["use_tls"], use_ssl=cfg["use_ssl"], timeout=cfg["timeout"],
                fail_silently=self.fail_silently,
            )
            for message in email_messages:
                message.from_email = cfg["from_email"]
                message.reply_to = [cfg["reply_to"]] if cfg["reply_to"] else []
            return connection.send_messages(email_messages)
        backend = getattr(settings, "EMAIL_ENV_BACKEND", "django.core.mail.backends.dummy.EmailBackend")
        connection = get_connection(backend=backend, fail_silently=self.fail_silently)
        return connection.send_messages(email_messages)
