# booking/views/viewsets/notifications.py
"""
Notification-related ViewSets for the Aperture Booking system.
Extracted from main.py for better organization.
"""

from rest_framework import viewsets, permissions

from rest_framework import serializers
from ...models import Notification, NotificationPreference, WaitingListEntry
from ...serializers import WaitingListEntrySerializer


# Create basic serializers for notifications (since they don't exist in main serializers.py)
class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = '__all__'


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """API viewset for user notifications."""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Notification.objects.filter(
            user=self.request.user
        ).order_by('-created_at')


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """API viewset for notification preferences."""
    serializer_class = NotificationPreferenceSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return NotificationPreference.objects.filter(user=self.request.user)


class WaitingListEntryViewSet(viewsets.ModelViewSet):
    """API viewset for waiting list entries."""
    serializer_class = WaitingListEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return WaitingListEntry.objects.filter(user=self.request.user).select_related('resource')