# booking/api/viewsets.py
"""
Enhanced API ViewSets with security features like rate limiting.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone

from ..models import (
    UserProfile, Resource, Booking, ApprovalRule, Maintenance, 
    WaitingListEntry, SecurityEvent
)
from ..serializers import (
    UserProfileSerializer, ResourceSerializer, BookingSerializer, 
    ApprovalRuleSerializer, MaintenanceSerializer, WaitingListEntrySerializer
)
from ..utils.security_utils import APIRateLimitMixin
from ..views.modules.api import (
    IsOwnerOrManagerPermission, IsManagerPermission, IsManagerOrReadOnly, CanViewResourceCalendar
)


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def log_security_event(user, event_type, description, request, metadata=None):
    """Helper to log security events."""
    SecurityEvent.objects.create(
        user=user,
        event_type=event_type,
        description=description,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        metadata=metadata or {}
    )


class UserProfileViewSet(APIRateLimitMixin, viewsets.ReadOnlyModelViewSet):
    """ViewSet for user profiles with rate limiting."""
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    # Rate limiting configuration
    api_ratelimit_group = 'user_profiles'
    api_ratelimit_rate = '50/1h'  # 50 requests per hour
    
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
            
            log_security_event(
                request.user, 'permission_denied', 
                f'Theme preference updated to {theme}',
                request, {'theme': theme}
            )
            
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


class ResourceViewSet(APIRateLimitMixin, viewsets.ModelViewSet):
    """ViewSet for resources with rate limiting."""
    queryset = Resource.objects.filter(is_active=True)
    serializer_class = ResourceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['resource_type', 'requires_induction', 'required_training_level']
    
    # Rate limiting configuration
    api_ratelimit_group = 'resources'
    api_ratelimit_rate = '100/1h'  # 100 requests per hour
    
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


class BookingViewSet(APIRateLimitMixin, viewsets.ModelViewSet):
    """ViewSet for bookings with rate limiting and security."""
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrManagerPermission]
    
    # Rate limiting configuration - more restrictive for bookings
    api_ratelimit_group = 'bookings'
    api_ratelimit_rate = '30/1h'  # 30 requests per hour
    
    def get_queryset(self):
        """Filter bookings based on user role and query parameters."""
        user = self.request.user
        queryset = Booking.objects.select_related('resource', 'user', 'approved_by')
        
        try:
            user_profile = user.userprofile
            if user_profile.role in ['technician', 'sysadmin']:
                # Admins can see all bookings
                return queryset.all()
            else:
                # Regular users can only see their own bookings
                return queryset.filter(user=user)
        except UserProfile.DoesNotExist:
            return queryset.filter(user=user)
    
    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated, CanViewResourceCalendar])
    def calendar(self, request):
        """Get bookings in calendar event format."""
        # For calendar view, show all bookings for the specified resource
        # (if user has calendar access, verified by permission class)
        resource_filter = request.query_params.get('resource')
        
        if resource_filter:
            try:
                resource_id = int(resource_filter)
                # Get all bookings for this resource (not just user's own bookings)
                queryset = Booking.objects.filter(
                    resource_id=resource_id
                ).select_related('resource', 'user', 'approved_by')
            except ValueError:
                return Response({'error': 'Invalid resource ID'}, status=400)
        else:
            # If no resource specified, fall back to user's own bookings
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
            
            # Show booking title or user name based on user's relationship to booking
            user_is_owner = booking.user == request.user
            if user_is_owner:
                title = booking.title or f"My Booking"
            else:
                # Show generic info for other users' bookings for privacy
                title = f"Booked by {booking.user.first_name or booking.user.username}"
            
            events.append({
                'id': booking.id,
                'title': title,
                'start': booking.start_time.isoformat(),
                'end': booking.end_time.isoformat(),
                'backgroundColor': color,
                'borderColor': color,
                'url': f'/booking/{booking.id}/' if user_is_owner else '#',
                'extendedProps': {
                    'resource': booking.resource.name,
                    'user': booking.user.get_full_name() or booking.user.username,
                    'status': booking.status,
                    'type': 'booking',
                    'is_owner': user_is_owner
                }
            })
        
        return Response(events)

    def create(self, request, *args, **kwargs):
        """Create booking with security logging."""
        response = super().create(request, *args, **kwargs)
        
        if response.status_code == 201:
            log_security_event(
                request.user, 'booking_created',
                f'Booking created via API',
                request, {'booking_id': response.data.get('id')}
            )
        
        return response
    
    def destroy(self, request, *args, **kwargs):
        """Delete booking with security logging."""
        booking = self.get_object()
        log_security_event(
            request.user, 'booking_deleted',
            f'Booking {booking.id} deleted via API',
            request, {'booking_id': booking.id}
        )
        
        return super().destroy(request, *args, **kwargs)


class ApprovalRuleViewSet(APIRateLimitMixin, viewsets.ModelViewSet):
    """ViewSet for approval rules with rate limiting."""
    queryset = ApprovalRule.objects.all()
    serializer_class = ApprovalRuleSerializer
    permission_classes = [permissions.IsAuthenticated, IsManagerOrReadOnly]
    
    # Rate limiting configuration
    api_ratelimit_group = 'approval_rules'
    api_ratelimit_rate = '20/1h'  # 20 requests per hour


class MaintenanceViewSet(APIRateLimitMixin, viewsets.ModelViewSet):
    """ViewSet for maintenance records with rate limiting."""
    queryset = Maintenance.objects.all()
    serializer_class = MaintenanceSerializer
    permission_classes = [permissions.IsAuthenticated, IsManagerOrReadOnly]
    
    # Rate limiting configuration
    api_ratelimit_group = 'maintenance'
    api_ratelimit_rate = '40/1h'  # 40 requests per hour
    
    def get_queryset(self):
        """Filter maintenance records based on user permissions."""
        user = self.request.user
        queryset = super().get_queryset()
        
        try:
            user_profile = user.userprofile
            if user_profile.role in ['technician', 'sysadmin']:
                return queryset.all()
            else:
                # Regular users can only see maintenance for resources they have access to
                user_resources = Resource.objects.filter(
                    resourceaccess__user_profile=user_profile
                )
                return queryset.filter(resource__in=user_resources)
        except UserProfile.DoesNotExist:
            return queryset.none()
    
    @action(detail=False, methods=['get'])
    def calendar(self, request):
        """Get maintenance events in calendar format."""
        queryset = self.get_queryset()
        
        # Apply any filtering from query parameters
        resource_filter = request.query_params.get('resource')
        if resource_filter:
            queryset = queryset.filter(resource_id=resource_filter)
        
        # Convert to FullCalendar event format
        events = []
        for maintenance in queryset:
            color = '#dc3545' if maintenance.is_emergency else '#fd7e14'  # Red for emergency, orange for regular
            
            events.append({
                'id': f'maintenance-{maintenance.id}',
                'title': f'Maintenance: {maintenance.resource.name}',
                'start': maintenance.scheduled_date.isoformat(),
                'end': (maintenance.scheduled_date + maintenance.estimated_duration).isoformat() if maintenance.estimated_duration else maintenance.scheduled_date.isoformat(),
                'backgroundColor': color,
                'borderColor': color,
                'extendedProps': {
                    'resource': maintenance.resource.name,
                    'type': 'maintenance',
                    'is_emergency': maintenance.is_emergency,
                    'blocks_booking': True,
                    'description': maintenance.description
                }
            })
        
        return Response(events)


class WaitingListEntryViewSet(APIRateLimitMixin, viewsets.ModelViewSet):
    """ViewSet for waiting list entries with rate limiting."""
    queryset = WaitingListEntry.objects.all()
    serializer_class = WaitingListEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    # Rate limiting configuration
    api_ratelimit_group = 'waiting_list'
    api_ratelimit_rate = '25/1h'  # 25 requests per hour
    
    def get_queryset(self):
        """Filter waiting list entries based on user role."""
        user = self.request.user
        queryset = super().get_queryset()
        
        try:
            user_profile = user.userprofile
            if user_profile.role in ['technician', 'sysadmin']:
                return queryset.all()
            else:
                # Regular users can only see their own waiting list entries
                return queryset.filter(user_profile=user_profile)
        except UserProfile.DoesNotExist:
            return queryset.filter(user_profile__user=user)
    
    def create(self, request, *args, **kwargs):
        """Create waiting list entry with security logging."""
        response = super().create(request, *args, **kwargs)
        
        if response.status_code == 201:
            log_security_event(
                request.user, 'waiting_list_entry_created',
                f'Waiting list entry created via API',
                request, {'entry_id': response.data.get('id')}
            )
        
        return response