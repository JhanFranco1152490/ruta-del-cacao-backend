import hashlib

from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    rate = "20/min"


class PasswordResetIPThrottle(AnonRateThrottle):
    rate = "5/hour"


class PasswordResetIdentifierThrottle(SimpleRateThrottle):
    scope = "password_reset_identifier"
    rate = "5/hour"

    def get_cache_key(self, request, view):
        email = str(request.data.get("email", "")).strip().lower()
        if not email:
            return None
        digest = hashlib.sha256(email.encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}
