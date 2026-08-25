"""
JWT Authentication utilities for PolitiK
Implements secure JWT authentication with HTTPOnly cookies and refresh tokens
"""
import datetime
import logging
from typing import Tuple, Optional

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.middleware.csrf import CsrfViewMiddleware
from django.utils import timezone

User = get_user_model()
logger = logging.getLogger(__name__)

# JWT Configuration
JWT_SECRET_KEY = getattr(settings, 'JWT_SECRET_KEY', settings.SECRET_KEY)
JWT_ALGORITHM = getattr(settings, 'JWT_ALGORITHM', 'HS256')
JWT_ACCESS_TOKEN_LIFETIME = getattr(settings, 'JWT_ACCESS_TOKEN_LIFETIME', datetime.timedelta(minutes=15))
JWT_REFRESH_TOKEN_LIFETIME = getattr(settings, 'JWT_REFRESH_TOKEN_LIFETIME', datetime.timedelta(days=7))
JWT_AUTH_COOKIE = getattr(settings, 'JWT_AUTH_COOKIE', 'access_token')
JWT_AUTH_REFRESH_COOKIE = getattr(settings, 'JWT_AUTH_REFRESH_COOKIE', 'refresh_token')


def create_access_token(user: User) -> str:
    """
    Create a JWT access token for the given user.

    Args:
        user: Django User instance

    Returns:
        Encoded JWT access token string
    """
    payload = {
        'user_id': user.id,
        'username': user.username,
        'email': user.email,
        'token_type': 'access',
        'exp': timezone.now() + JWT_ACCESS_TOKEN_LIFETIME,
        'iat': timezone.now(),
    }

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user: User) -> str:
    """
    Create a JWT refresh token for the given user.

    Args:
        user: Django User instance

    Returns:
        Encoded JWT refresh token string
    """
    payload = {
        'user_id': user.id,
        'token_type': 'refresh',
        'exp': timezone.now() + JWT_REFRESH_TOKEN_LIFETIME,
        'iat': timezone.now(),
    }

    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> Tuple[bool, Optional[dict]]:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token string

    Returns:
        Tuple of (is_valid, payload_dict_or_none)
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return True, payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        return False, None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {e}")
        return False, None


def get_user_from_token(token: str) -> Optional[User]:
    """
    Extract user from a valid JWT token.

    Args:
        token: JWT token string

    Returns:
        User instance if token is valid, None otherwise
    """
    is_valid, payload = verify_token(token)
    if not is_valid or not payload:
        return None

    try:
        user_id = payload.get('user_id')
        if not user_id:
            return None

        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.warning(f"User with id {payload.get('user_id')} not found")
        return None
    except Exception as e:
        logger.error(f"Error getting user from token: {e}")
        return None


def set_jwt_cookies(response, access_token: str, refresh_token: str) -> None:
    """
    Set JWT tokens as HTTPOnly cookies in the response.

    Args:
        response: Django HttpResponse object
        access_token: JWT access token
        refresh_token: JWT refresh token
    """
    # Set access token cookie (shorter lifetime)
    response.set_cookie(
        JWT_AUTH_COOKIE,
        access_token,
        max_age=int(JWT_ACCESS_TOKEN_LIFETIME.total_seconds()),
        httponly=True,
        secure=not settings.DEBUG,  # HTTPS in production
        samesite='Lax',
        path='/',
    )

    # Set refresh token cookie (longer lifetime)
    response.set_cookie(
        JWT_AUTH_REFRESH_COOKIE,
        refresh_token,
        max_age=int(JWT_REFRESH_TOKEN_LIFETIME.total_seconds()),
        httponly=True,
        secure=not settings.DEBUG,  # HTTPS in production
        samesite='Lax',
        path='/',
    )


def clear_jwt_cookies(response) -> None:
    """
    Clear JWT cookies from the response (logout).

    Args:
        response: Django HttpResponse object
    """
    response.delete_cookie(JWT_AUTH_COOKIE, path='/')
    response.delete_cookie(JWT_AUTH_REFRESH_COOKIE, path='/')


def get_tokens_from_request(request) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract access and refresh tokens from request cookies.

    Args:
        request: Django HttpRequest object

    Returns:
        Tuple of (access_token, refresh_token)
    """
    access_token = request.COOKIES.get(JWT_AUTH_COOKIE)
    refresh_token = request.COOKIES.get(JWT_AUTH_REFRESH_COOKIE)
    return access_token, refresh_token


def authenticate_request(request) -> Tuple[Optional[User], Optional[str]]:
    """
    Authenticate a request using JWT tokens from cookies.

    Args:
        request: Django HttpRequest object

    Returns:
        Tuple of (user, error_message)
    """
    access_token, _ = get_tokens_from_request(request)

    if not access_token:
        return None, "No access token provided"

    is_valid, payload = verify_token(access_token)
    if not is_valid:
        return None, "Invalid or expired access token"

    user = get_user_from_token(access_token)
    if not user:
        return None, "User not found"

    if not user.is_active:
        return None, "User account is disabled"

    return user, None


def enforce_csrf(request):
    """
    Enforce CSRF validation for requests.
    This is needed because we're using cookies for authentication.
    """
    def dummy_get_response(req):
        return None

    csrf_middleware = CsrfViewMiddleware(dummy_get_response)
    reason = csrf_middleware.process_view(request, None, (), {})
    if reason:
        # CSRF validation failed
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden(f'CSRF Failed: {reason}')
        
    return None