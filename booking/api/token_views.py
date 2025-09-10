# booking/api/token_views.py
"""
API views for JWT token management and rotation.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth import authenticate
from django.utils import timezone
from django.conf import settings

from .authentication import (
    generate_jwt_tokens,
    refresh_jwt_token,
    revoke_token,
    revoke_all_user_tokens
)
from ..models import APIToken, SecurityEvent


@api_view(['POST'])
@permission_classes([])
def obtain_jwt_token(request):
    """
    Obtain JWT tokens using username/password authentication.
    """
    username = request.data.get('username')
    password = request.data.get('password')
    
    if not username or not password:
        return Response({
            'error': 'Username and password required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    user = authenticate(username=username, password=password)
    
    if user is None:
        # Log security event
        SecurityEvent.objects.create(
            event_type='failed_login',
            description=f'Failed API login attempt for username: {username}',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            metadata={'username': username, 'endpoint': 'api_token_obtain'}
        )
        return Response({
            'error': 'Invalid credentials'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    if not user.is_active:
        return Response({
            'error': 'User account is disabled'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    # Generate tokens
    tokens = generate_jwt_tokens(user)
    
    # Update token usage metadata - extract JTI from JWT payload
    import jwt
    jwt_payload = jwt.decode(tokens['access_token'], options={"verify_signature": False})
    access_jti = jwt_payload.get('jti')
    if access_jti:
        try:
            token_obj = APIToken.objects.get(jti=access_jti)
            token_obj.update_usage(
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
        except APIToken.DoesNotExist:
            pass
    
    # Log security event
    SecurityEvent.objects.create(
        user=user,
        event_type='token_created',
        description='JWT tokens created via API',
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        metadata={'token_count': 2}
    )
    
    return Response({
        'access_token': tokens['access_token'],
        'refresh_token': tokens['refresh_token'],
        'access_token_expires': tokens['access_token_expiry'].isoformat(),
        'refresh_token_expires': tokens['refresh_token_expiry'].isoformat(),
        'token_type': 'Bearer'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([])
def refresh_jwt_token_view(request):
    """
    Refresh access token using refresh token.
    """
    refresh_token = request.data.get('refresh_token')
    
    if not refresh_token:
        return Response({
            'error': 'Refresh token required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        tokens = refresh_jwt_token(refresh_token)
        
        # Update token usage metadata - extract JTI from JWT payload
        import jwt
        jwt_payload = jwt.decode(tokens['access_token'], options={"verify_signature": False})
        access_jti = jwt_payload.get('jti')
        if access_jti:
            try:
                token_obj = APIToken.objects.get(jti=access_jti)
                token_obj.update_usage(
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
            except APIToken.DoesNotExist:
                pass
        
        return Response({
            'access_token': tokens['access_token'],
            'refresh_token': tokens['refresh_token'],
            'access_token_expires': tokens['access_token_expiry'].isoformat(),
            'refresh_token_expires': tokens['refresh_token_expiry'].isoformat(),
            'token_type': 'Bearer'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'error': str(e)
        }, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def revoke_token_view(request):
    """
    Revoke a specific token by JTI.
    """
    jti = request.data.get('jti')
    
    if not jti:
        return Response({
            'error': 'Token JTI required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Verify user owns the token
    try:
        token = APIToken.objects.get(jti=jti, user=request.user)
    except APIToken.DoesNotExist:
        return Response({
            'error': 'Token not found or access denied'
        }, status=status.HTTP_404_NOT_FOUND)
    
    revoke_token(jti)
    
    # Log security event
    SecurityEvent.objects.create(
        user=request.user,
        event_type='token_revoked',
        description=f'Token revoked by user: {jti}',
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        metadata={'jti': jti, 'token_type': token.token_type}
    )
    
    return Response({
        'message': 'Token revoked successfully'
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def revoke_all_tokens(request):
    """
    Revoke all tokens for the authenticated user.
    """
    revoke_all_user_tokens(request.user)
    
    # Log security event
    SecurityEvent.objects.create(
        user=request.user,
        event_type='token_revoked',
        description='All user tokens revoked',
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        metadata={'action': 'revoke_all'}
    )
    
    return Response({
        'message': 'All tokens revoked successfully'
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_user_tokens(request):
    """
    List active tokens for the authenticated user.
    """
    tokens = APIToken.objects.filter(
        user=request.user,
        is_revoked=False,
        expires_at__gt=timezone.now()
    ).order_by('-created_at')
    
    token_data = []
    for token in tokens:
        token_data.append({
            'jti': token.jti,
            'token_type': token.token_type,
            'created_at': token.created_at.isoformat(),
            'expires_at': token.expires_at.isoformat(),
            'last_used_at': token.last_used_at.isoformat() if token.last_used_at else None,
            'ip_address': token.ip_address,
            'user_agent': token.user_agent[:100] + '...' if token.user_agent and len(token.user_agent) > 100 else token.user_agent
        })
    
    return Response({
        'tokens': token_data,
        'count': len(token_data)
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def token_info(request):
    """
    Get information about the current token.
    """
    # This would typically be called with the current access token
    # The JWTAuthentication middleware would have decoded it
    # For now, return basic user info
    return Response({
        'user_id': request.user.id,
        'username': request.user.username,
        'is_active': request.user.is_active,
        'token_valid': True
    }, status=status.HTTP_200_OK)


def get_client_ip(request):
    """
    Get the client IP address from the request.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip