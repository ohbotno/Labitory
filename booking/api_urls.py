# booking/api_urls.py
"""
API URL configuration for the booking app.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views.viewsets import (
    UserProfileViewSet, BookingViewSet, ResourceViewSet, ResourceResponsibleViewSet,
    NotificationViewSet, NotificationPreferenceViewSet, WaitingListEntryViewSet
)

router = DefaultRouter()
# Use new modular ViewSets
router.register(r'profiles', UserProfileViewSet)
router.register(r'resources', ResourceViewSet)
router.register(r'bookings', BookingViewSet)
router.register(r'resource-responsible', ResourceResponsibleViewSet)
# Keep remaining ViewSets from main views temporarily
router.register(r'approval-rules', views.ApprovalRuleViewSet)
router.register(r'maintenance', views.MaintenanceViewSet)
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'notification-preferences', NotificationPreferenceViewSet, basename='notification-preference')
router.register(r'waiting-list', WaitingListEntryViewSet, basename='waiting-list-entry')

# Approval Workflow API endpoints
# router.register(r'resource-responsible', views.ResourceResponsibleViewSet)
# router.register(r'risk-assessments', views.RiskAssessmentViewSet)
# router.register(r'user-risk-assessments', views.UserRiskAssessmentViewSet)
# router.register(r'training-courses', views.TrainingCourseViewSet)
# router.register(r'resource-training-requirements', views.ResourceTrainingRequirementViewSet)
# router.register(r'user-training', views.UserTrainingViewSet)
# router.register(r'access-requests', views.AccessRequestViewSet)
# router.register(r'waiting-list-notifications', views.WaitingListNotificationViewSet, basename='waiting-list-notification')  # Removed - using Notification model

app_name = 'api'

urlpatterns = [
    # API URLs
    path('', include(router.urls)),
    
    # Additional API endpoints
    # path('booking/<int:booking_id>/checkin/', views.api_checkin_booking, name='checkin'),
    # path('booking/<int:booking_id>/checkout/', views.api_checkout_booking, name='api_checkout'),
    
    # AJAX URLs for dynamic form loading
    path('ajax/load-colleges/', views.ajax_load_colleges, name='ajax_load_colleges'),
    path('ajax/load-departments/', views.ajax_load_departments, name='ajax_load_departments'),
]