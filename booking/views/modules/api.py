# booking/views/modules/api.py
"""
API views (ViewSets) for the Aperture Booking system.

This file is part of the Aperture Booking.
Copyright (C) 2025 Aperture Booking Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperture-booking.org/commercial
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from datetime import datetime

from ...models import (
    UserProfile, Resource, Booking, ApprovalRule, Maintenance, 
    Notification, NotificationPreference, WaitingListEntry
)
from ...serializers import (
    UserProfileSerializer, ResourceSerializer, BookingSerializer, 
    ApprovalRuleSerializer, MaintenanceSerializer, WaitingListEntrySerializer
)


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
    queryset = UserProfile.objects.all()
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
    queryset = Resource.objects.filter(is_active=True)
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
        
        return queryset.order_by('-created_at')


class ApprovalRuleViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for approval rules."""
    queryset = ApprovalRule.objects.filter(is_active=True)
    serializer_class = ApprovalRuleSerializer
    permission_classes = [permissions.IsAuthenticated, IsManagerPermission]


class MaintenanceViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for maintenance records."""
    queryset = Maintenance.objects.all()
    serializer_class = MaintenanceSerializer
    permission_classes = [permissions.IsAuthenticated, IsManagerPermission]
    
    def get_queryset(self):
        """Filter maintenance records based on query parameters."""
        queryset = super().get_queryset()
        
        resource_id = self.request.query_params.get('resource')
        if resource_id:
            queryset = queryset.filter(resource_id=resource_id)
        
        maintenance_type = self.request.query_params.get('type')
        if maintenance_type:
            queryset = queryset.filter(maintenance_type=maintenance_type)
        
        return queryset.order_by('-scheduled_date')


# Notification ViewSets removed - serializers not available in current setup


class WaitingListEntryViewSet(viewsets.ModelViewSet):
    """ViewSet for waiting list entries."""
    queryset = WaitingListEntry.objects.all()
    serializer_class = WaitingListEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter waiting list entries based on user role."""
        user = self.request.user
        try:
            user_profile = user.userprofile
            if user_profile.role in ['technician', 'sysadmin']:
                # Managers can see all waiting list entries
                return WaitingListEntry.objects.all()
            else:
                # Users can only see their own entries
                return WaitingListEntry.objects.filter(user=user)
        except UserProfile.DoesNotExist:
            return WaitingListEntry.objects.filter(user=user)
    
    def perform_create(self, serializer):
        """Set the user to the current user."""
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        """Remove user from waiting list."""
        entry = self.get_object()
        if entry.user != request.user:
            return Response(
                {'error': 'Permission denied'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        entry.delete()
        return Response({'status': 'removed from waiting list'})