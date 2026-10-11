from django.conf import settings

ACCESS_COOKIE = "famuhle_access"
REFRESH_COOKIE = "famuhle_refresh"
ADMIN_ACCESS_COOKIE = "familyos_admin_access"
ADMIN_REFRESH_COOKIE = "familyos_admin_refresh"
ADMIN_COOKIE_PATH = "/api/superadmin/"


def _cookie_secure():
    return not settings.DEBUG


def _set_cookie(response, name, value, *, max_age, path):
    response.set_cookie(
        name,
        str(value),
        max_age=max_age,
        httponly=True,
        secure=_cookie_secure(),
        samesite="Lax",
        path=path,
    )
    return response


def set_access_cookie(response, access):
    return _set_cookie(
        response,
        ACCESS_COOKIE,
        access,
        max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        path="/",
    )


def set_admin_access_cookie(response, access):
    return _set_cookie(
        response,
        ADMIN_ACCESS_COOKIE,
        access,
        max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        path=ADMIN_COOKIE_PATH,
    )


def set_token_cookies(response, access, refresh=None):
    set_access_cookie(response, access)
    if refresh is not None:
        _set_cookie(
            response,
            REFRESH_COOKIE,
            refresh,
            max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
            path="/",
        )
    return response


def set_admin_token_cookies(response, access, refresh=None):
    set_admin_access_cookie(response, access)
    if refresh is not None:
        _set_cookie(
            response,
            ADMIN_REFRESH_COOKIE,
            refresh,
            max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
            path=ADMIN_COOKIE_PATH,
        )
    return response


def clear_token_cookies(response):
    response.delete_cookie(ACCESS_COOKIE, path="/", samesite="Lax")
    response.delete_cookie(REFRESH_COOKIE, path="/", samesite="Lax")
    return response


def clear_admin_token_cookies(response):
    response.delete_cookie(ADMIN_ACCESS_COOKIE, path=ADMIN_COOKIE_PATH, samesite="Lax")
    response.delete_cookie(ADMIN_REFRESH_COOKIE, path=ADMIN_COOKIE_PATH, samesite="Lax")
    return response
