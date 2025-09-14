"""
Approval-related models for the Labitory.

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
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta


class AccessRequestManager(models.Manager):
    """Custom manager for AccessRequest with improved constraint handling."""
    
    def create_request(self, user, resource, **kwargs):
        """Create a new access request, handling existing rejected requests."""
        # Check if user has existing pending request for this resource
        existing_pending = self.filter(
            user=user,
            resource=resource,
            status='pending'
        ).first()

        if existing_pending:
            raise ValidationError(
                f"You already have a pending access request for {resource.name}. "
                "Please wait for the current request to be processed."
            )

        # Archive any existing rejected requests (change status to archived)
        self.filter(
            user=user,
            resource=resource,
            status='rejected'
        ).update(status='archived')

        # Auto-check lab induction status from UserProfile
        try:
            user_profile = user.userprofile
            if user_profile.is_inducted:
                kwargs['safety_induction_confirmed'] = True
                kwargs['safety_induction_confirmed_by'] = user  # System auto-confirmation
                kwargs['safety_induction_confirmed_at'] = timezone.now()
                kwargs['safety_induction_notes'] = 'Auto-confirmed: User profile shows induction completed'
        except AttributeError:
            pass  # No user profile exists

        # Create the new request
        request = self.create(user=user, resource=resource, **kwargs)

        # Create training records for required training if needed
        request._create_required_training_records()

        # Create risk assessment records if needed
        request._create_required_risk_assessments()

        return request


class ApprovalRule(models.Model):
    """Rules for booking approval workflows with advanced conditional logic."""
    APPROVAL_TYPES = [
        ('auto', 'Automatic Approval'),
        ('single', 'Single Level Approval'),
        ('tiered', 'Tiered Approval'),
        ('quota', 'Quota Based'),
        ('conditional', 'Conditional Approval'),
    ]
    
    CONDITION_TYPES = [
        ('time_based', 'Time-Based Conditions'),
        ('usage_based', 'Usage-Based Conditions'),
        ('training_based', 'Training-Based Conditions'),
        ('role_based', 'Role-Based Conditions'),
        ('resource_based', 'Resource-Based Conditions'),
        ('custom', 'Custom Logic'),
    ]
    
    name = models.CharField(max_length=200)
    resource = models.ForeignKey('Resource', on_delete=models.CASCADE, related_name='approval_rules')
    approval_type = models.CharField(max_length=20, choices=APPROVAL_TYPES)
    user_roles = models.JSONField(default=list)  # Roles that this rule applies to
    approvers = models.ManyToManyField(User, related_name='approval_rules', blank=True)
    conditions = models.JSONField(default=dict)  # Additional conditions
    
    # Advanced conditional logic
    condition_type = models.CharField(max_length=20, choices=CONDITION_TYPES, default='role_based')
    conditional_logic = models.JSONField(default=dict, help_text="Advanced conditional rules")
    fallback_rule = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, help_text="Rule to apply if conditions not met")
    
    # Rule metadata
    is_active = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=1)
    description = models.TextField(blank=True, help_text="Detailed description of when this rule applies")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'booking_approvalrule'
        ordering = ['priority', 'name']

    def __str__(self):
        return f"{self.name} - {self.resource.name}"

    def applies_to_user(self, user_profile):
        """Check if this approval rule applies to a specific user."""
        if not self.is_active:
            return False
        if not self.user_roles:
            return True
        return user_profile.role in self.user_roles
    
    def evaluate_conditions(self, booking_request, user_profile):
        """Evaluate complex conditional logic for approval."""
        from datetime import datetime, timedelta
        from django.utils import timezone
        
        if self.condition_type == 'time_based':
            return self._evaluate_time_conditions(booking_request, user_profile)
        elif self.condition_type == 'usage_based':
            return self._evaluate_usage_conditions(booking_request, user_profile)
        elif self.condition_type == 'training_based':
            return self._evaluate_training_conditions(booking_request, user_profile)
        elif self.condition_type == 'role_based':
            return self._evaluate_role_conditions(booking_request, user_profile)
        elif self.condition_type == 'resource_based':
            return self._evaluate_resource_conditions(booking_request, user_profile)
        elif self.condition_type == 'custom':
            return self._evaluate_custom_conditions(booking_request, user_profile)
        
        return {'approved': False, 'reason': 'Unknown condition type'}
    
    def _evaluate_time_conditions(self, booking_request, user_profile):
        """Evaluate time-based conditions."""
        logic = self.conditional_logic
        
        # Check booking advance time
        if 'min_advance_hours' in logic:
            advance_hours = (booking_request.get('start_time') - timezone.now()).total_seconds() / 3600
            if advance_hours < logic['min_advance_hours']:
                return {'approved': False, 'reason': f'Must book at least {logic["min_advance_hours"]} hours in advance'}
        
        # Check maximum advance booking
        if 'max_advance_days' in logic:
            advance_days = (booking_request.get('start_time') - timezone.now()).days
            if advance_days > logic['max_advance_days']:
                return {'approved': False, 'reason': f'Cannot book more than {logic["max_advance_days"]} days in advance'}
        
        # Check booking duration limits
        if 'max_duration_hours' in logic:
            duration = booking_request.get('duration_hours', 0)
            if duration > logic['max_duration_hours']:
                return {'approved': False, 'reason': f'Booking duration cannot exceed {logic["max_duration_hours"]} hours'}
        
        # Check time of day restrictions
        if 'allowed_hours' in logic:
            start_hour = booking_request.get('start_time').hour
            end_hour = booking_request.get('end_time').hour
            allowed_start, allowed_end = logic['allowed_hours']
            if start_hour < allowed_start or end_hour > allowed_end:
                return {'approved': False, 'reason': f'Bookings only allowed between {allowed_start}:00 and {allowed_end}:00'}
        
        return {'approved': True, 'reason': 'Time conditions met'}
    
    def _evaluate_usage_conditions(self, booking_request, user_profile):
        """Evaluate usage-based conditions."""
        logic = self.conditional_logic
        
        # Check monthly usage quota
        if 'monthly_hour_limit' in logic:
            from datetime import datetime
            current_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            # Get user's bookings this month for this resource
            monthly_bookings = Booking.objects.filter(
                user=user_profile.user,
                resource=self.resource,
                start_time__gte=current_month,
                status__in=['approved', 'confirmed']
            )
            
            total_hours = sum([
                (b.end_time - b.start_time).total_seconds() / 3600 
                for b in monthly_bookings
            ])
            
            requested_hours = booking_request.get('duration_hours', 0)
            if total_hours + requested_hours > logic['monthly_hour_limit']:
                return {
                    'approved': False, 
                    'reason': f'Monthly usage limit of {logic["monthly_hour_limit"]} hours would be exceeded'
                }
        
        # Check consecutive booking limits
        if 'max_consecutive_days' in logic:
            # Implementation for consecutive booking checking
            pass
        
        return {'approved': True, 'reason': 'Usage conditions met'}
    
    def _evaluate_training_conditions(self, booking_request, user_profile):
        """Evaluate training-based conditions."""
        logic = self.conditional_logic
        
        # Check required certifications
        if 'required_certifications' in logic:
            for cert_code in logic['required_certifications']:
                try:
                    training = UserTraining.objects.get(
                        user=user_profile.user,
                        training_course__code=cert_code,
                        status='completed',
                        passed=True
                    )
                    if training.is_expired:
                        return {
                            'approved': False, 
                            'reason': f'Required certification {cert_code} has expired'
                        }
                except UserTraining.DoesNotExist:
                    return {
                        'approved': False, 
                        'reason': f'Required certification {cert_code} not found'
                    }
        
        # Check minimum training level
        if 'min_training_level' in logic:
            if user_profile.training_level < logic['min_training_level']:
                return {
                    'approved': False, 
                    'reason': f'Minimum training level {logic["min_training_level"]} required'
                }
        
        return {'approved': True, 'reason': 'Training conditions met'}
    
    def _evaluate_role_conditions(self, booking_request, user_profile):
        """Evaluate role-based conditions."""
        logic = self.conditional_logic
        
        # Check role hierarchy
        if 'role_hierarchy' in logic:
            role_levels = logic['role_hierarchy']
            user_level = role_levels.get(user_profile.role, 0)
            required_level = logic.get('min_role_level', 0)
            
            if user_level < required_level:
                return {
                    'approved': False, 
                    'reason': f'Insufficient role level for this resource'
                }
        
        return {'approved': True, 'reason': 'Role conditions met'}
    
    def _evaluate_resource_conditions(self, booking_request, user_profile):
        """Evaluate resource-based conditions."""
        logic = self.conditional_logic
        
        # Check resource availability
        if 'check_conflicts' in logic and logic['check_conflicts']:
            # Enhanced conflict checking beyond basic validation
            pass
        
        return {'approved': True, 'reason': 'Resource conditions met'}
    
    def _evaluate_custom_conditions(self, booking_request, user_profile):
        """Evaluate custom conditional logic."""
        logic = self.conditional_logic
        
        # Support for custom Python expressions (with safety limitations)
        if 'expression' in logic:
            # This would require careful implementation for security
            # For now, return a basic evaluation
            pass
        
        return {'approved': True, 'reason': 'Custom conditions met'}
    
    def get_applicable_rule(self, booking_request, user_profile):
        """Get the most appropriate rule based on conditions."""
        if not self.applies_to_user(user_profile):
            return None
        
        if self.approval_type == 'conditional':
            evaluation = self.evaluate_conditions(booking_request, user_profile)
            if not evaluation['approved']:
                # Try fallback rule
                if self.fallback_rule:
                    return self.fallback_rule.get_applicable_rule(booking_request, user_profile)
                return None
        
        return self


class ApprovalStatistics(models.Model):
    """Track approval workflow statistics for analytics."""
    resource = models.ForeignKey('Resource', on_delete=models.CASCADE, related_name='approval_stats')
    approver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='approval_stats')
    
    # Statistics period
    period_start = models.DateField()
    period_end = models.DateField()
    period_type = models.CharField(max_length=20, choices=[
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ], default='monthly')
    
    # Approval counts
    access_requests_received = models.IntegerField(default=0)
    access_requests_approved = models.IntegerField(default=0)
    access_requests_rejected = models.IntegerField(default=0)
    access_requests_pending = models.IntegerField(default=0)
    
    # Training statistics
    training_requests_received = models.IntegerField(default=0)
    training_sessions_conducted = models.IntegerField(default=0)
    training_completions = models.IntegerField(default=0)
    training_failures = models.IntegerField(default=0)
    
    # Risk assessment statistics
    assessments_created = models.IntegerField(default=0)
    assessments_reviewed = models.IntegerField(default=0)
    assessments_approved = models.IntegerField(default=0)
    assessments_rejected = models.IntegerField(default=0)
    
    # Response time metrics (in hours)
    avg_response_time_hours = models.FloatField(default=0.0)
    min_response_time_hours = models.FloatField(default=0.0)
    max_response_time_hours = models.FloatField(default=0.0)
    
    # Additional metrics
    overdue_items = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_approvalstatistics'
        unique_together = ['resource', 'approver', 'period_start', 'period_type']
        ordering = ['-period_start', 'resource', 'approver']
    
    def __str__(self):
        return f"{self.resource.name} - {self.approver.get_full_name()} ({self.period_start})"
    
    @property
    def approval_rate(self):
        """Calculate approval rate percentage."""
        total = self.access_requests_approved + self.access_requests_rejected
        if total == 0:
            return 0
        return (self.access_requests_approved / total) * 100
    
    @property
    def training_success_rate(self):
        """Calculate training success rate percentage."""
        total = self.training_completions + self.training_failures
        if total == 0:
            return 0
        return (self.training_completions / total) * 100
    
    @property
    def assessment_approval_rate(self):
        """Calculate assessment approval rate percentage."""
        total = self.assessments_approved + self.assessments_rejected
        if total == 0:
            return 0
        return (self.assessments_approved / total) * 100
    
    @classmethod
    def generate_statistics(cls, resource=None, approver=None, period_type='monthly', period_start=None):
        """Generate statistics for a given period."""
        from django.utils import timezone
        from datetime import timedelta, date
        from django.db.models import Avg, Min, Max
        
        if period_start is None:
            period_start = timezone.now().date().replace(day=1)  # Start of current month
        
        # Calculate period end based on type
        if period_type == 'daily':
            period_end = period_start
        elif period_type == 'weekly':
            period_end = period_start + timedelta(days=6)
        elif period_type == 'monthly':
            if period_start.month == 12:
                period_end = period_start.replace(year=period_start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                period_end = period_start.replace(month=period_start.month + 1, day=1) - timedelta(days=1)
        elif period_type == 'quarterly':
            quarter_start_month = ((period_start.month - 1) // 3) * 3 + 1
            period_start = period_start.replace(month=quarter_start_month, day=1)
            period_end = period_start.replace(month=quarter_start_month + 2, day=1)
            if period_end.month == 12:
                period_end = period_end.replace(year=period_end.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                period_end = period_end.replace(month=period_end.month + 1, day=1) - timedelta(days=1)
        elif period_type == 'yearly':
            period_start = period_start.replace(month=1, day=1)
            period_end = period_start.replace(year=period_start.year + 1, month=1, day=1) - timedelta(days=1)
        
        # Filter queryset
        queryset_filters = {
            'created_at__date__range': [period_start, period_end]
        }
        
        if resource:
            queryset_filters['resource'] = resource
        if approver:
            queryset_filters['reviewed_by'] = approver
        
        # Access request statistics
        access_requests = AccessRequest.objects.filter(**queryset_filters)
        access_requests_received = access_requests.count()
        access_requests_approved = access_requests.filter(status='approved').count()
        access_requests_rejected = access_requests.filter(status='rejected').count()
        access_requests_pending = access_requests.filter(status='pending').count()
        
        # Training statistics
        training_filters = queryset_filters.copy()
        if 'reviewed_by' in training_filters:
            training_filters['instructor'] = training_filters.pop('reviewed_by')
        
        # Return aggregated statistics
        return {
            'period_start': period_start,
            'period_end': period_end,
            'period_type': period_type,
            'access_requests_received': access_requests_received,
            'access_requests_approved': access_requests_approved,
            'access_requests_rejected': access_requests_rejected,
            'access_requests_pending': access_requests_pending,
        }


class AccessRequest(models.Model):
    """Requests for resource access."""
    REQUEST_TYPES = [
        ('view', 'View Only'),
        ('book', 'View and Book'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('archived', 'Archived'),
    ]
    
    resource = models.ForeignKey('Resource', on_delete=models.CASCADE, related_name='access_requests')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='access_requests')
    access_type = models.CharField(max_length=10, choices=REQUEST_TYPES, default='book')
    justification = models.TextField(help_text="Why do you need access to this resource?")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    
    # Approval workflow
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_access_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    
    # Duration request
    requested_duration_days = models.PositiveIntegerField(null=True, blank=True, help_text="Requested access duration in days")
    
    # Supervisor information (required for students)
    supervisor_name = models.CharField(max_length=200, blank=True, help_text="Name of supervisor (required for students)")
    supervisor_email = models.EmailField(blank=True, help_text="Email of supervisor (required for students)")
    
    # Prerequisites confirmation
    safety_induction_confirmed = models.BooleanField(default=False, help_text="Lab admin confirmed user completed safety induction")
    lab_training_confirmed = models.BooleanField(default=False, help_text="Lab admin confirmed user completed lab training")
    risk_assessment_confirmed = models.BooleanField(default=False, help_text="Lab admin confirmed user submitted required risk assessment")
    safety_induction_notes = models.TextField(blank=True, help_text="Notes about safety induction completion")
    lab_training_notes = models.TextField(blank=True, help_text="Notes about lab training completion")
    risk_assessment_notes = models.TextField(blank=True, help_text="Notes about risk assessment submission")
    safety_induction_confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='confirmed_safety_inductions')
    lab_training_confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='confirmed_lab_trainings')
    risk_assessment_confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='confirmed_risk_assessments')
    safety_induction_confirmed_at = models.DateTimeField(null=True, blank=True)
    lab_training_confirmed_at = models.DateTimeField(null=True, blank=True)
    risk_assessment_confirmed_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    objects = AccessRequestManager()
    
    class Meta:
        db_table = 'booking_accessrequest'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['resource', 'user'],
                condition=models.Q(status='pending'),
                name='unique_pending_access_request'
            )
        ]
    
    def __str__(self):
        return f"{self.user.username} requesting {self.get_access_type_display()} access to {self.resource.name}"
    
    def approve(self, reviewed_by, review_notes="", expires_in_days=None, send_notification=True):
        """Approve the access request and create ResourceAccess."""
        if self.status != 'pending':
            raise ValueError("Can only approve pending requests")
        
        # Check if prerequisites are met
        if not self.prerequisites_met():
            raise ValueError("Cannot approve: Safety induction and lab training must be confirmed first")
        
        # Create the access permission
        expires_at = None
        if expires_in_days or self.requested_duration_days:
            days = expires_in_days or self.requested_duration_days
            expires_at = timezone.now() + timedelta(days=days)
        
        from .resources import ResourceAccess
        ResourceAccess.objects.update_or_create(
            resource=self.resource,
            user=self.user,
            defaults={
                'access_type': self.access_type,
                'granted_by': reviewed_by,
                'is_active': True,
                'expires_at': expires_at,
                'notes': f"Approved via request: {review_notes}" if review_notes else "Approved via access request"
            }
        )
        
        # Update request status
        self.status = 'approved'
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.review_notes = review_notes
        self.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_notes', 'updated_at'])
        
        # Send notification (only if requested)
        if send_notification:
            try:
                from .notifications import access_request_notifications
                access_request_notifications.access_request_approved(self, reviewed_by)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send access request approval notification: {e}")
    
    def confirm_safety_induction(self, confirmed_by, notes=""):
        """Confirm that user has completed safety induction."""
        self.safety_induction_confirmed = True
        self.safety_induction_confirmed_by = confirmed_by
        self.safety_induction_confirmed_at = timezone.now()
        self.safety_induction_notes = notes
        self.save(update_fields=['safety_induction_confirmed', 'safety_induction_confirmed_by', 
                                'safety_induction_confirmed_at', 'safety_induction_notes', 'updated_at'])
        
        # Also mark the user as generally inducted if they aren't already
        try:
            user_profile = self.user.userprofile
            if not user_profile.is_inducted:
                user_profile.is_inducted = True
                user_profile.save(update_fields=['is_inducted'])
                
                # Send notification to user about general induction completion
                from .notifications import Notification
                Notification.objects.create(
                    user=self.user,
                    title='Lab Induction Completed',
                    message=f'Your lab induction has been confirmed by {confirmed_by.get_full_name() or confirmed_by.username}. You can now request access to lab resources.',
                    notification_type='induction'
                )
        except Exception as e:
            # Log error but don't fail the main operation
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to update general induction status: {e}")
    
    def confirm_lab_training(self, confirmed_by, notes=""):
        """Confirm that user has completed lab training."""
        self.lab_training_confirmed = True
        self.lab_training_confirmed_by = confirmed_by
        self.lab_training_confirmed_at = timezone.now()
        self.lab_training_notes = notes
        self.save(update_fields=['lab_training_confirmed', 'lab_training_confirmed_by',
                                'lab_training_confirmed_at', 'lab_training_notes', 'updated_at'])
    
    def confirm_risk_assessment(self, confirmed_by, notes=""):
        """Confirm that user has submitted required risk assessment."""
        self.risk_assessment_confirmed = True
        self.risk_assessment_confirmed_by = confirmed_by
        self.risk_assessment_confirmed_at = timezone.now()
        self.risk_assessment_notes = notes
        self.save(update_fields=['risk_assessment_confirmed', 'risk_assessment_confirmed_by',
                                'risk_assessment_confirmed_at', 'risk_assessment_notes', 'updated_at'])
    
    def prerequisites_met(self):
        """Check if all prerequisites for approval are met."""
        # Always require safety induction (this is a lab-wide requirement)
        prerequisites = [self.safety_induction_confirmed]

        # Only check training if resource requires it
        if self.resource.required_training_level > 0:
            prerequisites.append(self.lab_training_confirmed)

        # Only check risk assessment if resource requires it
        if self.resource.requires_risk_assessment:
            prerequisites.append(self.risk_assessment_confirmed)

        return all(prerequisites)
    
    def get_prerequisite_status(self):
        """Get the status of prerequisites for display."""
        return {
            'safety_induction': {
                'completed': self.safety_induction_confirmed,
                'confirmed_by': self.safety_induction_confirmed_by,
                'confirmed_at': self.safety_induction_confirmed_at,
                'notes': self.safety_induction_notes,
                'required': True  # Always required
            },
            'lab_training': {
                'completed': self.lab_training_confirmed,
                'confirmed_by': self.lab_training_confirmed_by,
                'confirmed_at': self.lab_training_confirmed_at,
                'notes': self.lab_training_notes,
                'required': self.resource.required_training_level > 0
            },
            'risk_assessment': {
                'completed': self.risk_assessment_confirmed,
                'confirmed_by': self.risk_assessment_confirmed_by,
                'confirmed_at': self.risk_assessment_confirmed_at,
                'notes': self.risk_assessment_notes,
                'required': self.resource.requires_risk_assessment
            },
            'all_met': self.prerequisites_met()
        }
    
    def requires_supervisor_info(self):
        """Check if this request requires supervisor information (for students)."""
        try:
            return self.user.userprofile.role == 'student'
        except AttributeError:
            return False
    
    def has_supervisor_info(self):
        """Check if supervisor information is provided."""
        return bool(self.supervisor_name and self.supervisor_email)
    
    def clean(self):
        """Validate the access request."""
        super().clean()
        if self.requires_supervisor_info() and not self.has_supervisor_info():
            raise ValidationError("Supervisor name and email are required for student access requests.")
    
    def reject(self, reviewed_by, review_notes="", send_notification=True, reset_progress=True):
        """Reject the access request."""
        if self.status != 'pending':
            raise ValueError("Can only reject pending requests")
        
        self.status = 'rejected'
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.review_notes = review_notes
        
        # Reset approval progress if requested (default behavior)
        if reset_progress:
            self.reset_approval_progress()
        
        self.save(update_fields=[
            'status', 'reviewed_by', 'reviewed_at', 'review_notes', 'updated_at',
            'safety_induction_confirmed', 'safety_induction_confirmed_by', 'safety_induction_confirmed_at', 'safety_induction_notes',
            'lab_training_confirmed', 'lab_training_confirmed_by', 'lab_training_confirmed_at', 'lab_training_notes',
            'risk_assessment_confirmed', 'risk_assessment_confirmed_by', 'risk_assessment_confirmed_at', 'risk_assessment_notes'
        ])
        
        # Send notification (only if requested)
        if send_notification:
            try:
                from .notifications import access_request_notifications
                access_request_notifications.access_request_rejected(self, reviewed_by, review_notes)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send access request rejection notification: {e}")
    
    def cancel(self):
        """Cancel the access request."""
        if self.status != 'pending':
            raise ValueError("Can only cancel pending requests")
        
        self.status = 'cancelled'
        self.save(update_fields=['status', 'updated_at'])
    
    def reset_approval_progress(self):
        """Reset all approval progress (safety induction, lab training, risk assessment)."""
        # Reset safety induction
        self.safety_induction_confirmed = False
        self.safety_induction_confirmed_by = None
        self.safety_induction_confirmed_at = None
        self.safety_induction_notes = ""
        
        # Reset lab training
        self.lab_training_confirmed = False
        self.lab_training_confirmed_by = None
        self.lab_training_confirmed_at = None
        self.lab_training_notes = ""
        
        # Reset risk assessment
        self.risk_assessment_confirmed = False
        self.risk_assessment_confirmed_by = None
        self.risk_assessment_confirmed_at = None
        self.risk_assessment_notes = ""
    
    def allow_resubmission(self):
        """Allow user to resubmit after rejection by creating a fresh request."""
        if self.status != 'rejected':
            raise ValueError("Can only enable resubmission for rejected requests")
        
        # Archive this request to allow new submission
        self.status = 'archived'
        self.save(update_fields=['status', 'updated_at'])
    
    def get_approval_requirements(self):
        """Get all requirements that must be met before approval."""
        requirements = {
            'training': [],
            'risk_assessments': [],
            'responsible_persons': []
        }

        # Get required training courses
        training_requirements = self.resource.training_requirements.filter(
            is_mandatory=True
        ).select_related('training_course')

        for req in training_requirements:
            # Check if access type requires this training
            if not req.required_for_access_types or self.access_type in req.required_for_access_types:
                requirements['training'].append(req.training_course)

        # Get required risk assessments
        risk_assessments = self.resource.risk_assessments.filter(
            is_mandatory=True,
            is_active=True
        )
        requirements['risk_assessments'] = list(risk_assessments)

        return requirements

    def _create_required_training_records(self):
        """Create UserTraining records for required training courses."""
        from django.apps import apps
        UserTraining = apps.get_model('booking', 'UserTraining')

        # Get required training courses
        training_requirements = self.resource.training_requirements.filter(
            is_mandatory=True
        ).select_related('training_course')

        for req in training_requirements:
            # Check if access type requires this training
            if req.required_for_access_types and self.access_type not in req.required_for_access_types:
                continue

            # Check if user already has this training
            existing_training = UserTraining.objects.filter(
                user=self.user,
                training_course=req.training_course
            ).first()

            if not existing_training:
                # Create new training record
                UserTraining.objects.create(
                    user=self.user,
                    training_course=req.training_course,
                    status='enrolled',
                    enrolled_at=timezone.now(),
                    instructor_notes=f'Auto-enrolled for resource access: {self.resource.name}'
                )
            elif existing_training.status in ['cancelled', 'failed']:
                # Re-enroll if previously cancelled/failed
                existing_training.status = 'enrolled'
                existing_training.enrolled_at = timezone.now()
                existing_training.instructor_notes = f'Re-enrolled for resource access: {self.resource.name}'
                existing_training.save(update_fields=['status', 'enrolled_at', 'instructor_notes'])

    def _create_required_risk_assessments(self):
        """Create UserRiskAssessment records for required risk assessments."""
        if not self.resource.requires_risk_assessment:
            return

        from django.apps import apps
        RiskAssessment = apps.get_model('booking', 'RiskAssessment')
        UserRiskAssessment = apps.get_model('booking', 'UserRiskAssessment')

        # Get required risk assessments for this resource
        required_assessments = RiskAssessment.objects.filter(
            resource=self.resource,
            is_mandatory=True,
            is_active=True
        )

        for assessment in required_assessments:
            # Check if user already has this assessment
            existing_assessment = UserRiskAssessment.objects.filter(
                user=self.user,
                risk_assessment=assessment
            ).first()

            if not existing_assessment:
                # Create new risk assessment record
                UserRiskAssessment.objects.create(
                    user=self.user,
                    risk_assessment=assessment,
                    status='draft',
                    created_at=timezone.now(),
                    notes=f'Required for resource access: {self.resource.name}'
                )
            elif existing_assessment.status == 'rejected':
                # Reset if previously rejected
                existing_assessment.status = 'draft'
                existing_assessment.notes = f'Reset for resource access: {self.resource.name}'
                existing_assessment.save(update_fields=['status', 'notes'])


class TrainingRequest(models.Model):
    """Requests for training on specific resources."""
    STATUS_CHOICES = [
        ('pending', 'Training Pending'),
        ('scheduled', 'Training Scheduled'),
        ('completed', 'Training Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='training_requests')
    resource = models.ForeignKey('Resource', on_delete=models.CASCADE, related_name='training_requests')
    requested_level = models.PositiveIntegerField(help_text="Training level being requested")
    current_level = models.PositiveIntegerField(help_text="User's current training level")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    
    # Training details
    justification = models.TextField(help_text="Why training is needed")
    training_date = models.DateTimeField(null=True, blank=True, help_text="Scheduled training date")
    completed_date = models.DateTimeField(null=True, blank=True, help_text="When training was completed")
    
    # Review information
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_training_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_trainingrequest'
        ordering = ['-created_at']
        unique_together = ['user', 'resource', 'status']  # Prevent duplicate pending requests
    
    def __str__(self):
        return f"{self.user.username} requesting level {self.requested_level} training for {self.resource.name}"
    
    def complete_training(self, reviewed_by, completed_date=None, send_notification=True):
        """Mark training as completed and update user's training level."""
        self.status = 'completed'
        self.completed_date = completed_date or timezone.now()
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.save()
        
        # Update user's training level
        user_profile = self.user.userprofile
        if user_profile.training_level < self.requested_level:
            user_profile.training_level = self.requested_level
            user_profile.save()
        
        # Send notification (only if requested)
        if send_notification:
            try:
                from .notifications import training_request_notifications
                training_request_notifications.training_request_completed(self)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send training completion notification: {e}")
    
    def schedule_training(self, training_date, reviewed_by, notes="", send_notification=True):
        """Schedule training for the user."""
        self.status = 'scheduled'
        self.training_date = training_date
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save()
        
        # Send notification (only if requested)
        if send_notification:
            try:
                from .notifications import training_request_notifications
                training_request_notifications.training_request_scheduled(self, training_date)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send training scheduled notification: {e}")
    
    def cancel_training(self, cancelled_by, reason="", send_notification=True):
        """Cancel the training request."""
        if self.status not in ['pending', 'scheduled']:
            raise ValueError("Can only cancel pending or scheduled training")
        
        self.status = 'cancelled'
        self.reviewed_by = cancelled_by
        self.reviewed_at = timezone.now()
        self.review_notes = reason
        self.save()
        
        # Send notification (only if requested)
        if send_notification:
            try:
                from .notifications import training_request_notifications
                training_request_notifications.training_request_cancelled(self, cancelled_by, reason)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send training cancellation notification: {e}")