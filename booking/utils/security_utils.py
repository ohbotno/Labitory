# booking/utils/security_utils.py
"""
Security utilities for rate limiting and authentication protection.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from functools import wraps
from django.conf import settings
from django.http import HttpResponse
from django.contrib.auth import views as auth_views
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited
from django.shortcuts import render
from rest_framework.response import Response
from rest_framework import status


class RateLimitMixin:
    """
    Mixin to add rate limiting to class-based views.
    """
    ratelimit_group = None
    ratelimit_key = 'ip'
    ratelimit_rate = '5/15m'
    ratelimit_method = 'POST'
    ratelimit_block = True
    
    def dispatch(self, request, *args, **kwargs):
        if getattr(settings, 'RATELIMIT_ENABLE', True):
            @ratelimit(
                group=self.ratelimit_group or f'{self.__class__.__name__.lower()}',
                key=self.ratelimit_key,
                rate=self.ratelimit_rate,
                method=self.ratelimit_method,
                block=self.ratelimit_block
            )
            def rate_limited_dispatch(request, *args, **kwargs):
                return super(RateLimitMixin, self).dispatch(request, *args, **kwargs)
            
            try:
                return rate_limited_dispatch(request, *args, **kwargs)
            except Ratelimited:
                return self.ratelimited(request)
        else:
            return super().dispatch(request, *args, **kwargs)
    
    def ratelimited(self, request):
        """Handle rate limited requests."""
        if request.headers.get('Accept', '').startswith('application/json'):
            return HttpResponse(
                '{"error": "Rate limit exceeded. Please try again later."}',
                status=429,
                content_type='application/json'
            )
        else:
            return render(request, 'ratelimited.html', status=429)


def login_rate_limit(view_func):
    """
    Rate limit decorator specifically for login attempts.
    """
    @wraps(view_func)
    @ratelimit(
        group='login_attempts',
        key='ip',
        rate=f"{getattr(settings, 'RATELIMIT_LOGIN_ATTEMPTS', 5)}/15m",
        method='POST',
        block=True
    )
    def wrapper(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    return wrapper


def api_rate_limit(view_func):
    """
    Rate limit decorator for API endpoints.
    """
    @wraps(view_func)
    @ratelimit(
        group='api_requests',
        key='user_or_ip',
        rate=f"{getattr(settings, 'RATELIMIT_API_REQUESTS', 100)}/1h",
        method=['GET', 'POST', 'PUT', 'DELETE'],
        block=True
    )
    def wrapper(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    return wrapper


def booking_rate_limit(view_func):
    """
    Rate limit decorator for booking operations.
    """
    @wraps(view_func)
    @ratelimit(
        group='booking_requests',
        key='user',
        rate=f"{getattr(settings, 'RATELIMIT_BOOKING_REQUESTS', 10)}/15m",
        method='POST',
        block=True
    )
    def wrapper(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    return wrapper


def password_reset_rate_limit(view_func):
    """
    Rate limit decorator for password reset requests.
    """
    @wraps(view_func)
    @ratelimit(
        group='password_reset',
        key='ip',
        rate=f"{getattr(settings, 'RATELIMIT_PASSWORD_RESET', 3)}/1h",
        method='POST',
        block=True
    )
    def wrapper(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    return wrapper


class RateLimitedLoginView(RateLimitMixin, auth_views.LoginView):
    """
    Login view with rate limiting protection.
    """
    ratelimit_group = 'login_attempts'
    ratelimit_rate = f"{getattr(settings, 'RATELIMIT_LOGIN_ATTEMPTS', 5)}/15m"
    ratelimit_method = 'POST'


class RateLimitedPasswordResetView(RateLimitMixin, auth_views.PasswordResetView):
    """
    Password reset view with rate limiting protection.
    """
    ratelimit_group = 'password_reset'
    ratelimit_rate = f"{getattr(settings, 'RATELIMIT_PASSWORD_RESET', 3)}/1h"
    ratelimit_method = 'POST'


def get_client_ip(request):
    """
    Get the client IP address from the request.
    Handles cases with proxy servers.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def is_rate_limited(group, key, rate):
    """
    Check if a specific rate limit has been exceeded.
    
    Args:
        group: Rate limit group name
        key: Rate limit key (IP, user, etc.)
        rate: Rate limit (e.g., '5/15m')
    
    Returns:
        bool: True if rate limited, False otherwise
    """
    from django_ratelimit.core import is_ratelimited
    from django.http import HttpRequest
    
    # Create a mock request for checking
    request = HttpRequest()
    request.META['REMOTE_ADDR'] = key if isinstance(key, str) else '127.0.0.1'
    
    return is_ratelimited(
        request=request,
        group=group,
        fn=lambda: None,
        key=key,
        rate=rate,
        increment=False
    )


class APIRateLimitMixin:
    """
    Mixin to add rate limiting to DRF ViewSets.
    """
    api_ratelimit_group = 'api_requests'
    api_ratelimit_key = 'user_or_ip'
    api_ratelimit_rate = None
    api_ratelimit_methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
    api_ratelimit_block = True
    
    def get_api_ratelimit_rate(self):
        """Get the rate limit for API requests."""
        if self.api_ratelimit_rate:
            return self.api_ratelimit_rate
        return f"{getattr(settings, 'RATELIMIT_API_REQUESTS', 100)}/1h"
    
    def dispatch(self, request, *args, **kwargs):
        """Apply rate limiting to the dispatch method."""
        if getattr(settings, 'RATELIMIT_ENABLE', True):
            @ratelimit(
                group=self.api_ratelimit_group,
                key=self.api_ratelimit_key,
                rate=self.get_api_ratelimit_rate(),
                method=self.api_ratelimit_methods,
                block=self.api_ratelimit_block
            )
            def rate_limited_dispatch(request, *args, **kwargs):
                return super(APIRateLimitMixin, self).dispatch(request, *args, **kwargs)
            
            try:
                return rate_limited_dispatch(request, *args, **kwargs)
            except Ratelimited:
                return self.api_ratelimited_response(request)
        else:
            return super().dispatch(request, *args, **kwargs)
    
    def api_ratelimited_response(self, request):
        """Return a rate-limited response for API requests."""
        return Response({
            'error': 'Rate limit exceeded',
            'detail': 'Too many requests. Please try again later.',
            'retry_after': '3600'  # 1 hour in seconds
        }, status=status.HTTP_429_TOO_MANY_REQUESTS)