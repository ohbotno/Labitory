# booking/api/urls.py
"""
API URL patterns for Labitory.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .token_views import (
    obtain_jwt_token,
    refresh_jwt_token_view,
    revoke_token_view,
    revoke_all_tokens,
    list_user_tokens,
    token_info,
)
from .viewsets import (
    UserProfileViewSet,
    ResourceViewSet,
    BookingViewSet,
    ApprovalRuleViewSet,
    MaintenanceViewSet,
    WaitingListEntryViewSet,
)

app_name = 'api'

# Create router and register viewsets
router = DefaultRouter()
router.register(r'users', UserProfileViewSet)
router.register(r'resources', ResourceViewSet)
router.register(r'bookings', BookingViewSet)
router.register(r'approval-rules', ApprovalRuleViewSet)
router.register(r'maintenance', MaintenanceViewSet)
router.register(r'waiting-list', WaitingListEntryViewSet)

urlpatterns = [
    # Authentication endpoints
    path('auth/token/', obtain_jwt_token, name='token_obtain'),
    path('auth/token/refresh/', refresh_jwt_token_view, name='token_refresh'),
    path('auth/token/revoke/', revoke_token_view, name='token_revoke'),
    path('auth/token/revoke-all/', revoke_all_tokens, name='token_revoke_all'),
    path('auth/tokens/', list_user_tokens, name='token_list'),
    path('auth/token/info/', token_info, name='token_info'),
    
    # Include router URLs
    path('', include(router.urls)),
]