from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from auth_sessions.cookies import ACCESS_COOKIE, ADMIN_ACCESS_COOKIE
from auth_sessions.models import AuthSession
from auth_sessions.service import active_session_for_token

from .request_context import set_current_actor


class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        is_superadmin_surface = request.path.startswith("/api/superadmin/")
        expected_surface = (
            AuthSession.Surface.SUPERADMIN if is_superadmin_surface else AuthSession.Surface.APP
        )
        header = self.get_header(request)
        if header is not None:
            raw_token = self.get_raw_token(header)
        else:
            cookie_name = ADMIN_ACCESS_COOKIE if is_superadmin_surface else ACCESS_COOKIE
            raw_token = request.COOKIES.get(cookie_name)
        if raw_token is None:
            return None
        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)
        session = active_session_for_token(validated_token)
        if session.surface != expected_surface:
            raise AuthenticationFailed("Sitzung ist für diese Anwendung nicht gültig.")
        request.auth_session = session
        set_current_actor(user, request.path)
        return user, validated_token
