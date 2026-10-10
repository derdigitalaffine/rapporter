from django.conf import settings
from django.core.checks import Error, Warning, register


@register("mailing")
def mailing_configuration_checks(app_configs, **kwargs):
    errors = []
    use_tls = bool(getattr(settings, "EMAIL_USE_TLS", False))
    use_ssl = bool(getattr(settings, "EMAIL_USE_SSL", False))
    backend = getattr(settings, "EMAIL_BACKEND", "")
    if use_tls and use_ssl:
        errors.append(Error("EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be enabled.", id="mailing.E001"))
    if backend.endswith("smtp.EmailBackend"):
        if not getattr(settings, "EMAIL_HOST", ""):
            errors.append(Error("SMTP mail backend requires EMAIL_HOST.", id="mailing.E002"))
        if not getattr(settings, "DEFAULT_FROM_EMAIL", ""):
            errors.append(Error("SMTP mail backend requires DEFAULT_FROM_EMAIL.", id="mailing.E003"))
        user = bool(getattr(settings, "EMAIL_HOST_USER", ""))
        password = bool(getattr(settings, "EMAIL_HOST_PASSWORD", ""))
        if user != password:
            errors.append(Warning("EMAIL_HOST_USER and EMAIL_HOST_PASSWORD should be configured together.", id="mailing.W001"))
    return errors
