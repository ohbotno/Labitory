# booking/views/viewsets/approvals.py
"""
Approval-related ViewSets for the Aperture Booking system.
Extracted from main.py for better organization.
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone

from ...models import (
    ApprovalRule, RiskAssessment, UserRiskAssessment, 
    TrainingCourse, ResourceTrainingRequirement, UserTraining,
    AccessRequest
)
from booking.serializers import (
    RiskAssessmentSerializer, UserRiskAssessmentSerializer,
    TrainingCourseSerializer, ResourceTrainingRequirementSerializer, UserTrainingSerializer,
    AccessRequestDetailSerializer
)


class ApprovalRuleViewSet(viewsets.ReadOnlyModelViewSet):
    """API viewset for approval rules."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return ApprovalRule.objects.filter(is_active=True)
    
    def get_serializer_class(self):
        from rest_framework import serializers
        
        class ApprovalRuleSerializer(serializers.ModelSerializer):
            class Meta:
                model = ApprovalRule
                fields = ['id', 'rule_type', 'condition', 'description', 'priority']
                read_only_fields = fields
        
        return ApprovalRuleSerializer




class RiskAssessmentViewSet(viewsets.ModelViewSet):
    """API viewset for risk assessments."""
    serializer_class = RiskAssessmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get risk assessments based on user permissions."""
        if hasattr(self.request.user, 'userprofile') and self.request.user.userprofile.role in ['technician', 'sysadmin']:
            return RiskAssessment.objects.all().select_related('resource', 'created_by')
        else:
            return RiskAssessment.objects.filter(is_active=True).select_related('resource', 'created_by')
    
    def perform_create(self, serializer):
        """Create risk assessment."""
        serializer.save(created_by=self.request.user)


class UserRiskAssessmentViewSet(viewsets.ModelViewSet):
    """API viewset for user risk assessments."""
    serializer_class = UserRiskAssessmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get user risk assessments based on permissions."""
        if hasattr(self.request.user, 'userprofile') and self.request.user.userprofile.role in ['technician', 'sysadmin']:
            return UserRiskAssessment.objects.all().select_related('user', 'risk_assessment')
        else:
            return UserRiskAssessment.objects.filter(user=self.request.user).select_related('risk_assessment')
    
    def perform_create(self, serializer):
        """Create user risk assessment."""
        serializer.save(user=self.request.user)


class TrainingCourseViewSet(viewsets.ModelViewSet):
    """API viewset for training courses."""
    serializer_class = TrainingCourseSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get training courses based on user permissions."""
        if hasattr(self.request.user, 'userprofile') and self.request.user.userprofile.role in ['technician', 'sysadmin']:
            return TrainingCourse.objects.all()
        else:
            return TrainingCourse.objects.filter(is_active=True)


class ResourceTrainingRequirementViewSet(viewsets.ModelViewSet):
    """API viewset for resource training requirements."""
    serializer_class = ResourceTrainingRequirementSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get resource training requirements."""
        return ResourceTrainingRequirement.objects.all().select_related('resource', 'training_course')


class UserTrainingViewSet(viewsets.ModelViewSet):
    """API viewset for user training records."""
    serializer_class = UserTrainingSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get user training records based on permissions."""
        if hasattr(self.request.user, 'userprofile') and self.request.user.userprofile.role in ['technician', 'sysadmin']:
            return UserTraining.objects.all().select_related('user', 'training_course')
        else:
            return UserTraining.objects.filter(user=self.request.user).select_related('training_course')
    
    def perform_create(self, serializer):
        """Create user training record."""
        if 'user' not in serializer.validated_data:
            serializer.save(user=self.request.user)
        else:
            serializer.save()


class AccessRequestViewSet(viewsets.ModelViewSet):
    """API viewset for access requests."""
    serializer_class = AccessRequestDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get access requests based on user permissions."""
        if hasattr(self.request.user, 'userprofile') and self.request.user.userprofile.role in ['technician', 'sysadmin']:
            return AccessRequest.objects.all().select_related('user', 'resource', 'reviewed_by')
        else:
            return AccessRequest.objects.filter(user=self.request.user).select_related('resource', 'reviewed_by')
    
    def perform_create(self, serializer):
        """Create access request."""
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve an access request."""
        access_request = self.get_object()
        
        if not (hasattr(request.user, 'userprofile') and request.user.userprofile.role in ['technician', 'sysadmin']):
            return Response({'error': 'Permission denied'}, status=403)
        
        if access_request.status != 'pending':
            return Response({'error': 'Request is not pending'}, status=400)
        
        access_request.status = 'approved'
        access_request.reviewed_by = request.user
        access_request.reviewed_at = timezone.now()
        access_request.save()
        
        return Response({'status': 'approved'})
    
    @action(detail=True, methods=['post'])
    def deny(self, request, pk=None):
        """Deny an access request."""
        access_request = self.get_object()
        
        if not (hasattr(request.user, 'userprofile') and request.user.userprofile.role in ['technician', 'sysadmin']):
            return Response({'error': 'Permission denied'}, status=403)
        
        if access_request.status != 'pending':
            return Response({'error': 'Request is not pending'}, status=400)
        
        access_request.status = 'denied'
        access_request.reviewed_by = request.user
        access_request.reviewed_at = timezone.now()
        access_request.save()
        
        return Response({'status': 'denied'})