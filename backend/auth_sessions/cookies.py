from django.conf import settings

ACCESS_COOKIE = "famuhle_access"
REFRESH_COOKIE = "famuhle_refresh"


def _cookie_secure():
    return not settings.DEBUG


def set_access_cookie(response, access):
    response.set_cookie(
        ACCESS_COOKIE,
        str(access),
        max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=_cookie_secure(),
        samesite="Lax",
        path="/",
    )
    return response


def set_token_cookies(response, access, refresh=None):
    set_access_cookie(response, access)
    if refresh is not None:
        response.set_cookie(
            REFRESH_COOKIE,
            str(refresh),
            max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
            httponly=True,
            secure=_cookie_secure(),
            samesite="Lax",
            path="/",
        )
    return response


def clear_token_cookies(response):
    response.delete_cookie(ACCESS_COOKIE, path="/", samesite="Lax")
    response.delete_cookie(REFRESH_COOKIE, path="/", samesite="Lax")
    return response
