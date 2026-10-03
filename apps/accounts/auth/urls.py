from django.urls import path

from .views import (
    ActivationConfirmView,
    CSRFTokenView,
    CurrentUserView,
    LoginView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ProfileView,
    RefreshView,
)

urlpatterns = [
    path("csrf", CSRFTokenView.as_view(), name="auth-csrf"),
    path("login", LoginView.as_view(), name="auth-login"),
    path("refresh", RefreshView.as_view(), name="auth-refresh"),
    path("logout", LogoutView.as_view(), name="auth-logout"),
    path("me", CurrentUserView.as_view(), name="auth-me"),
    path("profile", ProfileView.as_view(), name="auth-profile"),
    path("password-reset/request", PasswordResetRequestView.as_view(), name="password-reset"),
    path(
        "password-reset/confirm",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path(
        "activation/confirm",
        ActivationConfirmView.as_view(),
        name="activation-confirm",
    ),
]
