# booking/views.py
"""
API views for the Labitory.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.template.loader import render_to_string
from django.http import JsonResponse
from django.contrib.auth import login
from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView, LoginView
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count, Max
from datetime import datetime, timedelta
import json
from django.core.paginator import Paginator
from django.contrib.auth.models import User
from django.core.cache import cache
from ..forms import ChecklistItemForm
from ..models import (
    AboutPage, UserProfile, Resource, Booking, ApprovalRule, Maintenance, EmailVerificationToken, 
    PasswordResetToken, BookingTemplate, Notification, NotificationPreference, WaitingListEntry, 
    Faculty, College, Department, ResourceAccess, AccessRequest, TrainingRequest,
    ResourceResponsible, RiskAssessment, UserRiskAssessment, TrainingCourse, 
    ResourceTrainingRequirement, UserTraining, ResourceIssue
)
from ..forms import (
    UserRegistrationForm, UserProfileForm, CustomPasswordResetForm, CustomSetPasswordForm, 
    BookingForm, RecurringBookingForm, BookingTemplateForm, CreateBookingFromTemplateForm, 
    SaveAsTemplateForm, AccessRequestForm, AccessRequestReviewForm, RiskAssessmentForm, 
    UserRiskAssessmentForm, TrainingCourseForm, UserTrainingEnrollForm, ResourceResponsibleForm,
    ResourceForm, AboutPageEditForm, ResourceIssueReportForm, ResourceIssueUpdateForm, IssueFilterForm
)
from ..recurring import RecurringBookingGenerator, RecurringBookingManager
from ..conflicts import ConflictDetector, ConflictResolver, ConflictManager
from ..services.licensing import require_license_feature
from booking.serializers import (
    UserProfileSerializer, ResourceSerializer, BookingSerializer,
    ApprovalRuleSerializer, MaintenanceSerializer, WaitingListEntrySerializer,
    ResourceResponsibleSerializer, RiskAssessmentSerializer, UserRiskAssessmentSerializer,
    TrainingCourseSerializer, ResourceTrainingRequirementSerializer, UserTrainingSerializer,
    AccessRequestDetailSerializer
)
from booking.notifications import notification_service
from booking.waiting_list import waiting_list_service  
from booking.services.checkin_service import checkin_service


class IsOwnerOrManagerPermission(permissions.BasePermission):
    """Custom permission to only allow owners or managers to edit bookings."""
    
    def has_object_permission(self, request, view, obj):
        # Read permissions for authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions only to owner or lab managers
        if hasattr(request.user, 'userprofile'):
            user_profile = request.user.userprofile
            return (obj.user == request.user or 
                   user_profile.role in ['technician', 'sysadmin'])
        
        return obj.user == request.user


class IsManagerPermission(permissions.BasePermission):
    """Custom permission for managers only."""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        if hasattr(request.user, 'userprofile'):
            user_profile = request.user.userprofile
            return user_profile.role in ['technician', 'sysadmin']
        
        return False


class UserProfileViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for user profiles."""
    queryset = UserProfile.objects.select_related('user', 'faculty', 'college', 'department').all()
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter queryset based on user role."""
        user = self.request.user
        try:
            user_profile = user.userprofile
            if user_profile.role in ['technician', 'sysadmin']:
                return UserProfile.objects.all()
            else:
                # Regular users can only see their own profile and group members
                return UserProfile.objects.filter(
                    Q(user=user) | Q(group=user_profile.group)
                )
        except UserProfile.DoesNotExist:
            return UserProfile.objects.filter(user=user)
    
    @action(detail=False, methods=['post'], url_path='update-theme')
    def update_theme_preference(self, request):
        """Update the current user's theme preference."""
        theme = request.data.get('theme')
        if theme not in ['light', 'dark', 'system']:
            return Response(
                {'error': 'Invalid theme. Must be light, dark, or system.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            profile = request.user.userprofile
            profile.theme_preference = theme
            profile.save()
            return Response({
                'success': True, 
                'theme': theme,
                'message': 'Theme preference updated successfully.'
            })
        except UserProfile.DoesNotExist:
            return Response(
                {'error': 'User profile not found.'}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'], url_path='theme')
    def get_theme_preference(self, request):
        """Get the current user's theme preference."""
        try:
            profile = request.user.userprofile
            return Response({
                'theme': profile.theme_preference
            })
        except UserProfile.DoesNotExist:
            return Response(
                {'error': 'User profile not found.'}, 
                status=status.HTTP_404_NOT_FOUND
            )


class ResourceViewSet(viewsets.ModelViewSet):
    """ViewSet for resources."""
    queryset = Resource.objects.filter(is_active=True).select_related(
        'closed_by'
    ).prefetch_related(
        'access_permissions__user',
        'access_permissions__granted_by',
        'responsible_persons__user',
        'responsible_persons__assigned_by',
        'training_requirements__training_course'
    )
    serializer_class = ResourceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['resource_type', 'requires_induction', 'required_training_level']
    
    def get_permissions(self):
        """Different permissions for different actions."""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            # Only technicians and sysadmins can modify resources
            self.permission_classes = [permissions.IsAuthenticated, IsManagerPermission]
        return super().get_permissions()
    
    def get_queryset(self):
        """Filter resources based on query parameters."""
        queryset = super().get_queryset()
        
        # Filter by resource_type if provided
        resource_type = self.request.query_params.get('resource_type')
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)
            
        return queryset
    
    @action(detail=False, methods=['get'])
    def available(self, request):
        """Get resources available for the current user."""
        try:
            user_profile = request.user.userprofile
            available_resources = []
            
            for resource in self.get_queryset():
                if resource.is_available_for_user(user_profile):
                    available_resources.append(resource)
            
            serializer = self.get_serializer(available_resources, many=True)
            return Response(serializer.data)
        
        except UserProfile.DoesNotExist:
            return Response(
                {"error": "User profile not found"}, 
                status=status.HTTP_400_BAD_REQUEST
            )


class BookingViewSet(viewsets.ModelViewSet):
    """ViewSet for bookings with full CRUD operations."""
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrManagerPermission]
    
    def get_queryset(self):
        """Filter bookings based on user role and query parameters."""
        user = self.request.user
        queryset = Booking.objects.select_related('resource', 'user', 'approved_by')
        
        try:
            user_profile = user.userprofile
            
            # Filter by user role
            if user_profile.role in ['technician', 'sysadmin']:
                # Managers can see all bookings
                pass
            elif user_profile.role == 'lecturer':
                # Lecturers can see their bookings and their group's bookings
                queryset = queryset.filter(
                    Q(user=user) | 
                    Q(user__userprofile__group=user_profile.group, shared_with_group=True)
                )
            else:
                # Students/researchers see their own bookings and shared group bookings
                queryset = queryset.filter(
                    Q(user=user) |
                    Q(user__userprofile__group=user_profile.group, shared_with_group=True) |
                    Q(attendees=user)
                ).distinct()
        
        except UserProfile.DoesNotExist:
            queryset = queryset.filter(user=user)
        
        # Filter by query parameters
        resource_id = self.request.query_params.get('resource')
        if resource_id:
            queryset = queryset.filter(resource_id=resource_id)
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            try:
                # Parse date strings and make them timezone-aware
                start_datetime = timezone.make_aware(
                    datetime.strptime(start_date, '%Y-%m-%d')
                )
                end_datetime = timezone.make_aware(
                    datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                )
                queryset = queryset.filter(
                    start_time__gte=start_datetime,
                    end_time__lte=end_datetime
                )
            except ValueError:
                # If date parsing fails, skip filtering
                pass
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset.order_by('start_time')
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a booking."""
        booking = self.get_object()
        user_profile = request.user.userprofile
        
        if user_profile.role not in ['technician', 'sysadmin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        if booking.status != 'pending':
            return Response(
                {"error": "Only pending bookings can be approved"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.status = 'approved'
        booking.approved_by = request.user
        booking.approved_at = timezone.now()
        booking.save()
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject a booking."""
        booking = self.get_object()
        user_profile = request.user.userprofile
        
        if user_profile.role not in ['technician', 'sysadmin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        if booking.status != 'pending':
            return Response(
                {"error": "Only pending bookings can be rejected"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.status = 'rejected'
        booking.approved_by = request.user
        booking.approved_at = timezone.now()
        booking.save()
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a booking."""
        booking = self.get_object()
        
        if not booking.can_be_cancelled:
            return Response(
                {"error": "This booking cannot be cancelled"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.status = 'cancelled'
        booking.save()
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def calendar(self, request):
        """Get bookings in calendar event format."""
        queryset = self.get_queryset()
        
        # Convert to FullCalendar event format
        events = []
        for booking in queryset:
            color = {
                'pending': '#ffc107',
                'approved': '#28a745',
                'rejected': '#dc3545',
                'cancelled': '#6c757d',
                'completed': '#17a2b8'
            }.get(booking.status, '#007bff')
            
            events.append({
                'id': booking.id,
                'title': booking.title,
                'start': booking.start_time.isoformat(),
                'end': booking.end_time.isoformat(),
                'backgroundColor': color,
                'borderColor': color,
                'extendedProps': {
                    'resource': booking.resource.name,
                    'user': booking.user.get_full_name(),
                    'status': booking.status,
                    'description': booking.description,
                }
            })
        
        return Response(events)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get booking statistics."""
        user_profile = request.user.userprofile
        
        if user_profile.role not in ['technician', 'sysadmin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Date range for statistics
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        bookings = Booking.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date
        )
        
        stats = {
            'total_bookings': bookings.count(),
            'approved_bookings': bookings.filter(status='approved').count(),
            'pending_bookings': bookings.filter(status='pending').count(),
            'rejected_bookings': bookings.filter(status='rejected').count(),
            'cancelled_bookings': bookings.filter(status='cancelled').count(),
            'bookings_by_resource': list(
                bookings.values('resource__name')
                .annotate(count=Count('id'))
                .order_by('-count')
            ),
            'bookings_by_user': list(
                bookings.values('user__username', 'user__first_name', 'user__last_name')
                .annotate(count=Count('id'))
                .order_by('-count')
            ),
            'bookings_by_group': list(
                bookings.values('user__userprofile__group')
                .annotate(count=Count('id'))
                .order_by('-count')
            ),
        }
        
        return Response(stats)
    
    def destroy(self, request, *args, **kwargs):
        """Override destroy to cancel booking instead of deleting it."""
        booking = self.get_object()
        
        # Check if booking can be cancelled
        if not booking.can_be_cancelled:
            return Response(
                {"error": "This booking cannot be cancelled"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Mark as cancelled instead of deleting
        booking.status = 'cancelled'
        booking.save()
        
        # Create booking history entry
        from booking.models import BookingHistory
        BookingHistory.objects.create(
            booking=booking,
            user=request.user,
            action='cancelled',
            notes='Cancelled via API'
        )
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['post'])
    def add_prerequisite(self, request, pk=None):
        """Add a prerequisite booking dependency."""
        booking = self.get_object()
        user_profile = request.user.userprofile
        
        # Check permissions - only owner or managers can add dependencies
        if booking.user != request.user and user_profile.role not in ['technician', 'sysadmin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        prerequisite_id = request.data.get('prerequisite_id')
        dependency_type = request.data.get('dependency_type', 'sequential')
        conditions = request.data.get('conditions', {})
        
        if not prerequisite_id:
            return Response(
                {"error": "prerequisite_id is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            prerequisite_booking = Booking.objects.select_related('resource', 'user').get(id=prerequisite_id)
            
            # Validate that user has access to prerequisite booking
            if (prerequisite_booking.user != request.user and 
                user_profile.role not in ['technician', 'sysadmin']):
                return Response(
                    {"error": "You don't have access to the specified prerequisite booking"}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            booking.add_prerequisite(prerequisite_booking, dependency_type, conditions)
            
            serializer = self.get_serializer(booking)
            return Response(serializer.data)
            
        except Booking.DoesNotExist:
            return Response(
                {"error": "Prerequisite booking not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'])
    def remove_prerequisite(self, request, pk=None):
        """Remove a prerequisite booking dependency."""
        booking = self.get_object()
        user_profile = request.user.userprofile
        
        # Check permissions
        if booking.user != request.user and user_profile.role not in ['technician', 'sysadmin']:
            return Response(
                {"error": "Permission denied"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        prerequisite_id = request.data.get('prerequisite_id')
        
        if not prerequisite_id:
            return Response(
                {"error": "prerequisite_id is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            prerequisite_booking = Booking.objects.select_related('resource', 'user').get(id=prerequisite_id)
            booking.prerequisite_bookings.remove(prerequisite_booking)
            
            serializer = self.get_serializer(booking)
            return Response(serializer.data)
            
        except Booking.DoesNotExist:
            return Response(
                {"error": "Prerequisite booking not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['get'])
    def dependencies(self, request, pk=None):
        """Get booking dependency information."""
        booking = self.get_object()
        
        prerequisites = []
        for prereq in booking.prerequisite_bookings.select_related('resource', 'user'):
            prerequisites.append({
                'id': prereq.id,
                'title': prereq.title,
                'resource': prereq.resource.name,
                'start_time': prereq.start_time,
                'end_time': prereq.end_time,
                'status': prereq.status,
                'user': prereq.user.get_full_name()
            })
        
        dependents = []
        for dependent in booking.dependent_bookings.select_related('resource', 'user'):
            dependents.append({
                'id': dependent.id,
                'title': dependent.title,
                'resource': dependent.resource.name,
                'start_time': dependent.start_time,
                'end_time': dependent.end_time,
                'status': dependent.status,
                'user': dependent.user.get_full_name(),
                'dependency_type': dependent.dependency_type
            })
        
        return Response({
            'can_start': booking.can_start,
            'dependency_status': booking.dependency_status,
            'dependency_type': booking.dependency_type,
            'dependency_conditions': booking.dependency_conditions,
            'prerequisites': prerequisites,
            'dependents': dependents,
            'blocking_dependencies': [
                {
                    'id': dep.id,
                    'title': dep.title,
                    'status': dep.status,
                    'resource': dep.resource.name
                }
                for dep in booking.get_blocking_dependencies()
            ]
        })
    
    @action(detail=False, methods=['post'])
    def join_waiting_list(self, request):
        """Join waiting list when booking conflicts exist."""
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            # Check if validation failed due to conflicts
            errors = serializer.errors
            if any('conflict' in str(error).lower() for error in errors.values()):
                # Offer to join waiting list
                resource_id = request.data.get('resource_id')
                start_time = request.data.get('start_time')
                end_time = request.data.get('end_time')
                title = request.data.get('title', 'Booking Request')
                description = request.data.get('description', '')
                
                if resource_id and start_time and end_time:
                    waiting_entry = WaitingListEntry.objects.create(
                        user=request.user,
                        resource_id=resource_id,
                        desired_start_time=start_time,
                        desired_end_time=end_time,
                        title=title,
                        description=description,
                        flexible_start=request.data.get('flexible_start', False),
                        flexible_duration=request.data.get('flexible_duration', False),
                        auto_book=request.data.get('auto_book', False)
                    )
                    
                    return Response({
                        'booking_failed': True,
                        'reason': 'time_conflict',
                        'waiting_list_entry': WaitingListEntrySerializer(waiting_entry).data,
                        'message': 'Booking conflicts detected. You have been added to the waiting list.'
                    }, status=status.HTTP_201_CREATED)
            
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # If no conflicts, create booking normally
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class ApprovalRuleViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for approval rules (read-only for now)."""
    queryset = ApprovalRule.objects.filter(is_active=True).select_related(
        'resource',
        'fallback_rule'
    ).prefetch_related(
        'approvers'
    )
    serializer_class = ApprovalRuleSerializer
    permission_classes = [permissions.IsAuthenticated]


class MaintenanceViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for maintenance schedules."""
    queryset = Maintenance.objects.all().select_related(
        'resource',
        'vendor',
        'created_by',
        'assigned_to',
        'approved_by'
    ).prefetch_related(
        'affects_other_resources',
        'prerequisite_maintenances',
        'documents__uploaded_by'
    )
    serializer_class = MaintenanceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter maintenance by date range if provided."""
        queryset = super().get_queryset()
        
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date and end_date:
            try:
                # Parse date strings and make them timezone-aware
                start_datetime = timezone.make_aware(
                    datetime.strptime(start_date, '%Y-%m-%d')
                )
                end_datetime = timezone.make_aware(
                    datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                )
                queryset = queryset.filter(
                    start_time__gte=start_datetime,
                    end_time__lte=end_datetime
                )
            except ValueError:
                # If date parsing fails, skip filtering
                pass
        
        return queryset.order_by('start_time')
    
    @action(detail=False, methods=['get'])
    def calendar(self, request):
        """Get maintenance periods formatted for FullCalendar."""
        # Get date range from query params
        start = request.query_params.get('start')
        end = request.query_params.get('end')
        resource_id = request.query_params.get('resource')
        
        # Base queryset
        maintenance_periods = self.get_queryset()
        
        # Filter by date range if provided
        if start and end:
            try:
                start_date = timezone.make_aware(datetime.fromisoformat(start.replace('Z', '+00:00')))
                end_date = timezone.make_aware(datetime.fromisoformat(end.replace('Z', '+00:00')))
                maintenance_periods = maintenance_periods.filter(
                    end_time__gte=start_date,
                    start_time__lte=end_date
                )
            except ValueError:
                pass
        
        # Filter by resource if specified
        if resource_id:
            try:
                maintenance_periods = maintenance_periods.filter(resource_id=resource_id)
            except ValueError:
                pass
        
        # Format for FullCalendar
        events = []
        for maintenance in maintenance_periods:
            # Color coding based on maintenance type and status
            now = timezone.now()
            if maintenance.start_time > now:
                # Scheduled maintenance - blue
                color = '#007bff'
            elif maintenance.end_time < now:
                # Completed maintenance - gray
                color = '#6c757d'
            else:
                # Active maintenance - orange
                color = '#fd7e14'
            
            # Override color based on maintenance type
            type_colors = {
                'preventive': '#28a745',  # green
                'corrective': '#dc3545',  # red
                'inspection': '#17a2b8',  # cyan
                'calibration': '#6f42c1',  # purple
                'repair': '#ffc107',      # yellow
                'upgrade': '#6c757d'      # gray
            }
            color = type_colors.get(maintenance.maintenance_type, color)
            
            events.append({
                'id': f'maintenance-{maintenance.id}',
                'title': f'🔧 {maintenance.title}',
                'start': maintenance.start_time.isoformat(),
                'end': maintenance.end_time.isoformat(),
                'backgroundColor': color,
                'borderColor': color,
                'display': 'block',
                'classNames': ['maintenance-event'],
                'extendedProps': {
                    'type': 'maintenance',
                    'resource': maintenance.resource.name,
                    'maintenance_type': maintenance.maintenance_type,
                    'description': maintenance.description,
                    'blocks_booking': maintenance.blocks_booking,
                    'is_recurring': maintenance.is_recurring,
                    'created_by': maintenance.created_by.get_full_name() or maintenance.created_by.username,
                }
            })
        
        return Response(events)


# Template views
def register_view(request):
    """User registration view."""
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Get the verification token for development mode
            from booking.models import EmailVerificationToken
            from django.conf import settings
            token = EmailVerificationToken.objects.filter(user=user, is_used=False).first()
            
            if settings.DEBUG and token:
                # In development mode, show the verification URL
                verification_url = request.build_absolute_uri(f'/verify-email/{token.token}/')
                messages.success(
                    request, 
                    f'<strong>Registration Successful!</strong><br><br>'
                    f'<i class="bi bi-info-circle"></i> <strong>Important:</strong> Your account has been created but is currently <strong>inactive</strong>.<br><br>'
                    f'<i class="bi bi-envelope"></i> <strong>Next Steps:</strong><br>'
                    f'1. Check your email ({user.email}) for a verification link<br>'
                    f'2. Click the verification link to activate your account<br>'
                    f'3. Return here to log in<br><br>'
                    f'<i class="bi bi-gear"></i> <strong>Development Mode:</strong> You can verify directly using this link: <a href="{verification_url}" target="_blank" class="btn btn-sm btn-outline-primary">Verify Account Now</a><br><br>'
                    f'<small class="text-muted"><i class="bi bi-clock"></i> You cannot log in until your email is verified.</small>'
                )
            else:
                messages.success(
                    request, 
                    f'<strong>Registration Successful!</strong><br><br>'
                    f'<i class="bi bi-info-circle"></i> <strong>Important:</strong> Your account has been created but is currently <strong>inactive</strong>.<br><br>'
                    f'<i class="bi bi-envelope"></i> <strong>Next Steps:</strong><br>'
                    f'1. Check your email ({user.email}) for a verification link<br>'
                    f'2. Click the verification link to activate your account<br>'
                    f'3. Return here to log in<br><br>'
                    f'<small class="text-muted"><i class="bi bi-clock"></i> You cannot log in until your email is verified. If you don\'t see the email, check your spam folder or <a href="/resend-verification/">request a new verification email</a>.</small>'
                )
            return redirect('login')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserRegistrationForm()
        # Clear any existing messages when showing the registration form
        list(messages.get_messages(request))
    
    return render(request, 'registration/register.html', {'form': form})


def verify_email_view(request, token):
    """Email verification view."""
    verification_token = get_object_or_404(EmailVerificationToken, token=token)
    
    if verification_token.is_used:
        messages.warning(request, 'This verification link has already been used.')
        return redirect('login')
    
    if verification_token.is_expired():
        messages.error(request, 'This verification link has expired. Please contact support.')
        return redirect('login')
    
    # Activate user and mark email as verified
    user = verification_token.user
    user.is_active = True
    user.save()
    
    profile = user.userprofile
    profile.email_verified = True
    profile.save()
    
    verification_token.is_used = True
    verification_token.save()
    
    messages.success(request, 'Email verified successfully! You can now log in.')
    return redirect('login')


def resend_verification_view(request):
    """Resend verification email view."""
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            from django.contrib.auth.models import User
            user = User.objects.select_related('userprofile').get(email=email, is_active=False)
            
            # Check if there's an existing unused token
            try:
                token = EmailVerificationToken.objects.get(user=user, is_used=False)
                if token.is_expired():
                    token.delete()
                    token = EmailVerificationToken.objects.create(user=user)
            except EmailVerificationToken.DoesNotExist:
                token = EmailVerificationToken.objects.create(user=user)
            
            # Send verification email
            form = UserRegistrationForm()
            form.send_verification_email(user, token)
            
            messages.success(request, 'Verification email has been resent. Please check your inbox.')
            
        except User.DoesNotExist:
            messages.error(request, 'No unverified account found with this email address.')
    
    return render(request, 'registration/resend_verification.html')


class CustomPasswordResetView(PasswordResetView):
    """Custom password reset view using our token system."""
    form_class = CustomPasswordResetForm
    template_name = 'registration/password_reset_form.html'
    success_url = '/password-reset-done/'
    
    def form_valid(self, form):
        form.save(request=self.request)
        return redirect(self.success_url)


def password_reset_confirm_view(request, token):
    """Custom password reset confirmation view."""
    reset_token = get_object_or_404(PasswordResetToken, token=token)
    
    if reset_token.is_used:
        messages.error(request, 'This password reset link has already been used.')
        return render(request, 'registration/password_reset_confirm.html', {'validlink': False})
    
    if reset_token.is_expired():
        messages.error(request, 'This password reset link has expired.')
        return render(request, 'registration/password_reset_confirm.html', {'validlink': False})
    
    if request.method == 'POST':
        form = CustomSetPasswordForm(reset_token.user, request.POST)
        if form.is_valid():
            form.save()
            reset_token.is_used = True
            reset_token.save()
            messages.success(request, 'Your password has been set successfully.')
            return redirect('password_reset_complete')
    else:
        form = CustomSetPasswordForm(reset_token.user)
    
    return render(request, 'registration/password_reset_confirm.html', {
        'form': form,
        'validlink': True,
    })


def password_reset_done_view(request):
    """Password reset done view."""
    return render(request, 'registration/password_reset_done.html')


def password_reset_complete_view(request):
    """Password reset complete view."""
    return render(request, 'registration/password_reset_complete.html')


@login_required
def create_booking_view(request):
    """Create a new booking."""
    conflicts_detected = False
    conflicting_bookings = []
    
    if request.method == 'POST':
        form = BookingForm(request.POST, user=request.user)
        
        # Check if this is a conflict override attempt
        override_conflicts = request.POST.get('override_conflicts') == 'true'
        
        # Debug logging
        import logging
        logger = logging.getLogger('booking')
        logger.debug(f"Create booking POST data: {request.POST}")
        logger.debug(f"User: {request.user}, is_superuser: {request.user.is_superuser}, is_staff: {request.user.is_staff}")
        logger.debug(f"Override conflicts: {override_conflicts}")
        
        if form.is_valid():
            try:
                booking = form.save(commit=False)
                booking.user = request.user
                
                # Handle conflict override if requested
                if override_conflicts and form.cleaned_data.get('override_conflicts'):
                    override_message = form.cleaned_data.get('override_message', '')
                    conflicts = form.get_conflicts()
                    
                    # Process each conflicting booking
                    from booking.notifications import BookingNotifications
                    notification_service = BookingNotifications()
                    
                    for conflicting_booking in conflicts:
                        notification_service.booking_overridden(
                            conflicting_booking, 
                            booking, 
                            override_message
                        )
                
                booking.save()
                messages.success(request, f'Booking "{booking.title}" created successfully.')
                return redirect('booking:booking_detail', pk=booking.pk)
                
            except Exception as e:
                messages.error(request, f'Error creating booking: {str(e)}')
        else:
            # Check if form validation failed due to conflicts
            if hasattr(form, '_conflicts'):
                conflicts_detected = True
                conflicting_bookings = form._conflicts
            
            # Add error messages (excluding conflict messages for privileged users)
            for field, errors in form.errors.items():
                for error in errors:
                    # Skip conflict error messages for privileged users as we handle them specially
                    if not (conflicts_detected and form._can_override_conflicts() and 'conflict detected' in error.lower()):
                        messages.error(request, f'{field.replace("_", " ").title()}: {error}')
    else:
        form = BookingForm(user=request.user)
    
    context = {
        'form': form,
        'conflicts_detected': conflicts_detected,
        'conflicting_bookings': conflicting_bookings,
        'can_override': hasattr(form, '_can_override_conflicts') and form._can_override_conflicts(),
    }
    
    return render(request, 'booking/create_booking.html', context)


@login_required
def booking_detail_view(request, pk):
    """View booking details."""
    booking = get_object_or_404(Booking, pk=pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        if (booking.user != request.user and 
            user_profile.role not in ['technician', 'sysadmin'] and
            not booking.shared_with_group):
            messages.error(request, 'You do not have permission to view this booking.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        if booking.user != request.user:
            messages.error(request, 'You do not have permission to view this booking.')
            return redirect('booking:dashboard')
    
    # Handle POST requests (e.g., cancellation)
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'cancel':
            # Check if user can cancel this booking
            if (booking.user == request.user or 
                (hasattr(request.user, 'userprofile') and 
                 request.user.userprofile.role in ['technician', 'sysadmin'])):
                
                if booking.can_be_cancelled:
                    booking.status = 'cancelled'
                    booking.save()
                    messages.success(request, f'Booking "{booking.title}" has been cancelled.')
                    return redirect('booking:dashboard')
                else:
                    messages.error(request, 'This booking cannot be cancelled.')
            else:
                messages.error(request, 'You do not have permission to cancel this booking.')
    
    # Get recurring series if applicable
    recurring_series = None
    if booking.is_recurring:
        try:
            recurring_series = RecurringBookingManager.get_recurring_series(booking)
        except:
            recurring_series = None
    
    return render(request, 'booking/booking_detail.html', {
        'booking': booking,
        'recurring_series': recurring_series,
    })


@login_required
def create_recurring_booking_view(request, booking_pk):
    """Create recurring bookings based on an existing booking."""
    base_booking = get_object_or_404(Booking, pk=booking_pk, user=request.user)
    
    # Check if user can create recurring bookings
    try:
        user_profile = request.user.userprofile
        if not user_profile.can_create_recurring:
            messages.error(request, 'You do not have permission to create recurring bookings.')
            return redirect('booking:booking_detail', pk=booking_pk)
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to create recurring bookings.')
        return redirect('booking:booking_detail', pk=booking_pk)
    
    if request.method == 'POST':
        form = RecurringBookingForm(request.POST)
        if form.is_valid():
            try:
                pattern = form.create_pattern()
                generator = RecurringBookingGenerator(base_booking, pattern)
                
                skip_conflicts = form.cleaned_data.get('skip_conflicts', True)
                result = generator.create_recurring_bookings(skip_conflicts=skip_conflicts)
                
                # Update the base booking to mark it as recurring
                base_booking.is_recurring = True
                base_booking.recurring_pattern = pattern.to_dict()
                base_booking.save()
                
                success_msg = f"Created {result['total_created']} recurring bookings."
                if result['skipped_dates']:
                    success_msg += f" Skipped {len(result['skipped_dates'])} dates due to conflicts."
                
                messages.success(request, success_msg)
                return redirect('booking:booking_detail', pk=booking_pk)
                
            except Exception as e:
                messages.error(request, f'Error creating recurring bookings: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = RecurringBookingForm()
    
    return render(request, 'booking/create_recurring.html', {
        'form': form,
        'base_booking': base_booking,
    })


@login_required
def cancel_recurring_series_view(request, booking_pk):
    """Cancel an entire recurring series."""
    booking = get_object_or_404(Booking, pk=booking_pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        if (booking.user != request.user and 
            user_profile.role not in ['technician', 'sysadmin']):
            messages.error(request, 'You do not have permission to cancel this booking series.')
            return redirect('booking:booking_detail', pk=booking_pk)
    except UserProfile.DoesNotExist:
        if booking.user != request.user:
            messages.error(request, 'You do not have permission to cancel this booking series.')
            return redirect('booking:booking_detail', pk=booking_pk)
    
    if not booking.is_recurring:
        messages.error(request, 'This is not a recurring booking.')
        return redirect('booking:booking_detail', pk=booking_pk)
    
    if request.method == 'POST':
        cancel_future_only = request.POST.get('cancel_future_only') == 'on'
        
        try:
            cancelled_count = RecurringBookingManager.cancel_recurring_series(
                booking, cancel_future_only=cancel_future_only
            )
            
            if cancel_future_only:
                messages.success(request, f'Cancelled {cancelled_count} future bookings in the series.')
            else:
                messages.success(request, f'Cancelled {cancelled_count} bookings in the entire series.')
                
            return redirect('booking:dashboard')
            
        except Exception as e:
            messages.error(request, f'Error cancelling recurring series: {str(e)}')
    
    # Get series info for confirmation
    series = RecurringBookingManager.get_recurring_series(booking)
    future_count = sum(1 for b in series if b.start_time > timezone.now() and b.can_be_cancelled)
    total_count = sum(1 for b in series if b.can_be_cancelled)
    
    return render(request, 'booking/cancel_recurring.html', {
        'booking': booking,
        'series': series,
        'future_count': future_count,
        'total_count': total_count,
    })


@login_required
def conflict_detection_view(request):
    """Conflict detection and resolution interface."""
    # Check if user has permission to view conflicts
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to access conflict management.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to access conflict management.')
        return redirect('booking:dashboard')
    
    # Get filter parameters
    resource_id = request.GET.get('resource')
    days_ahead = int(request.GET.get('days', 30))
    
    conflicts_data = {}
    selected_resource = None
    
    if resource_id:
        try:
            selected_resource = Resource.objects.select_related('closed_by').get(pk=resource_id)
            conflicts_data = ConflictManager.get_resource_conflicts_report(
                selected_resource, days_ahead
            )
        except Resource.DoesNotExist:
            messages.error(request, 'Selected resource not found.')
    
    # Get all resources for filter dropdown
    resources = Resource.objects.filter(is_active=True).order_by('name')
    
    return render(request, 'booking/conflicts.html', {
        'conflicts_data': conflicts_data,
        'selected_resource': selected_resource,
        'resources': resources,
        'days_ahead': days_ahead,
    })


@login_required
def resolve_conflict_view(request, conflict_type, id1, id2):
    """Resolve a specific conflict between two bookings."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to resolve conflicts.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to resolve conflicts.')
        return redirect('booking:dashboard')
    
    try:
        booking1 = Booking.objects.get(pk=id1)
        booking2 = Booking.objects.get(pk=id2)
    except Booking.DoesNotExist:
        messages.error(request, 'One or more bookings not found.')
        return redirect('booking:conflicts')
    
    # Verify there's actually a conflict
    conflicts = ConflictDetector.check_booking_conflicts(booking1, exclude_booking_ids=[])
    conflict = None
    for c in conflicts:
        if c.booking2.pk == booking2.pk:
            conflict = c
            break
    
    if not conflict:
        messages.warning(request, 'No conflict detected between these bookings.')
        return redirect('booking:conflicts')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'cancel_booking1':
            if booking1.can_be_cancelled:
                booking1.status = 'cancelled'
                booking1.save()
                messages.success(request, f'Cancelled booking: {booking1.title}')
            else:
                messages.error(request, f'Cannot cancel booking: {booking1.title}')
                
        elif action == 'cancel_booking2':
            if booking2.can_be_cancelled:
                booking2.status = 'cancelled'
                booking2.save()
                messages.success(request, f'Cancelled booking: {booking2.title}')
            else:
                messages.error(request, f'Cannot cancel booking: {booking2.title}')
                
        elif action == 'reschedule_booking1':
            new_start = request.POST.get('new_start_time')
            new_end = request.POST.get('new_end_time')
            if new_start and new_end:
                try:
                    booking1.start_time = timezone.datetime.fromisoformat(new_start.replace('T', ' '))
                    booking1.end_time = timezone.datetime.fromisoformat(new_end.replace('T', ' '))
                    booking1.save()
                    messages.success(request, f'Rescheduled booking: {booking1.title}')
                except Exception as e:
                    messages.error(request, f'Error rescheduling booking: {str(e)}')
            else:
                messages.error(request, 'Invalid time values provided.')
                
        elif action == 'reschedule_booking2':
            new_start = request.POST.get('new_start_time')
            new_end = request.POST.get('new_end_time')
            if new_start and new_end:
                try:
                    booking2.start_time = timezone.datetime.fromisoformat(new_start.replace('T', ' '))
                    booking2.end_time = timezone.datetime.fromisoformat(new_end.replace('T', ' '))
                    booking2.save()
                    messages.success(request, f'Rescheduled booking: {booking2.title}')
                except Exception as e:
                    messages.error(request, f'Error rescheduling booking: {str(e)}')
            else:
                messages.error(request, 'Invalid time values provided.')
        
        return redirect('booking:conflicts')
    
    # Generate suggestions for resolution
    try:
        user1_profile = booking1.user.userprofile
        user2_profile = booking2.user.userprofile
        
        suggestions1 = ConflictResolver.suggest_alternative_times(booking1, [conflict])
        suggestions2 = ConflictResolver.suggest_alternative_times(booking2, [conflict])
        
        alt_resources1 = ConflictResolver.suggest_alternative_resources(booking1, user1_profile)
        alt_resources2 = ConflictResolver.suggest_alternative_resources(booking2, user2_profile)
    except:
        suggestions1 = suggestions2 = []
        alt_resources1 = alt_resources2 = []
    
    return render(request, 'booking/resolve_conflict.html', {
        'conflict': conflict,
        'booking1': booking1,
        'booking2': booking2,
        'suggestions1': suggestions1,
        'suggestions2': suggestions2,
        'alt_resources1': alt_resources1,
        'alt_resources2': alt_resources2,
    })


@login_required 
def bulk_resolve_conflicts_view(request):
    """Bulk resolve multiple conflicts."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to resolve conflicts.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to resolve conflicts.')
        return redirect('booking:dashboard')
    
    if request.method == 'POST':
        resource_id = request.POST.get('resource_id')
        strategy = request.POST.get('strategy', 'suggest_alternatives')
        conflict_ids = request.POST.getlist('conflict_ids')
        
        try:
            resource = Resource.objects.select_related('closed_by').get(pk=resource_id)
            
            # Get conflicts for the resource
            conflicts_data = ConflictManager.get_resource_conflicts_report(resource, 30)
            all_conflicts = []
            
            # Convert conflict data back to conflict objects for processing
            for conflict_dict in conflicts_data['all_conflicts']:
                try:
                    booking1 = Booking.objects.get(pk=conflict_dict['booking1']['id'])
                    booking2 = Booking.objects.get(pk=conflict_dict['booking2']['id'])
                    from ..conflicts import BookingConflict
                    conflict_obj = BookingConflict(booking1, booking2)
                    all_conflicts.append(conflict_obj)
                except Booking.DoesNotExist:
                    continue
            
            # Filter to selected conflicts if specified
            if conflict_ids:
                selected_conflicts = []
                for conflict in all_conflicts:
                    conflict_id = f"{conflict.booking1.pk}_{conflict.booking2.pk}"
                    if conflict_id in conflict_ids:
                        selected_conflicts.append(conflict)
                all_conflicts = selected_conflicts
            
            # Bulk resolve
            if all_conflicts:
                resolution_results = ConflictManager.bulk_resolve_conflicts(
                    all_conflicts, strategy
                )
                
                messages.success(
                    request, 
                    f"Processed {len(all_conflicts)} conflicts. "
                    f"{resolution_results['summary']['auto_resolvable']} can be auto-resolved, "
                    f"{resolution_results['summary']['manual_review']} need manual review."
                )
            else:
                messages.warning(request, 'No conflicts selected for resolution.')
                
        except Resource.DoesNotExist:
            messages.error(request, 'Resource not found.')
        except Exception as e:
            messages.error(request, f'Error processing conflicts: {str(e)}')
    
    return redirect('booking:conflicts')


@login_required
def notifications_list(request):
    """Display user's notifications."""
    from booking.models import Notification
    
    # Get user's notifications, ordered by most recent first
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:50]
    
    # Count unread notifications (not marked as read)
    unread_count = Notification.objects.filter(
        user=request.user, 
        read_at__isnull=True
    ).count()
    
    # Mark notifications as read when viewing the list
    if request.method == 'GET':
        from django.utils import timezone
        Notification.objects.filter(
            user=request.user,
            read_at__isnull=True
        ).update(read_at=timezone.now(), status='read')
    
    return render(request, 'booking/notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })


@login_required
def notification_preferences(request):
    """Display and update user's notification preferences."""
    if request.method == 'POST':
        # Update preferences
        for key, value in request.POST.items():
            if key.startswith('pref_'):
                # Parse preference key: pref_{notification_type}_{delivery_method}
                parts = key.replace('pref_', '').split('_')
                if len(parts) >= 2:
                    notification_type = '_'.join(parts[:-1])
                    delivery_method = parts[-1]
                    
                    preference, created = NotificationPreference.objects.get_or_create(
                        user=request.user,
                        notification_type=notification_type,
                        delivery_method=delivery_method,
                        defaults={'is_enabled': value == 'on'}
                    )
                    
                    if not created:
                        preference.is_enabled = value == 'on'
                        preference.save()
        
        messages.success(request, 'Notification preferences updated successfully.')
        return redirect('booking:notification_preferences')
    
    # Get current preferences
    preferences = {}
    user_prefs = NotificationPreference.objects.filter(user=request.user)
    
    for pref in user_prefs:
        key = f"{pref.notification_type}_{pref.delivery_method}"
        preferences[key] = pref.is_enabled
    
    # Available notification types and delivery methods
    notification_types = NotificationPreference.NOTIFICATION_TYPES
    delivery_methods = NotificationPreference.DELIVERY_METHODS
    
    return render(request, 'booking/notification_preferences.html', {
        'preferences': preferences,
        'notification_types': notification_types,
        'delivery_methods': delivery_methods,
    })


# API Views for notifications
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """API viewset for user notifications."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Notification.objects.filter(
            user=self.request.user,
            delivery_method='in_app'
        ).select_related('booking', 'resource', 'maintenance').order_by('-created_at')
    
    def get_serializer_class(self):
        # Simple serializer for notifications
        from rest_framework import serializers
        
        class NotificationSerializer(serializers.ModelSerializer):
            class Meta:
                model = Notification
                fields = [
                    'id', 'notification_type', 'title', 'message', 'priority',
                    'status', 'created_at', 'sent_at', 'read_at', 'metadata'
                ]
                read_only_fields = fields
        
        return NotificationSerializer
    
    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Get count of unread notifications."""
        count = self.get_queryset().filter(status__in=['pending', 'sent']).count()
        return Response({'unread_count': count})
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read."""
        notification_ids = list(
            self.get_queryset().filter(status__in=['pending', 'sent']).values_list('id', flat=True)
        )
        
        updated_count = notification_service.mark_notifications_as_read(
            request.user, notification_ids
        )
        
        return Response({
            'marked_read': updated_count,
            'message': f'Marked {updated_count} notifications as read'
        })
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a specific notification as read."""
        notification = self.get_object()
        notification.mark_as_read()
        
        return Response({
            'status': 'read',
            'message': 'Notification marked as read'
        })


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """API viewset for notification preferences."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return NotificationPreference.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        from rest_framework import serializers
        
        class NotificationPreferenceSerializer(serializers.ModelSerializer):
            class Meta:
                model = NotificationPreference
                fields = [
                    'id', 'notification_type', 'delivery_method', 
                    'is_enabled', 'frequency', 'created_at', 'updated_at'
                ]
                read_only_fields = ['id', 'created_at', 'updated_at']
        
        return NotificationPreferenceSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


# Waiting List Views
@login_required
def waiting_list_view(request):
    """Display user's waiting list entries."""
    entries = waiting_list_service.get_user_waiting_list_entries(request.user)
    
    # Get pending notifications
    notifications = WaitingListNotification.objects.filter(
        waiting_list_entry__user=request.user,
        user_response='pending'
    ).select_related('waiting_list_entry__resource').order_by('-sent_at')
    
    return render(request, 'booking/waiting_list.html', {
        'waiting_list_entries': entries,
        'pending_notifications': notifications,
    })


@login_required
def join_waiting_list(request, resource_id):
    """Join waiting list for a resource."""
    resource = get_object_or_404(Resource, id=resource_id)
    
    # Check if user can access this resource
    try:
        user_profile = request.user.userprofile
        if not resource.is_available_for_user(user_profile):
            messages.error(request, f'You do not meet the requirements to book {resource.name}.', extra_tags='persistent-alert')
            return redirect('booking:calendar')
    except:
        messages.error(request, 'User profile not found.')
        return redirect('booking:calendar')
    
    if request.method == 'POST':
        try:
            # Get form data
            preferred_start = timezone.datetime.fromisoformat(request.POST['preferred_start_time'])
            preferred_end = timezone.datetime.fromisoformat(request.POST['preferred_end_time'])
            
            # Optional parameters
            options = {
                'min_duration_minutes': int(request.POST.get('min_duration_minutes', 60)),
                'max_duration_minutes': int(request.POST.get('max_duration_minutes', 240)),
                'flexible_start_time': request.POST.get('flexible_start_time') == 'on',
                'flexible_duration': request.POST.get('flexible_duration') == 'on',
                'auto_book': request.POST.get('auto_book') == 'on',
                'priority': request.POST.get('priority', 'normal'),
                'notes': request.POST.get('notes', ''),
            }
            
            # Add to waiting list
            entry = waiting_list_service.add_to_waiting_list(
                user=request.user,
                resource=resource,
                preferred_start=preferred_start,
                preferred_end=preferred_end,
                **options
            )
            
            messages.success(request, f'Successfully added to waiting list for {resource.name}!')
            return redirect('booking:waiting_list')
            
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Failed to join waiting list: {str(e)}')
    
    # Pre-fill with requested time if available
    requested_start = request.GET.get('start_time')
    requested_end = request.GET.get('end_time')
    
    return render(request, 'booking/join_waiting_list.html', {
        'resource': resource,
        'requested_start_time': requested_start,
        'requested_end_time': requested_end,
    })


@login_required
def leave_waiting_list(request, entry_id):
    """Leave waiting list."""
    success, message = waiting_list_service.cancel_waiting_list_entry(entry_id, request.user)
    
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)
    
    return redirect('booking:waiting_list')


@login_required
def respond_to_availability(request, notification_id):
    """Respond to availability notification."""
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'accept':
            success, message = waiting_list_service.accept_availability_offer(notification_id, request.user)
        elif action == 'decline':
            success, message = waiting_list_service.decline_availability_offer(notification_id, request.user)
        else:
            success, message = False, 'Invalid action.'
        
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
    
    return redirect('booking:waiting_list')


# API Views for Waiting List
class WaitingListEntryViewSet(viewsets.ModelViewSet):
    """API viewset for waiting list entries."""
    serializer_class = WaitingListEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get waiting list entries based on user permissions."""
        if hasattr(self.request.user, 'userprofile') and self.request.user.userprofile.role in ['technician', 'sysadmin']:
            return WaitingListEntry.objects.all().select_related('user', 'resource', 'resulting_booking')
        else:
            return WaitingListEntry.objects.filter(user=self.request.user).select_related('resource', 'resulting_booking')
    
    def perform_create(self, serializer):
        """Create waiting list entry for current user."""
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel waiting list entry."""
        entry = self.get_object()
        
        if entry.user != request.user and request.user.userprofile.role not in ['technician', 'sysadmin']:
            return Response({'error': 'Permission denied'}, status=403)
        
        if entry.status not in ['waiting', 'notified']:
            return Response({'error': 'Cannot cancel entry in current status'}, status=400)
        
        entry.cancel_waiting()
        return Response({'status': 'success', 'message': 'Waiting list entry cancelled'})
    
    @action(detail=True, methods=['post'])
    def book_slot(self, request, pk=None):
        """Book an available slot from waiting list entry."""
        entry = self.get_object()
        
        if entry.user != request.user:
            return Response({'error': 'Permission denied'}, status=403)
        
        if entry.status != 'notified':
            return Response({'error': 'No available slot to book'}, status=400)
        
        # Get slot details from request
        slot_data = request.data.get('slot')
        if not slot_data:
            return Response({'error': 'Slot data required'}, status=400)
        
        try:
            booking = entry.create_booking_from_slot(slot_data)
            return Response({
                'status': 'success',
                'message': 'Booking created successfully',
                'booking_id': booking.id
            })
        except Exception as e:
            return Response({'error': str(e)}, status=400)
    
    @action(detail=False, methods=['get'])
    def find_opportunities(self, request):
        """Find available booking opportunities for waiting list entries."""
        if request.user.userprofile.role not in ['technician', 'sysadmin']:
            return Response({'error': 'Permission denied'}, status=403)
        
        resource_id = request.query_params.get('resource')
        resource = None
        
        if resource_id:
            try:
                resource = Resource.objects.select_related('closed_by').get(id=resource_id)
            except Resource.DoesNotExist:
                return Response({'error': 'Resource not found'}, status=404)
        
        opportunities = WaitingListEntry.find_opportunities(resource)
        
        # Format the response
        formatted_opportunities = []
        for opportunity in opportunities:
            entry_data = WaitingListEntrySerializer(opportunity['entry']).data
            formatted_opportunities.append({
                'entry': entry_data,
                'available_slots': opportunity['slots']
            })
        
        return Response(formatted_opportunities)
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """Get waiting list statistics."""
        if request.user.userprofile.role not in ['technician', 'sysadmin']:
            return Response({'error': 'Permission denied'}, status=403)
        
        resource_id = request.query_params.get('resource')
        queryset = self.get_queryset()
        
        if resource_id:
            try:
                resource = Resource.objects.select_related('closed_by').get(id=resource_id)
                queryset = queryset.filter(resource=resource)
            except Resource.DoesNotExist:
                return Response({'error': 'Resource not found'}, status=404)
        
        # Calculate statistics
        stats = {
            'total_entries': queryset.count(),
            'waiting': queryset.filter(status='waiting').count(),
            'notified': queryset.filter(status='notified').count(),
            'booked': queryset.filter(status='booked').count(),
            'expired': queryset.filter(status='expired').count(),
            'cancelled': queryset.filter(status='cancelled').count(),
            'by_priority': {
                'urgent': queryset.filter(priority='urgent').count(),
                'high': queryset.filter(priority='high').count(),
                'normal': queryset.filter(priority='normal').count(),
                'low': queryset.filter(priority='low').count(),
            },
            'auto_book_enabled': queryset.filter(auto_book=True).count()
        }
        
        return Response(stats)


# WaitingListNotificationViewSet removed - using Notification model instead


@login_required
def resources_list_view(request):
    """View to display all available resources with access control."""
    resources = Resource.objects.filter(is_active=True).order_by('resource_type', 'name')
    
    # Add access information for each resource
    for resource in resources:
        resource.user_has_access_result = resource.user_has_access(request.user)
        resource.can_view_calendar_result = resource.can_user_view_calendar(request.user)
        
        # Check if user has pending access request
        resource.has_pending_request = AccessRequest.objects.filter(
            resource=resource,
            user=request.user,
            status='pending'
        ).exists()
        
        # Check if user has pending training request
        resource.has_pending_training = TrainingRequest.objects.filter(
            resource=resource,
            user=request.user,
            status__in=['pending', 'scheduled']
        ).exists()
    
    return render(request, 'booking/resources_list.html', {
        'resources': resources,
        'user': request.user,
    })


@login_required
def resource_detail_view(request, resource_id):
    """View to show resource details and calendar or access request form."""
    resource = get_object_or_404(Resource, id=resource_id, is_active=True)
    
    # Check user's access
    user_has_access = resource.user_has_access(request.user)
    can_view_calendar = resource.can_user_view_calendar(request.user)
    
    # Check if user has pending access request
    has_pending_request = AccessRequest.objects.filter(
        resource=resource,
        user=request.user,
        status='pending'
    ).exists()
    
    # Check if user has pending training request
    has_pending_training = TrainingRequest.objects.filter(
        resource=resource,
        user=request.user,
        status__in=['pending', 'scheduled']
    ).exists()
    
    # Get approval progress for the user
    approval_progress = resource.get_approval_progress(request.user)
    
    # Check required risk assessments for this resource
    required_risk_assessments = RiskAssessment.objects.filter(
        resource=resource,
        is_active=True,
        valid_until__gte=timezone.now().date()
    ).order_by('risk_level', 'title')
    
    # Check user's status for each required risk assessment
    user_risk_assessments = {}
    risk_assessment_status = {'completed': 0, 'pending': 0, 'not_started': 0}
    
    for ra in required_risk_assessments:
        try:
            user_ra = UserRiskAssessment.objects.get(
                user=request.user,
                risk_assessment=ra
            )
            user_risk_assessments[ra.id] = user_ra
            if user_ra.status == 'approved':
                risk_assessment_status['completed'] += 1
            elif user_ra.status in ['submitted', 'in_progress']:
                risk_assessment_status['pending'] += 1
            else:
                risk_assessment_status['not_started'] += 1
        except UserRiskAssessment.DoesNotExist:
            user_risk_assessments[ra.id] = None
            risk_assessment_status['not_started'] += 1
    
    # Determine if user needs to complete risk assessments
    # Only consider risk assessment if the resource requires it via boolean field
    needs_risk_assessments = (
        resource.requires_risk_assessment and
        (required_risk_assessments.exists() and 
         risk_assessment_status['completed'] < required_risk_assessments.count())
    )
    
    # Check if training is actually complete by examining approval progress
    training_completed = False
    if approval_progress and approval_progress.get('stages'):
        for stage in approval_progress['stages']:
            if stage.get('key') == 'training' and stage.get('status') == 'completed':
                training_completed = True
                break
    
    # Override has_pending_training if training is actually completed
    # This ensures we don't show "Training Pending" when training is done
    if training_completed:
        has_pending_training = False
    
    # If user can view calendar and resource is not closed, show calendar view
    if can_view_calendar and not resource.is_closed:
        return render(request, 'booking/resource_detail.html', {
            'resource': resource,
            'user_has_access': user_has_access,
            'can_view_calendar': can_view_calendar,
            'has_pending_training': has_pending_training,
            'approval_progress': approval_progress,
            'required_risk_assessments': required_risk_assessments,
            'user_risk_assessments': user_risk_assessments,
            'risk_assessment_status': risk_assessment_status,
            'needs_risk_assessments': needs_risk_assessments,
            'show_calendar': True,
        })
    
    # Otherwise show access request form
    return render(request, 'booking/resource_detail.html', {
        'resource': resource,
        'user_has_access': user_has_access,
        'can_view_calendar': can_view_calendar,
        'has_pending_request': has_pending_request,
        'has_pending_training': has_pending_training,
        'approval_progress': approval_progress,
        'required_risk_assessments': required_risk_assessments,
        'user_risk_assessments': user_risk_assessments,
        'risk_assessment_status': risk_assessment_status,
        'needs_risk_assessments': needs_risk_assessments,
        'show_calendar': False,
    })


@login_required
def request_resource_access_view(request, resource_id):
    """Handle resource access requests."""
    resource = get_object_or_404(Resource, id=resource_id, is_active=True)
    
    # Check if user already has access or pending request
    if resource.user_has_access(request.user):
        messages.info(request, 'You already have access to this resource.', extra_tags='persistent-alert')
        return redirect('booking:resource_detail', resource_id=resource.id)
    
    if AccessRequest.objects.filter(resource=resource, user=request.user, status='pending').exists():
        messages.info(request, 'You already have a pending access request for this resource.', extra_tags='persistent-alert')
        return redirect('booking:resource_detail', resource_id=resource.id)
    
    # Check if user has pending training request
    if TrainingRequest.objects.filter(resource=resource, user=request.user, status__in=['pending', 'scheduled']).exists():
        messages.info(request, 'You already have a pending training request for this resource.', extra_tags='persistent-alert')
        return redirect('booking:resource_detail', resource_id=resource.id)
    
    if request.method == 'POST':
        access_type = request.POST.get('access_type', 'book')
        justification = request.POST.get('justification', '').strip()
        requested_duration_days = request.POST.get('requested_duration_days')
        has_training = request.POST.get('has_training', '')
        supervisor_name = request.POST.get('supervisor_name', '').strip()
        supervisor_email = request.POST.get('supervisor_email', '').strip()
        
        if not justification:
            messages.error(request, 'Please provide a justification for your access request.')
            return redirect('booking:request_resource_access', resource_id=resource.id)
        
        # Check supervisor requirements for students
        user_profile = request.user.userprofile
        if user_profile.role == 'student':
            if not supervisor_name:
                messages.error(request, 'Supervisor name is required for student access requests.')
                return redirect('booking:request_resource_access', resource_id=resource.id)
            if not supervisor_email:
                messages.error(request, 'Supervisor email is required for student access requests.')
                return redirect('booking:request_resource_access', resource_id=resource.id)
        
        # Check if user meets training requirements
        user_profile = request.user.userprofile
        needs_training = resource.required_training_level > user_profile.training_level
        
        if needs_training:
            if has_training == 'yes':
                # User claims to have training but system shows they don't
                messages.warning(request, 
                    f'Our records show you have training level {user_profile.training_level}, but {resource.name} requires level {resource.required_training_level}. '
                    'Training information will be sent to you to update your qualifications.', extra_tags='persistent-alert')
                
                # Create training request for verification
                existing_training = TrainingRequest.objects.filter(
                    user=request.user,
                    resource=resource,
                    status__in=['pending', 'scheduled']
                ).first()
                
                if existing_training:
                    training_request = existing_training
                    created = False
                else:
                    training_request = TrainingRequest.objects.create(
                        user=request.user,
                        resource=resource,
                        status='pending',
                        requested_level=resource.required_training_level,
                        current_level=user_profile.training_level,
                        justification=f"Training verification needed for access to {resource.name}. User claims training completion. Original request: {justification}"
                    )
                    created = True
                
            elif has_training == 'no':
                # User acknowledges they need training
                messages.info(request, 'Training information will be sent to you as this resource requires additional training.', extra_tags='persistent-alert')
                
                # Create training request
                existing_training = TrainingRequest.objects.filter(
                    user=request.user,
                    resource=resource,
                    status__in=['pending', 'scheduled']
                ).first()
                
                if existing_training:
                    training_request = existing_training
                    created = False
                else:
                    training_request = TrainingRequest.objects.create(
                        user=request.user,
                        resource=resource,
                        status='pending',
                        requested_level=resource.required_training_level,
                        current_level=user_profile.training_level,
                        justification=f"Training needed for access to {resource.name}. Original request: {justification}"
                    )
                    created = True
            
            if 'training_request' in locals():
                if created:
                    messages.success(request, f'Training request for {resource.name} has been submitted. You will be contacted with training details.', extra_tags='persistent-alert')
                    
                    # Send notifications
                    try:
                        from booking.notifications import training_request_notifications
                        training_request_notifications.training_request_submitted(training_request)
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f"Failed to send training request submission notification: {e}")
                else:
                    messages.info(request, f'You already have a pending training request for {resource.name}.', extra_tags='persistent-alert')
            
            return redirect('booking:resource_detail', resource_id=resource.id)
        
        # User has sufficient training, proceed with access request
        access_request = AccessRequest.objects.create(
            resource=resource,
            user=request.user,
            access_type=access_type,
            justification=justification,
            requested_duration_days=int(requested_duration_days) if requested_duration_days else None,
            supervisor_name=supervisor_name if user_profile.role == 'student' else '',
            supervisor_email=supervisor_email if user_profile.role == 'student' else ''
        )
        
        messages.success(request, f'Access request for {resource.name} has been submitted successfully.', extra_tags='persistent-alert')
        
        # Send notifications
        try:
            from booking.notifications import access_request_notifications
            access_request_notifications.access_request_submitted(access_request)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send access request submission notification: {e}")
        
        return redirect('booking:resource_detail', resource_id=resource.id)
    
    # Determine if user is a student and needs supervisor info
    is_student = hasattr(request.user, 'userprofile') and request.user.userprofile.role == 'student'
    
    return render(request, 'booking/request_access.html', {
        'resource': resource,
        'is_student': is_student,
    })


@login_required
def notification_preferences_view(request):
    """Notification preferences management view."""
    from booking.models import NotificationPreference
    
    # Get all notification types
    notification_types = NotificationPreference.NOTIFICATION_TYPES
    delivery_methods = NotificationPreference.DELIVERY_METHODS
    frequency_choices = [
        ('immediate', 'Immediate'),
        ('daily_digest', 'Daily Digest'),
        ('weekly_digest', 'Weekly Digest'),
    ]
    
    if request.method == 'POST':
        # Process preference updates
        updated_count = 0
        
        for notification_type, _ in notification_types:
            for delivery_method, _ in delivery_methods:
                # Get form field names
                enabled_field = f"{notification_type}_{delivery_method}_enabled"
                frequency_field = f"{notification_type}_{delivery_method}_frequency"
                
                is_enabled = request.POST.get(enabled_field) == 'on'
                frequency = request.POST.get(frequency_field, 'immediate')
                
                # Update or create preference
                preference, created = NotificationPreference.objects.update_or_create(
                    user=request.user,
                    notification_type=notification_type,
                    delivery_method=delivery_method,
                    defaults={
                        'is_enabled': is_enabled,
                        'frequency': frequency
                    }
                )
                
                if created or preference.is_enabled != is_enabled:
                    updated_count += 1
        
        messages.success(request, f'Updated {updated_count} notification preferences.')
        return redirect('booking:notification_preferences')
    
    # Get current preferences
    current_preferences = {}
    user_prefs = NotificationPreference.objects.filter(user=request.user)
    
    for pref in user_prefs:
        key = f"{pref.notification_type}_{pref.delivery_method}"
        current_preferences[key] = {
            'enabled': pref.is_enabled,
            'frequency': pref.frequency
        }
    
    # Add default values for missing preferences
    from booking.notifications import notification_service
    for notification_type, _ in notification_types:
        for delivery_method, _ in delivery_methods:
            key = f"{notification_type}_{delivery_method}"
            if key not in current_preferences:
                defaults = notification_service.default_preferences.get(notification_type, {})
                current_preferences[key] = {
                    'enabled': defaults.get(delivery_method, False),
                    'frequency': defaults.get('frequency', 'immediate')
                }
    
    return render(request, 'booking/notification_preferences.html', {
        'notification_types': notification_types,
        'delivery_methods': delivery_methods,
        'frequency_choices': frequency_choices,
        'current_preferences': current_preferences,
    })


@login_required
def profile_view(request):
    """User profile management view."""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile, current_user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserProfileForm(instance=profile, current_user=request.user)
    
    return render(request, 'registration/profile.html', {'form': form, 'profile': profile})


@login_required
def calendar_view(request):
    """Main calendar view."""
    # System administrators can see all resources, including inactive ones
    if hasattr(request.user, 'userprofile') and request.user.userprofile.role == 'sysadmin':
        resources = Resource.objects.all()
    else:
        resources = Resource.objects.filter(is_active=True)
    
    return render(request, 'booking/calendar.html', {
        'user': request.user,
        'resources': resources,
    })


@login_required
def dashboard_view(request):
    """User dashboard view."""
    user_bookings = Booking.objects.filter(user=request.user).order_by('-created_at')[:10]
    return render(request, 'booking/dashboard.html', {
        'user': request.user,
        'recent_bookings': user_bookings,
    })


@login_required
def template_list_view(request):
    """List user's booking templates."""
    # Database-level filtering for accessible templates
    from django.db.models import Q
    
    try:
        user_profile = request.user.userprofile
        # Build query for accessible templates using database filtering
        templates = BookingTemplate.objects.filter(
            Q(user=request.user) |  # User's own templates
            Q(is_public=True) |     # Public templates
            Q(user__userprofile__group=user_profile.group, user__userprofile__group__isnull=False)  # Same group
        ).distinct().order_by('-use_count', 'name')
    except:
        # Fallback to just user's own templates and public ones
        templates = BookingTemplate.objects.filter(
            Q(user=request.user) | Q(is_public=True)
        ).distinct().order_by('-use_count', 'name')
    
    user_templates = templates.filter(user=request.user)
    public_templates = templates.filter(is_public=True).exclude(user=request.user)
    group_templates = templates.exclude(user=request.user, is_public=True)
    
    return render(request, 'booking/templates.html', {
        'user_templates': user_templates,
        'public_templates': public_templates,
        'group_templates': group_templates,
    })


@login_required
def template_create_view(request):
    """Create a new booking template."""
    if request.method == 'POST':
        form = BookingTemplateForm(request.POST, user=request.user)
        if form.is_valid():
            template = form.save(commit=False)
            template.user = request.user
            template.save()
            messages.success(request, f'Template "{template.name}" created successfully.')
            return redirect('booking:templates')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BookingTemplateForm(user=request.user)
    
    return render(request, 'booking/template_form.html', {
        'form': form,
        'title': 'Create Template',
    })


@login_required
def template_edit_view(request, pk):
    """Edit a booking template."""
    template = get_object_or_404(BookingTemplate, pk=pk)
    
    # Check if user can edit this template
    if template.user != request.user:
        messages.error(request, 'You can only edit your own templates.')
        return redirect('booking:templates')
    
    if request.method == 'POST':
        form = BookingTemplateForm(request.POST, instance=template, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Template "{template.name}" updated successfully.')
            return redirect('booking:templates')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BookingTemplateForm(instance=template, user=request.user)
    
    return render(request, 'booking/template_form.html', {
        'form': form,
        'template': template,
        'title': 'Edit Template',
    })


@login_required
def template_delete_view(request, pk):
    """Delete a booking template."""
    template = get_object_or_404(BookingTemplate, pk=pk)
    
    # Check if user can delete this template
    if template.user != request.user:
        messages.error(request, 'You can only delete your own templates.')
        return redirect('booking:templates')
    
    if request.method == 'POST':
        template_name = template.name
        template.delete()
        messages.success(request, f'Template "{template_name}" deleted successfully.')
        return redirect('booking:templates')
    
    return render(request, 'booking/template_confirm_delete.html', {
        'template': template,
    })


@login_required
def create_booking_from_template_view(request):
    """Create a booking from a template."""
    if request.method == 'POST':
        form = CreateBookingFromTemplateForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                booking = form.create_booking()
                booking.save()
                messages.success(request, f'Booking "{booking.title}" created from template.')
                return redirect('booking:booking_detail', pk=booking.pk)
            except Exception as e:
                messages.error(request, f'Error creating booking: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CreateBookingFromTemplateForm(user=request.user)
    
    return render(request, 'booking/create_from_template.html', {
        'form': form,
    })


@login_required
def save_booking_as_template_view(request, booking_pk):
    """Save an existing booking as a template."""
    booking = get_object_or_404(Booking, pk=booking_pk)
    
    # Check if user owns the booking
    if booking.user != request.user:
        messages.error(request, 'You can only save your own bookings as templates.')
        return redirect('booking:booking_detail', pk=booking_pk)
    
    if request.method == 'POST':
        form = SaveAsTemplateForm(request.POST)
        if form.is_valid():
            try:
                template = booking.save_as_template(
                    template_name=form.cleaned_data['name'],
                    template_description=form.cleaned_data['description'],
                    is_public=form.cleaned_data['is_public']
                )
                messages.success(request, f'Booking saved as template "{template.name}".')
                return redirect('booking:templates')
            except Exception as e:
                messages.error(request, f'Error saving template: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # Pre-fill form with booking data
        initial_data = {
            'name': f"{booking.title} Template",
            'description': f"Template based on booking: {booking.title}",
        }
        form = SaveAsTemplateForm(initial=initial_data)
    
    return render(request, 'booking/save_as_template.html', {
        'form': form,
        'booking': booking,
    })


@login_required
def bulk_booking_operations_view(request):
    """Bulk operations on multiple bookings."""
    if request.method == 'POST':
        action = request.POST.get('action')
        booking_ids = request.POST.getlist('booking_ids')
        
        if not booking_ids:
            messages.error(request, 'No bookings selected.')
            return redirect('booking:dashboard')
        
        try:
            user_profile = request.user.userprofile
        except UserProfile.DoesNotExist:
            messages.error(request, 'User profile not found.')
            return redirect('booking:dashboard')
        
        # Get bookings that user has permission to modify
        if user_profile.role in ['technician', 'sysadmin']:
            bookings = Booking.objects.filter(pk__in=booking_ids)
        else:
            bookings = Booking.objects.filter(pk__in=booking_ids, user=request.user)
        
        if not bookings.exists():
            messages.error(request, 'No bookings found or you do not have permission to modify them.')
            return redirect('booking:dashboard')
        
        success_count = 0
        error_count = 0
        errors = []
        
        if action == 'cancel':
            for booking in bookings:
                if booking.can_be_cancelled:
                    booking.status = 'cancelled'
                    booking.save()
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f'{booking.title} - Cannot be cancelled')
            
            if success_count > 0:
                messages.success(request, f'Successfully cancelled {success_count} booking(s).')
            if error_count > 0:
                messages.warning(request, f'{error_count} booking(s) could not be cancelled: {", ".join(errors[:3])}')
        
        elif action == 'approve' and user_profile.role in ['technician', 'sysadmin']:
            for booking in bookings:
                if booking.status == 'pending':
                    booking.status = 'approved'
                    booking.approved_by = request.user
                    booking.approved_at = timezone.now()
                    booking.save()
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f'{booking.title} - Not pending')
            
            if success_count > 0:
                messages.success(request, f'Successfully approved {success_count} booking(s).')
            if error_count > 0:
                messages.warning(request, f'{error_count} booking(s) could not be approved: {", ".join(errors[:3])}')
        
        elif action == 'reject' and user_profile.role in ['technician', 'sysadmin']:
            for booking in bookings:
                if booking.status == 'pending':
                    booking.status = 'rejected'
                    booking.save()
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f'{booking.title} - Not pending')
            
            if success_count > 0:
                messages.success(request, f'Successfully rejected {success_count} booking(s).')
            if error_count > 0:
                messages.warning(request, f'{error_count} booking(s) could not be rejected: {", ".join(errors[:3])}')
        
        else:
            messages.error(request, 'Invalid action or insufficient permissions.')
    
    return redirect('booking:dashboard')


@login_required
def booking_management_view(request):
    """Management interface for bookings with bulk operations."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to access booking management.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to access booking management.')
        return redirect('booking:dashboard')
    
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    resource_filter = request.GET.get('resource', '')
    user_filter = request.GET.get('user', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Base queryset
    bookings = Booking.objects.select_related('resource', 'user', 'approved_by').order_by('-created_at')
    
    # Apply filters
    if status_filter:
        bookings = bookings.filter(status=status_filter)
    
    if resource_filter:
        bookings = bookings.filter(resource_id=resource_filter)
    
    if user_filter:
        bookings = bookings.filter(
            Q(user__username__icontains=user_filter) |
            Q(user__first_name__icontains=user_filter) |
            Q(user__last_name__icontains=user_filter)
        )
    
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            bookings = bookings.filter(start_time__date__gte=from_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            bookings = bookings.filter(start_time__date__lte=to_date)
        except ValueError:
            pass
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(bookings, 25)  # Show 25 bookings per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get resources for filter dropdown
    resources = Resource.objects.filter(is_active=True).order_by('name')
    
    context = {
        'page_obj': page_obj,
        'resources': resources,
        'status_filter': status_filter,
        'resource_filter': resource_filter,
        'user_filter': user_filter,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': Booking.STATUS_CHOICES,
    }
    
    return render(request, 'booking/booking_management.html', context)


@login_required
def my_bookings_view(request):
    """User's own bookings with bulk operations."""
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    resource_filter = request.GET.get('resource', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Base queryset - user's own bookings
    bookings = Booking.objects.filter(user=request.user).select_related('resource', 'approved_by').order_by('-created_at')
    
    # Apply filters
    if status_filter:
        bookings = bookings.filter(status=status_filter)
    
    if resource_filter:
        bookings = bookings.filter(resource_id=resource_filter)
    
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            bookings = bookings.filter(start_time__date__gte=from_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            bookings = bookings.filter(start_time__date__lte=to_date)
        except ValueError:
            pass
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(bookings, 20)  # Show 20 bookings per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get resources for filter dropdown (only ones user has access to) - with caching
    cache_key = f"user_resources_{request.user.id}_{getattr(request.user, 'userprofile', None) and request.user.userprofile.id}"
    resources = cache.get(cache_key)
    
    if resources is None:
        try:
            user_profile = request.user.userprofile
            if user_profile.role == 'sysadmin':
                resources = list(Resource.objects.filter(is_active=True).order_by('name'))
            else:
                # Database-level filtering based on user access rules
                resources_queryset = Resource.objects.filter(
                    is_active=True,
                    required_training_level__lte=user_profile.training_level
                ).order_by('name')
                
                # Additional filtering for induction requirements
                if not user_profile.is_inducted:
                    resources_queryset = resources_queryset.filter(requires_induction=False)
                
                resources = list(resources_queryset)
        except:
            resources = list(Resource.objects.filter(is_active=True).order_by('name'))
        
        # Cache for 5 minutes
        cache.set(cache_key, resources, 300)
    
    context = {
        'page_obj': page_obj,
        'resources': resources,
        'status_filter': status_filter,
        'resource_filter': resource_filter,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': Booking.STATUS_CHOICES,
    }
    
    return render(request, 'booking/my_bookings.html', context)


@login_required
def edit_booking_view(request, pk):
    """Edit an existing booking."""
    booking = get_object_or_404(Booking, pk=pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        can_edit = (booking.user == request.user or 
                   user_profile.role in ['technician', 'sysadmin'])
    except UserProfile.DoesNotExist:
        can_edit = booking.user == request.user
    
    if not can_edit:
        messages.error(request, 'You do not have permission to edit this booking.')
        return redirect('booking:booking_detail', pk=pk)
    
    # Check if booking can be edited
    if booking.status not in ['pending', 'approved']:
        messages.error(request, 'Only pending or approved bookings can be edited.')
        return redirect('booking:booking_detail', pk=pk)
    
    # Don't allow editing past bookings
    if booking.start_time < timezone.now():
        messages.error(request, 'Cannot edit bookings that have already started.')
        return redirect('booking:booking_detail', pk=pk)
    
    if request.method == 'POST':
        form = BookingForm(request.POST, instance=booking, user=request.user)
        if form.is_valid():
            try:
                updated_booking = form.save(commit=False)
                
                # If the booking was approved and user made changes, set it back to pending
                if (booking.status == 'approved' and 
                    booking.user == request.user and 
                    user_profile.role not in ['technician', 'sysadmin']):
                    
                    # Check if any important fields changed
                    important_changes = (
                        updated_booking.resource != booking.resource or
                        updated_booking.start_time != booking.start_time or
                        updated_booking.end_time != booking.end_time
                    )
                    
                    if important_changes:
                        updated_booking.status = 'pending'
                        updated_booking.approved_by = None
                        updated_booking.approved_at = None
                        messages.info(request, 'Booking updated and set to pending approval due to time/resource changes.', extra_tags='persistent-alert')
                    else:
                        messages.success(request, 'Booking updated successfully.')
                else:
                    messages.success(request, 'Booking updated successfully.')
                
                updated_booking.save()
                return redirect('booking:booking_detail', pk=updated_booking.pk)
                
            except Exception as e:
                messages.error(request, f'Error updating booking: {str(e)}')
        else:
            # Add detailed error messages
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = BookingForm(instance=booking, user=request.user)
    
    return render(request, 'booking/edit_booking.html', {
        'form': form,
        'booking': booking,
    })


@login_required
def cancel_booking_view(request, pk):
    """Cancel a booking with confirmation."""
    booking = get_object_or_404(Booking, pk=pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        can_cancel = (booking.user == request.user or 
                     user_profile.role in ['technician', 'sysadmin'])
    except UserProfile.DoesNotExist:
        can_cancel = booking.user == request.user
    
    if not can_cancel:
        messages.error(request, 'You do not have permission to cancel this booking.')
        return redirect('booking:booking_detail', pk=pk)
    
    if not booking.can_be_cancelled:
        messages.error(request, 'This booking cannot be cancelled.')
        return redirect('booking:booking_detail', pk=pk)
    
    if request.method == 'POST':
        confirm = request.POST.get('confirm')
        if confirm == 'yes':
            booking.status = 'cancelled'
            booking.save()
            messages.success(request, f'Booking "{booking.title}" has been cancelled.')
            
            # Redirect based on user role
            if hasattr(request.user, 'userprofile') and request.user.userprofile.role in ['technician', 'sysadmin']:
                return redirect('booking:manage_bookings')
            else:
                return redirect('booking:my_bookings')
        else:
            return redirect('booking:booking_detail', pk=pk)
    
    return render(request, 'booking/cancel_booking.html', {
        'booking': booking,
    })


@login_required
def delete_booking_view(request, pk):
    """Delete a booking permanently (only for cancelled/completed bookings)."""
    booking = get_object_or_404(Booking, pk=pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        can_delete = (booking.user == request.user or 
                     user_profile.role in ['technician', 'sysadmin'])
    except UserProfile.DoesNotExist:
        can_delete = booking.user == request.user
    
    if not can_delete:
        messages.error(request, 'You do not have permission to delete this booking.')
        return redirect('booking:booking_detail', pk=pk)
    
    # Only allow deletion of cancelled or completed bookings
    if booking.status not in ['cancelled', 'completed']:
        messages.error(request, 'Only cancelled or completed bookings can be deleted.')
        return redirect('booking:booking_detail', pk=pk)
    
    if request.method == 'POST':
        confirm = request.POST.get('confirm_delete')
        if confirm == 'yes':
            booking_title = booking.title
            booking.delete()
            messages.success(request, f'Booking "{booking_title}" has been permanently deleted.')
            
            # Redirect based on user role
            if hasattr(request.user, 'userprofile') and request.user.userprofile.role in ['technician', 'sysadmin']:
                return redirect('booking:manage_bookings')
            else:
                return redirect('booking:my_bookings')
        else:
            return redirect('booking:booking_detail', pk=pk)
    
    return render(request, 'booking/delete_booking.html', {
        'booking': booking,
    })


@login_required
def duplicate_booking_view(request, pk):
    """Create a new booking based on an existing one."""
    original_booking = get_object_or_404(Booking, pk=pk)
    
    # Check if user has access to view the original booking
    try:
        user_profile = request.user.userprofile
        can_access = (
            original_booking.user == request.user or 
            user_profile.role in ['technician', 'sysadmin'] or
            (original_booking.shared_with_group and 
             user_profile.group == original_booking.user.userprofile.group)
        )
    except UserProfile.DoesNotExist:
        can_access = original_booking.user == request.user
    
    if not can_access:
        messages.error(request, 'You do not have permission to duplicate this booking.')
        return redirect('booking:dashboard')
    
    if request.method == 'POST':
        form = BookingForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                new_booking = form.save(commit=False)
                new_booking.user = request.user
                new_booking.status = 'pending'
                new_booking.save()
                
                messages.success(request, f'Booking "{new_booking.title}" created successfully.')
                return redirect('booking:booking_detail', pk=new_booking.pk)
            except Exception as e:
                messages.error(request, f'Error creating booking: {str(e)}')
        else:
            # Add detailed error messages
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        # Pre-populate form with original booking data, but adjust times
        initial_data = {
            'resource': original_booking.resource,
            'title': f"Copy of {original_booking.title}",
            'description': original_booking.description,
            'shared_with_group': original_booking.shared_with_group,
            'notes': original_booking.notes,
        }
        
        # Set start time to tomorrow at the same time
        tomorrow = timezone.now() + timedelta(days=1)
        duration = original_booking.end_time - original_booking.start_time
        
        start_time = tomorrow.replace(
            hour=original_booking.start_time.hour,
            minute=original_booking.start_time.minute,
            second=0,
            microsecond=0
        )
        end_time = start_time + duration
        
        initial_data['start_time'] = start_time
        initial_data['end_time'] = end_time
        
        form = BookingForm(initial=initial_data, user=request.user)
    
    return render(request, 'booking/duplicate_booking.html', {
        'form': form,
        'original_booking': original_booking,
    })


# Check-in/Check-out Views
@login_required
def checkin_view(request, booking_id):
    """Check in to a booking."""
    booking = get_object_or_404(Booking, id=booking_id)
    
    # Check if user can check in
    try:
        user_profile = request.user.userprofile
        can_checkin = (
            booking.user == request.user or
            booking.attendees.filter(id=request.user.id).exists() or
            user_profile.role in ['technician', 'sysadmin']
        )
    except UserProfile.DoesNotExist:
        can_checkin = booking.user == request.user
    
    if not can_checkin:
        messages.error(request, 'You do not have permission to check in to this booking.')
        return redirect('booking:booking_detail', pk=booking_id)
    
    if request.method == 'POST':
        notes = request.POST.get('notes', '')
        
        # Get client info for tracking
        ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        success, message = checkin_service.check_in_booking(
            booking_id=booking_id,
            user=request.user,
            notes=notes,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        
        return redirect('booking:booking_detail', pk=booking_id)
    
    return render(request, 'booking/checkin.html', {
        'booking': booking,
    })


@login_required
def checkout_view(request, booking_id):
    """Check out of a booking."""
    booking = get_object_or_404(Booking, id=booking_id)
    
    # Check if user can check out
    try:
        user_profile = request.user.userprofile
        can_checkout = (
            booking.user == request.user or
            booking.attendees.filter(id=request.user.id).exists() or
            user_profile.role in ['technician', 'sysadmin']
        )
    except UserProfile.DoesNotExist:
        can_checkout = booking.user == request.user
    
    if not can_checkout:
        messages.error(request, 'You do not have permission to check out of this booking.')
        return redirect('booking:booking_detail', pk=booking_id)
    
    if request.method == 'POST':
        notes = request.POST.get('notes', '')
        
        # Get client info for tracking
        ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        success, message = checkin_service.check_out_booking(
            booking_id=booking_id,
            user=request.user,
            notes=notes,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        
        return redirect('booking:booking_detail', pk=booking_id)
    
    return render(request, 'booking/checkout.html', {
        'booking': booking,
    })


@login_required
def checkin_status_view(request):
    """View current check-in status for user's bookings."""
    # Get user's bookings for today
    today = timezone.now().date()
    user_bookings = Booking.objects.filter(
        Q(user=request.user) | Q(attendees=request.user),
        start_time__date=today,
        status__in=['approved', 'confirmed']
    ).select_related('resource').distinct().order_by('start_time')
    
    # Get currently checked in bookings
    checked_in_bookings = Booking.objects.filter(
        Q(user=request.user) | Q(attendees=request.user),
        checked_in_at__isnull=False,
        checked_out_at__isnull=True
    ).select_related('resource').distinct()
    
    return render(request, 'booking/checkin_status.html', {
        'user_bookings': user_bookings,
        'checked_in_bookings': checked_in_bookings,
        'today': today,
    })


@login_required
def resource_checkin_status_view(request, resource_id):
    """View current check-in status for a specific resource (managers only)."""
    resource = get_object_or_404(Resource, id=resource_id)
    
    # Check if user has permission
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to view resource check-in status.')
            return redirect('booking:calendar')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to view resource check-in status.')
        return redirect('booking:calendar')
    
    # Get current check-ins for this resource
    current_checkins = checkin_service.get_current_checkins(resource)
    
    # Get today's bookings for this resource
    today = timezone.now().date()
    today_bookings = Booking.objects.filter(
        resource=resource,
        start_time__date=today,
        status__in=['approved', 'confirmed']
    ).select_related('user').order_by('start_time')
    
    # Get overdue check-ins and check-outs for this resource
    overdue_checkins = [b for b in checkin_service.get_overdue_checkins() if b.resource == resource]
    overdue_checkouts = [b for b in checkin_service.get_overdue_checkouts() if b.resource == resource]
    
    return render(request, 'booking/resource_checkin_status.html', {
        'resource': resource,
        'current_checkins': current_checkins,
        'today_bookings': today_bookings,
        'overdue_checkins': overdue_checkins,
        'overdue_checkouts': overdue_checkouts,
        'today': today,
    })


@login_required
@require_license_feature('advanced_reports')
def usage_analytics_view(request):
    """View usage analytics (managers only)."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to view usage analytics.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to view usage analytics.')
        return redirect('booking:dashboard')
    
    # Get filter parameters
    resource_id = request.GET.get('resource')
    days = int(request.GET.get('days', 30))
    
    # Calculate date range
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)
    
    # Get analytics
    resource = None
    if resource_id:
        try:
            resource = Resource.objects.get(id=resource_id)
        except Resource.DoesNotExist:
            pass
    
    analytics = checkin_service.get_usage_analytics(
        resource=resource,
        start_date=start_date,
        end_date=end_date
    )
    
    # Get all resources for filter
    resources = Resource.objects.filter(is_active=True).order_by('name')
    
    return render(request, 'booking/usage_analytics.html', {
        'analytics': analytics,
        'resource': resource,
        'resources': resources,
        'days': days,
        'start_date': start_date,
        'end_date': end_date,
    })


# API Views for Check-in/Check-out
@login_required
def api_checkin_booking(request, booking_id):
    """API endpoint for checking in to a booking."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    success, message = checkin_service.check_in_booking(
        booking_id=booking_id,
        user=request.user,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    
    if success:
        return JsonResponse({'success': True, 'message': message})
    else:
        return JsonResponse({'success': False, 'message': message}, status=400)


@login_required  
def api_checkout_booking(request, booking_id):
    """API endpoint for checking out of a booking."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    success, message = checkin_service.check_out_booking(
        booking_id=booking_id,
        user=request.user,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    
    if success:
        return JsonResponse({'success': True, 'message': message})
    else:
        return JsonResponse({'success': False, 'message': message}, status=400)


def ajax_load_colleges(request):
    """AJAX view to load colleges based on faculty selection."""
    faculty_id = request.GET.get('faculty_id')
    colleges = College.objects.filter(faculty_id=faculty_id, is_active=True).order_by('name')
    data = [{'id': college.id, 'name': college.name} for college in colleges]
    return JsonResponse({'colleges': data})


def ajax_load_departments(request):
    """AJAX view to load departments based on college selection."""
    college_id = request.GET.get('college_id')
    departments = Department.objects.filter(college_id=college_id, is_active=True).order_by('name')
    data = [{'id': department.id, 'name': department.name} for department in departments]
    return JsonResponse({'departments': data})


@login_required
def group_management_view(request):
    """Group management interface for managers."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to manage groups.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to manage groups.')
        return redirect('booking:dashboard')

    # Handle POST requests for group operations
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create_group':
            return handle_create_group(request)
        elif action == 'rename_group':
            return handle_rename_group(request)
        elif action == 'merge_groups':
            return handle_merge_groups(request)
        elif action == 'delete_group':
            return handle_delete_group(request)
        elif action == 'bulk_assign':
            return handle_bulk_assign_users(request)

    # Get groups with member counts
    groups_data = UserProfile.objects.exclude(group='').values('group').annotate(
        member_count=Count('id'),
        students=Count('id', filter=Q(role='student')),
        researchers=Count('id', filter=Q(role='researcher')),
        academics=Count('id', filter=Q(role='academic')),
        technicians=Count('id', filter=Q(role='technician')),
        recent_activity=Count('user__booking', filter=Q(user__booking__created_at__gte=timezone.now() - timedelta(days=30)))
    ).order_by('-member_count')

    # Get users without groups
    ungrouped_users = UserProfile.objects.filter(group='').select_related('user')
    
    # Get recent group activities (bookings by group members)
    recent_bookings = Booking.objects.filter(
        user__userprofile__group__isnull=False,
        created_at__gte=timezone.now() - timedelta(days=7)
    ).select_related('user__userprofile', 'resource').order_by('-created_at')[:20]

    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        groups_data = groups_data.filter(group__icontains=search_query)

    # Pagination
    paginator = Paginator(groups_data, 20)
    page_number = request.GET.get('page')
    groups_page = paginator.get_page(page_number)

    context = {
        'groups_data': groups_page,
        'ungrouped_users': ungrouped_users,
        'recent_bookings': recent_bookings,
        'search_query': search_query,
        'total_groups': groups_data.count(),
        'total_ungrouped': ungrouped_users.count(),
    }

    return render(request, 'booking/group_management.html', context)


@login_required  
def group_detail_view(request, group_name):
    """Detailed view of a specific group."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to view group details.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to view group details.')
        return redirect('booking:dashboard')

    # Get group members
    group_members = UserProfile.objects.filter(group=group_name).select_related(
        'user', 'faculty', 'college', 'department'
    ).order_by('user__last_name', 'user__first_name')

    if not group_members.exists():
        messages.error(request, f'Group "{group_name}" not found.')
        return redirect('booking:group_management')

    # Handle POST requests for member management
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'remove_member':
            user_id = request.POST.get('user_id')
            try:
                member = UserProfile.objects.get(id=user_id, group=group_name)
                member.group = ''
                member.save()
                messages.success(request, f'Removed {member.user.get_full_name()} from group {group_name}.')
            except UserProfile.DoesNotExist:
                messages.error(request, 'User not found in this group.')
        
        elif action == 'change_role':
            user_id = request.POST.get('user_id')
            new_role = request.POST.get('new_role')
            try:
                member = UserProfile.objects.get(id=user_id, group=group_name)
                member.role = new_role
                member.save()
                messages.success(request, f'Changed {member.user.get_full_name()}\'s role to {new_role}.')
            except UserProfile.DoesNotExist:
                messages.error(request, 'User not found in this group.')
        
        return redirect('booking:group_detail', group_name=group_name)

    # Get group statistics
    group_stats = {
        'total_members': group_members.count(),
        'roles': group_members.values('role').annotate(count=Count('id')),
        'recent_bookings': Booking.objects.filter(
            user__userprofile__group=group_name,
            created_at__gte=timezone.now() - timedelta(days=30)
        ).count(),
        'active_bookings': Booking.objects.filter(
            user__userprofile__group=group_name,
            status__in=['pending', 'approved'],
            start_time__gte=timezone.now()
        ).count(),
    }

    # Get group's recent bookings
    recent_bookings = Booking.objects.filter(
        user__userprofile__group=group_name
    ).select_related('user', 'resource').order_by('-created_at')[:10]

    # Available users to add to group
    available_users = UserProfile.objects.filter(group='').select_related('user')

    context = {
        'group_name': group_name,
        'group_members': group_members,
        'group_stats': group_stats,
        'recent_bookings': recent_bookings,
        'available_users': available_users,
        'role_choices': UserProfile.ROLE_CHOICES,
    }

    return render(request, 'booking/group_detail.html', context)


def handle_create_group(request):
    """Handle group creation."""
    group_name = request.POST.get('group_name', '').strip()
    description = request.POST.get('description', '').strip()
    
    if not group_name:
        messages.error(request, 'Group name is required.')
        return redirect('booking:group_management')
    
    # Check if group already exists
    if UserProfile.objects.filter(group=group_name).exists():
        messages.error(request, f'Group "{group_name}" already exists.')
        return redirect('booking:group_management')
    
    # For now, we'll just create the group when first user is assigned
    # In a more advanced implementation, we might have a separate Group model
    messages.success(request, f'Group "{group_name}" will be created when first user is assigned.')
    return redirect('booking:group_management')


def handle_rename_group(request):
    """Handle group renaming."""
    old_name = request.POST.get('old_group_name', '').strip()
    new_name = request.POST.get('new_group_name', '').strip()
    
    if not old_name or not new_name:
        messages.error(request, 'Both old and new group names are required.')
        return redirect('booking:group_management')
    
    if old_name == new_name:
        messages.error(request, 'New group name must be different from old name.')
        return redirect('booking:group_management')
    
    # Check if new name already exists
    if UserProfile.objects.filter(group=new_name).exists():
        messages.error(request, f'Group "{new_name}" already exists.')
        return redirect('booking:group_management')
    
    # Rename the group
    updated = UserProfile.objects.filter(group=old_name).update(group=new_name)
    
    if updated > 0:
        messages.success(request, f'Renamed group "{old_name}" to "{new_name}" for {updated} users.')
    else:
        messages.error(request, f'Group "{old_name}" not found.')
    
    return redirect('booking:group_management')


def handle_merge_groups(request):
    """Handle merging groups."""
    source_group = request.POST.get('source_group', '').strip()
    target_group = request.POST.get('target_group', '').strip()
    
    if not source_group or not target_group:
        messages.error(request, 'Both source and target group names are required.')
        return redirect('booking:group_management')
    
    if source_group == target_group:
        messages.error(request, 'Source and target groups must be different.')
        return redirect('booking:group_management')
    
    # Check if both groups exist
    source_count = UserProfile.objects.filter(group=source_group).count()
    target_count = UserProfile.objects.filter(group=target_group).count()
    
    if source_count == 0:
        messages.error(request, f'Source group "{source_group}" not found.')
        return redirect('booking:group_management')
    
    if target_count == 0:
        messages.error(request, f'Target group "{target_group}" not found.')
        return redirect('booking:group_management')
    
    # Merge the groups
    updated = UserProfile.objects.filter(group=source_group).update(group=target_group)
    
    messages.success(request, f'Merged {updated} users from "{source_group}" into "{target_group}".')
    return redirect('booking:group_management')


def handle_delete_group(request):
    """Handle group deletion (removes group assignment from users)."""
    group_name = request.POST.get('group_name', '').strip()
    
    if not group_name:
        messages.error(request, 'Group name is required.')
        return redirect('booking:group_management')
    
    # Remove group assignment from all users
    updated = UserProfile.objects.filter(group=group_name).update(group='')
    
    if updated > 0:
        messages.success(request, f'Removed group assignment from {updated} users in "{group_name}".')
    else:
        messages.error(request, f'Group "{group_name}" not found.')
    
    return redirect('booking:group_management')


def handle_bulk_assign_users(request):
    """Handle bulk assignment of users to a group."""
    group_name = request.POST.get('target_group', '').strip()
    user_ids = request.POST.getlist('user_ids')
    
    if not group_name:
        messages.error(request, 'Target group name is required.')
        return redirect('booking:group_management')
    
    if not user_ids:
        messages.error(request, 'No users selected.')
        return redirect('booking:group_management')
    
    # Update selected users
    updated = UserProfile.objects.filter(id__in=user_ids).update(group=group_name)
    
    messages.success(request, f'Assigned {updated} users to group "{group_name}".')
    return redirect('booking:group_management')


@login_required
def add_user_to_group(request, group_name):
    """Add a user to a specific group via AJAX."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            return JsonResponse({'error': 'Permission denied'}, status=403)
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    user_id = request.POST.get('user_id')
    
    try:
        user_profile = UserProfile.objects.get(id=user_id)
        user_profile.group = group_name
        user_profile.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Added {user_profile.user.get_full_name()} to group {group_name}.'
        })
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# Approval Workflow API Views

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from booking.serializers import (
    ResourceResponsibleSerializer, RiskAssessmentSerializer, UserRiskAssessmentSerializer,
    TrainingCourseSerializer, ResourceTrainingRequirementSerializer, UserTrainingSerializer,
    AccessRequestDetailSerializer
)
from ..models import (
    ResourceResponsible, RiskAssessment, UserRiskAssessment, TrainingCourse,
    ResourceTrainingRequirement, UserTraining, AccessRequest
)


class IsManagerOrReadOnly(permissions.BasePermission):
    """Permission that allows managers to edit, others to read only."""
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        
        # Write permissions for managers only
        try:
            user_profile = request.user.userprofile
            return user_profile.role in ['technician', 'sysadmin']
        except:
            return False


class ResourceResponsibleViewSet(viewsets.ModelViewSet):
    queryset = ResourceResponsible.objects.select_related('user', 'resource', 'assigned_by').all()
    serializer_class = ResourceResponsibleSerializer
    permission_classes = [IsManagerOrReadOnly]
    
    def get_queryset(self):
        queryset = ResourceResponsible.objects.select_related('user', 'resource', 'assigned_by')
        
        # Filter by resource
        resource_id = self.request.query_params.get('resource', None)
        if resource_id:
            queryset = queryset.filter(resource_id=resource_id)
        
        # Filter by user
        user_id = self.request.query_params.get('user', None)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Filter by role type
        role_type = self.request.query_params.get('role_type', None)
        if role_type:
            queryset = queryset.filter(role_type=role_type)
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def by_resource(self, request):
        """Get responsible persons for a specific resource."""
        resource_id = request.query_params.get('resource_id')
        if not resource_id:
            return Response({'error': 'resource_id parameter required'}, status=400)
        
        responsible_persons = self.get_queryset().filter(resource_id=resource_id, is_active=True)
        serializer = self.get_serializer(responsible_persons, many=True)
        return Response(serializer.data)


class RiskAssessmentViewSet(viewsets.ModelViewSet):
    queryset = RiskAssessment.objects.all()
    serializer_class = RiskAssessmentSerializer
    permission_classes = [IsManagerOrReadOnly]
    
    def get_queryset(self):
        queryset = RiskAssessment.objects.select_related('resource', 'created_by', 'approved_by')
        
        # Filter by resource
        resource_id = self.request.query_params.get('resource', None)
        if resource_id:
            queryset = queryset.filter(resource_id=resource_id)
        
        # Filter by assessment type
        assessment_type = self.request.query_params.get('assessment_type', None)
        if assessment_type:
            queryset = queryset.filter(assessment_type=assessment_type)
        
        # Filter by risk level
        risk_level = self.request.query_params.get('risk_level', None)
        if risk_level:
            queryset = queryset.filter(risk_level=risk_level)
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Filter by mandatory status
        is_mandatory = self.request.query_params.get('is_mandatory', None)
        if is_mandatory is not None:
            queryset = queryset.filter(is_mandatory=is_mandatory.lower() == 'true')
        
        return queryset
    
    @action(detail=True, methods=['post'], permission_classes=[IsManagerOrReadOnly])
    def approve(self, request, pk=None):
        """Approve a risk assessment."""
        assessment = self.get_object()
        assessment.approved_by = request.user
        assessment.approved_at = timezone.now()
        assessment.save()
        
        serializer = self.get_serializer(assessment)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_resource(self, request):
        """Get risk assessments for a specific resource."""
        resource_id = request.query_params.get('resource_id')
        if not resource_id:
            return Response({'error': 'resource_id parameter required'}, status=400)
        
        assessments = self.get_queryset().filter(resource_id=resource_id, is_active=True)
        serializer = self.get_serializer(assessments, many=True)
        return Response(serializer.data)


class UserRiskAssessmentViewSet(viewsets.ModelViewSet):
    queryset = UserRiskAssessment.objects.all()
    serializer_class = UserRiskAssessmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = UserRiskAssessment.objects.select_related('user', 'risk_assessment', 'reviewed_by')
        
        # Users can only see their own assessments unless they're managers
        try:
            user_profile = self.request.user.userprofile
            if user_profile.role not in ['technician', 'sysadmin']:
                queryset = queryset.filter(user=self.request.user)
        except:
            queryset = queryset.filter(user=self.request.user)
        
        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by user
        user_id = self.request.query_params.get('user', None)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Filter by risk assessment
        assessment_id = self.request.query_params.get('risk_assessment', None)
        if assessment_id:
            queryset = queryset.filter(risk_assessment_id=assessment_id)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start a risk assessment."""
        assessment = self.get_object()
        if assessment.user != request.user:
            return Response({'error': 'Permission denied'}, status=403)
        
        assessment.start_assessment()
        serializer = self.get_serializer(assessment)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Submit assessment for review."""
        assessment = self.get_object()
        if assessment.user != request.user:
            return Response({'error': 'Permission denied'}, status=403)
        
        responses = request.data.get('responses', {})
        declaration = request.data.get('declaration', '')
        
        assessment.submit_for_review(responses, declaration)
        serializer = self.get_serializer(assessment)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsManagerOrReadOnly])
    def approve(self, request, pk=None):
        """Approve an assessment."""
        assessment = self.get_object()
        score = request.data.get('score')
        notes = request.data.get('notes', '')
        
        assessment.approve(request.user, score, notes)
        serializer = self.get_serializer(assessment)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsManagerOrReadOnly])
    def reject(self, request, pk=None):
        """Reject an assessment."""
        assessment = self.get_object()
        notes = request.data.get('notes', '')
        
        assessment.reject(request.user, notes)
        serializer = self.get_serializer(assessment)
        return Response(serializer.data)


class TrainingCourseViewSet(viewsets.ModelViewSet):
    queryset = TrainingCourse.objects.all()
    serializer_class = TrainingCourseSerializer
    permission_classes = [IsManagerOrReadOnly]
    
    def get_queryset(self):
        queryset = TrainingCourse.objects.select_related('created_by').prefetch_related('instructors', 'prerequisite_courses')
        
        # Filter by course type
        course_type = self.request.query_params.get('course_type', None)
        if course_type:
            queryset = queryset.filter(course_type=course_type)
        
        # Filter by delivery method
        delivery_method = self.request.query_params.get('delivery_method', None)
        if delivery_method:
            queryset = queryset.filter(delivery_method=delivery_method)
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Filter by mandatory status
        is_mandatory = self.request.query_params.get('is_mandatory', None)
        if is_mandatory is not None:
            queryset = queryset.filter(is_mandatory=is_mandatory.lower() == 'true')
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def available_for_resource(self, request):
        """Get training courses required for a specific resource."""
        resource_id = request.query_params.get('resource_id')
        if not resource_id:
            return Response({'error': 'resource_id parameter required'}, status=400)
        
        # Get training requirements for the resource
        requirements = ResourceTrainingRequirement.objects.filter(
            resource_id=resource_id
        ).select_related('training_course')
        
        courses = [req.training_course for req in requirements]
        serializer = self.get_serializer(courses, many=True)
        return Response(serializer.data)


class ResourceTrainingRequirementViewSet(viewsets.ModelViewSet):
    queryset = ResourceTrainingRequirement.objects.all()
    serializer_class = ResourceTrainingRequirementSerializer
    permission_classes = [IsManagerOrReadOnly]
    
    def get_queryset(self):
        queryset = ResourceTrainingRequirement.objects.select_related('resource', 'training_course')
        
        # Filter by resource
        resource_id = self.request.query_params.get('resource', None)
        if resource_id:
            queryset = queryset.filter(resource_id=resource_id)
        
        # Filter by training course
        course_id = self.request.query_params.get('training_course', None)
        if course_id:
            queryset = queryset.filter(training_course_id=course_id)
        
        # Filter by mandatory status
        is_mandatory = self.request.query_params.get('is_mandatory', None)
        if is_mandatory is not None:
            queryset = queryset.filter(is_mandatory=is_mandatory.lower() == 'true')
        
        return queryset


class UserTrainingViewSet(viewsets.ModelViewSet):
    queryset = UserTraining.objects.all()
    serializer_class = UserTrainingSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = UserTraining.objects.select_related('user', 'training_course', 'instructor')
        
        # Users can only see their own training unless they're managers
        try:
            user_profile = self.request.user.userprofile
            if user_profile.role not in ['technician', 'sysadmin']:
                queryset = queryset.filter(user=self.request.user)
        except:
            queryset = queryset.filter(user=self.request.user)
        
        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by user
        user_id = self.request.query_params.get('user', None)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Filter by training course
        course_id = self.request.query_params.get('training_course', None)
        if course_id:
            queryset = queryset.filter(training_course_id=course_id)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start training."""
        training = self.get_object()
        if training.user != request.user:
            return Response({'error': 'Permission denied'}, status=403)
        
        training.start_training()
        serializer = self.get_serializer(training)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsManagerOrReadOnly])
    def complete(self, request, pk=None):
        """Complete training with scores."""
        training = self.get_object()
        
        theory_score = request.data.get('theory_score')
        practical_score = request.data.get('practical_score')
        instructor_notes = request.data.get('instructor_notes', '')
        
        training.complete_training(
            theory_score=theory_score,
            practical_score=practical_score,
            instructor=request.user,
            notes=instructor_notes
        )
        
        serializer = self.get_serializer(training)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def enroll(self, request):
        """Enroll user in a training course."""
        course_id = request.data.get('training_course_id')
        if not course_id:
            return Response({'error': 'training_course_id required'}, status=400)
        
        try:
            course = TrainingCourse.objects.get(id=course_id)
            training, created = UserTraining.objects.get_or_create(
                user=request.user,
                training_course=course,
                status='enrolled',
                defaults={'status': 'enrolled'}
            )
            
            if not created:
                return Response({'error': 'Already enrolled in this course'}, status=400)
            
            serializer = self.get_serializer(training)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        except TrainingCourse.DoesNotExist:
            return Response({'error': 'Training course not found'}, status=404)


class AccessRequestViewSet(viewsets.ModelViewSet):
    """Enhanced AccessRequest viewset with approval workflow."""
    queryset = AccessRequest.objects.select_related(
        'resource',
        'user__userprofile',
        'reviewed_by'
    ).all()
    serializer_class = AccessRequestDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = AccessRequest.objects.select_related('user', 'resource', 'reviewed_by')
        
        # Users can see their own requests, managers can see all
        try:
            user_profile = self.request.user.userprofile
            if user_profile.role not in ['technician', 'sysadmin']:
                # Check if user can approve requests for any resources
                can_approve = ResourceResponsible.objects.filter(
                    user=self.request.user,
                    is_active=True,
                    can_approve_access=True
                ).exists()
                
                if not can_approve:
                    queryset = queryset.filter(user=self.request.user)
        except:
            queryset = queryset.filter(user=self.request.user)
        
        # Filter by status
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by resource
        resource_id = self.request.query_params.get('resource', None)
        if resource_id:
            queryset = queryset.filter(resource_id=resource_id)
        
        # Filter requests that need approval by current user
        needs_approval = self.request.query_params.get('needs_approval', None)
        if needs_approval == 'true':
            # Get resources where current user can approve
            approvable_resources = ResourceResponsible.objects.filter(
                user=self.request.user,
                is_active=True,
                can_approve_access=True
            ).values_list('resource_id', flat=True)
            
            queryset = queryset.filter(
                resource_id__in=approvable_resources,
                status='pending'
            )
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve an access request."""
        access_request = self.get_object()
        
        # Check if user can approve this request
        if not access_request.can_be_approved_by(request.user):
            return Response({'error': 'Permission denied'}, status=403)
        
        # Check if user meets all requirements
        compliance = access_request.check_user_compliance()
        if not (compliance['training_complete'] and compliance['risk_assessments_complete']):
            return Response({
                'error': 'User has not completed all required training and risk assessments',
                'missing_requirements': {
                    'training': [str(t) for t in compliance['missing_training']],
                    'assessments': [str(a) for a in compliance['missing_assessments']]
                }
            }, status=400)
        
        review_notes = request.data.get('review_notes', '')
        expires_in_days = request.data.get('expires_in_days')
        
        access_request.approve(request.user, review_notes, expires_in_days)
        
        serializer = self.get_serializer(access_request)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject an access request."""
        access_request = self.get_object()
        
        # Check if user can approve this request
        if not access_request.can_be_approved_by(request.user):
            return Response({'error': 'Permission denied'}, status=403)
        
        review_notes = request.data.get('review_notes', '')
        access_request.reject(request.user, review_notes)
        
        serializer = self.get_serializer(access_request)
        return Response(serializer.data)


# Approval Workflow Template Views

@login_required
def approval_dashboard_view(request):
    """Dashboard for approval workflow management."""
    # Summary statistics
    pending_access_requests = AccessRequest.objects.filter(status='pending').count()
    incomplete_assessments = UserRiskAssessment.objects.filter(status='submitted').count()
    pending_training = UserTraining.objects.filter(status='completed').count()
    overdue_items = 0  # Placeholder for overdue calculations
    
    # Recent access requests
    recent_access_requests = AccessRequest.objects.filter(
        status='pending'
    ).select_related('user', 'resource').order_by('-created_at')[:5]
    
    # Quick stats
    approved_today = AccessRequest.objects.filter(
        status='approved',
        reviewed_at__date=timezone.now().date()
    ).count()
    total_this_week = AccessRequest.objects.filter(
        created_at__week=timezone.now().isocalendar().week
    ).count()
    
    context = {
        'pending_access_requests': pending_access_requests,
        'incomplete_assessments': incomplete_assessments,
        'pending_training': pending_training,
        'overdue_items': overdue_items,
        'recent_access_requests': recent_access_requests,
        'approved_today': approved_today,
        'total_this_week': total_this_week,
    }
    
    return render(request, 'booking/approval_dashboard.html', context)


@login_required
def access_requests_view(request):
    """List view for access requests."""
    from django.core.paginator import Paginator
    
    # Start with all access requests
    access_requests = AccessRequest.objects.select_related('user', 'resource', 'reviewed_by')
    
    # Apply filters
    status_filter = request.GET.get('status')
    if status_filter:
        access_requests = access_requests.filter(status=status_filter)
    
    resource_type_filter = request.GET.get('resource_type')
    if resource_type_filter:
        access_requests = access_requests.filter(resource__resource_type=resource_type_filter)
    
    access_type_filter = request.GET.get('access_type')
    if access_type_filter:
        access_requests = access_requests.filter(access_type=access_type_filter)
    
    # Order by priority and creation date
    access_requests = access_requests.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(access_requests, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Filter options for the template
    resource_types = Resource.RESOURCE_TYPE_CHOICES
    
    context = {
        'access_requests': page_obj,
        'resource_types': resource_types,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
    }
    
    return render(request, 'booking/access_requests.html', context)


@login_required
def access_request_detail_view(request, request_id):
    """Detail view for a single access request."""
    access_request = get_object_or_404(AccessRequest, id=request_id)
    
    # Check if current user can approve
    can_approve = access_request.can_be_approved_by(request.user)
    
    context = {
        'access_request': access_request,
        'can_approve': can_approve,
    }
    
    return render(request, 'booking/access_request_detail.html', context)


@login_required
def approve_access_request_view(request, request_id):
    """Approve an access request."""
    access_request = get_object_or_404(AccessRequest, id=request_id)
    
    # Check permissions
    if not access_request.can_be_approved_by(request.user):
        messages.error(request, "You don't have permission to approve this request.")
        return redirect('booking:access_request_detail', request_id=request_id)
    
    if request.method == 'POST':
        form = AccessRequestReviewForm(request.POST)
        if form.is_valid():
            review_notes = form.cleaned_data.get('review_notes', '')
            granted_duration = form.cleaned_data.get('granted_duration_days')
            
            # Approve the request
            access_request.approve(request.user, review_notes, granted_duration)
            
            messages.success(request, f"Access request for {access_request.resource.name} has been approved.")
            return redirect('booking:access_request_detail', request_id=request_id)
    else:
        form = AccessRequestReviewForm(initial={'decision': 'approve'})
    
    context = {
        'access_request': access_request,
        'form': form,
        'action': 'approve',
    }
    
    return render(request, 'booking/access_request_review.html', context)


@login_required
def reject_access_request_view(request, request_id):
    """Reject an access request."""
    access_request = get_object_or_404(AccessRequest, id=request_id)
    
    # Check permissions
    if not access_request.can_be_approved_by(request.user):
        messages.error(request, "You don't have permission to reject this request.")
        return redirect('booking:access_request_detail', request_id=request_id)
    
    if request.method == 'POST':
        form = AccessRequestReviewForm(request.POST)
        if form.is_valid():
            review_notes = form.cleaned_data.get('review_notes', '')
            
            # Reject the request
            access_request.reject(request.user, review_notes)
            
            messages.success(request, f"Access request for {access_request.resource.name} has been rejected.")
            return redirect('booking:access_request_detail', request_id=request_id)
    else:
        form = AccessRequestReviewForm(initial={'decision': 'reject'})
    
    context = {
        'access_request': access_request,
        'form': form,
        'action': 'reject',
    }
    
    return render(request, 'booking/access_request_review.html', context)


@login_required
def risk_assessments_view(request):
    """List view for risk assessments."""
    from django.core.paginator import Paginator
    
    # Get all risk assessments
    risk_assessments = RiskAssessment.objects.select_related('resource', 'created_by')
    
    # Apply filters
    assessment_type_filter = request.GET.get('assessment_type')
    if assessment_type_filter:
        risk_assessments = risk_assessments.filter(assessment_type=assessment_type_filter)
    
    risk_level_filter = request.GET.get('risk_level')
    if risk_level_filter:
        risk_assessments = risk_assessments.filter(risk_level=risk_level_filter)
    
    resource_filter = request.GET.get('resource')
    if resource_filter:
        risk_assessments = risk_assessments.filter(resource_id=resource_filter)
    
    status_filter = request.GET.get('status')
    if status_filter == 'active':
        risk_assessments = risk_assessments.filter(is_active=True, valid_until__gte=timezone.now().date())
    elif status_filter == 'expired':
        risk_assessments = risk_assessments.filter(valid_until__lt=timezone.now().date())
    
    # Filter by user (for viewing a specific user's risk assessments)
    user_filter = request.GET.get('user')
    if user_filter:
        risk_assessments = risk_assessments.filter(created_by_id=user_filter)
    
    # Order by creation date
    risk_assessments = risk_assessments.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(risk_assessments, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get user's assessment status
    user_assessments = {}
    if request.user.is_authenticated:
        user_assessment_qs = UserRiskAssessment.objects.filter(
            user=request.user,
            risk_assessment__in=risk_assessments
        ).select_related('risk_assessment')
        
        user_assessments = {
            ua.risk_assessment.id: ua for ua in user_assessment_qs
        }
    
    # Filter options
    assessment_types = RiskAssessment.ASSESSMENT_TYPES
    resources = Resource.objects.filter(is_active=True).order_by('name')
    
    context = {
        'risk_assessments': page_obj,
        'assessment_types': assessment_types,
        'resources': resources,
        'user_assessments': user_assessments,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
    }
    
    return render(request, 'booking/risk_assessments.html', context)


@login_required
def risk_assessment_detail_view(request, assessment_id):
    """Detail view for a risk assessment."""
    assessment = get_object_or_404(RiskAssessment, id=assessment_id)
    
    # Get user's assessment if exists
    user_assessment = None
    if request.user.is_authenticated:
        try:
            user_assessment = UserRiskAssessment.objects.get(
                user=request.user,
                risk_assessment=assessment
            )
        except UserRiskAssessment.DoesNotExist:
            pass
    
    context = {
        'assessment': assessment,
        'user_assessment': user_assessment,
    }
    
    return render(request, 'booking/risk_assessment_detail.html', context)


@login_required
def start_risk_assessment_view(request, assessment_id):
    """Start a risk assessment."""
    assessment = get_object_or_404(RiskAssessment, id=assessment_id)
    
    # Check if user already has an assessment
    user_assessment, created = UserRiskAssessment.objects.get_or_create(
        user=request.user,
        risk_assessment=assessment,
        defaults={'status': 'not_started'}
    )
    
    if request.method == 'POST':
        form = UserRiskAssessmentForm(request.POST, request.FILES, instance=user_assessment, risk_assessment=assessment)
        if form.is_valid():
            user_assessment = form.save(commit=False)
            
            # Handle file upload
            if form.cleaned_data.get('risk_assessment_file'):
                user_assessment.assessment_file = form.cleaned_data['risk_assessment_file']
            
            user_assessment.status = 'submitted'
            user_assessment.submitted_at = timezone.now()
            user_assessment.save()
            
            messages.success(request, "Risk assessment submitted for review.")
            return redirect('booking:resource_detail', resource_id=assessment.resource.id)
        else:
            # Add error message for failed validation
            messages.error(request, "Please correct the errors below before submitting.")
    else:
        # Mark as started
        if user_assessment.status == 'not_started':
            user_assessment.status = 'in_progress'
            user_assessment.started_at = timezone.now()
            user_assessment.save()
        
        form = UserRiskAssessmentForm(instance=user_assessment, risk_assessment=assessment)
    
    context = {
        'assessment': assessment,
        'user_assessment': user_assessment,
        'form': form,
    }
    
    return render(request, 'booking/start_risk_assessment.html', context)


@login_required
def submit_risk_assessment_view(request, assessment_id):
    """Submit a completed risk assessment."""
    assessment = get_object_or_404(RiskAssessment, id=assessment_id)
    user_assessment = get_object_or_404(
        UserRiskAssessment,
        user=request.user,
        risk_assessment=assessment
    )
    
    if user_assessment.status != 'in_progress':
        messages.error(request, "This assessment cannot be submitted.")
        return redirect('booking:risk_assessment_detail', assessment_id=assessment_id)
    
    user_assessment.status = 'submitted'
    user_assessment.submitted_at = timezone.now()
    user_assessment.save()
    
    messages.success(request, "Risk assessment submitted for review.")
    return redirect('booking:risk_assessment_detail', assessment_id=assessment_id)


@login_required
def create_risk_assessment_view(request):
    """Create a new risk assessment."""
    if not request.user.userprofile.role in ['technician', 'academic', 'sysadmin']:
        messages.error(request, "You don't have permission to create risk assessments.")
        return redirect('booking:risk_assessments')
    
    if request.method == 'POST':
        form = RiskAssessmentForm(request.POST)
        if form.is_valid():
            assessment = form.save(commit=False)
            assessment.created_by = request.user
            assessment.save()
            
            messages.success(request, f"Risk assessment '{assessment.title}' created successfully.")
            return redirect('booking:risk_assessment_detail', assessment_id=assessment.id)
    else:
        form = RiskAssessmentForm()
    
    context = {
        'form': form,
    }
    
    return render(request, 'booking/create_risk_assessment.html', context)


@login_required
def training_dashboard_view(request):
    """Dashboard for training management."""
    # User's training statistics
    my_completed_training = UserTraining.objects.filter(
        user=request.user, status='completed'
    ).count()
    
    my_in_progress_training = UserTraining.objects.filter(
        user=request.user, status='in_progress'
    ).count()
    
    available_courses = TrainingCourse.objects.filter(is_active=True).count()
    
    expiring_soon = UserTraining.objects.filter(
        user=request.user,
        status='completed',
        expires_at__lte=timezone.now() + timedelta(days=30)
    ).count()
    
    # User's training progress
    my_training = UserTraining.objects.filter(
        user=request.user
    ).select_related('training_course').order_by('-enrolled_at')[:6]
    
    # Recommended courses (placeholder logic)
    recommended_courses = TrainingCourse.objects.filter(
        is_active=True
    ).exclude(
        id__in=UserTraining.objects.filter(user=request.user).values_list('training_course_id', flat=True)
    )[:5]
    
    # Upcoming sessions
    upcoming_sessions = UserTraining.objects.filter(
        user=request.user,
        session_date__gte=timezone.now(),
        status__in=['enrolled', 'in_progress']
    ).order_by('session_date')[:5]
    
    context = {
        'my_completed_training': my_completed_training,
        'my_in_progress_training': my_in_progress_training,
        'available_courses': available_courses,
        'expiring_soon': expiring_soon,
        'my_training': my_training,
        'recommended_courses': recommended_courses,
        'upcoming_sessions': upcoming_sessions,
    }
    
    return render(request, 'booking/training_dashboard.html', context)


@login_required
def training_redirect_view(request, course_id=None):
    """Redirect training courses URLs to training dashboard."""
    messages.info(request, "Training enrollment has been replaced with scheduled training managed by lab administrators.")
    return redirect('booking:training_dashboard')


@login_required  
def training_course_detail_view(request, course_id):
    """Redirect to training dashboard - course enrollment removed."""
    return training_redirect_view(request, course_id)


@login_required
def enroll_training_view(request, course_id):
    """Redirect to training dashboard - course enrollment removed."""
    return training_redirect_view(request, course_id)


@login_required
def my_training_view(request):
    """View user's training records."""
    training_records = UserTraining.objects.filter(
        user=request.user
    ).select_related('training_course').order_by('-enrolled_at')
    
    context = {
        'training_records': training_records,
    }
    
    return render(request, 'booking/my_training.html', context)


@login_required
def manage_training_view(request):
    """Manage training (for instructors/managers)."""
    if not request.user.userprofile.role in ['technician', 'academic', 'sysadmin']:
        messages.error(request, "You don't have permission to manage training.")
        return redirect('booking:training_dashboard')
    
    # Get training records to review
    pending_training = UserTraining.objects.filter(
        status='completed'
    ).select_related('user', 'training_course').order_by('-completed_at')
    
    context = {
        'pending_training': pending_training,
    }
    
    return render(request, 'booking/manage_training.html', context)


@login_required
def manage_resource_view(request, resource_id):
    """Manage a specific resource."""
    resource = get_object_or_404(Resource, id=resource_id)
    
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        messages.error(request, "You don't have permission to manage resources.")
        return redirect('booking:resource_detail', resource_id=resource_id)
    
    context = {
        'resource': resource,
    }
    
    return render(request, 'booking/manage_resource.html', context)


@login_required
def assign_resource_responsible_view(request, resource_id):
    """Assign responsibility for a resource."""
    resource = get_object_or_404(Resource, id=resource_id)
    
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        messages.error(request, "You don't have permission to assign resource responsibility.")
        return redirect('booking:resource_detail', resource_id=resource_id)
    
    if request.method == 'POST':
        form = ResourceResponsibleForm(request.POST, resource=resource)
        if form.is_valid():
            responsible = form.save(commit=False)
            responsible.resource = resource
            responsible.assigned_by = request.user
            responsible.save()
            
            messages.success(request, f"Resource responsibility assigned to {responsible.user.get_full_name()}.")
            return redirect('booking:manage_resource', resource_id=resource_id)
    else:
        form = ResourceResponsibleForm(resource=resource)
    
    context = {
        'resource': resource,
        'form': form,
    }
    
    return render(request, 'booking/assign_resource_responsible.html', context)


@login_required
def resource_training_requirements_view(request, resource_id):
    """Manage training requirements for a resource."""
    resource = get_object_or_404(Resource, id=resource_id)
    
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        messages.error(request, "You don't have permission to manage training requirements.")
        return redirect('booking:resource_detail', resource_id=resource_id)
    
    training_requirements = ResourceTrainingRequirement.objects.filter(
        resource=resource
    ).select_related('training_course').order_by('order')
    
    context = {
        'resource': resource,
        'training_requirements': training_requirements,
    }
    
    return render(request, 'booking/resource_training_requirements.html', context)



def is_lab_admin(user):
    """Check if user is in Lab Admin group."""
    return user.groups.filter(name='Lab Admin').exists() or user.is_staff or user.userprofile.role in ['technician', 'sysadmin']

@login_required
@user_passes_test(is_lab_admin)
@require_license_feature('advanced_reports')
def approval_statistics_view(request):
    """User-friendly approval statistics dashboard."""
    from booking.models import ApprovalStatistics, AccessRequest, TrainingRequest
    from django.db.models import Avg, Sum, Count
    from datetime import datetime, timedelta
    import json
    
    # Get filter parameters
    period_type = request.GET.get('period', 'monthly')
    resource_filter = request.GET.get('resource')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Set default date range (last 30 days)
    today = timezone.now().date()
    if not start_date:
        start_date = today - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    if not end_date:
        end_date = today
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # Base queryset for statistics
    stats_qs = ApprovalStatistics.objects.filter(
        period_start__gte=start_date,
        period_end__lte=end_date,
        period_type=period_type
    )
    
    # Filter by resource if specified
    if resource_filter:
        stats_qs = stats_qs.filter(resource_id=resource_filter)
    
    # Only show statistics for resources the user has responsibility for (unless admin)
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        stats_qs = stats_qs.filter(resource__responsible_persons__user=request.user)
    
    # Calculate summary statistics
    summary_data = stats_qs.aggregate(
        total_requests=Sum('access_requests_received'),
        total_approved=Sum('access_requests_approved'),
        total_rejected=Sum('access_requests_rejected'),
        total_pending=Sum('access_requests_pending'),
        avg_response_time=Avg('avg_response_time_hours'),
        total_overdue=Sum('overdue_items'),
        total_training_requests=Sum('training_requests_received'),
        total_training_completions=Sum('training_completions'),
        total_assessments=Sum('assessments_created'),
    )
    
    # Calculate approval rate
    total_processed = (summary_data['total_approved'] or 0) + (summary_data['total_rejected'] or 0)
    approval_rate = (summary_data['total_approved'] or 0) / total_processed * 100 if total_processed > 0 else 0
    
    # Calculate trends (comparing to previous period)
    previous_start = start_date - (end_date - start_date)
    previous_end = start_date - timedelta(days=1)
    
    previous_stats = ApprovalStatistics.objects.filter(
        period_start__gte=previous_start,
        period_end__lte=previous_end,
        period_type=period_type
    )
    
    if resource_filter:
        previous_stats = previous_stats.filter(resource_id=resource_filter)
    
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        previous_stats = previous_stats.filter(resource__responsible_persons__user=request.user)
    
    previous_data = previous_stats.aggregate(
        prev_total_requests=Sum('access_requests_received'),
        prev_total_approved=Sum('access_requests_approved'),
        prev_total_rejected=Sum('access_requests_rejected'),
        prev_avg_response_time=Avg('avg_response_time_hours'),
        prev_total_overdue=Sum('overdue_items'),
    )
    
    # Calculate trend indicators
    prev_processed = (previous_data['prev_total_approved'] or 0) + (previous_data['prev_total_rejected'] or 0)
    prev_approval_rate = (previous_data['prev_total_approved'] or 0) / prev_processed * 100 if prev_processed > 0 else 0
    
    summary = {
        'total_requests': summary_data['total_requests'] or 0,
        'approval_rate': approval_rate,
        'avg_response_time': summary_data['avg_response_time'] or 0,
        'overdue_items': summary_data['total_overdue'] or 0,
        
        # Trends
        'approval_change': approval_rate - prev_approval_rate,
        'approval_trend': 'up' if approval_rate > prev_approval_rate else 'down' if approval_rate < prev_approval_rate else 'stable',
        'response_change': (summary_data['avg_response_time'] or 0) - (previous_data['prev_avg_response_time'] or 0),
        'response_trend': 'down' if (summary_data['avg_response_time'] or 0) < (previous_data['prev_avg_response_time'] or 0) else 'up' if (summary_data['avg_response_time'] or 0) > (previous_data['prev_avg_response_time'] or 0) else 'stable',
        'overdue_change': (summary_data['total_overdue'] or 0) - (previous_data['prev_total_overdue'] or 0),
        'overdue_trend': 'up' if (summary_data['total_overdue'] or 0) > (previous_data['prev_total_overdue'] or 0) else 'down' if (summary_data['total_overdue'] or 0) < (previous_data['prev_total_overdue'] or 0) else 'stable',
        'volume_change': (summary_data['total_requests'] or 0) - (previous_data['prev_total_requests'] or 0),
        'volume_trend': 'up' if (summary_data['total_requests'] or 0) > (previous_data['prev_total_requests'] or 0) else 'down' if (summary_data['total_requests'] or 0) < (previous_data['prev_total_requests'] or 0) else 'stable',
    }
    
    # Resource-level statistics
    resource_stats = []
    for stat in stats_qs.select_related('resource', 'approver'):
        total_requests = stat.access_requests_received
        approved = stat.access_requests_approved
        rejected = stat.access_requests_rejected
        processed = approved + rejected
        
        resource_stats.append({
            'resource_name': stat.resource.name,
            'approver_name': stat.approver.get_full_name() or stat.approver.username,
            'total_requests': total_requests,
            'approved': approved,
            'rejected': rejected,
            'approval_rate': (approved / processed * 100) if processed > 0 else 0,
            'avg_response_time': stat.avg_response_time_hours,
            'overdue': stat.overdue_items,
        })
    
    # Sort by total requests descending
    resource_stats.sort(key=lambda x: x['total_requests'], reverse=True)
    
    # Top performers (by approval rate and response time)
    top_performers = sorted(resource_stats, key=lambda x: (x['approval_rate'], -x['avg_response_time']), reverse=True)[:5]
    
    # Chart data for distribution
    distribution_labels = ['Approved', 'Rejected', 'Pending']
    distribution_data = [
        summary_data['total_approved'] or 0,
        summary_data['total_rejected'] or 0,
        summary_data['total_pending'] or 0
    ]
    
    # Timeline data for response time trend
    timeline_stats = stats_qs.order_by('period_start').values('period_start', 'avg_response_time_hours')
    timeline_labels = [stat['period_start'].strftime('%m/%d') for stat in timeline_stats]
    timeline_data = [stat['avg_response_time_hours'] for stat in timeline_stats]
    
    # Recent activity (mock data - in real implementation, this would come from audit logs)
    recent_activity = [
        {
            'description': 'New access request approved for Lab Equipment A',
            'timestamp': timezone.now() - timedelta(hours=2),
            'icon': 'check',
            'color': 'success'
        },
        {
            'description': 'Training session completed for Safety Protocol',
            'timestamp': timezone.now() - timedelta(hours=5),
            'icon': 'graduation-cap',
            'color': 'info'
        },
        {
            'description': 'Risk assessment reviewed for Chemical Lab',
            'timestamp': timezone.now() - timedelta(hours=8),
            'icon': 'shield-alt',
            'color': 'warning'
        },
    ]
    
    # Get all resources for filter dropdown
    resources = Resource.objects.all().order_by('name')
    
    # Handle CSV export
    if request.GET.get('export') == 'csv':
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="approval_statistics_{start_date}_to_{end_date}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Resource', 'Approver', 'Total Requests', 'Approved', 'Rejected', 
            'Approval Rate (%)', 'Avg Response Time (hours)', 'Overdue Items'
        ])
        
        for stat in resource_stats:
            writer.writerow([
                stat['resource_name'],
                stat['approver_name'],
                stat['total_requests'],
                stat['approved'],
                stat['rejected'],
                f"{stat['approval_rate']:.1f}",
                f"{stat['avg_response_time']:.1f}",
                stat['overdue']
            ])
        
        return response
    
    context = {
        'summary': summary,
        'resource_stats': resource_stats[:10],  # Limit to top 10 for display
        'top_performers': top_performers,
        'recent_activity': recent_activity,
        'resources': resources,
        
        # Chart data (convert to JSON for template)
        'distribution_labels': json.dumps(distribution_labels),
        'distribution_data': json.dumps(distribution_data),
        'timeline_labels': json.dumps(timeline_labels),
        'timeline_data': json.dumps(timeline_data),
    }
    
    return render(request, 'booking/approval_statistics.html', context)


@login_required
def approval_rules_view(request):
    """User-friendly approval rules management interface."""
    from booking.models import ApprovalRule
    import json
    
    # Only allow technicians and sysadmins to manage rules
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        messages.error(request, "You don't have permission to manage approval rules.")
        return redirect('booking:dashboard')
    
    # Get all rules with filters
    rules_qs = ApprovalRule.objects.all().select_related('resource', 'fallback_rule')
    
    # Apply filters
    type_filter = request.GET.get('type')
    resource_filter = request.GET.get('resource')
    search_filter = request.GET.get('search')
    
    if type_filter:
        rules_qs = rules_qs.filter(approval_type=type_filter)
    
    if resource_filter:
        rules_qs = rules_qs.filter(resource_id=resource_filter)
    
    if search_filter:
        rules_qs = rules_qs.filter(
            Q(name__icontains=search_filter) |
            Q(description__icontains=search_filter)
        )
    
    # Order by priority, then by created date
    rules_qs = rules_qs.order_by('priority', '-created_at')
    
    # Pagination
    paginator = Paginator(rules_qs, 10)
    page_number = request.GET.get('page')
    rules = paginator.get_page(page_number)
    
    # Calculate statistics
    stats = {
        'auto_rules': ApprovalRule.objects.filter(approval_type='auto').count(),
        'manual_rules': ApprovalRule.objects.filter(approval_type__in=['single', 'tiered']).count(),
        'conditional_rules': ApprovalRule.objects.filter(approval_type='conditional').count(),
        'active_rules': ApprovalRule.objects.filter(is_active=True).count(),
    }
    
    # Get resources for filters and creation
    resources = Resource.objects.all().order_by('name')
    
    # Get all rules for fallback options
    all_rules = ApprovalRule.objects.all().order_by('name')
    
    # Handle POST request for creating rule
    if request.method == 'POST':
        try:
            # Get form data
            name = request.POST.get('name')
            approval_type = request.POST.get('approval_type')
            description = request.POST.get('description', '')
            resource_id = request.POST.get('resource')
            user_role = request.POST.get('user_role')
            priority = int(request.POST.get('priority', 100))
            fallback_rule_id = request.POST.get('fallback_rule')
            condition_type = request.POST.get('condition_type')
            conditional_logic_json = request.POST.get('conditional_logic')
            
            # Validate required fields
            if not all([name, approval_type]):
                messages.error(request, "Please fill in all required fields.")
                return redirect('booking:approval_rules')
            
            # Get related objects
            resource = None
            if resource_id:
                resource = get_object_or_404(Resource, id=resource_id)
            
            fallback_rule = None
            if fallback_rule_id:
                fallback_rule = get_object_or_404(ApprovalRule, id=fallback_rule_id)
            
            # Parse conditional logic
            conditional_logic = {}
            if approval_type == 'conditional' and conditional_logic_json:
                try:
                    conditional_logic = json.loads(conditional_logic_json)
                except json.JSONDecodeError:
                    conditional_logic = {}
            
            # Create approval rule
            rule = ApprovalRule.objects.create(
                name=name,
                approval_type=approval_type,
                description=description,
                resource=resource,
                user_role=user_role if user_role else None,
                priority=priority,
                fallback_rule=fallback_rule,
                condition_type=condition_type if approval_type == 'conditional' else 'role_based',
                conditional_logic=conditional_logic,
                is_active=True,
                created_by=request.user
            )
            
            messages.success(request, f"Approval rule '{name}' created successfully.")
            return redirect('booking:approval_rules')
            
        except Exception as e:
            messages.error(request, f"Error creating approval rule: {str(e)}")
            return redirect('booking:approval_rules')
    
    context = {
        'rules': rules,
        'stats': stats,
        'resources': resources,
        'all_rules': all_rules,
    }
    
    return render(request, 'booking/approval_rules.html', context)


@login_required
def approval_rule_toggle_view(request, rule_id):
    """Toggle approval rule active/inactive status."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})
    
    # Only allow technicians and sysadmins
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    try:
        import json
        
        rule = get_object_or_404(ApprovalRule, id=rule_id)
        
        data = json.loads(request.body)
        new_status = data.get('active', False)
        
        rule.is_active = new_status
        rule.save()
        
        return JsonResponse({
            'success': True, 
            'message': f"Rule {'enabled' if new_status else 'disabled'} successfully"
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# Lab Admin Views

@login_required
@user_passes_test(is_lab_admin)
def lab_admin_dashboard_view(request):
    """Lab Admin dashboard with overview of pending tasks."""
    from booking.models import AccessRequest, TrainingRequest, UserTraining, UserProfile
    from django.utils import timezone
    from datetime import timedelta
    
    # Get pending items
    pending_access_requests = AccessRequest.objects.filter(status='pending').count()
    pending_training_requests = TrainingRequest.objects.filter(status='pending').count()
    
    # Get upcoming training sessions
    upcoming_training = UserTraining.objects.filter(
        session_date__gte=timezone.now().date(),
        status='scheduled'
    ).count()
    
    # Get recent registrations (last 7 days)
    week_ago = timezone.now() - timedelta(days=7)
    recent_registrations = UserProfile.objects.filter(
        user__date_joined__gte=week_ago
    ).count()
    
    # Get overdue items
    overdue_access_requests = AccessRequest.objects.filter(
        status='pending',
        created_at__lt=timezone.now() - timedelta(days=3)
    ).count()
    
    # Get induction statistics
    not_inducted_count = UserProfile.objects.filter(is_inducted=False).count()
    
    context = {
        'pending_access_requests': pending_access_requests,
        'pending_training_requests': pending_training_requests,
        'upcoming_training': upcoming_training,
        'recent_registrations': recent_registrations,
        'overdue_access_requests': overdue_access_requests,
        'not_inducted_count': not_inducted_count,
    }
    
    return render(request, 'booking/lab_admin_dashboard.html', context)


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_access_requests_view(request):
    """Manage access requests."""
    from booking.models import AccessRequest, TrainingRequest
    
    # Handle status updates
    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')
        
        if request_id and action:
            access_request = get_object_or_404(AccessRequest, id=request_id)
            
            if action == 'approve':
                try:
                    # Double-check prerequisites before approval
                    if not access_request.prerequisites_met():
                        missing = []
                        if not access_request.safety_induction_confirmed:
                            missing.append("Safety Induction")
                        if not access_request.lab_training_confirmed:
                            missing.append("Lab Training")
                        if not access_request.risk_assessment_confirmed:
                            missing.append("Risk Assessment")
                        
                        missing_str = ", ".join(missing)
                        messages.error(request, f'Cannot approve: Missing prerequisites - {missing_str}', extra_tags='persistent-alert')
                    else:
                        access_request.approve(request.user, "Approved via Lab Admin dashboard")
                        messages.success(request, f'Access request approved for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                except ValueError as e:
                    messages.error(request, f'Error approving request: {str(e)}', extra_tags='persistent-alert')
                except Exception as e:
                    messages.error(request, f'Unexpected error: {str(e)}', extra_tags='persistent-alert')
                
            elif action == 'reject':
                try:
                    access_request.reject(request.user, "Rejected via Lab Admin dashboard")
                    messages.success(request, f'Access request rejected for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                except ValueError as e:
                    messages.error(request, f'Error rejecting request: {str(e)}')
                except Exception as e:
                    messages.error(request, f'Unexpected error: {str(e)}')
                    
            elif action == 'confirm_safety':
                notes = request.POST.get('safety_notes', '').strip()
                try:
                    access_request.confirm_safety_induction(request.user, notes)
                    messages.success(request, f'Safety induction confirmed for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                except Exception as e:
                    messages.error(request, f'Error confirming safety induction: {str(e)}')
                    
            elif action == 'confirm_training':
                notes = request.POST.get('training_notes', '').strip()
                try:
                    access_request.confirm_lab_training(request.user, notes)
                    messages.success(request, f'Lab training confirmed for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                except Exception as e:
                    messages.error(request, f'Error confirming lab training: {str(e)}')
                    
            elif action == 'confirm_risk_assessment':
                notes = request.POST.get('risk_assessment_notes', '').strip()
                try:
                    access_request.confirm_risk_assessment(request.user, notes)
                    messages.success(request, f'Risk assessment confirmed for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                except Exception as e:
                    messages.error(request, f'Error confirming risk assessment: {str(e)}')
                    
            elif action == 'schedule_training':
                justification = request.POST.get('training_justification', '').strip()
                training_date = request.POST.get('training_date', '').strip()
                training_time = request.POST.get('training_time', '').strip()
                training_duration = request.POST.get('training_duration', '').strip()
                trainer_notes = request.POST.get('trainer_notes', '').strip()
                
                if not justification:
                    justification = f"Training requested for access to {access_request.resource.name}"
                
                # Parse training date and time
                training_datetime = None
                if training_date and training_time:
                    try:
                        from datetime import datetime
                        training_datetime = datetime.strptime(f"{training_date} {training_time}", "%Y-%m-%d %H:%M")
                        training_datetime = timezone.make_aware(training_datetime)
                    except ValueError:
                        messages.error(request, 'Invalid date or time format.')
                        return redirect('booking:lab_admin_access_requests')
                elif training_date:
                    try:
                        from datetime import datetime
                        training_datetime = datetime.strptime(training_date, "%Y-%m-%d")
                        training_datetime = timezone.make_aware(training_datetime)
                    except ValueError:
                        messages.error(request, 'Invalid date format.')
                        return redirect('booking:lab_admin_access_requests')
                
                # Add duration and trainer notes to justification if provided
                full_justification = justification
                if training_duration:
                    duration_text = f"{training_duration} hour{'s' if float(training_duration) != 1 else ''}"
                    full_justification += f"\n\nExpected Duration: {duration_text}"
                if trainer_notes:
                    full_justification += f"\n\nTrainer Notes: {trainer_notes}"
                
                try:
                    # Check if training request already exists for this user and resource with active status
                    existing_request = TrainingRequest.objects.filter(
                        user=access_request.user,
                        resource=access_request.resource,
                        status__in=['pending', 'scheduled']
                    ).first()
                    
                    if existing_request:
                        # Update existing request with new details
                        existing_request.justification = full_justification
                        if training_datetime:
                            existing_request.training_date = training_datetime
                            existing_request.status = 'scheduled'
                        existing_request.save()
                        training_request = existing_request
                        created = False
                    else:
                        # Create new training request with appropriate status
                        initial_status = 'scheduled' if training_datetime else 'pending'
                        training_request = TrainingRequest.objects.create(
                            user=access_request.user,
                            resource=access_request.resource,
                            status=initial_status,
                            requested_level=access_request.resource.required_training_level or 1,
                            current_level=access_request.user.userprofile.training_level,
                            justification=full_justification,
                            training_date=training_datetime
                        )
                        created = True
                    
                    # Handle booking creation and notifications when training is scheduled
                    if training_datetime:
                        try:
                            # Calculate end time (default 2 hours if no duration specified)
                            duration_hours = 2  # Default duration
                            if training_duration:
                                try:
                                    duration_hours = float(training_duration)
                                except ValueError:
                                    duration_hours = 2
                            
                            training_end_time = training_datetime + timedelta(hours=duration_hours)
                            
                            # Check for booking conflicts
                            conflicts = Booking.objects.filter(
                                resource=access_request.resource,
                                status__in=['approved', 'pending'],
                                start_time__lt=training_end_time,
                                end_time__gt=training_datetime
                            )
                            
                            if conflicts.exists():
                                # Find next available slot
                                next_slot = None
                                for hour_offset in range(1, 168):  # Check next week
                                    test_start = training_datetime + timedelta(hours=hour_offset)
                                    test_end = test_start + timedelta(hours=duration_hours)
                                    
                                    test_conflicts = Booking.objects.filter(
                                        resource=access_request.resource,
                                        status__in=['approved', 'pending'],
                                        start_time__lt=test_end,
                                        end_time__gt=test_start
                                    )
                                    
                                    if not test_conflicts.exists():
                                        next_slot = test_start
                                        break
                                
                                conflict_msg = f'The requested time slot conflicts with existing bookings.'
                                if next_slot:
                                    conflict_msg += f' Next available slot: {next_slot.strftime("%B %d, %Y at %I:%M %p")}'
                                
                                messages.warning(request, conflict_msg, extra_tags='persistent-alert')
                                # Reset to pending status and clear training_date
                                training_request.status = 'pending'
                                training_request.training_date = None
                                training_request.save()
                            else:
                                # No conflicts, create the booking
                                booking = Booking.objects.create(
                                    resource=access_request.resource,
                                    user=access_request.user,
                                    title=f'Training Session: {access_request.resource.name}',
                                    description=f'Training session for {access_request.user.get_full_name()}.\n\n{training_request.justification}',
                                    start_time=training_datetime,
                                    end_time=training_end_time,
                                    status='approved',  # Training bookings are auto-approved
                                    notes=f'Training Request ID: {training_request.id}'
                                )
                                
                                # Send notifications
                                try:
                                    from booking.notifications import training_request_notifications
                                    training_request_notifications.training_request_scheduled(training_request, training_datetime)
                                except Exception as e:
                                    import logging
                                    logger = logging.getLogger(__name__)
                                    logger.error(f"Failed to send training scheduled notification: {e}")
                                
                                if created:
                                    messages.success(request, f'Training session scheduled for {access_request.user.get_full_name()} on {training_datetime.strftime("%B %d, %Y at %I:%M %p")}. Resource has been booked.', extra_tags='persistent-alert')
                                else:
                                    messages.success(request, f'Training session updated and scheduled for {access_request.user.get_full_name()} on {training_datetime.strftime("%B %d, %Y at %I:%M %p")}. Resource has been booked.', extra_tags='persistent-alert')
                                    
                        except Exception as e:
                            messages.error(request, f'Error scheduling training session: {str(e)}')
                            # Reset to pending status
                            training_request.status = 'pending'
                            training_request.training_date = None
                            training_request.save()
                    else:
                        # No specific time scheduled
                        if created:
                            messages.success(request, f'Training request created for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                        else:
                            messages.info(request, f'Training request already exists for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                        
                except Exception as e:
                    messages.error(request, f'Error creating training request: {str(e)}')
        
        return redirect('booking:lab_admin_access_requests')
    
    # Get access requests
    access_requests = AccessRequest.objects.select_related(
        'user', 'resource', 'reviewed_by', 'safety_induction_confirmed_by', 'lab_training_confirmed_by', 'risk_assessment_confirmed_by'
    ).order_by('-created_at')
    
    # Apply filters
    status_filter = request.GET.get('status', 'pending')
    if status_filter and status_filter != 'all':
        access_requests = access_requests.filter(status=status_filter)
    
    # Pagination
    paginator = Paginator(access_requests, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Add prerequisite status to each request
    for request_obj in page_obj:
        request_obj.prerequisite_status = request_obj.get_prerequisite_status()
    
    # Add today's date for date picker minimum value
    from datetime import date
    
    context = {
        'access_requests': page_obj,
        'status_filter': status_filter,
        'today': date.today(),
    }
    
    return render(request, 'booking/lab_admin_access_requests.html', context)


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_training_view(request):
    """Manage training requests and sessions."""
    from booking.models import TrainingRequest, UserTraining, TrainingCourse
    
    # Handle training request actions
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'complete_training':
            request_id = request.POST.get('request_id')
            training_request = get_object_or_404(TrainingRequest, id=request_id)
            
            # Mark training as completed
            training_request.status = 'completed'
            training_request.completed_date = timezone.now()
            training_request.reviewed_by = request.user
            training_request.reviewed_at = timezone.now()
            training_request.save()
            
            # Update user's training level if this training increased it
            user_profile = training_request.user.userprofile
            if training_request.requested_level > user_profile.training_level:
                user_profile.training_level = training_request.requested_level
                user_profile.save()
            
            # Create UserTraining record if there's a specific course involved
            if hasattr(training_request, 'training_course') and training_request.training_course:
                user_training, created = UserTraining.objects.get_or_create(
                    user=training_request.user,
                    training_course=training_request.training_course,
                    defaults={
                        'status': 'completed',
                        'completed_at': timezone.now(),
                        'enrolled_at': training_request.created_at
                    }
                )
                if not created and user_training.status != 'completed':
                    user_training.status = 'completed'
                    user_training.completed_at = timezone.now()
                    user_training.save()
            
            messages.success(request, f'Training marked as completed for {training_request.user.get_full_name()}. Training level updated to {training_request.requested_level}.')
            
        elif action == 'delete_request':
            request_id = request.POST.get('request_id')
            training_request = get_object_or_404(TrainingRequest, id=request_id)
            user_name = training_request.user.get_full_name()
            
            training_request.delete()
            messages.success(request, f'Training request for {user_name} has been deleted', extra_tags='persistent-alert')
            
        elif action == 'edit_request':
            request_id = request.POST.get('request_id')
            training_request = get_object_or_404(TrainingRequest, id=request_id)
            
            # Parse training date and time
            training_date = request.POST.get('training_date')
            training_time = request.POST.get('training_time')
            training_datetime = None
            
            if training_date and training_time:
                try:
                    from datetime import datetime
                    training_datetime = datetime.strptime(f"{training_date} {training_time}", "%Y-%m-%d %H:%M")
                    training_datetime = timezone.make_aware(training_datetime)
                except ValueError:
                    messages.error(request, 'Invalid date or time format.')
                    return redirect('booking:lab_admin_training')
            elif training_date:
                try:
                    from datetime import datetime
                    training_datetime = datetime.strptime(training_date, "%Y-%m-%d")
                    training_datetime = timezone.make_aware(training_datetime)
                except ValueError:
                    messages.error(request, 'Invalid date format.')
                    return redirect('booking:lab_admin_training')
            
            # Update training request fields
            training_request.training_date = training_datetime
            training_request.justification = request.POST.get('training_justification', training_request.justification)
            training_request.save()
            
            messages.success(request, f'Training request updated for {training_request.user.get_full_name()}', extra_tags='persistent-alert')
            
        elif action == 'schedule_training':
            user_training_id = request.POST.get('user_training_id')
            session_date = request.POST.get('session_date')
            
            if user_training_id and session_date:
                user_training = get_object_or_404(UserTraining, id=user_training_id)
                
                try:
                    # Parse session date and create datetime object
                    session_datetime = datetime.strptime(session_date, "%Y-%m-%d")
                    session_datetime = timezone.make_aware(session_datetime)
                    
                    # Set default training duration (2 hours)
                    training_duration = timedelta(hours=2)
                    session_end_time = session_datetime + training_duration
                    
                    # Find associated resource (from training course requirements)
                    resource = None
                    training_requirements = user_training.training_course.resource_requirements.all()
                    if training_requirements.exists():
                        resource = training_requirements.first().resource
                    
                    if resource:
                        # Check for booking conflicts
                        conflicts = Booking.objects.filter(
                            resource=resource,
                            status__in=['approved', 'pending'],
                            start_time__lt=session_end_time,
                            end_time__gt=session_datetime
                        )
                        
                        if conflicts.exists():
                            # Find next available slot
                            next_slot = None
                            for day_offset in range(1, 30):  # Check next month
                                test_start = session_datetime + timedelta(days=day_offset)
                                test_end = test_start + training_duration
                                
                                test_conflicts = Booking.objects.filter(
                                    resource=resource,
                                    status__in=['approved', 'pending'],
                                    start_time__lt=test_end,
                                    end_time__gt=test_start
                                )
                                
                                if not test_conflicts.exists():
                                    next_slot = test_start
                                    break
                            
                            conflict_msg = f'The requested date conflicts with existing bookings for {resource.name}.'
                            if next_slot:
                                conflict_msg += f' Next available date: {next_slot.strftime("%B %d, %Y")}'
                            
                            messages.warning(request, conflict_msg, extra_tags='persistent-alert')
                        else:
                            # No conflicts, create the booking
                            booking = Booking.objects.create(
                                resource=resource,
                                user=user_training.user,
                                title=f'Training Session: {user_training.training_course.title}',
                                description=f'Training session for {user_training.user.get_full_name()} - {user_training.training_course.title}',
                                start_time=session_datetime,
                                end_time=session_end_time,
                                status='approved',  # Training bookings are auto-approved
                                notes=f'User Training ID: {user_training.id}'
                            )
                            
                            # Update user training
                            user_training.session_date = session_date
                            user_training.instructor = request.user
                            user_training.status = 'scheduled'
                            user_training.save()
                            
                            # Send notifications
                            try:
                                from booking.notifications import training_request_notifications
                                training_request_notifications.training_request_scheduled(user_training, session_datetime)
                            except Exception as e:
                                import logging
                                logger = logging.getLogger(__name__)
                                logger.error(f"Failed to send training scheduled notification: {e}")
                            
                            messages.success(request, f'Training session scheduled for {user_training.user.get_full_name()} on {session_datetime.strftime("%B %d, %Y")}. Resource {resource.name} has been booked.', extra_tags='persistent-alert')
                    else:
                        # No specific resource, just update the user training
                        user_training.session_date = session_date
                        user_training.instructor = request.user
                        user_training.status = 'scheduled'
                        user_training.save()
                        
                        # Send notifications
                        try:
                            from booking.notifications import training_request_notifications
                            training_request_notifications.training_request_scheduled(user_training, session_datetime)
                        except Exception as e:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.error(f"Failed to send training scheduled notification: {e}")
                        
                        messages.success(request, f'Training session scheduled for {user_training.user.get_full_name()} on {session_datetime.strftime("%B %d, %Y")}', extra_tags='persistent-alert')
                        
                except ValueError:
                    messages.error(request, 'Invalid date format.')
                except Exception as e:
                    messages.error(request, f'Error scheduling training session: {str(e)}')
        
        return redirect('booking:lab_admin_training')
    
    # Get training data
    pending_requests = TrainingRequest.objects.filter(status='pending').select_related('user', 'resource', 'reviewed_by')
    upcoming_sessions = UserTraining.objects.filter(
        session_date__gte=timezone.now().date(),
        status='scheduled'
    ).select_related('user', 'training_course', 'instructor')
    
    # Get training courses for management
    training_courses = TrainingCourse.objects.all().select_related('created_by').prefetch_related(
        'instructors', 'prerequisite_courses'
    ).order_by('-created_at')
    
    context = {
        'pending_requests': pending_requests,
        'upcoming_sessions': upcoming_sessions,
        'training_courses': training_courses,
    }
    
    return render(request, 'booking/lab_admin_training.html', context)


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_risk_assessments_view(request):
    """Manage user risk assessments."""
    from booking.models import UserRiskAssessment, RiskAssessment
    
    # Handle risk assessment actions
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve_assessment':
            assessment_id = request.POST.get('assessment_id')
            user_assessment = get_object_or_404(UserRiskAssessment, id=assessment_id)
            
            user_assessment.status = 'approved'
            user_assessment.completed_at = timezone.now()
            user_assessment.save()
            
            messages.success(request, f'Risk assessment approved for {user_assessment.user.get_full_name()}')
            
        elif action == 'reject_assessment':
            assessment_id = request.POST.get('assessment_id')
            user_assessment = get_object_or_404(UserRiskAssessment, id=assessment_id)
            rejection_reason = request.POST.get('rejection_reason', '')
            
            user_assessment.status = 'rejected'
            user_assessment.rejection_reason = rejection_reason
            user_assessment.save()
            
            messages.success(request, f'Risk assessment rejected for {user_assessment.user.get_full_name()}')
            
        elif action == 'view_details':
            assessment_id = request.POST.get('assessment_id')
            # This could redirect to a detailed view of the assessment
            return redirect('booking:lab_admin_risk_assessments')
        
        return redirect('booking:lab_admin_risk_assessments')
    
    # Get risk assessment data
    submitted_assessments = UserRiskAssessment.objects.filter(
        status='submitted'
    ).select_related('user', 'risk_assessment').order_by('-submitted_at')
    
    approved_assessments = UserRiskAssessment.objects.filter(
        status='approved'
    ).select_related('user', 'risk_assessment').order_by('-completed_at')[:20]  # Show recent 20
    
    rejected_assessments = UserRiskAssessment.objects.filter(
        status='rejected'
    ).select_related('user', 'risk_assessment').order_by('-submitted_at')[:20]  # Show recent 20
    
    context = {
        'submitted_assessments': submitted_assessments,
        'approved_assessments': approved_assessments,
        'rejected_assessments': rejected_assessments,
    }
    
    return render(request, 'booking/lab_admin_risk_assessments.html', context)


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_users_view(request):
    """Manage user profiles and access."""
    from booking.models import UserProfile, ResourceAccess
    
    # Get users
    users = User.objects.select_related('userprofile').order_by('username')
    
    # Apply filters
    is_active_filter = request.GET.get('is_active')
    role_filter = request.GET.get('role')
    search_query = request.GET.get('search')
    
    # Clean up empty values
    if search_query:
        search_query = search_query.strip()
        if not search_query:
            search_query = None
    
    if is_active_filter == 'true':
        users = users.filter(is_active=True)
    elif is_active_filter == 'false':
        users = users.filter(is_active=False)
    
    if role_filter:
        users = users.filter(userprofile__role=role_filter)
    
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(users, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get role choices for filter
    role_choices = UserProfile.ROLE_CHOICES
    
    context = {
        'users': page_obj,
        'is_active_filter': is_active_filter,
        'role_filter': role_filter,
        'search_query': search_query,
        'role_choices': role_choices,
    }
    
    return render(request, 'booking/lab_admin_users.html', context)


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_user_detail_view(request, user_id):
    """Get user details for viewing."""
    try:
        user = User.objects.select_related('userprofile').get(id=user_id)
        
        # Prepare user data
        user_data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_active': user.is_active,
            'date_joined': user.date_joined,
            'last_login': user.last_login,
        }
        
        if hasattr(user, 'userprofile'):
            user_data.update({
                'role': user.userprofile.role,
                'phone': user.userprofile.phone,
                'department': user.userprofile.department.name if user.userprofile.department else None,
                'email_verified': user.userprofile.email_verified,
                'is_inducted': user.userprofile.is_inducted,
            })
        
        # Render HTML for modal
        html = f"""
        <div class="row">
            <div class="col-md-6">
                <h6>Basic Information</h6>
                <dl class="row">
                    <dt class="col-sm-4">Username:</dt>
                    <dd class="col-sm-8">{user.username}</dd>
                    <dt class="col-sm-4">Full Name:</dt>
                    <dd class="col-sm-8">{user.get_full_name() or '-'}</dd>
                    <dt class="col-sm-4">Email:</dt>
                    <dd class="col-sm-8">{user.email}</dd>
                    <dt class="col-sm-4">Status:</dt>
                    <dd class="col-sm-8">
                        {'<span class="badge bg-success">Active</span>' if user.is_active else '<span class="badge bg-danger">Inactive</span>'}
                    </dd>
                </dl>
            </div>
            <div class="col-md-6">
                <h6>Profile Information</h6>
                <dl class="row">
                    <dt class="col-sm-4">Role:</dt>
                    <dd class="col-sm-8">{user.userprofile.get_role_display() if hasattr(user, 'userprofile') else '-'}</dd>
                    <dt class="col-sm-4">Department:</dt>
                    <dd class="col-sm-8">{user_data.get('department', '-')}</dd>
                    <dt class="col-sm-4">Phone:</dt>
                    <dd class="col-sm-8">{user_data.get('phone', '-')}</dd>
                    <dt class="col-sm-4">Email Verified:</dt>
                    <dd class="col-sm-8">
                        {'<span class="badge bg-success">Yes</span>' if user_data.get('email_verified') else '<span class="badge bg-warning text-dark">No</span>'}
                    </dd>
                </dl>
            </div>
        </div>
        <hr>
        <div class="row">
            <div class="col-12">
                <h6>Account Activity</h6>
                <dl class="row">
                    <dt class="col-sm-3">Date Joined:</dt>
                    <dd class="col-sm-9">{user.date_joined.strftime('%B %d, %Y at %I:%M %p')}</dd>
                    <dt class="col-sm-3">Last Login:</dt>
                    <dd class="col-sm-9">{user.last_login.strftime('%B %d, %Y at %I:%M %p') if user.last_login else 'Never'}</dd>
                </dl>
            </div>
        </div>
        """
        
        return JsonResponse({
            'success': True,
            'user': user_data,
            'html': html
        })
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_user_edit_view(request, user_id):
    """Edit user details."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    try:
        user = User.objects.get(id=user_id)
        
        # Update user fields
        user.username = request.POST.get('username', user.username)
        user.email = request.POST.get('email', user.email)
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.is_active = request.POST.get('is_active') == 'on'
        user.save()
        
        # Update or create user profile
        if hasattr(user, 'userprofile'):
            profile = user.userprofile
        else:
            from booking.models import UserProfile
            profile = UserProfile(user=user)
        
        profile.role = request.POST.get('role', profile.role)
        profile.phone = request.POST.get('phone', profile.phone)
        profile.save()
        
        messages.success(request, f'User {user.username} updated successfully.')
        return JsonResponse({'success': True})
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_user_delete_view(request, user_id):
    """Delete a user."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    try:
        from django.db import transaction
        from booking.models import Booking, ResourceAccess, TrainingRequest, RiskAssessment
        
        user = User.objects.get(id=user_id)
        
        # Don't allow deleting superusers
        if user.is_superuser:
            return JsonResponse({'success': False, 'error': 'Cannot delete superuser accounts'})
        
        # Don't allow self-deletion
        if user.id == request.user.id:
            return JsonResponse({'success': False, 'error': 'Cannot delete your own account'})
        
        # Check for related data
        related_data = []
        
        # Check for active bookings
        active_bookings = Booking.objects.filter(user=user, status__in=['pending', 'approved']).count()
        if active_bookings > 0:
            related_data.append(f'{active_bookings} active booking(s)')
        
        # Check for resource access
        resource_access = ResourceAccess.objects.filter(user=user).count()
        if resource_access > 0:
            related_data.append(f'{resource_access} resource access permission(s)')
        
        # Check for training requests
        training_requests = TrainingRequest.objects.filter(user=user).count()
        if training_requests > 0:
            related_data.append(f'{training_requests} training request(s)')
        
        # Check for risk assessments
        try:
            risk_assessments = RiskAssessment.objects.filter(created_by=user).count()
            if risk_assessments > 0:
                related_data.append(f'{risk_assessments} risk assessment(s)')
        except:
            # Model might not exist or have different fields
            pass
        
        # Check for other important relationships
        from booking.models import AccessRequest, WaitingListEntry
        
        access_requests = AccessRequest.objects.filter(user=user).count()
        if access_requests > 0:
            related_data.append(f'{access_requests} access request(s)')
            
        waiting_list = WaitingListEntry.objects.filter(user=user).count()
        if waiting_list > 0:
            related_data.append(f'{waiting_list} waiting list entries')
        
        if related_data:
            return JsonResponse({
                'success': False, 
                'error': f'Cannot delete user. They have: {", ".join(related_data)}. Please reassign or remove these items first.'
            })
        
        username = user.username
        
        # Use transaction to ensure all deletions succeed or none do
        with transaction.atomic():
            # Delete user profile if exists
            if hasattr(user, 'userprofile'):
                user.userprofile.delete()
            
            # Delete the user
            user.delete()
        
        messages.success(request, f'User {username} has been deleted.')
        return JsonResponse({'success': True})
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        # For debugging, let's provide more detail about the constraint error
        error_msg = str(e)
        if 'FOREIGN KEY constraint failed' in error_msg:
            return JsonResponse({
                'success': False, 
                'error': 'Cannot delete user due to existing data dependencies. Please contact system administrator to review user data.'
            })
        return JsonResponse({'success': False, 'error': error_msg})


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_user_toggle_view(request, user_id):
    """Toggle user active status."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    try:
        user = User.objects.get(id=user_id)
        
        # Don't allow toggling superusers
        if user.is_superuser:
            return JsonResponse({'success': False, 'error': 'Cannot modify superuser accounts'})
        
        # Don't allow self-deactivation
        if user.id == request.user.id and not json.loads(request.body).get('active', True):
            return JsonResponse({'success': False, 'error': 'Cannot deactivate your own account'})
        
        data = json.loads(request.body)
        user.is_active = data.get('active', True)
        user.save()
        
        action = 'activated' if user.is_active else 'deactivated'
        messages.success(request, f'User {user.username} has been {action}.')
        return JsonResponse({'success': True})
        
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_user_add_view(request):
    """Add a new user."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    try:
        from django.contrib.auth.forms import UserCreationForm
        from booking.models import UserProfile
        
        # Validate passwords match
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')
        if password1 != password2:
            return JsonResponse({'success': False, 'error': 'Passwords do not match'})
        
        # Check if username already exists
        username = request.POST.get('username')
        if User.objects.filter(username=username).exists():
            return JsonResponse({'success': False, 'error': 'Username already exists'})
        
        # Create user
        user = User.objects.create_user(
            username=username,
            email=request.POST.get('email'),
            password=password1,
            first_name=request.POST.get('first_name'),
            last_name=request.POST.get('last_name'),
        )
        user.is_active = request.POST.get('is_active') == 'on'
        user.save()
        
        # Create user profile
        UserProfile.objects.create(
            user=user,
            role=request.POST.get('role'),
            phone=request.POST.get('phone', ''),
        )
        
        messages.success(request, f'User {user.username} created successfully.')
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_users_bulk_import_view(request):
    """Bulk import users from CSV."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    try:
        import csv
        from io import StringIO
        from booking.models import UserProfile
        
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            return JsonResponse({'success': False, 'error': 'No file uploaded'})
        
        # Check file size
        if csv_file.size > 5 * 1024 * 1024:  # 5MB limit
            return JsonResponse({'success': False, 'error': 'File too large (max 5MB)'})
        
        # Read CSV with better error handling
        try:
            file_data = csv_file.read().decode('utf-8')
        except UnicodeDecodeError:
            try:
                csv_file.seek(0)
                file_data = csv_file.read().decode('latin-1')
            except:
                return JsonResponse({'success': False, 'error': 'Unable to decode file. Please ensure it\'s a valid UTF-8 or Latin-1 encoded CSV file.'})
        
        # Parse CSV
        try:
            csv_reader = csv.DictReader(StringIO(file_data))
            rows = list(csv_reader)
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Invalid CSV format: {str(e)}'})
        
        if not rows:
            return JsonResponse({'success': False, 'error': 'CSV file is empty or has no data rows'})
        
        # Check required columns
        required_columns = ['username']
        first_row = rows[0]
        missing_columns = [col for col in required_columns if col not in first_row]
        if missing_columns:
            return JsonResponse({
                'success': False, 
                'error': f'Missing required columns: {", ".join(missing_columns)}. Available columns: {", ".join(first_row.keys())}'
            })
        
        created = 0
        updated = 0
        errors = []
        row_num = 1  # Start from 1 (header is row 0)
        
        for row in rows:
            row_num += 1
            try:
                username = row.get('username', '').strip()
                if not username:
                    errors.append(f'Row {row_num}: Missing username')
                    continue
                
                email = row.get('email', '').strip()
                first_name = row.get('first_name', '').strip()
                last_name = row.get('last_name', '').strip()
                role = row.get('role', 'researcher').strip()
                
                if User.objects.filter(username=username).exists():
                    if request.POST.get('update_existing') == 'on':
                        user = User.objects.get(username=username)
                        
                        # Update user fields
                        if email:
                            user.email = email
                        if first_name:
                            user.first_name = first_name
                        if last_name:
                            user.last_name = last_name
                        user.save()
                        
                        # Update or create profile
                        if hasattr(user, 'userprofile'):
                            if role:
                                user.userprofile.role = role
                                user.userprofile.save()
                        else:
                            UserProfile.objects.create(
                                user=user,
                                role=role,
                            )
                        
                        updated += 1
                    else:
                        errors.append(f'Row {row_num}: User {username} already exists')
                else:
                    # Create new user
                    from django.contrib.auth.models import make_password
                    import secrets
                    import string
                    
                    # Generate random password
                    password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
                    
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                        first_name=first_name,
                        last_name=last_name,
                    )
                    
                    # Create user profile (use get_or_create to avoid duplicates)
                    profile, created_profile = UserProfile.objects.get_or_create(
                        user=user,
                        defaults={
                            'role': role,
                            'phone': '',  # Default empty phone
                            'is_inducted': False,
                            'email_verified': False,
                        }
                    )
                    
                    # If profile existed, update the role
                    if not created_profile and role:
                        profile.role = role
                        profile.save()
                    
                    created += 1
                    
            except Exception as e:
                errors.append(f'Row {row_num}: Error processing - {str(e)}')
        
        # Prepare response
        response_data = {
            'success': True,
            'created': created,
            'updated': updated,
        }
        
        if errors:
            response_data['errors'] = errors
            response_data['message'] = f'Processed with {len(errors)} error(s)'
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Import failed: {str(e)}'})


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_users_bulk_action_view(request):
    """Perform bulk actions on multiple users."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    try:
        from django.db import transaction
        
        data = json.loads(request.body)
        action = data.get('action')
        user_ids = data.get('user_ids', [])
        
        if not action or not user_ids:
            return JsonResponse({'success': False, 'error': 'Missing action or user IDs'})
        
        if action not in ['activate', 'deactivate', 'delete']:
            return JsonResponse({'success': False, 'error': 'Invalid action'})
        
        # Get users (exclude superusers and current user for safety)
        users = User.objects.filter(
            id__in=user_ids,
            is_superuser=False
        ).exclude(id=request.user.id)
        
        if not users.exists():
            return JsonResponse({'success': False, 'error': 'No valid users found'})
        
        processed = 0
        errors = []
        
        with transaction.atomic():
            for user in users:
                try:
                    if action == 'activate':
                        user.is_active = True
                        user.save()
                        processed += 1
                        
                    elif action == 'deactivate':
                        user.is_active = False
                        user.save()
                        processed += 1
                        
                    elif action == 'delete':
                        # Check for dependencies like we do in single delete
                        from booking.models import Booking, ResourceAccess, TrainingRequest, AccessRequest, WaitingListEntry
                        
                        # Check for blocking relationships
                        active_bookings = Booking.objects.filter(user=user, status__in=['pending', 'approved']).count()
                        if active_bookings > 0:
                            errors.append(f'{user.username}: Has {active_bookings} active booking(s)')
                            continue
                        
                        resource_access = ResourceAccess.objects.filter(user=user).count()
                        if resource_access > 0:
                            errors.append(f'{user.username}: Has {resource_access} resource access permission(s)')
                            continue
                        
                        training_requests = TrainingRequest.objects.filter(user=user).count()
                        if training_requests > 0:
                            errors.append(f'{user.username}: Has {training_requests} training request(s)')
                            continue
                        
                        access_requests = AccessRequest.objects.filter(user=user).count()
                        if access_requests > 0:
                            errors.append(f'{user.username}: Has {access_requests} access request(s)')
                            continue
                        
                        waiting_list = WaitingListEntry.objects.filter(user=user).count()
                        if waiting_list > 0:
                            errors.append(f'{user.username}: Has {waiting_list} waiting list entries')
                            continue
                        
                        # Safe to delete
                        if hasattr(user, 'userprofile'):
                            user.userprofile.delete()
                        user.delete()
                        processed += 1
                        
                except Exception as e:
                    errors.append(f'{user.username}: {str(e)}')
        
        # Create success message
        messages.success(request, f'Bulk {action} completed: {processed} user(s) processed')
        
        response_data = {
            'success': True,
            'processed': processed,
            'action': action
        }
        
        if errors:
            response_data['errors'] = errors
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Bulk action failed: {str(e)}'})


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_users_export_view(request):
    """Export users to CSV."""
    import csv
    from django.http import HttpResponse
    
    # Create response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="users_export.csv"'
    
    # Get filtered users
    users = User.objects.select_related('userprofile').order_by('username')
    
    # Apply filters
    is_active_filter = request.GET.get('is_active')
    if is_active_filter == 'true':
        users = users.filter(is_active=True)
    elif is_active_filter == 'false':
        users = users.filter(is_active=False)
    
    role_filter = request.GET.get('role')
    if role_filter:
        users = users.filter(userprofile__role=role_filter)
    
    search_query = request.GET.get('search')
    # Clean up empty values
    if search_query:
        search_query = search_query.strip()
        if not search_query:
            search_query = None
    
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    # Write CSV
    writer = csv.writer(response)
    writer.writerow(['username', 'email', 'first_name', 'last_name', 'role', 'department', 'is_active', 'email_verified', 'date_joined'])
    
    for user in users:
        writer.writerow([
            user.username,
            user.email,
            user.first_name,
            user.last_name,
            user.userprofile.get_role_display() if hasattr(user, 'userprofile') else '',
            user.userprofile.department.name if hasattr(user, 'userprofile') and user.userprofile.department else '',
            'Yes' if user.is_active else 'No',
            'Yes' if hasattr(user, 'userprofile') and user.userprofile.email_verified else 'No',
            user.date_joined.strftime('%Y-%m-%d'),
        ])
    
    return response


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_resources_view(request):
    """Manage resources - list, add, edit, delete."""
    from booking.models import Resource
    
    # Get resources
    resources = Resource.objects.all().order_by('name')
    
    # Apply filters
    resource_type_filter = request.GET.get('type')
    search_query = request.GET.get('search')
    status_filter = request.GET.get('status', 'all')
    
    # Clean up empty search values
    if search_query:
        search_query = search_query.strip()
        if not search_query:
            search_query = None
    
    if resource_type_filter:
        resources = resources.filter(resource_type=resource_type_filter)
    
    if search_query:
        resources = resources.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(location__icontains=search_query)
        )
    
    if status_filter == 'active':
        resources = resources.filter(is_active=True)
    elif status_filter == 'inactive':
        resources = resources.filter(is_active=False)
    
    # Pagination
    paginator = Paginator(resources, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get resource type choices for filter
    resource_types = Resource.RESOURCE_TYPES
    
    context = {
        'resources': page_obj,
        'resource_type_filter': resource_type_filter,
        'search_query': search_query,
        'status_filter': status_filter,
        'resource_types': resource_types,
    }
    
    return render(request, 'booking/lab_admin_resources.html', context)


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_resources_bulk_import_view(request):
    """Bulk import resources from CSV."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    try:
        import csv
        from io import StringIO
        from booking.models import Resource
        
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            return JsonResponse({'success': False, 'error': 'No file uploaded'})
        
        # Check file size
        if csv_file.size > 5 * 1024 * 1024:  # 5MB limit
            return JsonResponse({'success': False, 'error': 'File too large (max 5MB)'})
        
        # Read CSV with better error handling
        try:
            file_data = csv_file.read().decode('utf-8')
        except UnicodeDecodeError:
            try:
                csv_file.seek(0)
                file_data = csv_file.read().decode('latin-1')
            except:
                return JsonResponse({'success': False, 'error': 'Unable to decode file. Please ensure it\'s a valid UTF-8 or Latin-1 encoded CSV file.'})
        
        # Parse CSV
        try:
            csv_reader = csv.DictReader(StringIO(file_data))
            rows = list(csv_reader)
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Invalid CSV format: {str(e)}'})
        
        if not rows:
            return JsonResponse({'success': False, 'error': 'CSV file is empty or has no data rows'})
        
        # Check required columns
        required_columns = ['name', 'resource_type']
        first_row = rows[0]
        missing_columns = [col for col in required_columns if col not in first_row]
        if missing_columns:
            return JsonResponse({
                'success': False, 
                'error': f'Missing required columns: {", ".join(missing_columns)}. Available columns: {", ".join(first_row.keys())}'
            })
        
        # Valid resource types
        valid_resource_types = [choice[0] for choice in Resource.RESOURCE_TYPES]
        
        created = 0
        updated = 0
        errors = []
        row_num = 1  # Start from 1 (header is row 0)
        
        for row in rows:
            row_num += 1
            try:
                name = row.get('name', '').strip()
                if not name:
                    errors.append(f'Row {row_num}: Missing name')
                    continue
                
                resource_type = row.get('resource_type', '').strip().lower()
                if not resource_type:
                    errors.append(f'Row {row_num}: Missing resource_type')
                    continue
                
                if resource_type not in valid_resource_types:
                    errors.append(f'Row {row_num}: Invalid resource_type "{resource_type}". Valid types: {", ".join(valid_resource_types)}')
                    continue
                
                description = row.get('description', '').strip()
                location = row.get('location', '').strip()
                capacity_str = row.get('capacity', '').strip()
                is_active_str = row.get('is_active', 'true').strip().lower()
                
                # Parse capacity
                capacity = 1  # default
                if capacity_str:
                    try:
                        capacity = int(capacity_str)
                        if capacity < 1:
                            capacity = 1
                    except ValueError:
                        errors.append(f'Row {row_num}: Invalid capacity "{capacity_str}", using default of 1')
                        capacity = 1
                
                # Parse is_active
                is_active = is_active_str in ['true', '1', 'yes', 'active']
                
                if Resource.objects.filter(name=name).exists():
                    if request.POST.get('update_existing') == 'on':
                        resource = Resource.objects.get(name=name)
                        
                        # Update resource fields
                        resource.resource_type = resource_type
                        if description:
                            resource.description = description
                        if location:
                            resource.location = location
                        resource.capacity = capacity
                        resource.is_active = is_active
                        resource.save()
                        
                        updated += 1
                    else:
                        errors.append(f'Row {row_num}: Resource "{name}" already exists')
                else:
                    # Create new resource
                    resource = Resource.objects.create(
                        name=name,
                        resource_type=resource_type,
                        description=description,
                        location=location,
                        capacity=capacity,
                        is_active=is_active,
                    )
                    
                    created += 1
                    
            except Exception as e:
                errors.append(f'Row {row_num}: Error processing - {str(e)}')
        
        # Prepare response
        response_data = {
            'success': True,
            'created': created,
            'updated': updated,
        }
        
        if errors:
            response_data['errors'] = errors
            response_data['message'] = f'Processed with {len(errors)} error(s)'
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Import failed: {str(e)}'})


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_add_resource_view(request):
    """Add a new resource."""
    from booking.models import Resource
    from ..forms import ResourceForm
    
    if request.method == 'POST':
        form = ResourceForm(request.POST, request.FILES)
        if form.is_valid():
            resource = form.save()
            messages.success(request, f'Resource "{resource.name}" has been created successfully.')
            return redirect('booking:lab_admin_resources')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ResourceForm()
    
    context = {
        'form': form,
        'title': 'Add New Resource',
        'action': 'Add',
    }
    
    return render(request, 'booking/lab_admin_resource_form.html', context)


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_edit_resource_view(request, resource_id):
    """Edit an existing resource."""
    from booking.models import Resource, ResourceTrainingRequirement, TrainingCourse
    from ..forms import ResourceForm
    
    resource = get_object_or_404(Resource, id=resource_id)
    
    if request.method == 'POST':
        # Handle regular form submission
        form = ResourceForm(request.POST, request.FILES, instance=resource)
        if form.is_valid():
            resource = form.save()
            messages.success(request, f'Resource "{resource.name}" has been updated successfully.')
            return redirect('booking:lab_admin_resources')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ResourceForm(instance=resource)
    
    # Get current training requirements for this resource
    training_requirements = ResourceTrainingRequirement.objects.filter(
        resource=resource
    ).select_related('training_course').order_by('order')
    
    # Get all active training courses for the dropdown
    available_courses = TrainingCourse.objects.filter(is_active=True).order_by('title')
    
    # Get IDs of courses already assigned to this resource
    assigned_course_ids = training_requirements.values_list('training_course_id', flat=True)
    
    context = {
        'form': form,
        'resource': resource,
        'title': f'Edit Resource: {resource.name}',
        'action': 'Update',
        'training_requirements': training_requirements,
        'available_courses': available_courses,
        'assigned_course_ids': list(assigned_course_ids),
    }
    
    return render(request, 'booking/lab_admin_resource_form.html', context)


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_delete_resource_view(request, resource_id):
    """Delete a resource with confirmation."""
    from booking.models import Resource
    
    resource = get_object_or_404(Resource, id=resource_id)
    
    if request.method == 'POST':
        # Check if resource has any bookings
        if resource.bookings.exists():
            messages.error(request, f'Cannot delete "{resource.name}" because it has existing bookings. Please deactivate it instead.')
            return redirect('booking:lab_admin_resources')
        
        resource_name = resource.name
        resource.delete()
        messages.success(request, f'Resource "{resource_name}" has been deleted successfully.')
        return redirect('booking:lab_admin_resources')
    
    # Check dependencies
    booking_count = resource.bookings.count()
    access_count = resource.access_permissions.count()
    
    context = {
        'resource': resource,
        'booking_count': booking_count,
        'access_count': access_count,
        'can_delete': booking_count == 0,
    }
    
    return render(request, 'booking/lab_admin_resource_delete.html', context)


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_close_resource_view(request, resource_id):
    """Close a resource to prevent new bookings."""
    from booking.models import Resource
    
    resource = get_object_or_404(Resource, id=resource_id)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        resource.close_resource(request.user, reason)
        messages.success(request, f'Resource "{resource.name}" has been closed to prevent new bookings.')
        return redirect('booking:lab_admin_resources')
    
    context = {
        'resource': resource,
    }
    
    return render(request, 'booking/lab_admin_resource_close.html', context)


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["POST"])
def lab_admin_open_resource_view(request, resource_id):
    """Reopen a closed resource for bookings."""
    from booking.models import Resource
    
    resource = get_object_or_404(Resource, id=resource_id)
    resource.open_resource()
    messages.success(request, f'Resource "{resource.name}" has been reopened for bookings.')
    return redirect('booking:lab_admin_resources')


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["POST"])
def add_training_requirement_api(request, resource_id):
    """API endpoint to add a training requirement to a resource."""
    from booking.models import Resource, ResourceTrainingRequirement, TrainingCourse
    import json
    
    try:
        resource = get_object_or_404(Resource, id=resource_id)
        data = json.loads(request.body)
        
        course_id = data.get('course_id')
        is_mandatory = data.get('is_mandatory', True)
        
        if not course_id:
            return JsonResponse({'error': 'Training course ID is required'}, status=400)
        
        course = get_object_or_404(TrainingCourse, id=course_id)
        
        # Check if requirement already exists
        if ResourceTrainingRequirement.objects.filter(resource=resource, training_course=course).exists():
            return JsonResponse({'error': 'This training requirement already exists'}, status=400)
        
        # Get the highest order number
        max_order = ResourceTrainingRequirement.objects.filter(resource=resource).aggregate(
            Max('order')
        )['order__max'] or 0
        
        # Create the requirement
        requirement = ResourceTrainingRequirement.objects.create(
            resource=resource,
            training_course=course,
            is_mandatory=is_mandatory,
            order=max_order + 1
        )
        
        return JsonResponse({
            'success': True,
            'requirement': {
                'id': requirement.id,
                'course_title': course.title,
                'course_code': course.code,
                'course_type': course.get_course_type_display(),
                'duration': course.duration_hours,
                'is_mandatory': requirement.is_mandatory,
                'order': requirement.order
            }
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["DELETE"])
def remove_training_requirement_api(request, resource_id, requirement_id):
    """API endpoint to remove a training requirement from a resource."""
    from booking.models import Resource, ResourceTrainingRequirement
    
    try:
        resource = get_object_or_404(Resource, id=resource_id)
        requirement = get_object_or_404(ResourceTrainingRequirement, id=requirement_id, resource=resource)
        
        # Store the course details before deletion
        course_name = requirement.training_course.title
        course_id = requirement.training_course.id
        course_code = requirement.training_course.code
        
        # Delete the requirement
        requirement.delete()
        
        # Reorder remaining requirements
        remaining_requirements = ResourceTrainingRequirement.objects.filter(
            resource=resource
        ).order_by('order')
        
        for idx, req in enumerate(remaining_requirements, 1):
            req.order = idx
            req.save(update_fields=['order'])
        
        return JsonResponse({
            'success': True,
            'message': f'Training requirement "{course_name}" removed successfully',
            'course_id': course_id,
            'course_code': course_code,
            'course_name': course_name
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["POST"])
def update_training_requirement_order_api(request, resource_id):
    """API endpoint to update the order of training requirements."""
    from booking.models import Resource, ResourceTrainingRequirement
    import json
    
    try:
        resource = get_object_or_404(Resource, id=resource_id)
        data = json.loads(request.body)
        
        requirement_orders = data.get('requirements', [])
        
        for order_data in requirement_orders:
            requirement_id = order_data.get('id')
            new_order = order_data.get('order')
            
            if requirement_id and new_order is not None:
                ResourceTrainingRequirement.objects.filter(
                    id=requirement_id,
                    resource=resource
                ).update(order=new_order)
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_resource_checklist_view(request, resource_id):
    """Manage checklist items for a resource."""
    from django.shortcuts import render, redirect, get_object_or_404
    from django.contrib import messages
    from booking.models import Resource, ChecklistItem, ResourceChecklistItem
    from ..forms import ResourceChecklistConfigForm
    from django.utils import timezone
    
    resource = get_object_or_404(Resource, id=resource_id)
    
    if request.method == 'POST':
        form = ResourceChecklistConfigForm(resource, request.POST)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f'Checklist configuration updated for "{resource.name}".')
                return redirect('booking:lab_admin_resource_checklist', resource_id=resource.id)
            except Exception as e:
                messages.error(request, f'Error updating checklist: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ResourceChecklistConfigForm(resource)
    
    # Get available checklist items grouped by category
    available_items = ChecklistItem.objects.all().order_by('category', 'title')
    items_by_category = {}
    for item in available_items:
        category = item.get_category_display()
        if category not in items_by_category:
            items_by_category[category] = []
        items_by_category[category].append(item)
    
    # Get currently assigned items
    assigned_items = ResourceChecklistItem.objects.filter(
        resource=resource,
        is_active=True
    ).select_related('checklist_item').order_by('order', 'checklist_item__category')
    
    context = {
        'resource': resource,
        'form': form,
        'items_by_category': items_by_category,
        'assigned_items': assigned_items,
        'total_available': available_items.count(),
        'total_assigned': assigned_items.count(),
    }
    
    return render(request, 'booking/lab_admin_resource_checklist.html', context)


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_maintenance_view(request):
    """Display and manage maintenance periods for lab administrators."""
    from django.core.paginator import Paginator
    from django.utils import timezone
    
    # Get filter parameters
    resource_filter = request.GET.get('resource', '')
    type_filter = request.GET.get('type', '')
    search_query = request.GET.get('search', '')
    
    # Base queryset
    maintenance_list = Maintenance.objects.select_related('resource', 'created_by').order_by('-start_time')
    
    # Apply filters
    if resource_filter:
        maintenance_list = maintenance_list.filter(resource_id=resource_filter)
    
    if type_filter:
        maintenance_list = maintenance_list.filter(maintenance_type=type_filter)
    
    if search_query:
        maintenance_list = maintenance_list.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(resource__name__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(maintenance_list, 25)
    page_number = request.GET.get('page')
    maintenance_periods = paginator.get_page(page_number)
    
    # Statistics
    now = timezone.now()
    stats = {
        'scheduled_count': Maintenance.objects.filter(start_time__gt=now).count(),
        'active_count': Maintenance.objects.filter(start_time__lte=now, end_time__gte=now).count(),
        'completed_count': Maintenance.objects.filter(
            end_time__lt=now,
            start_time__month=now.month,
            start_time__year=now.year
        ).count(),
        'recurring_count': Maintenance.objects.filter(is_recurring=True).count(),
    }
    
    # Get all resources for filtering
    resources = Resource.objects.filter(is_active=True).order_by('name')
    
    context = {
        'maintenance_periods': maintenance_periods,
        'resources': resources,
        'stats': stats,
        'resource_filter': resource_filter,
        'type_filter': type_filter,
        'search_query': search_query,
    }
    
    return render(request, 'booking/lab_admin_maintenance.html', context)


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_add_maintenance_view(request):
    """Add a new maintenance period."""
    import json
    from django.utils.dateparse import parse_datetime
    
    if request.method == 'POST':
        try:
            # Get form data
            title = request.POST.get('title')
            resource_id = request.POST.get('resource')
            description = request.POST.get('description', '')
            start_time = parse_datetime(request.POST.get('start_time'))
            end_time = parse_datetime(request.POST.get('end_time'))
            
            # Make datetimes timezone-aware if they're not already
            if start_time and timezone.is_naive(start_time):
                start_time = timezone.make_aware(start_time)
            if end_time and timezone.is_naive(end_time):
                end_time = timezone.make_aware(end_time)
            
            maintenance_type = request.POST.get('maintenance_type')
            blocks_booking = request.POST.get('blocks_booking') == 'on'
            is_recurring = request.POST.get('is_recurring') == 'on'
            
            # Validation
            if not all([title, resource_id, start_time, end_time, maintenance_type]):
                return JsonResponse({'success': False, 'error': 'All required fields must be filled'})
            
            if end_time <= start_time:
                return JsonResponse({'success': False, 'error': 'End time must be after start time'})
            
            resource = get_object_or_404(Resource, id=resource_id)
            
            # Handle recurring pattern
            recurring_pattern = None
            if is_recurring and request.POST.get('recurring_pattern'):
                recurring_pattern = json.loads(request.POST.get('recurring_pattern'))
            
            # Create maintenance
            maintenance = Maintenance.objects.create(
                resource=resource,
                title=title,
                description=description,
                start_time=start_time,
                end_time=end_time,
                maintenance_type=maintenance_type,
                blocks_booking=blocks_booking,
                is_recurring=is_recurring,
                recurring_pattern=recurring_pattern,
                created_by=request.user
            )
            
            return JsonResponse({'success': True, 'message': 'Maintenance period scheduled successfully'})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_edit_maintenance_view(request, maintenance_id):
    """Edit or view an existing maintenance period."""
    maintenance = get_object_or_404(Maintenance, id=maintenance_id)
    
    if request.method == 'GET':
        # Return maintenance data for viewing/editing
        maintenance_data = {
            'id': maintenance.id,
            'title': maintenance.title,
            'description': maintenance.description,
            'resource_id': maintenance.resource.id,
            'resource_name': maintenance.resource.name,
            'start_time': maintenance.start_time.strftime('%Y-%m-%dT%H:%M'),
            'end_time': maintenance.end_time.strftime('%Y-%m-%dT%H:%M'),
            'maintenance_type': maintenance.maintenance_type,
            'blocks_booking': maintenance.blocks_booking,
            'is_recurring': maintenance.is_recurring,
            'recurring_pattern': maintenance.recurring_pattern,
            'created_by': maintenance.created_by.get_full_name() or maintenance.created_by.username,
            'created_at': maintenance.created_at.strftime('%Y-%m-%d %H:%M'),
        }
        
        # Generate HTML for view modal
        from django.template.loader import render_to_string
        html = render_to_string('booking/maintenance_detail.html', {'maintenance': maintenance}, request=request)
        
        return JsonResponse({
            'success': True,
            'maintenance': maintenance_data,
            'html': html
        })
    
    elif request.method == 'POST':
        # Update maintenance
        try:
            from django.utils.dateparse import parse_datetime
            
            maintenance.title = request.POST.get('title')
            maintenance.description = request.POST.get('description', '')
            
            # Parse and make datetimes timezone-aware
            start_time = parse_datetime(request.POST.get('start_time'))
            end_time = parse_datetime(request.POST.get('end_time'))
            
            if start_time and timezone.is_naive(start_time):
                start_time = timezone.make_aware(start_time)
            if end_time and timezone.is_naive(end_time):
                end_time = timezone.make_aware(end_time)
            
            maintenance.start_time = start_time
            maintenance.end_time = end_time
            maintenance.maintenance_type = request.POST.get('maintenance_type')
            maintenance.blocks_booking = request.POST.get('blocks_booking') == 'on'
            
            # Validation
            if maintenance.end_time <= maintenance.start_time:
                return JsonResponse({'success': False, 'error': 'End time must be after start time'})
            
            # Update resource if changed
            resource_id = request.POST.get('resource')
            if resource_id and str(maintenance.resource.id) != resource_id:
                maintenance.resource = get_object_or_404(Resource, id=resource_id)
            
            maintenance.save()
            
            return JsonResponse({'success': True, 'message': 'Maintenance period updated successfully'})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_delete_maintenance_view(request, maintenance_id):
    """Delete a maintenance period."""
    maintenance = get_object_or_404(Maintenance, id=maintenance_id)
    
    if request.method == 'POST':
        try:
            maintenance_title = maintenance.title
            maintenance.delete()
            return JsonResponse({'success': True, 'message': f'Maintenance period "{maintenance_title}" deleted successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@login_required
def download_booking_invitation(request, booking_id):
    """Download a calendar invitation for a specific booking."""
    from booking.calendar_sync import ICSCalendarGenerator, create_ics_response
    from booking.models import Booking
    
    booking = get_object_or_404(Booking, id=booking_id)
    
    # Check permissions - user must be the booking owner or have admin access
    if not (booking.user == request.user or 
            request.user.userprofile.role in ['technician', 'sysadmin'] or
            request.user.groups.filter(name='Lab Admin').exists()):
        messages.error(request, "You don't have permission to download this booking invitation.")
        return redirect('booking:my_bookings')
    
    # Generate ICS invitation
    generator = ICSCalendarGenerator(request)
    ics_content = generator.generate_booking_invitation(booking)
    
    # Create filename
    safe_title = booking.title.replace(' ', '-').replace('/', '-')
    filename = f"booking-{safe_title}-{booking.start_time.strftime('%Y%m%d')}.ics"
    
    return create_ics_response(ics_content, filename)


@login_required
@user_passes_test(is_lab_admin)
def download_maintenance_invitation(request, maintenance_id):
    """Download a calendar invitation for a specific maintenance period."""
    from booking.calendar_sync import ICSCalendarGenerator, create_ics_response
    from booking.models import Maintenance
    
    maintenance = get_object_or_404(Maintenance, id=maintenance_id)
    
    # Generate ICS invitation
    generator = ICSCalendarGenerator(request)
    ics_content = generator.generate_maintenance_invitation(maintenance)
    
    # Create filename
    safe_title = maintenance.title.replace(' ', '-').replace('/', '-')
    filename = f"maintenance-{safe_title}-{maintenance.start_time.strftime('%Y%m%d')}.ics"
    
    return create_ics_response(ics_content, filename)


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_inductions_view(request):
    """Manage lab induction status for users."""
    from django.db.models import Q
    from django.core.paginator import Paginator
    from booking.models import UserProfile
    from django.contrib.auth.models import User
    
    # Get filter parameters
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('search', '').strip()
    
    # Base queryset - users with profiles
    users = User.objects.select_related('userprofile').filter(userprofile__isnull=False)
    
    # Apply status filter
    if status_filter == 'inducted':
        users = users.filter(userprofile__is_inducted=True)
    elif status_filter == 'not_inducted':
        users = users.filter(userprofile__is_inducted=False)
    
    # Apply search filter
    if search_query:
        users = users.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(userprofile__student_id__icontains=search_query)
        )
    
    # Handle POST requests for updating induction status
    if request.method == 'POST':
        action = request.POST.get('action')
        user_id = request.POST.get('user_id')
        
        try:
            user = User.objects.select_related('userprofile').get(id=user_id)
            user_profile = user.userprofile
            
            if action == 'mark_inducted':
                user_profile.is_inducted = True
                user_profile.save()
                
                # Also mark safety induction as confirmed on any pending access requests
                from booking.models import AccessRequest
                from django.utils import timezone
                pending_requests = AccessRequest.objects.filter(
                    user=user, 
                    status='pending',
                    safety_induction_confirmed=False
                )
                
                for access_request in pending_requests:
                    access_request.safety_induction_confirmed = True
                    access_request.safety_induction_confirmed_by = request.user
                    access_request.safety_induction_confirmed_at = timezone.now()
                    access_request.safety_induction_notes = f"Confirmed via general lab induction by {request.user.get_full_name() or request.user.username}"
                    access_request.save(update_fields=[
                        'safety_induction_confirmed', 'safety_induction_confirmed_by', 
                        'safety_induction_confirmed_at', 'safety_induction_notes', 'updated_at'
                    ])
                
                messages.success(request, f'Successfully marked {user.get_full_name() or user.username} as inducted.')
                
                # Send notification to user
                from booking.models import Notification
                Notification.objects.create(
                    user=user,
                    title='Lab Induction Completed',
                    message=f'Your lab induction has been confirmed by {request.user.get_full_name() or request.user.username}. You can now request access to lab resources.',
                    notification_type='induction',
                    is_read=False
                )
                
            elif action == 'mark_not_inducted':
                user_profile.is_inducted = False
                user_profile.save()
                
                # Also clear safety induction confirmation on any pending access requests
                from booking.models import AccessRequest
                pending_requests = AccessRequest.objects.filter(
                    user=user, 
                    status='pending',
                    safety_induction_confirmed=True
                )
                
                for access_request in pending_requests:
                    access_request.safety_induction_confirmed = False
                    access_request.safety_induction_confirmed_by = None
                    access_request.safety_induction_confirmed_at = None
                    access_request.safety_induction_notes = ""
                    access_request.save(update_fields=[
                        'safety_induction_confirmed', 'safety_induction_confirmed_by', 
                        'safety_induction_confirmed_at', 'safety_induction_notes', 'updated_at'
                    ])
                
                messages.success(request, f'Successfully marked {user.get_full_name() or user.username} as not inducted.')
                
        except User.DoesNotExist:
            messages.error(request, 'User not found.')
        except Exception as e:
            messages.error(request, f'Error updating induction status: {str(e)}')
        
        return redirect('booking:lab_admin_inductions')
    
    # Order by induction status (not inducted first) then by name
    users = users.order_by('userprofile__is_inducted', 'first_name', 'last_name')
    
    # Pagination
    paginator = Paginator(users, 25)
    page_number = request.GET.get('page')
    users_page = paginator.get_page(page_number)
    
    # Count statistics
    total_users = User.objects.filter(userprofile__isnull=False).count()
    inducted_count = User.objects.filter(userprofile__is_inducted=True).count()
    not_inducted_count = total_users - inducted_count
    
    context = {
        'users': users_page,
        'total_users': total_users,
        'inducted_count': inducted_count,
        'not_inducted_count': not_inducted_count,
        'status_filter': status_filter,
        'search_query': search_query,
    }
    
    return render(request, 'booking/lab_admin_inductions.html', context)



def about_page_view(request):
    """Display the about page with configurable content."""
    about_page = AboutPage.get_active()
    
    context = {
        'about_page': about_page,
    }
    
    return render(request, 'booking/about.html', context)


@user_passes_test(lambda u: u.is_staff or (hasattr(u, 'userprofile') and u.userprofile.role in ['technician', 'sysadmin']))
def about_page_edit_view(request):
    """Edit the about page with WYSIWYG editor."""
    about_page = AboutPage.get_active()
    
    if request.method == 'POST':
        form = AboutPageEditForm(request.POST, request.FILES, instance=about_page)
        if form.is_valid():
            about_page = form.save()
            messages.success(request, 'About page has been updated successfully.')
            return redirect('booking:about')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = AboutPageEditForm(instance=about_page)
    
    context = {
        'form': form,
        'about_page': about_page,
        'is_new': about_page is None,
    }
    
    return render(request, 'booking/about_edit.html', context)


class CustomLoginView(LoginView):
    """Custom login view that handles first login redirect logic."""
    
    def get_success_url(self):
        """Redirect to about page on first login, dashboard on subsequent logins."""
        user = self.request.user
        
        try:
            profile = user.userprofile
            
            # Check if this is the user's first login
            if profile.first_login is None:
                # Mark the first login time
                profile.first_login = timezone.now()
                profile.save()
                
                # Redirect to about page for first-time users
                return '/about/'
            else:
                # Redirect to dashboard for returning users
                return '/dashboard/'
                
        except UserProfile.DoesNotExist:
            # If no profile exists, redirect to about page
            return '/about/'


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_dashboard_view(request):
    """Site administration dashboard - replaces Django admin."""
    from django.contrib.auth.models import User
    from django.db.models import Count, Q
    from django.utils import timezone
    from datetime import timedelta
    import sys
    import platform
    import django
    
    # System Information
    system_info = {
        'python_version': sys.version,
        'django_version': django.get_version(),
        'platform': f"{platform.system()} {platform.release()}",
        'server_time': timezone.now(),
    }
    
    # Database Statistics
    total_users = User.objects.count()
    total_resources = Resource.objects.count()
    total_bookings = Booking.objects.count()
    
    # Recent Activity (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_users = User.objects.filter(date_joined__gte=thirty_days_ago).count()
    recent_bookings = Booking.objects.filter(created_at__gte=thirty_days_ago).count()
    
    # User Role Distribution
    user_roles = UserProfile.objects.values('role').annotate(count=Count('role')).order_by('-count')
    
    # Pending Approvals
    pending_access_requests = AccessRequest.objects.filter(status='pending').count()
    pending_training_requests = TrainingRequest.objects.filter(status='pending').count()
    
    # Resource Status
    active_resources = Resource.objects.filter(is_active=True).count()
    inactive_resources = Resource.objects.filter(is_active=False).count()
    
    # Maintenance Status
    active_maintenance = Maintenance.objects.filter(
        start_time__lte=timezone.now(),
        end_time__gte=timezone.now()
    ).count()
    
    upcoming_maintenance = Maintenance.objects.filter(
        start_time__gt=timezone.now(),
        start_time__lte=timezone.now() + timedelta(days=7)
    ).count()
    
    # Update Information
    try:
        from booking.models import UpdateInfo
        from booking.update_service import UpdateService
        
        update_info = UpdateInfo.objects.first()
        if not update_info:
            # Create default update info if none exists
            update_service = UpdateService()
            update_info = update_service.get_or_create_update_info()
        
    except Exception:
        # If update system isn't available, create a basic placeholder
        update_info = None
    
    # License Information
    try:
        from ..services.licensing import license_manager
        from ..models import LicenseConfiguration, LicenseValidationLog
        
        license_info = license_manager.get_license_info()
        license_config = license_manager.get_current_license()
        
        # Recent validation attempts
        recent_validations = 0
        validation_failures = 0
        if license_config:
            recent_validations = LicenseValidationLog.objects.filter(
                license=license_config,
                created_at__gte=thirty_days_ago
            ).count()
            validation_failures = LicenseValidationLog.objects.filter(
                license=license_config,
                result__in=['expired', 'invalid_key', 'domain_mismatch', 'usage_exceeded'],
                created_at__gte=thirty_days_ago
            ).count()
        
        license_stats = {
            'license_type': license_info.get('type', 'open_source'),
            'is_valid': license_info.get('is_valid', True),
            'organization': license_info.get('organization', 'Open Source User'),
            'expires_at': license_info.get('expires_at'),
            'recent_validations': recent_validations,
            'validation_failures': validation_failures,
            'enabled_features': license_manager.get_enabled_features(),
        }
        
    except Exception as e:
        # Fallback to open source defaults
        license_stats = {
            'license_type': 'open_source',
            'is_valid': True,
            'organization': 'Open Source User',
            'expires_at': None,
            'recent_validations': 0,
            'validation_failures': 0,
            'enabled_features': {},
        }
    
    context = {
        'system_info': system_info,
        'stats': {
            'total_users': total_users,
            'total_resources': total_resources, 
            'total_bookings': total_bookings,
            'recent_users': recent_users,
            'recent_bookings': recent_bookings,
            'active_resources': active_resources,
            'inactive_resources': inactive_resources,
            'active_maintenance': active_maintenance,
            'upcoming_maintenance': upcoming_maintenance,
            'pending_access_requests': pending_access_requests,
            'pending_training_requests': pending_training_requests,
        },
        'user_roles': user_roles,
        'update_info': update_info,
        'license_stats': license_stats,
    }
    
    return render(request, 'booking/site_admin_dashboard.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_license_management_view(request):
    """Site admin license management page."""
    try:
        from ..services.licensing import license_manager
        from ..models import LicenseConfiguration, BrandingConfiguration, LicenseValidationLog
        
        # Get current license information
        license_info = license_manager.get_license_info()
        license_config = license_manager.get_current_license()
        
        # Get branding configuration
        branding_config = None
        if license_config:
            try:
                branding_config = license_config.branding
            except BrandingConfiguration.DoesNotExist:
                pass
        
        # Get recent validation logs
        validation_logs = []
        if license_config:
            validation_logs = LicenseValidationLog.objects.filter(
                license=license_config
            ).order_by('-created_at')[:10]
        
        # Get all license configurations (for enterprise setups)
        all_licenses = LicenseConfiguration.objects.all().order_by('-created_at')
        
        context = {
            'license_info': license_info,
            'license_config': license_config,
            'branding_config': branding_config,
            'validation_logs': validation_logs,
            'all_licenses': all_licenses,
            'enabled_features': license_manager.get_enabled_features(),
        }
        
    except Exception as e:
        context = {
            'error': f"Error loading license information: {e}",
            'license_info': {'type': 'open_source', 'is_valid': True},
            'enabled_features': {},
        }
    
    return render(request, 'booking/site_admin_license_management.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
@require_license_feature('custom_branding')
def site_admin_branding_config_view(request):
    """Site admin branding configuration page."""
    try:
        from ..services.licensing import license_manager, get_branding_config
        from ..models import LicenseConfiguration, BrandingConfiguration
        from ..views.licensing import BrandingConfigurationForm
        
        license_config = license_manager.get_current_license()
        
        if not license_config:
            messages.error(request, "No active license found. Please activate a license first.")
            return redirect('booking:site_admin_license_management')
        
        # Check if branding is enabled
        enabled_features = license_manager.get_enabled_features()
        if not enabled_features.get('custom_branding', False):
            messages.warning(request, "Custom branding is not available in your current license.")
            return redirect('booking:site_admin_license_management')
        
        # Get or create branding configuration
        try:
            branding_config = license_config.branding
        except BrandingConfiguration.DoesNotExist:
            branding_config = BrandingConfiguration(license=license_config)
        
        if request.method == 'POST':
            form = BrandingConfigurationForm(request.POST, request.FILES, instance=branding_config)
            if form.is_valid():
                form.save()
                license_manager.clear_cache()
                messages.success(request, "Branding configuration updated successfully")
                return redirect('booking:site_admin_branding_config')
        else:
            form = BrandingConfigurationForm(instance=branding_config)
        
        context = {
            'form': form,
            'license_config': license_config,
            'branding_config': branding_config,
            'current_branding': get_branding_config(),
        }
        
    except Exception as e:
        messages.error(request, f"Error loading branding configuration: {e}")
        return redirect('booking:site_admin_dashboard')
    
    return render(request, 'booking/site_admin_branding_config.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_license_activate_view(request):
    """Site admin license activation page."""
    try:
        from ..views.licensing import LicenseActivationForm
        from ..services.licensing import license_manager
        from ..models import LicenseConfiguration, BrandingConfiguration
        from django.db import transaction
        
        if request.method == 'POST':
            form = LicenseActivationForm(request.POST)
            if form.is_valid():
                try:
                    with transaction.atomic():
                        # Deactivate any existing licenses
                        LicenseConfiguration.objects.filter(is_active=True).update(is_active=False)
                        
                        # Create new license configuration
                        license_config = LicenseConfiguration.objects.create(
                            license_key=form.cleaned_data['license_key'],
                            license_type='basic_commercial',  # Default for manual activation
                            organization_name=form.cleaned_data['organization_name'],
                            organization_slug=form.cleaned_data['organization_name'].lower().replace(' ', '-'),
                            contact_email=form.cleaned_data['contact_email'],
                            is_active=True
                        )
                        
                        # Create default branding configuration
                        BrandingConfiguration.objects.create(
                            license=license_config,
                            company_name=form.cleaned_data['organization_name'],
                            email_from_name=form.cleaned_data['organization_name'],
                        )
                        
                        # Clear license cache
                        license_manager.clear_cache()
                        
                        messages.success(request, f"License activated successfully for {license_config.organization_name}")
                        return redirect('booking:site_admin_license_management')
                        
                except Exception as e:
                    messages.error(request, f"License activation failed: {e}")
        else:
            form = LicenseActivationForm()
        
        context = {
            'form': form,
        }
        
    except Exception as e:
        messages.error(request, f"Error loading license activation: {e}")
        return redirect('booking:site_admin_dashboard')
    
    return render(request, 'booking/site_admin_license_activate.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_license_select_open_source_view(request):
    """Site admin open source license selection page."""
    try:
        from ..services.licensing import license_manager
        from ..models import LicenseConfiguration, BrandingConfiguration
        from django.db import transaction
        
        if request.method == 'POST':
            try:
                with transaction.atomic():
                    # Deactivate any existing licenses
                    LicenseConfiguration.objects.filter(is_active=True).update(is_active=False)
                    
                    # Create open source license configuration
                    license_config = LicenseConfiguration.objects.create(
                        license_key='OPEN_SOURCE_GPL3',
                        license_type='open_source',
                        organization_name='Open Source User',
                        organization_slug='open-source',
                        contact_email='user@example.com',
                        is_active=True
                    )
                    
                    # Create default branding configuration for open source
                    BrandingConfiguration.objects.create(
                        license=license_config,
                        company_name='Open Source Lab',
                        show_powered_by=False,  # Hide licensing messages for open source
                    )
                    
                    # Clear license cache
                    license_manager.clear_cache()
                    
                    messages.success(request, "Open Source license selected. Licensing messages have been removed.")
                    return redirect('booking:site_admin_license_management')
                    
            except Exception as e:
                messages.error(request, f"Failed to select open source license: {e}")
        
        context = {
            'current_license': license_manager.get_current_license(),
        }
        
    except Exception as e:
        messages.error(request, f"Error loading open source license selection: {e}")
        return redirect('booking:site_admin_dashboard')
    
    return render(request, 'booking/site_admin_license_select_open_source.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_license_validation_logs_view(request):
    """Site admin license validation logs page."""
    try:
        from ..services.licensing import license_manager
        from ..models import LicenseValidationLog
        from django.core.paginator import Paginator
        
        license_config = license_manager.get_current_license()
        
        if not license_config:
            messages.error(request, "No active license found.")
            return redirect('booking:site_admin_license_management')
        
        # Get validation logs with pagination
        logs = LicenseValidationLog.objects.filter(
            license=license_config
        ).order_by('-created_at')
        
        paginator = Paginator(logs, 50)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Summary statistics
        total_validations = logs.count()
        successful_validations = logs.filter(result='success').count()
        failed_validations = logs.exclude(result='success').count()
        
        context = {
            'license_config': license_config,
            'page_obj': page_obj,
            'logs': page_obj,
            'total_validations': total_validations,
            'successful_validations': successful_validations,
            'failed_validations': failed_validations,
        }
        
    except Exception as e:
        messages.error(request, f"Error loading validation logs: {e}")
        return redirect('booking:site_admin_dashboard')
    
    return render(request, 'booking/site_admin_license_logs.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_license_validate_ajax(request):
    """AJAX endpoint for manual license validation."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        from ..services.licensing import license_manager
        
        is_valid, error_msg = license_manager.validate_license(force_remote=True)
        
        return JsonResponse({
            'success': True,
            'valid': is_valid,
            'message': 'License validation successful' if is_valid else error_msg,
            'license_info': license_manager.get_license_info()
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_license_export_view(request):
    """Export license information and validation logs to CSV."""
    try:
        from ..services.licensing import license_manager
        from ..models import LicenseValidationLog
        import csv
        from django.http import HttpResponse
        
        license_config = license_manager.get_current_license()
        
        if not license_config:
            messages.error(request, "No active license found.")
            return redirect('booking:site_admin_license_management')
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="license_export_{license_config.organization_slug}.csv"'
        
        writer = csv.writer(response)
        
        # License Information Header
        writer.writerow(['License Information'])
        writer.writerow(['Organization', license_config.organization_name])
        writer.writerow(['License Type', license_config.get_license_type_display()])
        writer.writerow(['License Key', license_config.license_key])
        writer.writerow(['Contact Email', license_config.contact_email])
        writer.writerow(['Active', 'Yes' if license_config.is_active else 'No'])
        writer.writerow(['Expires At', license_config.expires_at.strftime('%Y-%m-%d') if license_config.expires_at else 'Never'])
        writer.writerow(['Support Expires At', license_config.support_expires_at.strftime('%Y-%m-%d') if license_config.support_expires_at else 'Never'])
        writer.writerow(['Max Users', license_config.max_users or 'Unlimited'])
        writer.writerow(['Max Resources', license_config.max_resources or 'Unlimited'])
        writer.writerow(['Last Validation', license_config.last_validation.strftime('%Y-%m-%d %H:%M:%S') if license_config.last_validation else 'Never'])
        writer.writerow(['Validation Failures', license_config.validation_failures])
        writer.writerow([])  # Empty row
        
        # Enabled Features
        writer.writerow(['Enabled Features'])
        enabled_features = license_manager.get_enabled_features()
        for feature, enabled in enabled_features.items():
            writer.writerow([feature.replace('_', ' ').title(), 'Yes' if enabled else 'No'])
        writer.writerow([])  # Empty row
        
        # Validation Logs Header
        writer.writerow(['Validation Logs'])
        writer.writerow([
            'Date/Time', 'Validation Type', 'Result', 'Domain Checked', 
            'Response Time (seconds)', 'Error Message'
        ])
        
        # Export recent validation logs (last 100)
        logs = LicenseValidationLog.objects.filter(
            license=license_config
        ).order_by('-created_at')[:100]
        
        for log in logs:
            writer.writerow([
                log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                log.get_validation_type_display(),
                log.get_result_display(),
                log.domain_checked or '',
                f"{log.response_time:.3f}" if log.response_time else '',
                log.error_message or '',
            ])
        
        return response
        
    except Exception as e:
        messages.error(request, f"Error exporting license information: {e}")
        return redirect('booking:site_admin_license_management')


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_users_view(request):
    """User management interface."""
    users = User.objects.select_related('userprofile').order_by('-date_joined')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    # Role filter
    role_filter = request.GET.get('role', '')
    if role_filter:
        users = users.filter(userprofile__role=role_filter)
    
    # Status filter
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(users, 25)
    page_number = request.GET.get('page')
    users_page = paginator.get_page(page_number)
    
    context = {
        'users': users_page,
        'search_query': search_query,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'role_choices': UserProfile.ROLE_CHOICES,
    }
    
    return render(request, 'booking/site_admin_users.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_user_delete_view(request, user_id):
    """Delete user interface with confirmation."""
    from django.contrib import messages
    from django.db import transaction
    from django.contrib.auth.models import User
    from booking.models import UserProfile, Booking, ResourceAccess, UserTraining
    
    user_to_delete = get_object_or_404(User, id=user_id)
    
    # Prevent deletion of the current user
    if user_to_delete == request.user:
        messages.error(request, "You cannot delete your own account.")
        return redirect('booking:site_admin_users')
    
    # Prevent deletion of other sysadmins unless current user is superuser
    if (hasattr(user_to_delete, 'userprofile') and 
        user_to_delete.userprofile.role == 'sysadmin' and 
        not request.user.is_superuser):
        messages.error(request, "You cannot delete other system administrators.")
        return redirect('booking:site_admin_users')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Get user info for confirmation message
                username = user_to_delete.username
                full_name = user_to_delete.get_full_name()
                
                # Delete the user (CASCADE relationships will be handled automatically)
                user_to_delete.delete()
                
                messages.success(
                    request, 
                    f'User "{username}" ({full_name}) has been permanently deleted.'
                )
                
                return redirect('booking:site_admin_users')
                
        except Exception as e:
            messages.error(
                request, 
                f'Error deleting user: {str(e)}'
            )
            return redirect('booking:site_admin_users')
    
    # Calculate impact for GET request (confirmation page)
    try:
        bookings_count = Booking.objects.filter(user=user_to_delete).count()
        active_bookings_count = Booking.objects.filter(
            user=user_to_delete, 
            status__in=['approved', 'pending']
        ).count()
        resource_access_count = ResourceAccess.objects.filter(user=user_to_delete).count()
        training_records_count = UserTraining.objects.filter(user=user_to_delete).count()
        
        # Check if user is referenced in any SET_NULL relationships
        approved_bookings_count = Booking.objects.filter(approved_by=user_to_delete).count()
        
    except Exception:
        # Fallback values if queries fail
        bookings_count = 0
        active_bookings_count = 0
        resource_access_count = 0
        training_records_count = 0
        approved_bookings_count = 0
    
    context = {
        'user_to_delete': user_to_delete,
        'bookings_count': bookings_count,
        'active_bookings_count': active_bookings_count,
        'resource_access_count': resource_access_count,
        'training_records_count': training_records_count,
        'approved_bookings_count': approved_bookings_count,
        'can_delete': active_bookings_count == 0,  # Only allow deletion if no active bookings
    }
    
    return render(request, 'booking/site_admin_user_confirm_delete.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_system_config_view(request):
    """System configuration interface."""
    from django.conf import settings
    from django.http import JsonResponse
    from django.core.cache import cache
    
    # Handle AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        action = request.GET.get('action')
        
        if action == 'clear_cache' and request.method == 'POST':
            try:
                # Clear Django cache
                cache.clear()
                
                # Try to clear additional caches if available
                cache_stats = {
                    'django_cache': 'cleared',
                }
                
                # If using Redis, could also clear Redis cache
                try:
                    from django.core.cache.backends.redis import RedisCache
                    from django_redis import get_redis_connection
                    if isinstance(cache, RedisCache):
                        redis_conn = get_redis_connection("default")
                        redis_conn.flushdb()
                        cache_stats['redis_cache'] = 'cleared'
                except ImportError:
                    pass
                except Exception:
                    pass
                
                # Clear session cache if using cached sessions
                try:
                    from django.contrib.sessions.backends.cached_db import SessionStore
                    from django.contrib.sessions.backends.cache import SessionStore as CacheSessionStore
                    cache_stats['session_cache'] = 'cleared'
                except Exception:
                    pass
                
                return JsonResponse({
                    'success': True,
                    'message': f'Application cache cleared successfully. Cache types cleared: {", ".join(cache_stats.keys())}',
                    'cache_stats': cache_stats
                })
                
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to clear cache: {str(e)}'
                })
        
        elif action == 'restart_app' and request.method == 'POST':
            try:
                import os
                import sys
                import signal
                import subprocess
                from django.conf import settings
                
                # Log the restart attempt
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Application restart initiated by user: {request.user.username}")
                
                # Different restart methods depending on deployment
                restart_method = None
                restart_command = None
                
                # Try to detect deployment method and choose appropriate restart
                if hasattr(settings, 'WSGI_APPLICATION'):
                    # Production WSGI deployment
                    if os.environ.get('GUNICORN_CMD_ARGS') or 'gunicorn' in sys.modules:
                        # Gunicorn deployment
                        restart_method = 'gunicorn'
                        try:
                            # Send HUP signal to gunicorn master process
                            ppid = os.getppid()
                            os.kill(ppid, signal.SIGHUP)
                            restart_command = f'SIGHUP signal sent to gunicorn master (PID: {ppid})'
                        except Exception as e:
                            # Alternative: try to restart via systemctl if available
                            try:
                                result = subprocess.run(['systemctl', 'reload', 'gunicorn'], 
                                                      capture_output=True, text=True, timeout=5)
                                if result.returncode == 0:
                                    restart_command = 'systemctl reload gunicorn executed'
                                else:
                                    raise Exception(f'systemctl failed: {result.stderr}')
                            except Exception:
                                restart_command = f'Gunicorn restart attempted but may have failed: {e}'
                    
                    elif 'uwsgi' in sys.modules or os.environ.get('UWSGI_ORIGINAL_PROC_NAME'):
                        # uWSGI deployment
                        restart_method = 'uwsgi'
                        try:
                            # Send SIGHUP to uwsgi master
                            ppid = os.getppid()
                            os.kill(ppid, signal.SIGHUP)
                            restart_command = f'SIGHUP signal sent to uwsgi master (PID: {ppid})'
                        except Exception as e:
                            restart_command = f'uWSGI restart attempted: {e}'
                    
                    else:
                        # Generic WSGI or unknown deployment
                        restart_method = 'generic'
                        try:
                            # Try touching wsgi.py file to trigger reload
                            wsgi_file = os.path.join(settings.BASE_DIR, 'labitory', 'wsgi.py')
                            if os.path.exists(wsgi_file):
                                # Touch the file to update modification time
                                os.utime(wsgi_file, None)
                                restart_command = f'Touched WSGI file: {wsgi_file}'
                            else:
                                restart_command = 'WSGI file not found for touch restart'
                        except Exception as e:
                            restart_command = f'Generic restart attempted: {e}'
                
                else:
                    # Development server
                    restart_method = 'development'
                    try:
                        # For development, we can restart by sending signal to current process
                        # This will cause the Django development server to restart
                        def restart_server():
                            import threading
                            import time
                            time.sleep(1)  # Small delay to allow response to be sent
                            os.kill(os.getpid(), signal.SIGTERM)
                        
                        # Start restart in a separate thread to allow response to be sent first
                        restart_thread = threading.Thread(target=restart_server)
                        restart_thread.daemon = True
                        restart_thread.start()
                        
                        restart_command = 'Development server restart initiated'
                    except Exception as e:
                        restart_command = f'Development restart attempted: {e}'
                
                return JsonResponse({
                    'success': True,
                    'message': 'Application restart initiated successfully',
                    'restart_method': restart_method,
                    'restart_command': restart_command,
                    'note': 'The application should be back online within 10-30 seconds'
                })
                
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to restart application: {str(e)}'
                })
    
    if request.method == 'POST':
        # Handle configuration updates
        # This would need to be implemented based on your configuration system
        messages.success(request, 'Configuration updated successfully.')
        return redirect('booking:site_admin_config')
    
    # Get current configuration
    config_settings = {
        'debug_mode': settings.DEBUG,
        'time_zone': settings.TIME_ZONE,
        'language_code': settings.LANGUAGE_CODE,
        'email_backend': getattr(settings, 'EMAIL_BACKEND', 'Not configured'),
        'database_engine': settings.DATABASES['default']['ENGINE'],
        'static_url': settings.STATIC_URL,
        'media_url': settings.MEDIA_URL,
    }
    
    context = {
        'config_settings': config_settings,
    }
    
    return render(request, 'booking/site_admin_config.html', context)


@login_required
@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_lab_settings_view(request):
    """Lab settings management interface."""
    from django.contrib import messages
    from ..models import LabSettings
    
    # Get or create lab settings
    lab_settings = LabSettings.get_active()
    if not lab_settings:
        lab_settings = LabSettings.objects.create(
            lab_name="Labitory",
            is_active=True
        )
    
    if request.method == 'POST':
        lab_name = request.POST.get('lab_name', '').strip()
        
        if lab_name:
            lab_settings.lab_name = lab_name
            lab_settings.save()
            messages.success(request, 'Lab settings updated successfully.')
            return redirect('booking:site_admin_lab_settings')
        else:
            messages.error(request, 'Lab name cannot be empty.')
    
    context = {
        'lab_settings': lab_settings,
    }
    
    return render(request, 'booking/site_admin_lab_settings.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_audit_logs_view(request):
    """Audit logs and system monitoring."""
    from booking.log_viewer import log_viewer
    
    # Recent bookings with actions
    recent_bookings = Booking.objects.select_related('user', 'resource').order_by('-created_at')[:20]
    
    # Recent user registrations
    recent_users = User.objects.order_by('-date_joined')[:10]
    
    # Recent access requests
    recent_access_requests = AccessRequest.objects.select_related('user', 'resource').order_by('-created_at')[:15]
    
    # System logs
    system_logs = log_viewer.get_logs(hours=24, max_lines=50)
    log_sources = log_viewer.get_available_sources()
    
    context = {
        'recent_bookings': recent_bookings,
        'recent_users': recent_users,
        'recent_access_requests': recent_access_requests,
        'system_logs': system_logs,
        'log_sources': log_sources,
    }
    
    return render(request, 'booking/site_admin_audit.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_logs_ajax(request):
    """AJAX endpoint for system logs."""
    from django.http import JsonResponse
    from booking.log_viewer import log_viewer
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        source = request.GET.get('source')
        level = request.GET.get('level')
        search = request.GET.get('search')
        
        # Validate numeric parameters
        try:
            hours = int(request.GET.get('hours', 24))
            max_lines = int(request.GET.get('max_lines', 100))
        except ValueError:
            return JsonResponse({
                'error': 'Invalid numeric parameter'
            }, status=400)
        
        # Limit parameters to reasonable values
        hours = min(max(hours, 1), 720)  # 1 hour to 30 days
        max_lines = min(max(max_lines, 1), 1000)  # 1 to 1000 lines
        
        logs = log_viewer.get_logs(source, level, search, hours, max_lines)
        
        log_data = []
        for log in logs:
            try:
                log_data.append({
                    'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'level': log.level,
                    'source': log.source,
                    'message': log.message,
                    'level_color': log.get_level_color()
                })
            except Exception as e:
                logger.warning(f"Error processing log entry: {e}")
                continue
        
        return JsonResponse({
            'logs': log_data,
            'total': len(log_data),
            'status': 'success'
        })
        
    except Exception as e:
        logger.error(f"Error in logs AJAX endpoint: {e}")
        return JsonResponse({
            'error': f'Server error: {str(e)}',
            'logs': [],
            'total': 0
        }, status=500)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_health_check_view(request):
    """System health check endpoint for site administrators."""
    from django.http import JsonResponse
    from django.db import connection
    from django.core.cache import cache
    from django.conf import settings
    import os
    import time
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    health_results = {}
    overall_status = 'healthy'
    
    # Database connectivity check
    try:
        start_time = time.time()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        db_response_time = round((time.time() - start_time) * 1000, 2)
        health_results['database'] = {
            'status': 'healthy',
            'response_time_ms': db_response_time,
            'message': 'Database connection successful'
        }
    except Exception as e:
        health_results['database'] = {
            'status': 'unhealthy',
            'error': str(e),
            'message': 'Database connection failed'
        }
        overall_status = 'unhealthy'
    
    # Cache system check (if configured)
    try:
        cache_key = 'health_check_test'
        cache_value = 'test_value'
        cache.set(cache_key, cache_value, timeout=60)
        retrieved_value = cache.get(cache_key)
        
        if retrieved_value == cache_value:
            health_results['cache'] = {
                'status': 'healthy',
                'message': 'Cache system operational'
            }
        else:
            health_results['cache'] = {
                'status': 'warning',
                'message': 'Cache not working properly'
            }
            if overall_status == 'healthy':
                overall_status = 'warning'
    except Exception as e:
        health_results['cache'] = {
            'status': 'warning',
            'error': str(e),
            'message': 'Cache check failed - may not be configured'
        }
        if overall_status == 'healthy':
            overall_status = 'warning'
    
    # System resources check
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        system_status = 'healthy'
        warnings = []
        
        if cpu_percent > 80:
            warnings.append(f'High CPU usage: {cpu_percent}%')
            system_status = 'warning'
        
        if memory.percent > 80:
            warnings.append(f'High memory usage: {memory.percent}%')
            system_status = 'warning'
        
        if disk.percent > 85:
            warnings.append(f'High disk usage: {disk.percent}%')
            system_status = 'warning'
        
        health_results['system_resources'] = {
            'status': system_status,
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'disk_percent': disk.percent,
            'warnings': warnings,
            'message': 'System resources monitored'
        }
        
        if system_status == 'warning' and overall_status == 'healthy':
            overall_status = 'warning'
            
    except ImportError:
        health_results['system_resources'] = {
            'status': 'warning',
            'message': 'System resource monitoring unavailable (psutil not installed)'
        }
        if overall_status == 'healthy':
            overall_status = 'warning'
    except Exception as e:
        health_results['system_resources'] = {
            'status': 'warning',
            'error': str(e),
            'message': 'Could not check system resources'
        }
        if overall_status == 'healthy':
            overall_status = 'warning'
    
    # Application models check
    try:
        models_check = []
        
        # Check critical models
        user_count = User.objects.count()
        resource_count = Resource.objects.count()
        booking_count = Booking.objects.count()
        
        models_check.append(f'Users: {user_count}')
        models_check.append(f'Resources: {resource_count}')
        models_check.append(f'Bookings: {booking_count}')
        
        health_results['application_models'] = {
            'status': 'healthy',
            'counts': models_check,
            'message': 'Application models accessible'
        }
        
    except Exception as e:
        health_results['application_models'] = {
            'status': 'unhealthy',
            'error': str(e),
            'message': 'Application models check failed'
        }
        overall_status = 'unhealthy'
    
    # File system permissions check
    try:
        media_root = getattr(settings, 'MEDIA_ROOT', '/tmp')
        test_file = os.path.join(media_root, 'health_check_test.txt')
        
        # Try to write and read a test file
        with open(test_file, 'w') as f:
            f.write('health check test')
        
        with open(test_file, 'r') as f:
            content = f.read()
        
        os.remove(test_file)
        
        if content == 'health check test':
            health_results['file_system'] = {
                'status': 'healthy',
                'message': 'File system read/write operational'
            }
        else:
            health_results['file_system'] = {
                'status': 'warning',
                'message': 'File system write/read issue detected'
            }
            if overall_status == 'healthy':
                overall_status = 'warning'
                
    except Exception as e:
        health_results['file_system'] = {
            'status': 'warning',
            'error': str(e),
            'message': 'File system permissions check failed'
        }
        if overall_status == 'healthy':
            overall_status = 'warning'
    
    # Environment configuration check
    try:
        config_issues = []
        
        # Check critical settings
        if not settings.SECRET_KEY:
            config_issues.append('SECRET_KEY not configured')
        
        if settings.DEBUG:
            config_issues.append('DEBUG is True (should be False in production)')
        
        if not settings.ALLOWED_HOSTS:
            config_issues.append('ALLOWED_HOSTS not configured')
        
        config_status = 'warning' if config_issues else 'healthy'
        
        health_results['configuration'] = {
            'status': config_status,
            'issues': config_issues,
            'message': 'Configuration checked'
        }
        
        if config_status == 'warning' and overall_status == 'healthy':
            overall_status = 'warning'
            
    except Exception as e:
        health_results['configuration'] = {
            'status': 'warning',
            'error': str(e),
            'message': 'Configuration check failed'
        }
        if overall_status == 'healthy':
            overall_status = 'warning'
    
    # Return comprehensive health check results
    return JsonResponse({
        'overall_status': overall_status,
        'timestamp': timezone.now().isoformat(),
        'checks': health_results,
        'summary': {
            'healthy': len([k for k, v in health_results.items() if v['status'] == 'healthy']),
            'warnings': len([k for k, v in health_results.items() if v['status'] == 'warning']),
            'unhealthy': len([k for k, v in health_results.items() if v['status'] == 'unhealthy']),
            'total': len(health_results)
        }
    })


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_test_email_view(request):
    """Test email configuration endpoint for site administrators."""
    from django.http import JsonResponse
    from django.core.mail import send_mail, EmailMultiAlternatives
    from django.conf import settings
    from django.template.loader import render_to_string
    import time
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    import json
    try:
        data = json.loads(request.body)
        test_email = data.get('email', request.user.email)
    except (json.JSONDecodeError, AttributeError):
        test_email = request.user.email
    
    test_results = {}
    overall_status = 'success'
    
    # Check email configuration
    try:
        config_check = []
        config_issues = []
        
        # Check basic email settings
        if not settings.EMAIL_HOST:
            config_issues.append('EMAIL_HOST not configured')
        else:
            config_check.append(f'Email Host: {settings.EMAIL_HOST}')
            
        if not settings.DEFAULT_FROM_EMAIL:
            config_issues.append('DEFAULT_FROM_EMAIL not configured')
        else:
            config_check.append(f'From Email: {settings.DEFAULT_FROM_EMAIL}')
            
        config_check.append(f'Email Backend: {settings.EMAIL_BACKEND}')
        config_check.append(f'Email Port: {settings.EMAIL_PORT}')
        config_check.append(f'Use TLS: {settings.EMAIL_USE_TLS}')
        
        if settings.EMAIL_HOST_USER:
            config_check.append(f'SMTP User: {settings.EMAIL_HOST_USER}')
        else:
            config_check.append('SMTP User: Not configured')
            
        test_results['configuration'] = {
            'status': 'warning' if config_issues else 'success',
            'settings': config_check,
            'issues': config_issues,
            'message': 'Email configuration checked'
        }
        
        if config_issues and overall_status == 'success':
            overall_status = 'warning'
            
    except Exception as e:
        test_results['configuration'] = {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to check email configuration'
        }
        overall_status = 'error'
    
    # Test basic email sending capability
    try:
        start_time = time.time()
        
        # Test with simple send_mail
        subject = 'Labitory - Email Configuration Test'
        message = f"""
Email Configuration Test

This is a test email sent from the Labitory system to verify email configuration.

Test Details:
- Sent at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}
- Sent to: {test_email}
- Sent from: {settings.DEFAULT_FROM_EMAIL}
- Email Backend: {settings.EMAIL_BACKEND}
- SMTP Host: {settings.EMAIL_HOST}
- SMTP Port: {settings.EMAIL_PORT}

If you received this email, your email configuration is working correctly!

--
Labitory System
        """.strip()
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[test_email],
            fail_silently=False
        )
        
        send_time = round((time.time() - start_time) * 1000, 2)
        
        test_results['basic_send'] = {
            'status': 'success',
            'send_time_ms': send_time,
            'recipient': test_email,
            'message': 'Basic email sent successfully'
        }
        
    except Exception as e:
        test_results['basic_send'] = {
            'status': 'error',
            'error': str(e),
            'recipient': test_email,
            'message': 'Failed to send basic email'
        }
        overall_status = 'error'
    
    # Test HTML email sending capability
    try:
        start_time = time.time()
        
        # Create a more complex HTML test email
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Email Test</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f4f4f4; }}
        .container {{ max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ background-color: #007bff; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; margin: -20px -20px 20px -20px; }}
        .success {{ background-color: #d4edda; border: 1px solid #c3e6cb; color: #155724; padding: 15px; border-radius: 4px; margin: 20px 0; }}
        .info {{ background-color: #e7f3ff; border: 1px solid #b3d7ff; color: #004085; padding: 15px; border-radius: 4px; margin: 20px 0; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>🧪 Labitory - HTML Email Test</h2>
        </div>
        
        <div class="success">
            <strong>✅ HTML Email Test Successful!</strong><br>
            Your email system can successfully send and render HTML emails.
        </div>
        
        <p>This is an HTML test email sent from the <strong>Labitory</strong> system.</p>
        
        <div class="info">
            <strong>Test Information:</strong><br>
            • Sent at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}<br>
            • Recipient: {test_email}<br>
            • From: {settings.DEFAULT_FROM_EMAIL}<br>
            • Backend: {settings.EMAIL_BACKEND}<br>
            • SMTP Host: {settings.EMAIL_HOST}<br>
            • SMTP Port: {settings.EMAIL_PORT}
        </div>
        
        <p>If you can see this formatted email with colors and styling, your HTML email configuration is working correctly!</p>
        
        <div class="footer">
            <p>This email was automatically generated by the Labitory system for testing purposes.</p>
        </div>
    </div>
</body>
</html>
        """.strip()
        
        text_content = f"""
HTML Email Configuration Test

This is an HTML test email sent from the Labitory system.

Test Details:
- Sent at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}
- Sent to: {test_email}
- Sent from: {settings.DEFAULT_FROM_EMAIL}
- Email Backend: {settings.EMAIL_BACKEND}
- SMTP Host: {settings.EMAIL_HOST}
- SMTP Port: {settings.EMAIL_PORT}

If you received this email with proper HTML formatting, your email configuration supports HTML emails!

--
Labitory System
        """.strip()
        
        email = EmailMultiAlternatives(
            subject='Labitory - HTML Email Configuration Test',
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[test_email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        send_time = round((time.time() - start_time) * 1000, 2)
        
        test_results['html_send'] = {
            'status': 'success',
            'send_time_ms': send_time,
            'recipient': test_email,
            'message': 'HTML email sent successfully'
        }
        
    except Exception as e:
        test_results['html_send'] = {
            'status': 'error',
            'error': str(e),
            'recipient': test_email,
            'message': 'Failed to send HTML email'
        }
        if overall_status == 'success':
            overall_status = 'warning'  # HTML failure is less critical than basic email failure
    
    # Test notification system integration
    try:
        from booking.notifications import NotificationService
        
        notification_service = NotificationService()
        
        # Test if notification service can access email settings
        test_results['notification_integration'] = {
            'status': 'success',
            'message': 'Notification service integration available',
            'service_available': True
        }
        
    except Exception as e:
        test_results['notification_integration'] = {
            'status': 'warning',
            'error': str(e),
            'message': 'Notification service integration check failed',
            'service_available': False
        }
        if overall_status == 'success':
            overall_status = 'warning'
    
    # Connection test (if using SMTP)
    if 'smtp' in settings.EMAIL_BACKEND.lower():
        try:
            import smtplib
            from email.mime.text import MIMEText
            
            start_time = time.time()
            
            # Test SMTP connection
            if settings.EMAIL_USE_TLS:
                server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
                server.starttls()
            else:
                server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
            
            if settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD:
                server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            
            server.quit()
            
            connection_time = round((time.time() - start_time) * 1000, 2)
            
            test_results['smtp_connection'] = {
                'status': 'success',
                'connection_time_ms': connection_time,
                'message': 'SMTP connection successful'
            }
            
        except Exception as e:
            test_results['smtp_connection'] = {
                'status': 'error',
                'error': str(e),
                'message': 'SMTP connection failed'
            }
            overall_status = 'error'
    else:
        test_results['smtp_connection'] = {
            'status': 'info',
            'message': f'Not using SMTP backend (using {settings.EMAIL_BACKEND})'
        }
    
    # Return comprehensive email test results
    return JsonResponse({
        'overall_status': overall_status,
        'timestamp': timezone.now().isoformat(),
        'test_email': test_email,
        'tests': test_results,
        'summary': {
            'success': len([k for k, v in test_results.items() if v['status'] == 'success']),
            'warnings': len([k for k, v in test_results.items() if v['status'] == 'warning']),
            'errors': len([k for k, v in test_results.items() if v['status'] == 'error']),
            'info': len([k for k, v in test_results.items() if v['status'] == 'info']),
            'total': len(test_results)
        },
        'recommendations': [
            'Check your spam/junk folder if test emails are not received',
            'Verify firewall settings allow outbound SMTP connections',
            'Ensure email credentials are correct if using authentication',
            'Consider using environment variables for sensitive email settings'
        ]
    })


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_email_config_view(request):
    """Email configuration management for site administrators."""
    from django.shortcuts import render, redirect, get_object_or_404
    from django.contrib import messages
    from django.http import JsonResponse
    from booking.models import EmailConfiguration
    from ..forms import EmailConfigurationForm, EmailConfigurationTestForm
    
    # Get all email configurations
    configurations = EmailConfiguration.objects.all().order_by('-is_active', '-updated_at')
    active_config = EmailConfiguration.get_active_configuration()
    
    # Handle AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        action = request.GET.get('action')
        
        if action == 'activate' and request.method == 'POST':
            config_id = request.POST.get('config_id')
            try:
                config = get_object_or_404(EmailConfiguration, id=config_id)
                config.activate()
                return JsonResponse({
                    'success': True,
                    'message': f'Configuration "{config.name}" activated successfully'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to activate configuration: {str(e)}'
                })
        
        elif action == 'deactivate' and request.method == 'POST':
            config_id = request.POST.get('config_id')
            try:
                config = get_object_or_404(EmailConfiguration, id=config_id)
                if not config.is_active:
                    return JsonResponse({
                        'success': False,
                        'message': 'Configuration is not currently active'
                    })
                config.is_active = False
                config.save()
                return JsonResponse({
                    'success': True,
                    'message': f'Configuration "{config.name}" deactivated successfully'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to deactivate configuration: {str(e)}'
                })
        
        elif action == 'test' and request.method == 'POST':
            config_id = request.POST.get('config_id')
            test_email = request.POST.get('test_email')
            try:
                config = get_object_or_404(EmailConfiguration, id=config_id)
                success, message = config.test_configuration(test_email)
                return JsonResponse({
                    'success': success,
                    'message': message,
                    'last_test_date': config.last_test_date.isoformat() if config.last_test_date else None,
                    'is_validated': config.is_validated
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Test failed: {str(e)}'
                })
        
        elif action == 'delete' and request.method == 'POST':
            config_id = request.POST.get('config_id')
            try:
                config = get_object_or_404(EmailConfiguration, id=config_id)
                if config.is_active:
                    return JsonResponse({
                        'success': False,
                        'message': 'Cannot delete the active configuration'
                    })
                config_name = config.name
                config.delete()
                return JsonResponse({
                    'success': True,
                    'message': f'Configuration "{config_name}" deleted successfully'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to delete configuration: {str(e)}'
                })
    
    context = {
        'configurations': configurations,
        'active_config': active_config,
        'common_configs': EmailConfiguration.get_common_configurations(),
    }
    
    return render(request, 'booking/site_admin_email_config.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_email_config_create_view(request):
    """Create new email configuration."""
    from django.shortcuts import render, redirect
    from django.contrib import messages
    from booking.models import EmailConfiguration
    from ..forms import EmailConfigurationForm
    
    if request.method == 'POST':
        form = EmailConfigurationForm(request.POST)
        if form.is_valid():
            config = form.save(commit=False)
            config.created_by = request.user
            config.save()
            messages.success(request, f'Email configuration "{config.name}" created successfully.')
            return redirect('booking:site_admin_email_config')
    else:
        form = EmailConfigurationForm()
        
        # Pre-fill with common configuration if requested
        preset = request.GET.get('preset')
        if preset:
            common_configs = EmailConfiguration.get_common_configurations()
            for config in common_configs:
                if config['name'].lower().replace(' ', '_') == preset:
                    for field, value in config.items():
                        if field in form.fields:
                            form.fields[field].initial = value
                    break
    
    context = {
        'form': form,
        'title': 'Create Email Configuration',
        'common_configs': EmailConfiguration.get_common_configurations(),
    }
    
    return render(request, 'booking/site_admin_email_config_form.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_email_config_edit_view(request, config_id):
    """Edit existing email configuration."""
    from django.shortcuts import render, redirect, get_object_or_404
    from django.contrib import messages
    from booking.models import EmailConfiguration
    from ..forms import EmailConfigurationForm
    
    config = get_object_or_404(EmailConfiguration, id=config_id)
    
    if request.method == 'POST':
        form = EmailConfigurationForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, f'Email configuration "{config.name}" updated successfully.')
            return redirect('booking:site_admin_email_config')
    else:
        form = EmailConfigurationForm(instance=config)
    
    context = {
        'form': form,
        'config': config,
        'title': f'Edit Email Configuration: {config.name}',
        'common_configs': EmailConfiguration.get_common_configurations(),
    }
    
    return render(request, 'booking/site_admin_email_config_form.html', context)


# Backup Management Views
@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
@require_license_feature('advanced_reports')
def site_admin_backup_management_view(request):
    """Backup management interface."""
    from booking.backup_service import BackupService
    import json
    
    backup_service = BackupService()
    
    # Handle POST requests for backup operations
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create_backup':
            include_media = request.POST.get('include_media') == 'on'
            description = request.POST.get('description', '')
            
            try:
                result = backup_service.create_full_backup(
                    include_media=include_media,
                    description=description
                )
                
                if result['success']:
                    messages.success(request, f"Backup created successfully: {result['backup_name']}")
                else:
                    messages.error(request, f"Backup failed: {', '.join(result['errors'])}")
                    
            except Exception as e:
                messages.error(request, f"Backup creation failed: {str(e)}")
        
        elif action == 'delete_backup':
            backup_name = request.POST.get('backup_name')
            if backup_name:
                try:
                    result = backup_service.delete_backup(backup_name)
                    if result['success']:
                        messages.success(request, result['message'])
                    else:
                        messages.error(request, result['message'])
                except Exception as e:
                    messages.error(request, f"Failed to delete backup: {str(e)}")
        
        elif action == 'cleanup_old':
            try:
                result = backup_service.cleanup_old_backups()
                if result['success']:
                    messages.success(request, f"Cleanup completed. Deleted {result['deleted_count']} old backups.")
                    if result['errors']:
                        for error in result['errors']:
                            messages.warning(request, error)
                else:
                    messages.error(request, f"Cleanup failed: {', '.join(result['errors'])}")
            except Exception as e:
                messages.error(request, f"Cleanup failed: {str(e)}")
        
        elif action == 'create_schedule':
            try:
                from booking.models import BackupSchedule
                schedule = BackupSchedule(
                    name=request.POST.get('name', 'Automated Backup'),
                    enabled=request.POST.get('enabled') == 'on',
                    frequency=request.POST.get('frequency', 'weekly'),
                    backup_time=request.POST.get('backup_time', '02:00'),
                    day_of_week=int(request.POST.get('day_of_week', 6)),
                    day_of_month=int(request.POST.get('day_of_month', 1)),
                    include_media=request.POST.get('include_media') == 'on',
                    include_database=request.POST.get('include_database') == 'on',
                    include_configuration=request.POST.get('include_configuration') == 'on',
                    max_backups_to_keep=int(request.POST.get('max_backups_to_keep', 7)),
                    retention_days=int(request.POST.get('retention_days', 30)),
                    notification_email=request.POST.get('notification_email', ''),
                    created_by=request.user
                )
                schedule.clean()
                schedule.save()
                messages.success(request, f"Backup schedule '{schedule.name}' created successfully")
                
            except Exception as e:
                messages.error(request, f"Failed to create backup schedule: {str(e)}")
        
        elif action == 'update_schedule':
            schedule_id = request.POST.get('schedule_id')
            try:
                from booking.models import BackupSchedule
                schedule = BackupSchedule.objects.get(id=schedule_id)
                schedule.name = request.POST.get('name', schedule.name)
                schedule.enabled = request.POST.get('enabled') == 'on'
                schedule.frequency = request.POST.get('frequency', schedule.frequency)
                schedule.backup_time = request.POST.get('backup_time', schedule.backup_time)
                schedule.day_of_week = int(request.POST.get('day_of_week', schedule.day_of_week))
                schedule.day_of_month = int(request.POST.get('day_of_month', schedule.day_of_month))
                schedule.include_media = request.POST.get('include_media') == 'on'
                schedule.include_database = request.POST.get('include_database') == 'on'
                schedule.include_configuration = request.POST.get('include_configuration') == 'on'
                schedule.max_backups_to_keep = int(request.POST.get('max_backups_to_keep', schedule.max_backups_to_keep))
                schedule.retention_days = int(request.POST.get('retention_days', schedule.retention_days))
                schedule.notification_email = request.POST.get('notification_email', schedule.notification_email)
                schedule.clean()
                schedule.save()
                messages.success(request, f"Backup schedule '{schedule.name}' updated successfully")
                
            except Exception as e:
                messages.error(request, f"Failed to update backup schedule: {str(e)}")
        
        elif action == 'delete_schedule':
            schedule_id = request.POST.get('schedule_id')
            try:
                from booking.models import BackupSchedule
                schedule = BackupSchedule.objects.get(id=schedule_id)
                schedule_name = schedule.name
                schedule.delete()
                messages.success(request, f"Backup schedule '{schedule_name}' deleted successfully")
                
            except Exception as e:
                messages.error(request, f"Failed to delete backup schedule: {str(e)}")
        
        elif action == 'test_schedule':
            schedule_id = request.POST.get('schedule_id')
            try:
                result = backup_service.test_scheduled_backup(int(schedule_id))
                if result.get('success'):
                    messages.success(request, f"Test backup completed successfully: {result.get('backup_name', 'Unknown')}")
                else:
                    error_msg = '; '.join(result.get('errors', ['Unknown error']))
                    messages.error(request, f"Test backup failed: {error_msg}")
                    
            except Exception as e:
                messages.error(request, f"Failed to test backup schedule: {str(e)}")
        
        return redirect('booking:site_admin_backup_management')
    
    # Get backup information
    try:
        backups = backup_service.list_backups()
        stats = backup_service.get_backup_statistics()
        automation_status = backup_service.get_backup_schedules_status()
    except Exception as e:
        messages.error(request, f"Failed to load backup information: {str(e)}")
        backups = []
        stats = {}
        automation_status = {}
    
    # Get backup schedules for automation tab
    try:
        from booking.models import BackupSchedule
        schedules = BackupSchedule.objects.all().order_by('-created_at')
        
        # Get form choices for templates
        frequency_choices = BackupSchedule.FREQUENCY_CHOICES
        day_of_week_choices = BackupSchedule.DAY_OF_WEEK_CHOICES
    except Exception as e:
        schedules = []
        frequency_choices = []
        day_of_week_choices = []
    
    context = {
        'backups': backups,
        'stats': stats,
        'automation_status': automation_status,
        'schedules': schedules,
        'frequency_choices': frequency_choices,
        'day_of_week_choices': day_of_week_choices,
        'title': 'Backup Management',
    }
    
    return render(request, 'booking/site_admin_backup_management.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_create_ajax(request):
    """AJAX endpoint for creating backups."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    from booking.backup_service import BackupService
    import json
    
    try:
        data = json.loads(request.body)
        backup_service = BackupService()
        
        include_media = data.get('include_media', True)
        description = data.get('description', '')
        
        result = backup_service.create_full_backup(
            include_media=include_media,
            description=description
        )
        
        if result['success']:
            # Convert datetime objects to strings for JSON serialization
            if 'timestamp' in result:
                result['timestamp'] = result['timestamp'].isoformat()
            
            return JsonResponse({
                'success': True,
                'backup_name': result['backup_name'],
                'message': f"Backup created successfully: {result['backup_name']}",
                'details': result
            })
        else:
            return JsonResponse({
                'success': False,
                'error': ', '.join(result['errors'])
            })
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_status_ajax(request):
    """AJAX endpoint for getting backup status and statistics."""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    from booking.backup_service import BackupService
    
    try:
        backup_service = BackupService()
        
        backups = backup_service.list_backups()
        stats = backup_service.get_backup_statistics()
        
        # Convert datetime objects to strings for JSON serialization
        for backup in backups:
            if 'timestamp' in backup:
                backup['timestamp'] = backup['timestamp']
        
        return JsonResponse({
            'success': True,
            'backups': backups,
            'stats': stats
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_download_view(request, backup_name):
    """Download a specific backup file."""
    from booking.backup_service import BackupService
    from django.http import FileResponse, Http404
    import os
    
    try:
        backup_service = BackupService()
        backup_path = os.path.join(backup_service.backup_dir, backup_name)
        compressed_path = f"{backup_path}.tar.gz"
        
        # Check for compressed backup first
        if os.path.exists(compressed_path):
            response = FileResponse(
                open(compressed_path, 'rb'),
                as_attachment=True,
                filename=f"{backup_name}.tar.gz"
            )
            return response
        elif os.path.exists(backup_path) and os.path.isfile(backup_path):
            response = FileResponse(
                open(backup_path, 'rb'),
                as_attachment=True,
                filename=backup_name
            )
            return response
        else:
            raise Http404("Backup file not found")
            
    except Exception as e:
        messages.error(request, f"Failed to download backup: {str(e)}")
        return redirect('booking:site_admin_backup_management')


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_restore_info_ajax(request, backup_name):
    """AJAX endpoint for getting backup restoration information."""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    from booking.backup_service import BackupService
    
    try:
        backup_service = BackupService()
        result = backup_service.get_backup_restoration_info(backup_name)
        
        if result['success']:
            # Convert datetime objects to strings for JSON serialization
            if 'timestamp' in result.get('backup_info', {}):
                result['backup_info']['timestamp'] = result['backup_info']['timestamp']
            
            return JsonResponse(result)
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Unknown error')
            })
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_restore_ajax(request):
    """AJAX endpoint for restoring backups."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    from booking.backup_service import BackupService
    import json
    import secrets
    
    try:
        data = json.loads(request.body)
        backup_service = BackupService()
        
        backup_name = data.get('backup_name')
        restore_components = data.get('restore_components', {})
        confirmation_token = data.get('confirmation_token')
        
        if not backup_name:
            return JsonResponse({'success': False, 'error': 'Backup name is required'})
        
        # Generate a secure confirmation token if database restoration is requested
        expected_token = None
        if restore_components.get('database', False):
            expected_token = f"RESTORE_{backup_name}_{secrets.token_hex(8)}"
            
            # Check if the provided token matches (for database restoration)
            if not confirmation_token or confirmation_token != expected_token:
                return JsonResponse({
                    'success': False,
                    'error': 'Database restoration requires confirmation',
                    'confirmation_required': True,
                    'confirmation_token': expected_token,
                    'warning_message': f'This will PERMANENTLY OVERWRITE your current database with data from backup "{backup_name}". This action cannot be undone.'
                })
        
        result = backup_service.restore_backup(
            backup_name=backup_name,
            restore_components=restore_components,
            confirmation_token=confirmation_token
        )
        
        if result['success']:
            # Convert datetime objects to strings for JSON serialization
            if 'timestamp' in result:
                result['timestamp'] = result['timestamp'].isoformat()
            
            return JsonResponse({
                'success': True,
                'message': f"Backup '{backup_name}' restored successfully",
                'details': result
            })
        else:
            return JsonResponse({
                'success': False,
                'error': ', '.join(result['errors']) if result['errors'] else 'Restoration failed'
            })
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_restore_view(request, backup_name):
    """Backup restoration interface."""
    from booking.backup_service import BackupService
    
    backup_service = BackupService()
    
    # Get backup restoration information
    try:
        restore_info = backup_service.get_backup_restoration_info(backup_name)
        
        if not restore_info['success']:
            messages.error(request, restore_info.get('error', 'Failed to get backup information'))
            return redirect('booking:site_admin_backup_management')
            
    except Exception as e:
        messages.error(request, f"Failed to analyze backup: {str(e)}")
        return redirect('booking:site_admin_backup_management')
    
    # Handle POST request for restoration
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'restore_backup':
            restore_components = {
                'database': request.POST.get('restore_database') == 'on',
                'media': request.POST.get('restore_media') == 'on',
                'configuration': request.POST.get('restore_configuration') == 'on'
            }
            
            confirmation_token = request.POST.get('confirmation_token')
            
            try:
                result = backup_service.restore_backup(
                    backup_name=backup_name,
                    restore_components=restore_components,
                    confirmation_token=confirmation_token
                )
                
                if result['success']:
                    messages.success(request, f"Backup '{backup_name}' restored successfully!")
                    
                    # Show component-specific results
                    for component, details in result.get('components_restored', {}).items():
                        if details.get('success'):
                            if component == 'database':
                                if details.get('backup_created'):
                                    messages.info(request, "Current database was backed up before restoration")
                            elif component == 'media':
                                count = details.get('restored_count', 0)
                                messages.info(request, f"Restored {count} media files")
                            elif component == 'configuration':
                                files = details.get('files_found', [])
                                messages.info(request, f"Configuration analysis complete: {len(files)} files found")
                    
                    # Show warnings
                    for warning in result.get('warnings', []):
                        messages.warning(request, warning)
                        
                else:
                    messages.error(request, f"Restoration failed: {', '.join(result['errors'])}")
                    
            except Exception as e:
                messages.error(request, f"Restoration failed: {str(e)}")
        
        return redirect('booking:site_admin_backup_management')
    
    context = {
        'backup_name': backup_name,
        'restore_info': restore_info,
        'title': f'Restore Backup: {backup_name}',
    }
    
    return render(request, 'booking/site_admin_backup_restore.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_automation_view(request):
    """Backup automation management interface."""
    from booking.models import BackupSchedule
    from booking.backup_service import BackupService
    
    backup_service = BackupService()
    
    # Handle POST requests for schedule operations
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create_schedule':
            try:
                schedule = BackupSchedule(
                    name=request.POST.get('name', 'Automated Backup'),
                    enabled=request.POST.get('enabled') == 'on',
                    frequency=request.POST.get('frequency', 'weekly'),
                    backup_time=request.POST.get('backup_time', '02:00'),
                    day_of_week=int(request.POST.get('day_of_week', 6)),
                    day_of_month=int(request.POST.get('day_of_month', 1)),
                    include_media=request.POST.get('include_media') == 'on',
                    include_database=request.POST.get('include_database') == 'on',
                    include_configuration=request.POST.get('include_configuration') == 'on',
                    max_backups_to_keep=int(request.POST.get('max_backups_to_keep', 7)),
                    retention_days=int(request.POST.get('retention_days', 30)),
                    notification_email=request.POST.get('notification_email', ''),
                    created_by=request.user
                )
                schedule.clean()
                schedule.save()
                messages.success(request, f"Backup schedule '{schedule.name}' created successfully")
                
            except Exception as e:
                messages.error(request, f"Failed to create backup schedule: {str(e)}")
        
        elif action == 'update_schedule':
            schedule_id = request.POST.get('schedule_id')
            try:
                schedule = BackupSchedule.objects.get(id=schedule_id)
                schedule.name = request.POST.get('name', schedule.name)
                schedule.enabled = request.POST.get('enabled') == 'on'
                schedule.frequency = request.POST.get('frequency', schedule.frequency)
                schedule.backup_time = request.POST.get('backup_time', schedule.backup_time)
                schedule.day_of_week = int(request.POST.get('day_of_week', schedule.day_of_week))
                schedule.day_of_month = int(request.POST.get('day_of_month', schedule.day_of_month))
                schedule.include_media = request.POST.get('include_media') == 'on'
                schedule.include_database = request.POST.get('include_database') == 'on'
                schedule.include_configuration = request.POST.get('include_configuration') == 'on'
                schedule.max_backups_to_keep = int(request.POST.get('max_backups_to_keep', schedule.max_backups_to_keep))
                schedule.retention_days = int(request.POST.get('retention_days', schedule.retention_days))
                schedule.notification_email = request.POST.get('notification_email', schedule.notification_email)
                schedule.clean()
                schedule.save()
                messages.success(request, f"Backup schedule '{schedule.name}' updated successfully")
                
            except BackupSchedule.DoesNotExist:
                messages.error(request, "Backup schedule not found")
            except Exception as e:
                messages.error(request, f"Failed to update backup schedule: {str(e)}")
        
        elif action == 'delete_schedule':
            schedule_id = request.POST.get('schedule_id')
            try:
                schedule = BackupSchedule.objects.get(id=schedule_id)
                schedule_name = schedule.name
                schedule.delete()
                messages.success(request, f"Backup schedule '{schedule_name}' deleted successfully")
                
            except BackupSchedule.DoesNotExist:
                messages.error(request, "Backup schedule not found")
            except Exception as e:
                messages.error(request, f"Failed to delete backup schedule: {str(e)}")
        
        elif action == 'test_schedule':
            schedule_id = request.POST.get('schedule_id')
            try:
                result = backup_service.test_scheduled_backup(int(schedule_id))
                if result.get('success'):
                    messages.success(request, f"Test backup completed successfully: {result.get('backup_name', 'Unknown')}")
                else:
                    error_msg = '; '.join(result.get('errors', ['Unknown error']))
                    messages.error(request, f"Test backup failed: {error_msg}")
                    
            except Exception as e:
                messages.error(request, f"Failed to test backup schedule: {str(e)}")
        
        return redirect('booking:site_admin_backup_automation')
    
    # Get backup schedules and status
    try:
        schedules = BackupSchedule.objects.all().order_by('-created_at')
        automation_status = backup_service.get_backup_schedules_status()
        
        # Get scheduler status
        from booking.scheduler import get_scheduler
        scheduler = get_scheduler()
        scheduler_status = scheduler.get_status()
        automation_status['scheduler'] = scheduler_status
        
    except Exception as e:
        messages.error(request, f"Failed to load backup schedules: {str(e)}")
        schedules = []
        automation_status = {}
    
    context = {
        'schedules': schedules,
        'automation_status': automation_status,
        'frequency_choices': BackupSchedule.FREQUENCY_CHOICES,
        'day_of_week_choices': BackupSchedule.DAY_OF_WEEK_CHOICES,
        'title': 'Backup Automation',
    }
    
    return render(request, 'booking/site_admin_backup_automation.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_automation_ajax(request):
    """AJAX endpoint for backup automation operations."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    from booking.models import BackupSchedule
    from booking.backup_service import BackupService
    import json
    
    try:
        data = json.loads(request.body)
        action = data.get('action')
        backup_service = BackupService()
        
        if action == 'run_schedules':
            # Run all scheduled backups
            results = backup_service.run_scheduled_backups()
            return JsonResponse({
                'success': True,
                'results': results
            })
        
        elif action == 'test_schedule':
            schedule_id = data.get('schedule_id')
            result = backup_service.test_scheduled_backup(int(schedule_id))
            return JsonResponse(result)
        
        elif action == 'get_status':
            status = backup_service.get_backup_schedules_status()
            return JsonResponse({
                'success': True,
                'status': status
            })
        
        elif action == 'toggle_schedule':
            schedule_id = data.get('schedule_id')
            schedule = BackupSchedule.objects.get(id=schedule_id)
            schedule.enabled = not schedule.enabled
            schedule.save()
            
            return JsonResponse({
                'success': True,
                'enabled': schedule.enabled,
                'message': f"Schedule '{schedule.name}' {'enabled' if schedule.enabled else 'disabled'}"
            })
        
        else:
            return JsonResponse({'success': False, 'error': 'Unknown action'})
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_schedule_detail_ajax(request, schedule_id):
    """AJAX endpoint for getting backup schedule details."""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    try:
        from booking.models import BackupSchedule
        
        schedule = BackupSchedule.objects.get(id=schedule_id)
        
        schedule_data = {
            'id': schedule.id,
            'name': schedule.name,
            'enabled': schedule.enabled,
            'frequency': schedule.frequency,
            'backup_time': schedule.backup_time.strftime('%H:%M'),
            'day_of_week': schedule.day_of_week,
            'day_of_month': schedule.day_of_month,
            'include_media': schedule.include_media,
            'include_database': schedule.include_database,
            'include_configuration': schedule.include_configuration,
            'max_backups_to_keep': schedule.max_backups_to_keep,
            'retention_days': schedule.retention_days,
            'notification_email': schedule.notification_email,
            'last_run': schedule.last_run.isoformat() if schedule.last_run else None,
            'last_success': schedule.last_success.isoformat() if schedule.last_success else None,
            'last_backup_name': schedule.last_backup_name,
            'consecutive_failures': schedule.consecutive_failures,
            'total_runs': schedule.total_runs,
            'total_successes': schedule.total_successes,
            'success_rate': schedule.success_rate,
            'is_healthy': schedule.is_healthy,
            'next_run': schedule.get_next_run_time().isoformat() if schedule.get_next_run_time() else None,
            'last_error': schedule.last_error
        }
        
        return JsonResponse({
            'success': True,
            'schedule': schedule_data
        })
        
    except BackupSchedule.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Schedule not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role in ['technician', 'sysadmin'])
def site_admin_updates_view(request):
    """Site admin view for managing application updates."""
    from booking.update_service import UpdateService
    from booking.models import UpdateInfo, UpdateHistory
    
    update_service = UpdateService()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'check_updates':
            result = update_service.check_for_updates()
            if result['success']:
                if result['update_available']:
                    messages.success(request, f"Update available: {result['latest_version']}")
                else:
                    messages.info(request, "You are running the latest version")
            else:
                messages.error(request, f"Failed to check for updates: {result['error']}")
        
        elif action == 'download_update':
            result = update_service.download_update()
            if result['success']:
                messages.success(request, "Update downloaded successfully")
            else:
                messages.error(request, f"Failed to download update: {result['error']}")
        
        elif action == 'install_update':
            backup_enabled = request.POST.get('create_backup') == 'on'
            result = update_service.install_update(backup_before_update=backup_enabled)
            if result['success']:
                message = "Update installed successfully"
                if result.get('backup_created'):
                    message += f" (Backup created: {result['backup_path']})"
                messages.success(request, message)
            else:
                messages.error(request, f"Failed to install update: {result['error']}")
        
        elif action == 'configure_repo':
            repo = request.POST.get('github_repo', '').strip()
            auto_check = request.POST.get('auto_check_enabled') == 'on'
            
            if repo:
                update_info = UpdateInfo.get_instance()
                update_info.github_repo = repo
                update_info.auto_check_enabled = auto_check
                update_info.save()
                messages.success(request, "Update settings saved successfully")
            else:
                messages.error(request, "GitHub repository is required")
        
        return redirect('booking:site_admin_updates')
    
    # Get update status and history
    update_status = update_service.get_update_status()
    update_history = UpdateHistory.objects.all()[:10]  # Last 10 updates
    
    context = {
        'update_status': update_status,
        'update_history': update_history,
    }
    
    return render(request, 'booking/site_admin_updates.html', context)


@login_required
@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role in ['technician', 'sysadmin'])
def site_admin_updates_ajax_view(request):
    """AJAX endpoint for update operations."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    from booking.update_service import UpdateService
    import json
    
    try:
        data = json.loads(request.body)
        action = data.get('action')
        
        update_service = UpdateService()
        
        if action == 'check_updates':
            result = update_service.check_for_updates()
            return JsonResponse(result)
        
        elif action == 'download_update':
            result = update_service.download_update()
            return JsonResponse(result)
        
        elif action == 'install_update':
            backup_enabled = data.get('create_backup', True)
            result = update_service.install_update(backup_before_update=backup_enabled)
            return JsonResponse(result)
        
        elif action == 'get_status':
            status = update_service.get_update_status()
            return JsonResponse({'success': True, 'status': status})
        
        elif action == 'rollback':
            update_id = data.get('update_id')
            if not update_id:
                return JsonResponse({'success': False, 'error': 'Update ID required'})
            
            result = update_service.rollback_update(update_id)
            return JsonResponse(result)
        
        else:
            return JsonResponse({'success': False, 'error': 'Unknown action'})
    
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Error in update AJAX view: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


# ============= RESOURCE ISSUE REPORTING VIEWS =============

@login_required
def report_resource_issue(request, resource_id):
    """Allow users to report issues with a resource."""
    resource = get_object_or_404(Resource, id=resource_id)
    booking_id = request.GET.get('booking')
    booking = None
    
    if booking_id:
        booking = get_object_or_404(Booking, id=booking_id, user=request.user)
    
    if request.method == 'POST':
        form = ResourceIssueReportForm(
            request.POST, 
            request.FILES,
            user=request.user,
            resource=resource,
            booking=booking
        )
        if form.is_valid():
            issue = form.save()
            messages.success(
                request, 
                f'Issue reported successfully. Reference #: {issue.id}'
            )
            return redirect('booking:resource_detail', resource_id=resource.id)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ResourceIssueReportForm(
            user=request.user,
            resource=resource,
            booking=booking
        )
    
    return render(request, 'booking/report_issue.html', {
        'form': form,
        'resource': resource,
        'booking': booking,
    })


@login_required
@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role in ['technician', 'sysadmin'])
def issues_dashboard(request):
    """Dashboard for managing resource issues."""
    filter_form = IssueFilterForm(request.GET)
    issues = ResourceIssue.objects.select_related('resource', 'reported_by', 'assigned_to').all()
    
    # Apply filters
    if filter_form.is_valid():
        if filter_form.cleaned_data['resource']:
            issues = issues.filter(resource=filter_form.cleaned_data['resource'])
        if filter_form.cleaned_data['status']:
            issues = issues.filter(status=filter_form.cleaned_data['status'])
        if filter_form.cleaned_data['severity']:
            issues = issues.filter(severity=filter_form.cleaned_data['severity'])
        if filter_form.cleaned_data['category']:
            issues = issues.filter(category=filter_form.cleaned_data['category'])
        if filter_form.cleaned_data['assigned_to']:
            issues = issues.filter(assigned_to=filter_form.cleaned_data['assigned_to'])
        if filter_form.cleaned_data['is_overdue']:
            # Filter for overdue issues (this would need a more complex query)
            pass
        if filter_form.cleaned_data['date_from']:
            issues = issues.filter(created_at__gte=filter_form.cleaned_data['date_from'])
        if filter_form.cleaned_data['date_to']:
            issues = issues.filter(created_at__lte=filter_form.cleaned_data['date_to'])
    
    # Statistics
    stats = {
        'total': issues.count(),
        'open': issues.filter(status='open').count(),
        'in_progress': issues.filter(status='in_progress').count(),
        'critical': issues.filter(severity='critical').count(),
        'overdue': sum(1 for issue in issues if issue.is_overdue),
    }
    
    # Pagination
    paginator = Paginator(issues, 25)
    page = request.GET.get('page')
    issues = paginator.get_page(page)
    
    return render(request, 'booking/issues_dashboard.html', {
        'issues': issues,
        'filter_form': filter_form,
        'stats': stats,
    })


@login_required
@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role in ['technician', 'sysadmin'])
def issue_detail(request, issue_id):
    """View and update a specific issue."""
    issue = get_object_or_404(ResourceIssue, id=issue_id)
    
    if request.method == 'POST':
        form = ResourceIssueUpdateForm(request.POST, instance=issue)
        if form.is_valid():
            form.save()
            messages.success(request, 'Issue updated successfully.')
            return redirect('booking:issue_detail', issue_id=issue.id)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ResourceIssueUpdateForm(instance=issue)
    
    return render(request, 'booking/issue_detail.html', {
        'issue': issue,
        'form': form,
    })


@login_required
def my_reported_issues(request):
    """View issues reported by the current user."""
    issues = ResourceIssue.objects.filter(
        reported_by=request.user
    ).select_related('resource', 'assigned_to').order_by('-created_at')
    
    # Pagination
    paginator = Paginator(issues, 20)
    page = request.GET.get('page')
    issues = paginator.get_page(page)
    
    return render(request, 'booking/my_issues.html', {
        'issues': issues,
    })


# =============================================================================
# Checklist Item AJAX Views
# =============================================================================

@login_required
@require_http_methods(["GET", "POST"])
def ajax_create_checklist_item(request):
    """AJAX view for creating checklist items in a popup."""
    if not (request.user.is_staff or hasattr(request.user, 'userprofile') and 
            request.user.userprofile.role in ['technician', 'sysadmin']):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    if request.method == 'GET':
        form = ChecklistItemForm()
        html = render_to_string('booking/modals/checklist_item_form.html', {
            'form': form,
        }, request=request)
        return JsonResponse({'html': html})
    
    elif request.method == 'POST':
        form = ChecklistItemForm(request.POST)
        if form.is_valid():
            checklist_item = form.save(commit=False)
            checklist_item.created_by = request.user
            checklist_item.save()
            
            return JsonResponse({
                'success': True,
                'item': {
                    'id': checklist_item.id,
                    'title': checklist_item.title,
                    'description': checklist_item.description,
                    'category': checklist_item.get_category_display(),
                    'item_type': checklist_item.get_item_type_display(),
                    'is_required': checklist_item.is_required,
                }
            })
        else:
            html = render_to_string('booking/modals/checklist_item_form.html', {
                'form': form,
            }, request=request)
            return JsonResponse({'html': html, 'errors': form.errors})


# =============================================================================
# Academic Hierarchy Management Views (Site Admin)
# =============================================================================


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["POST"])
def add_training_course_api(request):
    """API endpoint to add a new training course."""
    from booking.models import TrainingCourse
    import json
    
    try:
        # Parse JSON data
        data = json.loads(request.body)
        
        # Validate required fields
        title = data.get('title', '').strip()
        code = data.get('code', '').strip()
        
        if not title:
            return JsonResponse({'error': 'Course title is required'}, status=400)
        
        if not code:
            return JsonResponse({'error': 'Course code is required'}, status=400)
        
        # Check for duplicate code
        if TrainingCourse.objects.filter(code=code).exists():
            return JsonResponse({'error': 'A course with this code already exists'}, status=400)
        
        # Parse numeric fields safely
        try:
            duration_hours = float(data.get('duration_hours', 1.0)) if data.get('duration_hours') else 1.0
        except (ValueError, TypeError):
            duration_hours = 1.0
            
        try:
            max_participants = int(data.get('max_participants', 10)) if data.get('max_participants') else 10
        except (ValueError, TypeError):
            max_participants = 10
            
        try:
            valid_for_months = int(data.get('valid_for_months', 24)) if data.get('valid_for_months') else 24
        except (ValueError, TypeError):
            valid_for_months = 24
            
        try:
            pass_mark_percentage = float(data.get('pass_mark_percentage', 80.0)) if data.get('pass_mark_percentage') else 80.0
        except (ValueError, TypeError):
            pass_mark_percentage = 80.0
        
        # Create the course
        course = TrainingCourse.objects.create(
            title=title,
            code=code,
            description=data.get('description', ''),
            course_type=data.get('course_type', 'equipment'),
            delivery_method=data.get('delivery_method', 'in_person'),
            duration_hours=duration_hours,
            max_participants=max_participants,
            learning_objectives=data.get('learning_objectives', []) if isinstance(data.get('learning_objectives'), list) else [],
            course_materials=data.get('course_materials', []) if isinstance(data.get('course_materials'), list) else [],
            assessment_criteria=data.get('assessment_criteria', []) if isinstance(data.get('assessment_criteria'), list) else [],
            valid_for_months=valid_for_months,
            requires_practical_assessment=data.get('requires_practical_assessment') in ['true', 'True', True, '1', 1, 'on'] if data.get('requires_practical_assessment') is not None else False,
            pass_mark_percentage=pass_mark_percentage,
            is_active=data.get('is_active') not in ['false', 'False', False, '0', 0, 'off', None] if data.get('is_active') is not None else True,
            is_mandatory=data.get('is_mandatory') in ['true', 'True', True, '1', 1, 'on'] if data.get('is_mandatory') is not None else False,
            created_by=request.user,
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Training course "{title}" created successfully',
            'course': {
                'id': course.id,
                'title': course.title,
                'code': course.code,
                'course_type': course.get_course_type_display(),
                'delivery_method': course.get_delivery_method_display(),
                'duration_hours': float(course.duration_hours),
                'is_active': course.is_active,
                'created_date': course.created_at.strftime('%Y-%m-%d'),
            }
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["POST", "PUT"])
def edit_training_course_api(request, course_id):
    """API endpoint to edit an existing training course."""
    from booking.models import TrainingCourse
    import json
    
    try:
        course = get_object_or_404(TrainingCourse, id=course_id)
        
        # Parse JSON data
        data = json.loads(request.body)
        
        # Validate required fields
        title = data.get('title', '').strip()
        code = data.get('code', '').strip()
        
        if not title:
            return JsonResponse({'error': 'Course title is required'}, status=400)
        
        if not code:
            return JsonResponse({'error': 'Course code is required'}, status=400)
        
        # Check for duplicate code (excluding current course)
        if TrainingCourse.objects.filter(code=code).exclude(id=course_id).exists():
            return JsonResponse({'error': 'A course with this code already exists'}, status=400)
        
        # Parse numeric fields safely
        try:
            duration_hours = float(data.get('duration_hours')) if data.get('duration_hours') else course.duration_hours
        except (ValueError, TypeError):
            duration_hours = course.duration_hours
            
        try:
            max_participants = int(data.get('max_participants')) if data.get('max_participants') else course.max_participants
        except (ValueError, TypeError):
            max_participants = course.max_participants
            
        try:
            valid_for_months = int(data.get('valid_for_months')) if data.get('valid_for_months') else course.valid_for_months
        except (ValueError, TypeError):
            valid_for_months = course.valid_for_months
            
        try:
            pass_mark_percentage = float(data.get('pass_mark_percentage')) if data.get('pass_mark_percentage') else course.pass_mark_percentage
        except (ValueError, TypeError):
            pass_mark_percentage = course.pass_mark_percentage
        
        # Update the course
        course.title = title
        course.code = code
        course.description = data.get('description', course.description)
        course.course_type = data.get('course_type', course.course_type)
        course.delivery_method = data.get('delivery_method', course.delivery_method)
        course.duration_hours = duration_hours
        course.max_participants = max_participants
        course.learning_objectives = data.get('learning_objectives', course.learning_objectives) if isinstance(data.get('learning_objectives'), list) else course.learning_objectives
        course.course_materials = data.get('course_materials', course.course_materials) if isinstance(data.get('course_materials'), list) else course.course_materials
        course.assessment_criteria = data.get('assessment_criteria', course.assessment_criteria) if isinstance(data.get('assessment_criteria'), list) else course.assessment_criteria
        course.valid_for_months = valid_for_months
        course.requires_practical_assessment = data.get('requires_practical_assessment') in ['true', 'True', True, '1', 1, 'on'] if data.get('requires_practical_assessment') is not None else course.requires_practical_assessment
        course.pass_mark_percentage = pass_mark_percentage
        course.is_active = data.get('is_active') not in ['false', 'False', False, '0', 0, 'off', None] if data.get('is_active') is not None else course.is_active
        course.is_mandatory = data.get('is_mandatory') in ['true', 'True', True, '1', 1, 'on'] if data.get('is_mandatory') is not None else course.is_mandatory
        course.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Training course "{title}" updated successfully',
            'course': {
                'id': course.id,
                'title': course.title,
                'code': course.code,
                'course_type': course.get_course_type_display(),
                'delivery_method': course.get_delivery_method_display(),
                'duration_hours': float(course.duration_hours),
                'is_active': course.is_active,
                'updated_date': course.updated_at.strftime('%Y-%m-%d %H:%M'),
            }
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["DELETE"])
def delete_training_course_api(request, course_id):
    """API endpoint to delete a training course."""
    from booking.models import TrainingCourse, ResourceTrainingRequirement, UserTraining
    
    try:
        course = get_object_or_404(TrainingCourse, id=course_id)
        
        # Check if course is being used in any resource requirements
        resource_count = ResourceTrainingRequirement.objects.filter(training_course=course).count()
        if resource_count > 0:
            return JsonResponse({
                'error': f'Cannot delete this course. It is currently required by {resource_count} resource(s).'
            }, status=400)
        
        # Check if users have training records for this course
        user_training_count = UserTraining.objects.filter(training_course=course).count()
        if user_training_count > 0:
            return JsonResponse({
                'error': f'Cannot delete this course. {user_training_count} user(s) have training records for it.'
            }, status=400)
        
        course_title = course.title
        course.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Training course "{course_title}" deleted successfully'
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

