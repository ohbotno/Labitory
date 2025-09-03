"""
Resource-related models for the Labitory.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal


class Resource(models.Model):
    """Bookable resources (robots, instruments, rooms, etc.)."""
    RESOURCE_TYPES = [
        ('robot', 'Robot'),
        ('instrument', 'Instrument'),
        ('room', 'Room'),
        ('safety_cabinet', 'Safety Cabinet'),
        ('equipment', 'Generic Equipment'),
    ]
    
    name = models.CharField(max_length=200)
    resource_type = models.CharField(max_length=20, choices=RESOURCE_TYPES)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200)
    capacity = models.PositiveIntegerField(default=1)
    required_training_level = models.PositiveIntegerField(default=1)
    requires_induction = models.BooleanField(default=False)
    requires_risk_assessment = models.BooleanField(
        default=False,
        help_text="Require users to complete a risk assessment before accessing this resource"
    )
    max_booking_hours = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_closed = models.BooleanField(
        default=False,
        help_text="Temporarily close this resource to prevent new bookings"
    )
    closed_reason = models.TextField(
        blank=True,
        help_text="Reason for closing the resource (optional)"
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='closed_resources',
        help_text="User who closed the resource"
    )
    image = models.ImageField(upload_to='resources/', blank=True, null=True, help_text="Resource image")
    
    # Sign-off checklist configuration
    requires_checkout_checklist = models.BooleanField(
        default=False,
        help_text="Require users to complete a checklist before checking out"
    )
    checkout_checklist_title = models.CharField(
        max_length=200,
        blank=True,
        default="Pre-Checkout Safety Checklist",
        help_text="Title displayed on the checkout checklist"
    )
    checkout_checklist_description = models.TextField(
        blank=True,
        help_text="Instructions or description shown above the checklist"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_resource'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_resource_type_display()})"

    def is_available_for_user(self, user_profile):
        """Check if resource is available for a specific user."""
        # System administrators bypass all restrictions
        if user_profile.role == 'sysadmin':
            return self.is_active
            
        if not self.is_active:
            return False
        if self.requires_induction and not user_profile.is_inducted:
            return False
        if user_profile.training_level < self.required_training_level:
            return False
        return True
    
    def user_has_access(self, user):
        """Check if user has explicit access to this resource."""
        from django.db.models import Q
        
        # System administrators always have full access
        try:
            if hasattr(user, 'userprofile') and user.userprofile.role == 'sysadmin':
                return True
        except:
            pass
        
        return ResourceAccess.objects.filter(
            resource=self,
            user=user,
            is_active=True
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        ).exists()
    
    def can_user_view_calendar(self, user):
        """Check if user can view the resource calendar."""
        if self.user_has_access(user):
            return True
        
        try:
            return user.userprofile.role in ['technician', 'sysadmin']
        except:
            return False
    
    def get_approval_progress(self, user):
        """Get approval progress information for a user."""
        progress = {
            'has_access': self.user_has_access(user),
            'stages': []
        }
        
        try:
            user_profile = user.userprofile
        except:
            return progress
        
        # System administrators have automatic access to all resources
        if user_profile.role == 'sysadmin':
            progress['has_access'] = True
            progress['stages'] = [{
                'name': 'System Administrator Access',
                'key': 'sysadmin',
                'required': True,
                'completed': True,
                'status': 'completed',
                'icon': 'bi-shield-check',
                'description': 'Full access granted as System Administrator'
            }]
            progress['overall'] = {
                'total_stages': 1,
                'completed_stages': 1,
                'percentage': 100,
                'all_completed': True
            }
            progress['next_step'] = None
            return progress
        
        # Stage 1: Lab Induction (one-time user requirement)
        induction_stage = {
            'name': 'Lab Induction',
            'key': 'induction',
            'required': True,  # Always required for lab access
            'completed': user_profile.is_inducted,
            'status': 'completed' if user_profile.is_inducted else 'pending',
            'icon': 'bi-shield-check',
            'description': 'One-time general laboratory safety induction'
        }
        progress['stages'].append(induction_stage)
        
        # Stage 2: Equipment-Specific Training Requirements
        required_training = ResourceTrainingRequirement.objects.filter(resource=self)
        training_completed = []
        training_pending = []
        training_records = []  # Store actual UserTraining record info
        
        for req in required_training:
            user_training = UserTraining.objects.filter(
                user=user,
                training_course=req.training_course,
                status='completed'
            ).first()
            
            if user_training and user_training.is_valid:
                training_completed.append(req.training_course.title)
                training_records.append({
                    'course_title': req.training_course.title,
                    'status': 'completed',
                    'completed_at': user_training.completed_at,
                    'expires_at': user_training.expires_at,
                    'training_id': user_training.id
                })
            else:
                # Check if there's any training record at all
                any_training = UserTraining.objects.filter(
                    user=user,
                    training_course=req.training_course
                ).first()
                
                training_pending.append(req.training_course.title)
                training_records.append({
                    'course_title': req.training_course.title,
                    'status': any_training.status if any_training else 'not_enrolled',
                    'training_id': any_training.id if any_training else None,
                    'enrolled_at': any_training.enrolled_at if any_training else None
                })
        
        # Check if training is required either through specific courses or training level
        has_specific_requirements = len(required_training) > 0
        requires_training_level = self.required_training_level > user_profile.training_level
        
        if not has_specific_requirements and not requires_training_level:
            # No training requirements at all
            training_description = 'Equipment-specific training: Not required for this resource'
            training_status = 'not_required'
            training_completed_flag = True
            training_required = False
        elif not has_specific_requirements and requires_training_level:
            # Training level requirement but no specific courses configured yet
            training_description = f'Equipment-specific training: Level {self.required_training_level} required (current level: {user_profile.training_level})'
            training_status = 'pending'
            training_completed_flag = False
            training_required = True
        elif has_specific_requirements:
            # Specific training courses configured
            training_description = f'Equipment-specific training: {len(training_completed)} of {len(required_training)} courses completed'
            training_status = 'completed' if len(training_pending) == 0 else 'pending'
            training_completed_flag = len(training_pending) == 0
            training_required = True
        
        training_stage = {
            'name': 'Equipment Training',
            'key': 'training',
            'required': training_required,
            'completed': training_completed_flag,
            'status': training_status,
            'icon': 'bi-mortarboard',
            'description': training_description,
            'details': {
                'completed': training_completed,
                'pending': training_pending,
                'total_required': len(required_training),
                'training_records': training_records,  # Include actual training record details
                'required_level': self.required_training_level,
                'user_level': user_profile.training_level
            }
        }
        progress['stages'].append(training_stage)
        
        # Stage 3: Risk Assessment
        risk_assessment_required = self.requires_risk_assessment
        
        # If risk assessment is required, check for any required assessments for this resource
        required_assessments = RiskAssessment.objects.filter(resource=self, is_mandatory=True) if risk_assessment_required else RiskAssessment.objects.none()
        assessment_completed = []
        assessment_pending = []
        
        if risk_assessment_required:
            for assessment in required_assessments:
                user_assessment = UserRiskAssessment.objects.filter(
                    user=user,
                    risk_assessment=assessment,
                    status='approved'
                ).first()
                
                if user_assessment:
                    assessment_completed.append(assessment.title)
                else:
                    assessment_pending.append(assessment.title)
        
        # If risk assessment required but no assessments exist yet, show as pending
        if risk_assessment_required and not required_assessments.exists():
            risk_completed = False
            risk_status = 'pending'
            description = 'Risk assessment required - no assessments configured yet'
        elif risk_assessment_required:
            risk_completed = len(assessment_pending) == 0 and len(required_assessments) > 0
            risk_status = 'completed' if risk_completed else 'pending'
            description = f'{len(assessment_completed)} of {len(required_assessments)} risk assessments completed'
        else:
            risk_completed = True  # Not required means completed
            risk_status = 'not_required'
            description = 'Risk assessment not required for this resource'
        
        risk_stage = {
            'name': 'Risk Assessment',
            'key': 'risk_assessment',
            'required': risk_assessment_required,
            'completed': risk_completed,
            'status': risk_status,
            'icon': 'bi-shield-exclamation',
            'description': description,
            'details': {
                'completed': assessment_completed,
                'pending': assessment_pending,
                'total_required': len(required_assessments),
                'resource_requires': risk_assessment_required
            }
        }
        progress['stages'].append(risk_stage)
        
        # Stage 4: Administrative Approval
        pending_request = AccessRequest.objects.filter(
            resource=self,
            user=user,
            status='pending'
        ).first()
        
        approved_request = AccessRequest.objects.filter(
            resource=self,
            user=user,
            status='approved'
        ).first()
        
        admin_stage = {
            'name': 'Administrative Approval',
            'key': 'admin_approval',
            'required': True,
            'completed': progress['has_access'],
            'status': 'completed' if progress['has_access'] else ('pending' if pending_request else 'not_started'),
            'icon': 'bi-person-check',
            'description': 'Final approval by lab administrator',
            'details': {
                'has_pending_request': bool(pending_request),
                'request_date': pending_request.created_at if pending_request else None,
                'approved_date': approved_request.reviewed_at if approved_request else None
            }
        }
        progress['stages'].append(admin_stage)
        
        # Calculate overall progress
        required_stages = [s for s in progress['stages'] if s['required']]
        completed_stages = [s for s in required_stages if s['completed']]
        
        progress['overall'] = {
            'total_stages': len(required_stages),
            'completed_stages': len(completed_stages),
            'percentage': int((len(completed_stages) / len(required_stages)) * 100) if required_stages else 100,
            'all_completed': len(completed_stages) == len(required_stages) and len(required_stages) > 0
        }
        
        # Find the next pending stage for guidance
        next_pending_stage = None
        for stage in progress['stages']:
            if stage['required'] and not stage['completed']:
                next_pending_stage = stage
                break
        
        progress['next_step'] = next_pending_stage
        
        return progress
    
    @property
    def requires_risk_assessment_safe(self):
        """Safely access requires_risk_assessment field."""
        return self.requires_risk_assessment
    
    @property
    def active_checklist_items_count(self):
        """Get count of active checklist items assigned to this resource."""
        return self.checklist_items.filter(is_active=True).count()
    
    def is_available_for_booking(self):
        """Check if resource is available for new bookings."""
        return self.is_active and not self.is_closed
    
    def close_resource(self, user, reason=None):
        """Close the resource to prevent new bookings."""
        self.is_closed = True
        self.closed_reason = reason or ""
        self.closed_at = timezone.now()
        self.closed_by = user
        self.save()
    
    def open_resource(self):
        """Reopen the resource for bookings."""
        self.is_closed = False
        self.closed_reason = ""
        self.closed_at = None
        self.closed_by = None
        self.save()


class ResourceAccess(models.Model):
    """User access permissions to specific resources."""
    ACCESS_TYPES = [
        ('view', 'View Only'),
        ('book', 'View and Book'),
        ('manage', 'Full Management'),
    ]
    
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='access_permissions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='resource_access')
    access_type = models.CharField(max_length=10, choices=ACCESS_TYPES, default='book')
    granted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='granted_access')
    granted_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Optional expiration date")
    
    class Meta:
        db_table = 'booking_resourceaccess'
        unique_together = ['resource', 'user']
        ordering = ['-granted_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.resource.name} ({self.get_access_type_display()})"
    
    @property
    def is_expired(self):
        """Check if access has expired."""
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at
    
    @property
    def is_valid(self):
        """Check if access is currently valid."""
        return self.is_active and not self.is_expired


class ResourceResponsible(models.Model):
    """Defines who is responsible for approving access to specific resources."""
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='responsible_persons')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='responsible_resources')
    role_type = models.CharField(max_length=50, choices=[
        ('primary', 'Primary Responsible'),
        ('secondary', 'Secondary Responsible'),
        ('trainer', 'Authorized Trainer'),
        ('safety_officer', 'Safety Officer'),
    ], default='primary')
    can_approve_access = models.BooleanField(default=True)
    can_approve_training = models.BooleanField(default=True)
    can_conduct_assessments = models.BooleanField(default=True)
    assigned_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assigned_responsibilities')
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'booking_resourceresponsible'
        unique_together = ['resource', 'user', 'role_type']
        ordering = ['role_type', 'assigned_at']
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.resource.name} ({self.get_role_type_display()})"
    
    def can_approve_request(self, request_type='access'):
        """Check if this person can approve a specific request type."""
        # Check if this person can directly approve
        if request_type == 'access' and self.can_approve_access and self.is_active:
            return True
        elif request_type == 'training' and self.can_approve_training and self.is_active:
            return True
        elif request_type == 'assessment' and self.can_conduct_assessments and self.is_active:
            return True
        
        return False
    
    def get_current_approvers(self, request_type='access'):
        """Get list of users who can currently approve."""
        approvers = []
        
        # Add this person if they can approve
        if self.can_approve_request(request_type):
            approvers.append({
                'user': self.user,
                'type': 'primary',
                'responsible': self
            })
        
        return approvers


class ResourceTrainingRequirement(models.Model):
    """Defines training requirements for specific resources."""
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='training_requirements')
    training_course = models.ForeignKey('TrainingCourse', on_delete=models.CASCADE, related_name='resource_requirements')
    is_mandatory = models.BooleanField(default=True, help_text="Must be completed before access")
    required_for_access_types = models.JSONField(default=list, help_text="Access types that require this training")
    order = models.PositiveIntegerField(default=1, help_text="Order in which training should be completed")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'booking_resourcetrainingrequirement'
        unique_together = ['resource', 'training_course']
        ordering = ['order', 'training_course__title']
    
    def __str__(self):
        return f"{self.resource.name} requires {self.training_course.title}"



class ResourceIssue(models.Model):
    """Model for tracking issues reported by users for resources."""
    
    SEVERITY_CHOICES = [
        ('low', 'Low - Minor issue, resource still usable'),
        ('medium', 'Medium - Issue affects functionality'),
        ('high', 'High - Resource partially unusable'),
        ('critical', 'Critical - Resource completely unusable'),
    ]
    
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('waiting_parts', 'Waiting for Parts'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
        ('duplicate', 'Duplicate'),
    ]
    
    CATEGORY_CHOICES = [
        ('mechanical', 'Mechanical Issue'),
        ('electrical', 'Electrical Issue'),
        ('software', 'Software Issue'),
        ('safety', 'Safety Concern'),
        ('calibration', 'Calibration Required'),
        ('maintenance', 'Maintenance Required'),
        ('damage', 'Physical Damage'),
        ('other', 'Other'),
    ]
    
    resource = models.ForeignKey(
        Resource, 
        on_delete=models.CASCADE, 
        related_name='issues'
    )
    reported_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='reported_issues'
    )
    title = models.CharField(
        max_length=200, 
        help_text="Brief description of the issue"
    )
    description = models.TextField(
        help_text="Detailed description of the issue, including steps to reproduce if applicable"
    )
    severity = models.CharField(
        max_length=20, 
        choices=SEVERITY_CHOICES, 
        default='medium'
    )
    category = models.CharField(
        max_length=20, 
        choices=CATEGORY_CHOICES, 
        default='other'
    )
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='open'
    )
    
    # Related booking if issue occurred during a specific booking
    related_booking = models.ForeignKey(
        'Booking',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reported_issues',
        help_text="Booking during which this issue was discovered"
    )
    
    # Image upload for visual evidence
    image = models.ImageField(
        upload_to='issue_reports/',
        blank=True,
        null=True,
        help_text="Photo of the issue (optional)"
    )
    
    # Location details
    specific_location = models.CharField(
        max_length=200,
        blank=True,
        help_text="Specific part or area of the resource affected"
    )
    
    # Admin fields
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_issues',
        limit_choices_to={'userprofile__role__in': ['technician', 'sysadmin']},
        help_text="Technician assigned to resolve this issue"
    )
    
    admin_notes = models.TextField(
        blank=True,
        help_text="Internal notes for tracking resolution progress"
    )
    
    resolution_description = models.TextField(
        blank=True,
        help_text="Description of how the issue was resolved"
    )
    
    estimated_repair_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Estimated cost to repair (optional)"
    )
    
    actual_repair_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Actual cost of repair (optional)"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the issue was marked as resolved"
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the issue was closed"
    )
    
    # Priority and urgency flags
    is_urgent = models.BooleanField(
        default=False,
        help_text="Requires immediate attention"
    )
    
    blocks_resource_use = models.BooleanField(
        default=False,
        help_text="This issue prevents the resource from being used"
    )
    
    class Meta:
        db_table = 'booking_resourceissue'
        verbose_name = "Resource Issue"
        verbose_name_plural = "Resource Issues"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['resource', 'status']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['severity', '-created_at']),
            models.Index(fields=['assigned_to', 'status']),
        ]
    
    def __str__(self):
        return f"{self.resource.name} - {self.title} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        # Set timestamps based on status changes
        if self.status == 'resolved' and not self.resolved_at:
            self.resolved_at = timezone.now()
        elif self.status == 'closed' and not self.closed_at:
            self.closed_at = timezone.now()
        
        super().save(*args, **kwargs)
    
    @property
    def age_in_days(self):
        """How many days since the issue was reported."""
        return (timezone.now() - self.created_at).days
    
    @property
    def is_overdue(self):
        """Check if issue is overdue based on severity."""
        age = self.age_in_days
        if self.severity == 'critical':
            return age > 1  # Critical issues should be resolved within 1 day
        elif self.severity == 'high':
            return age > 3  # High severity within 3 days
        elif self.severity == 'medium':
            return age > 7  # Medium severity within 1 week
        else:
            return age > 14  # Low severity within 2 weeks
    
    @property
    def time_to_resolution(self):
        """Time taken to resolve the issue."""
        if self.resolved_at:
            return self.resolved_at - self.created_at
        return None
    
    def can_be_edited_by(self, user):
        """Check if user can edit this issue."""
        # Reporters can edit their own issues if they're still open
        if self.reported_by == user and self.status == 'open':
            return True
        
        # Technicians and sysadmins can always edit
        try:
            return user.userprofile.role in ['technician', 'sysadmin']
        except:
            return False
    
    def get_status_color(self):
        """Get Bootstrap color class for status."""
        status_colors = {
            'open': 'danger',
            'in_progress': 'warning',
            'waiting_parts': 'info',
            'resolved': 'success',
            'closed': 'secondary',
            'duplicate': 'secondary',
        }
        return status_colors.get(self.status, 'secondary')
    
    def get_severity_color(self):
        """Get Bootstrap color class for severity."""
        severity_colors = {
            'low': 'success',
            'medium': 'warning',
            'high': 'danger',
            'critical': 'danger',
        }
        return severity_colors.get(self.severity, 'secondary')