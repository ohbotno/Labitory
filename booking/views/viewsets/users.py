# booking/views/viewsets/users.py
"""
User-related ViewSets for the Aperture Booking system.
Extracted from main.py for better organization.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q

from ...models import UserProfile
from ...serializers import UserProfileSerializer


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