from rest_framework_simplejwt.authentication import JWTAuthentication

from auth_sessions.cookies import ACCESS_COOKIE, REFRESH_COOKIE
from auth_sessions.service import active_session_for_token

from .request_context import set_current_actor


class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = self.get_header(request)
        if header is not None:
            raw_token = self.get_raw_token(header)
        else:
            raw_token = request.COOKIES.get(ACCESS_COOKIE)
        if raw_token is None:
            return None
        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)
        session = active_session_for_token(validated_token)
        request.auth_session = session
        set_current_actor(user, request.path)
        return user, validated_token
