from django.contrib import admin
from django.urls import include, path

from family.auth_views import login_view, logout_view, refresh_view, session_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/login/", login_view, name="auth_login"),
    path("api/auth/refresh/", refresh_view, name="auth_refresh"),
    path("api/auth/logout/", logout_view, name="auth_logout"),
    path("api/auth/session/", session_view, name="auth_session"),
    path("api/", include("family.urls")),
    path("api/", include("expenses.urls")),
    path("api/", include("baby.urls")),
]
