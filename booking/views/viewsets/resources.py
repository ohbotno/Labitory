# booking/views/viewsets/resources.py
"""
Resource-related ViewSets for the Aperture Booking system.
Extracted from main.py for better organization.
"""

from rest_framework import viewsets, permissions

from ...models import Resource, ResourceResponsible
from ...serializers import ResourceSerializer, ResourceResponsibleSerializer
from ..modules.api import IsManagerOrReadOnly


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
            return [IsManagerOrReadOnly()]
        return super().get_permissions()


class ResourceResponsibleViewSet(viewsets.ModelViewSet):
    """ViewSet for resource responsible persons."""
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
        
        return queryset