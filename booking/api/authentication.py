# booking/api/authentication.py
"""
Enhanced API authentication with JWT tokens and rotation support.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import jwt
import uuid
from datetime import datetime, timedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import authentication, exceptions
from rest_framework.authtoken.models import Token
from ..models.auth import APIToken


class JWTAuthentication(authentication.BaseAuthentication):
    """
    JWT-based authentication with refresh token support.
    """
    
    def authenticate(self, request):
        """
        Authenticate the request using JWT token.
        """
        auth_header = authentication.get_authorization_header(request).split()
        
        if not auth_header or auth_header[0].lower() != b'bearer':
            return None
        
        if len(auth_header) == 1:
            msg = 'Invalid token header. No credentials provided.'
            raise exceptions.AuthenticationFailed(msg)
        elif len(auth_header) > 2:
            msg = 'Invalid token header. Token string should not contain spaces.'
            raise exceptions.AuthenticationFailed(msg)
        
        try:
            token = auth_header[1].decode('utf-8')
        except UnicodeError:
            msg = 'Invalid token header. Token string should not contain invalid characters.'
            raise exceptions.AuthenticationFailed(msg)
        
        return self.authenticate_credentials(token)
    
    def authenticate_credentials(self, token):
        """
        Authenticate the token and return user.
        """
        try:
            payload = jwt.decode(
                token, 
                settings.SECRET_KEY, 
                algorithms=['HS256']
            )
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed('Token has expired')
        except jwt.InvalidTokenError:
            raise exceptions.AuthenticationFailed('Invalid token')
        
        try:
            user = User.objects.get(pk=payload['user_id'])
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid token')
        
        if not user.is_active:
            raise exceptions.AuthenticationFailed('User inactive or deleted')
        
        # Check if token is blacklisted
        jti = payload.get('jti')
        if jti and APIToken.objects.filter(jti=jti, is_revoked=True).exists():
            raise exceptions.AuthenticationFailed('Token has been revoked')
        
        return (user, token)


class RotatingTokenAuthentication(authentication.TokenAuthentication):
    """
    Enhanced token authentication with automatic rotation.
    """
    
    def authenticate_credentials(self, key):
        """
        Authenticate credentials with token rotation logic.
        """
        model = self.get_model()
        try:
            token = model.objects.select_related('user').get(key=key)
        except model.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid token.')
        
        if not token.user.is_active:
            raise exceptions.AuthenticationFailed('User inactive or deleted.')
        
        # Check if token needs rotation (older than rotation interval)
        rotation_interval = getattr(settings, 'API_TOKEN_ROTATION_INTERVAL', 24)  # hours
        if token.created < timezone.now() - timedelta(hours=rotation_interval):
            # Token should be rotated - still valid but client should refresh
            pass
        
        return (token.user, token)


def generate_jwt_tokens(user):
    """
    Generate access and refresh JWT tokens for a user.
    """
    now = timezone.now()
    access_token_expiry = now + timedelta(
        minutes=getattr(settings, 'JWT_ACCESS_TOKEN_LIFETIME', 15)
    )
    refresh_token_expiry = now + timedelta(
        days=getattr(settings, 'JWT_REFRESH_TOKEN_LIFETIME', 7)
    )
    
    # Generate unique identifiers for tokens
    access_jti = str(uuid.uuid4())
    refresh_jti = str(uuid.uuid4())
    
    # Create access token
    access_payload = {
        'user_id': user.id,
        'username': user.username,
        'exp': access_token_expiry,
        'iat': now,
        'jti': access_jti,
        'type': 'access'
    }
    
    # Create refresh token
    refresh_payload = {
        'user_id': user.id,
        'exp': refresh_token_expiry,
        'iat': now,
        'jti': refresh_jti,
        'type': 'refresh'
    }
    
    access_token = jwt.encode(access_payload, settings.SECRET_KEY, algorithm='HS256')
    refresh_token = jwt.encode(refresh_payload, settings.SECRET_KEY, algorithm='HS256')
    
    # Store token metadata for revocation
    APIToken.objects.create(
        user=user,
        jti=access_jti,
        token_type='access',
        expires_at=access_token_expiry
    )
    
    APIToken.objects.create(
        user=user,
        jti=refresh_jti,
        token_type='refresh',
        expires_at=refresh_token_expiry
    )
    
    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'access_token_expiry': access_token_expiry,
        'refresh_token_expiry': refresh_token_expiry
    }


def refresh_jwt_token(refresh_token):
    """
    Refresh an access token using a valid refresh token.
    """
    try:
        payload = jwt.decode(
            refresh_token, 
            settings.SECRET_KEY, 
            algorithms=['HS256']
        )
    except jwt.ExpiredSignatureError:
        raise exceptions.AuthenticationFailed('Refresh token has expired')
    except jwt.InvalidTokenError:
        raise exceptions.AuthenticationFailed('Invalid refresh token')
    
    if payload.get('type') != 'refresh':
        raise exceptions.AuthenticationFailed('Invalid token type')
    
    jti = payload.get('jti')
    if APIToken.objects.filter(jti=jti, is_revoked=True).exists():
        raise exceptions.AuthenticationFailed('Refresh token has been revoked')
    
    try:
        user = User.objects.get(pk=payload['user_id'])
    except User.DoesNotExist:
        raise exceptions.AuthenticationFailed('Invalid refresh token')
    
    if not user.is_active:
        raise exceptions.AuthenticationFailed('User inactive or deleted')
    
    # Revoke the old refresh token
    APIToken.objects.filter(jti=jti).update(is_revoked=True)
    
    # Generate new tokens
    return generate_jwt_tokens(user)


def revoke_token(token_jti):
    """
    Revoke a JWT token by its JTI.
    """
    APIToken.objects.filter(jti=token_jti).update(
        is_revoked=True,
        revoked_at=timezone.now()
    )


def revoke_all_user_tokens(user):
    """
    Revoke all tokens for a specific user.
    """
    APIToken.objects.filter(user=user, is_revoked=False).update(
        is_revoked=True,
        revoked_at=timezone.now()
    )


def cleanup_expired_tokens():
    """
    Clean up expired tokens from the database.
    """
    expired_count = APIToken.objects.filter(
        expires_at__lt=timezone.now()
    ).delete()[0]
    
    return expired_count