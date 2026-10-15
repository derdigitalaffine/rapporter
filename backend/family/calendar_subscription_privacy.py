"""Never cache private exports or include bearer subscription URLs in app logs."""
import logging
import re
from urllib.parse import unquote

FEED_PATTERN = re.compile(r'(/calendar-feed/)[^\s/?#\"<>]+', re.I)


def redact(value):
    # Also handle percent-encoded route characters in access records.
    return FEED_PATTERN.sub(r'\1[redacted]', unquote(str(value)))


class CalendarSecretFilter(logging.Filter):
    def filter(self, record):
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


class CalendarSubscriptionPrivacyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        result = self.get_response(request)
        if request.path.startswith(('/calendar-feed/', '/caldav/', '/api/calendar-subscriptions/')):
            result['Cache-Control'] = 'private, no-store, max-age=0'
            result['Referrer-Policy'] = 'no-referrer'
            result['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
        return result
