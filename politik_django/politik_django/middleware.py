import datetime
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from .auth import authenticate_request, create_access_token, JWT_AUTH_COOKIE, JWT_ACCESS_TOKEN_LIFETIME

class JWTSlidingSessionMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        user, _ = authenticate_request(request)
        if user:
            new_token = create_access_token(user)
            response.set_cookie(
                JWT_AUTH_COOKIE,
                new_token,
                max_age=int(JWT_ACCESS_TOKEN_LIFETIME.total_seconds()),
                httponly=True,
                secure=not settings.DEBUG,
                samesite='Lax',
                path='/'
            )
        return response
