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
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from datetime import datetime
import json
import os
import mimetypes

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


class CanViewResourceCalendar(permissions.BasePermission):
    """Custom permission to allow users to view calendar events for resources they have access to."""
    
    def has_permission(self, request, view):
        # Must be authenticated
        if not request.user.is_authenticated:
            return False
        
        # For calendar views, check if user has access to the specified resource
        if view.action == 'calendar':
            resource_id = request.query_params.get('resource')
            if resource_id:
                try:
                    from ...models import Resource
                    resource = Resource.objects.get(id=resource_id)
                    # User can view calendar if they can view the resource calendar
                    return resource.can_user_view_calendar(request.user)
                except (Resource.DoesNotExist, ValueError):
                    return False
        
        # For other actions, use default permission logic
        return True
    
    def has_object_permission(self, request, view, obj):
        # For individual booking objects, use standard read permissions
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


class IsManagerOrReadOnly(permissions.BasePermission):
    """Permission that allows managers to edit, others to read only."""
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        
        # Write permissions for managers only
        try:
            user_profile = request.user.userprofile
            return user_profile.role in ['technician', 'sysadmin']
        except AttributeError:
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
    filterset_fields = ['resource_type', 'requires_induction']
    
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


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def validate_file_api(request):
    """Validate uploaded files for security and requirements."""
    if 'file' not in request.FILES:
        return JsonResponse({
            'valid': False,
            'error': 'No file provided'
        }, status=400)

    uploaded_file = request.FILES['file']
    field_type = request.POST.get('field_type', 'file')

    # Basic validation
    validation_result = {
        'valid': True,
        'error': None,
        'warnings': []
    }

    # Check file size (5MB limit by default)
    max_size = 5 * 1024 * 1024  # 5MB
    if uploaded_file.size > max_size:
        validation_result['valid'] = False
        validation_result['error'] = f'File size exceeds {max_size / (1024*1024):.1f}MB limit'
        return JsonResponse(validation_result, status=400)

    # Check if file is empty
    if uploaded_file.size == 0:
        validation_result['valid'] = False
        validation_result['error'] = 'File is empty'
        return JsonResponse(validation_result, status=400)

    # Check file extension
    file_ext = os.path.splitext(uploaded_file.name)[1].lower()

    # Dangerous extensions that should never be allowed
    dangerous_extensions = [
        '.exe', '.bat', '.cmd', '.scr', '.com', '.pif', '.vbs', '.js', '.jar',
        '.app', '.deb', '.pkg', '.dmg', '.run', '.msi', '.dll', '.so', '.sh',
        '.ps1', '.psm1', '.reg', '.scf', '.lnk', '.inf', '.msc'
    ]

    if file_ext in dangerous_extensions:
        validation_result['valid'] = False
        validation_result['error'] = f'File type {file_ext} is not allowed for security reasons'
        return JsonResponse(validation_result, status=400)

    # Check MIME type
    mime_type, _ = mimetypes.guess_type(uploaded_file.name)

    if field_type == 'image' or field_type == 'file':
        # For image fields, only allow image types
        allowed_image_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml']
        allowed_image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']

        if field_type == 'image':
            if mime_type not in allowed_image_types:
                validation_result['valid'] = False
                validation_result['error'] = 'Only image files are allowed (JPEG, PNG, GIF, WebP, SVG)'
                return JsonResponse(validation_result, status=400)

            if file_ext not in allowed_image_extensions:
                validation_result['valid'] = False
                validation_result['error'] = f'Invalid image extension: {file_ext}'
                return JsonResponse(validation_result, status=400)

    # Check filename for path traversal attempts
    if '..' in uploaded_file.name or '/' in uploaded_file.name or '\\' in uploaded_file.name:
        validation_result['valid'] = False
        validation_result['error'] = 'Invalid filename'
        return JsonResponse(validation_result, status=400)

    # Check for double extensions
    name_parts = uploaded_file.name.split('.')
    if len(name_parts) > 2:
        # Warn about double extensions but don't block
        validation_result['warnings'].append('Filename contains multiple extensions')

    # Additional checks for images (optional - only if PIL is available)
    if field_type == 'image' and mime_type and mime_type.startswith('image/'):
        try:
            from PIL import Image
            from io import BytesIO

            # Try to open and verify the image
            img_data = uploaded_file.read()
            uploaded_file.seek(0)  # Reset file pointer

            img = Image.open(BytesIO(img_data))
            img.verify()  # Verify it's a valid image

            # Check image dimensions
            img = Image.open(BytesIO(img_data))  # Need to reopen after verify
            width, height = img.size

            # Warn if image is too large
            if width > 4000 or height > 4000:
                validation_result['warnings'].append(f'Image dimensions are very large ({width}x{height})')

            # Add image info to response
            validation_result['image_info'] = {
                'width': width,
                'height': height,
                'format': img.format,
                'mode': img.mode
            }

        except ImportError:
            # PIL not installed - skip advanced image validation
            validation_result['warnings'].append('Advanced image validation unavailable')
        except Exception as e:
            validation_result['valid'] = False
            validation_result['error'] = 'Invalid or corrupted image file'
            return JsonResponse(validation_result, status=400)

    return JsonResponse(validation_result)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_theme_preference_api(request):
    """Get the current user's theme preference."""
    try:
        profile = request.user.userprofile
        theme = getattr(profile, 'theme_preference', 'system')
        return JsonResponse({
            'theme': theme,
            'success': True
        })
    except UserProfile.DoesNotExist:
        # Return default theme if profile doesn't exist
        return JsonResponse({
            'theme': 'system',
            'success': True
        })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def update_theme_preference_api(request):
    """Update the current user's theme preference."""
    theme = request.data.get('theme')
    if theme not in ['light', 'dark', 'system']:
        return JsonResponse({
            'error': 'Invalid theme. Must be light, dark, or system.',
            'success': False
        }, status=400)

    try:
        profile = request.user.userprofile
        profile.theme_preference = theme
        profile.save()

        return JsonResponse({
            'success': True,
            'theme': theme,
            'message': 'Theme preference updated successfully.'
        })
    except UserProfile.DoesNotExist:
        # Create profile if it doesn't exist
        profile = UserProfile.objects.create(
            user=request.user,
            theme_preference=theme
        )
        return JsonResponse({
            'success': True,
            'theme': theme,
            'message': 'Theme preference updated successfully.'
        })