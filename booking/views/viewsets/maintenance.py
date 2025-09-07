# booking/views/viewsets/maintenance.py
"""
Maintenance-related ViewSets for the Aperture Booking system.
Extracted from main.py for better organization.
"""

from rest_framework import viewsets, permissions
from django.utils import timezone

from ...models import Maintenance


class MaintenanceViewSet(viewsets.ReadOnlyModelViewSet):
    """API viewset for maintenance records."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get maintenance records based on user permissions."""
        if hasattr(self.request.user, 'userprofile') and self.request.user.userprofile.role in ['technician', 'sysadmin']:
            return Maintenance.objects.all().select_related('resource', 'performed_by')
        else:
            # Regular users can only see current maintenance that affects them
            return Maintenance.objects.filter(
                start_time__lte=timezone.now(),
                end_time__gte=timezone.now(),
                is_emergency=False
            ).select_related('resource')
    
    def get_serializer_class(self):
        from rest_framework import serializers
        
        class MaintenanceSerializer(serializers.ModelSerializer):
            resource_name = serializers.CharField(source='resource.name', read_only=True)
            performed_by_name = serializers.CharField(source='performed_by.get_full_name', read_only=True)
            
            class Meta:
                model = Maintenance
                fields = [
                    'id', 'resource', 'resource_name', 'title', 'description', 
                    'start_time', 'end_time', 'is_emergency', 'status',
                    'performed_by', 'performed_by_name', 'created_at'
                ]
                read_only_fields = fields
        
        return MaintenanceSerializer