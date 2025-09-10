# booking/api/request_signing.py
"""
HMAC request signing for sensitive API endpoints.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import hmac
import hashlib
import time
import base64
from urllib.parse import urlencode
from django.conf import settings
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication


class HMACAuthentication(BaseAuthentication):
    """
    HMAC-based request signing authentication.
    
    Expected headers:
    - X-Signature: HMAC signature
    - X-Timestamp: Unix timestamp
    - X-API-Key: API key identifier
    """
    
    def authenticate(self, request):
        """
        Authenticate the request using HMAC signature.
        """
        signature = request.META.get('HTTP_X_SIGNATURE')
        timestamp = request.META.get('HTTP_X_TIMESTAMP')
        api_key_id = request.META.get('HTTP_X_API_KEY')
        
        if not all([signature, timestamp, api_key_id]):
            return None  # Let other authentication methods handle it
        
        try:
            timestamp = int(timestamp)
        except ValueError:
            raise exceptions.AuthenticationFailed('Invalid timestamp format')
        
        # Check timestamp freshness (prevent replay attacks)
        current_time = int(time.time())
        max_age = getattr(settings, 'HMAC_MAX_AGE', 300)  # 5 minutes default
        
        if abs(current_time - timestamp) > max_age:
            raise exceptions.AuthenticationFailed('Request timestamp too old')
        
        # Get API key and secret from settings or database
        api_keys = getattr(settings, 'API_SIGNING_KEYS', {})
        if api_key_id not in api_keys:
            raise exceptions.AuthenticationFailed('Invalid API key')
        
        secret = api_keys[api_key_id]['secret']
        user_id = api_keys[api_key_id].get('user_id')
        
        # Generate expected signature
        expected_signature = self.generate_signature(
            request, secret, timestamp, api_key_id
        )
        
        # Compare signatures securely
        if not hmac.compare_digest(signature, expected_signature):
            raise exceptions.AuthenticationFailed('Invalid signature')
        
        # Get user if specified
        user = None
        if user_id:
            from django.contrib.auth.models import User
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                raise exceptions.AuthenticationFailed('User not found')
        
        return (user, {'api_key_id': api_key_id, 'timestamp': timestamp})
    
    def generate_signature(self, request, secret, timestamp, api_key_id):
        """
        Generate HMAC signature for the request.
        
        Signature includes:
        - HTTP method
        - Request path
        - Query parameters (sorted)
        - Request body
        - Timestamp
        - API key ID
        """
        method = request.method.upper()
        path = request.path
        
        # Sort query parameters for consistent signing
        query_params = sorted(request.GET.items()) if request.GET else []
        query_string = urlencode(query_params)
        
        # Get request body
        body = getattr(request, 'body', b'')
        if isinstance(body, str):
            body = body.encode('utf-8')
        
        # Create signature payload
        payload_parts = [
            method,
            path,
            query_string,
            base64.b64encode(body).decode('utf-8'),
            str(timestamp),
            api_key_id
        ]
        
        payload = '\n'.join(payload_parts)
        
        # Generate HMAC
        signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature


def generate_client_signature(method, url, body=None, api_key_id=None, secret=None, timestamp=None):
    """
    Helper function to generate signature on client side.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        url: Full URL including query parameters
        body: Request body (bytes or string)
        api_key_id: API key identifier
        secret: API secret key
        timestamp: Unix timestamp (optional, will use current time)
    
    Returns:
        dict: Headers to include in request
    """
    if timestamp is None:
        timestamp = int(time.time())
    
    from urllib.parse import urlparse, parse_qs
    
    parsed_url = urlparse(url)
    path = parsed_url.path
    
    # Parse query parameters
    query_params = []
    if parsed_url.query:
        query_dict = parse_qs(parsed_url.query, keep_blank_values=True)
        for key, values in query_dict.items():
            for value in values:
                query_params.append((key, value))
    
    query_params.sort()
    query_string = urlencode(query_params)
    
    # Prepare body
    if body is None:
        body = b''
    elif isinstance(body, str):
        body = body.encode('utf-8')
    
    # Create signature payload
    payload_parts = [
        method.upper(),
        path,
        query_string,
        base64.b64encode(body).decode('utf-8'),
        str(timestamp),
        api_key_id
    ]
    
    payload = '\n'.join(payload_parts)
    
    # Generate signature
    signature = hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return {
        'X-Signature': signature,
        'X-Timestamp': str(timestamp),
        'X-API-Key': api_key_id,
        'Content-Type': 'application/json'
    }


class RequireHMACSignature:
    """
    Decorator/mixin to require HMAC signature for sensitive endpoints.
    """
    
    def __init__(self, view_func=None):
        self.view_func = view_func
    
    def __call__(self, *args, **kwargs):
        if self.view_func:
            # Used as decorator
            def wrapped_view(request, *view_args, **view_kwargs):
                self._check_signature(request)
                return self.view_func(request, *view_args, **view_kwargs)
            return wrapped_view
        else:
            # Used as mixin
            return self._check_signature(*args, **kwargs)
    
    def _check_signature(self, request):
        """
        Check if request has valid HMAC signature.
        """
        auth = HMACAuthentication()
        try:
            result = auth.authenticate(request)
            if result is None:
                raise exceptions.AuthenticationFailed('HMAC signature required')
        except exceptions.AuthenticationFailed:
            raise


def require_hmac_signature(view_func):
    """
    Decorator to require HMAC signature for a view.
    """
    return RequireHMACSignature(view_func)


class HMACSignatureMixin:
    """
    Mixin for ViewSets that require HMAC signature.
    """
    
    def dispatch(self, request, *args, **kwargs):
        """
        Check HMAC signature before processing request.
        """
        # Only check signature for specific actions or all actions
        if hasattr(self, 'hmac_required_actions'):
            if self.action not in self.hmac_required_actions:
                return super().dispatch(request, *args, **kwargs)
        
        auth = HMACAuthentication()
        try:
            result = auth.authenticate(request)
            if result is None and getattr(self, 'hmac_required', True):
                raise exceptions.AuthenticationFailed('HMAC signature required for this endpoint')
            
            if result:
                request.user, request.auth = result
                
        except exceptions.AuthenticationFailed as e:
            from rest_framework.response import Response
            return Response({
                'error': str(e),
                'code': 'hmac_authentication_failed'
            }, status=403)
        
        return super().dispatch(request, *args, **kwargs)


# Example usage in views
def create_signing_keys_for_user(user, key_name="default"):
    """
    Create API signing keys for a user.
    This would typically be done through an admin interface.
    """
    import secrets
    
    api_key_id = f"labitory_{user.id}_{int(time.time())}"
    secret = secrets.token_urlsafe(32)
    
    # In production, store these in database or secure configuration
    # For now, return them for manual configuration
    return {
        'api_key_id': api_key_id,
        'secret': secret,
        'user_id': user.id,
        'created_at': timezone.now().isoformat()
    }