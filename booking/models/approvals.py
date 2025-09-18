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
    resource = models.ForeignKey('Resource', on_delete=models.CASCADE, related_name='approval_rules', null=True, blank=True)
    approval_type = models.CharField(max_length=20, choices=APPROVAL_TYPES)
    user_roles = models.JSONField(default=list)  # Roles that this rule applies to
    approvers = models.ManyToManyField(User, related_name='approval_rules', blank=True)
    conditions = models.JSONField(default=dict)  # Additional conditions
    
    # Advanced conditional logic
    condition_type = models.CharField(max_length=20, choices=CONDITION_TYPES, default='role_based')
    conditional_logic = models.JSONField(default=dict, help_text="Advanced conditional rules")
    fallback_rule = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, help_text="Rule to apply if conditions not met")

    # Tiered approval configuration
    tier_mode = models.CharField(max_length=20, choices=[
        ('sequential', 'Sequential - Each tier must approve in order'),
        ('parallel', 'Parallel - All tiers can approve simultaneously'),
        ('conditional', 'Conditional - Next tier depends on previous decisions')
    ], default='sequential', help_text="How tiers are processed")
    tier_escalation_enabled = models.BooleanField(default=True, help_text="Enable automatic escalation on timeout")
    tier_timeout_hours = models.PositiveIntegerField(default=48, help_text="Default timeout for tier approval")

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
        resource_name = self.resource.name if self.resource else "All Resources"
        return f"{self.name} - {resource_name}"

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
        
        # Training level checks removed - use specific training courses instead
        
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
        elif self.approval_type == 'quota':
            # For quota-based rules, always return the rule
            # The actual quota evaluation happens during booking approval
            return self

        return self

    def create_tiered_approval_steps(self, booking):
        """Create approval steps for tiered approval workflow."""
        if self.approval_type != 'tiered':
            return []

        approval_steps = []
        tiers = self.approval_tiers.all()

        for tier in tiers:
            eligible_approvers = tier.get_eligible_approvers(booking.user.userprofile)

            if tier.requires_all_approvers:
                # Create an approval step for each approver
                for approver in eligible_approvers:
                    approval_steps.append(
                        BookingApproval(
                            booking=booking,
                            approval_rule=self,
                            tier_level=tier.tier_level,
                            approver=approver,
                            deadline=timezone.now() + timedelta(hours=tier.approval_deadline_hours)
                        )
                    )
            else:
                # Create approval steps up to the threshold
                threshold = min(tier.approval_threshold, len(eligible_approvers))
                for approver in eligible_approvers[:threshold]:
                    approval_steps.append(
                        BookingApproval(
                            booking=booking,
                            approval_rule=self,
                            tier_level=tier.tier_level,
                            approver=approver,
                            deadline=timezone.now() + timedelta(hours=tier.approval_deadline_hours)
                        )
                    )

        return approval_steps

    def get_next_approval_tier(self, booking):
        """Get the next tier that needs approval for this booking."""
        completed_tiers = set(
            booking.approval_steps.filter(
                approval_rule=self,
                status='approved'
            ).values_list('tier_level', flat=True)
        )

        all_tiers = list(self.approval_tiers.values_list('tier_level', flat=True).order_by('tier_level'))

        for tier_level in all_tiers:
            if tier_level not in completed_tiers:
                return self.approval_tiers.get(tier_level=tier_level)

        return None  # All tiers completed

    def is_tier_complete(self, booking, tier_level):
        """Check if a specific tier is complete for this booking."""
        tier = self.approval_tiers.get(tier_level=tier_level)
        approvals = booking.approval_steps.filter(
            approval_rule=self,
            tier_level=tier_level,
            status='approved'
        )

        if tier.requires_all_approvers:
            required_count = tier.approvers.count()
            if tier.approver_roles:
                from booking.models.core import UserProfile
                role_approvers_count = User.objects.filter(
                    userprofile__role__in=tier.approver_roles,
                    is_active=True
                ).exclude(id=booking.user.id).count()
                required_count += role_approvers_count
        else:
            required_count = tier.approval_threshold

        return approvals.count() >= required_count

    def is_tiered_approval_complete(self, booking):
        """Check if all tiers for this booking are complete."""
        all_tiers = self.approval_tiers.values_list('tier_level', flat=True)
        for tier_level in all_tiers:
            if not self.is_tier_complete(booking, tier_level):
                return False
        return True

    def evaluate_quota_based_approval(self, booking_request, user_profile):
        """Evaluate quota-based approval for a booking request."""
        if self.approval_type != 'quota':
            return {'approved': True, 'reason': 'Not a quota-based rule'}

        # Calculate booking duration in hours
        duration_hours = booking_request.get('duration_hours', 0)
        if not duration_hours:
            start_time = booking_request.get('start_time')
            end_time = booking_request.get('end_time')
            if start_time and end_time:
                duration_hours = (end_time - start_time).total_seconds() / 3600

        # Find applicable quota allocations
        applicable_allocations = QuotaAllocation.objects.filter(
            is_active=True
        ).order_by('-priority')

        quota_result = None
        for allocation in applicable_allocations:
            if (allocation.applies_to_user(user_profile) and
                allocation.applies_to_resource(self.resource)):

                quota_result = self._check_quota_availability(
                    allocation, user_profile.user, duration_hours, booking_request
                )
                break

        if not quota_result:
            # No applicable quota found - default to manual approval
            return {
                'approved': False,
                'reason': 'No applicable quota allocation found - manual approval required'
            }

        return quota_result

    def _check_quota_availability(self, allocation, user, requested_amount, booking_request):
        """Check if user has sufficient quota for the requested amount."""
        # Get or create current period quota for user
        current_period = self._get_current_quota_period(allocation)
        user_quota, created = UserQuota.objects.get_or_create(
            user=user,
            allocation=allocation,
            period_start=current_period['start'],
            defaults={
                'period_end': current_period['end'],
                'used_amount': 0,
                'reserved_amount': 0,
                'overdraft_used': 0,
            }
        )

        # Check if quota can accommodate the request
        if user_quota.can_allocate(requested_amount):
            if allocation.auto_approve_within_quota:
                # Reserve the quota for this booking
                user_quota.allocate_usage(requested_amount, is_reservation=True)

                # Log the reservation
                QuotaUsageLog.objects.create(
                    user_quota=user_quota,
                    amount_used=requested_amount,
                    usage_type='reservation',
                    description=f'Reserved for booking: {booking_request.get("title", "Untitled booking")}'
                )

                return {
                    'approved': True,
                    'reason': f'Auto-approved within quota ({user_quota.available_amount:.1f}h remaining)',
                    'quota_info': {
                        'allocation_name': allocation.name,
                        'available_amount': float(user_quota.available_amount),
                        'usage_percentage': user_quota.usage_percentage
                    }
                }

        # Quota exceeded - check if manual approval is required
        if allocation.require_approval_over_quota:
            return {
                'approved': False,
                'reason': f'Quota exceeded - manual approval required (requested: {requested_amount}h, available: {user_quota.available_amount:.1f}h)',
                'quota_info': {
                    'allocation_name': allocation.name,
                    'available_amount': float(user_quota.available_amount),
                    'usage_percentage': user_quota.usage_percentage,
                    'quota_exceeded': True
                }
            }
        else:
            # Allow overdraft or auto-approve over quota
            if allocation.allow_overdraft and user_quota.can_allocate(requested_amount):
                user_quota.allocate_usage(requested_amount, is_reservation=True)

                QuotaUsageLog.objects.create(
                    user_quota=user_quota,
                    amount_used=requested_amount,
                    usage_type='reservation',
                    description=f'Reserved for booking (overdraft): {booking_request.get("title", "Untitled booking")}'
                )

                return {
                    'approved': True,
                    'reason': f'Auto-approved with overdraft ({user_quota.overdraft_used:.1f}h overdraft used)',
                    'quota_info': {
                        'allocation_name': allocation.name,
                        'available_amount': float(user_quota.available_amount),
                        'usage_percentage': user_quota.usage_percentage,
                        'overdraft_used': float(user_quota.overdraft_used)
                    }
                }
            else:
                return {
                    'approved': False,
                    'reason': f'Quota and overdraft limit exceeded',
                    'quota_info': {
                        'allocation_name': allocation.name,
                        'available_amount': float(user_quota.available_amount),
                        'usage_percentage': user_quota.usage_percentage,
                        'quota_exceeded': True
                    }
                }

    def _get_current_quota_period(self, allocation):
        """Calculate the current quota period based on allocation settings."""
        now = timezone.now()

        if allocation.period_type == 'daily':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        elif allocation.period_type == 'weekly':
            # Start of week (Monday)
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start = start - timedelta(days=start.weekday())
            end = start + timedelta(weeks=1)
        elif allocation.period_type == 'monthly':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start.month + 1)
        elif allocation.period_type == 'quarterly':
            quarter = ((now.month - 1) // 3) + 1
            start_month = (quarter - 1) * 3 + 1
            start = now.replace(month=start_month, day=1, hour=0, minute=0, second=0, microsecond=0)

            if quarter == 4:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start_month + 3)
        elif allocation.period_type == 'yearly':
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end = start.replace(year=start.year + 1)
        else:
            # Default to monthly
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start.month + 1)

        return {'start': start, 'end': end}

    @staticmethod
    def get_user_quota_status(user, resource=None):
        """Get quota status for a user across all applicable allocations."""
        user_profile = user.userprofile
        quota_status = []

        # Find applicable quota allocations
        allocations = QuotaAllocation.objects.filter(is_active=True).order_by('-priority')

        for allocation in allocations:
            if allocation.applies_to_user(user_profile):
                if resource and not allocation.applies_to_resource(resource):
                    continue

                # Get current period
                from booking.models.approvals import ApprovalRule
                rule = ApprovalRule()
                current_period = rule._get_current_quota_period(allocation)

                # Get or calculate user quota
                try:
                    user_quota = UserQuota.objects.get(
                        user=user,
                        allocation=allocation,
                        period_start=current_period['start']
                    )
                except UserQuota.DoesNotExist:
                    user_quota = UserQuota(
                        user=user,
                        allocation=allocation,
                        period_start=current_period['start'],
                        period_end=current_period['end'],
                        used_amount=0,
                        reserved_amount=0,
                        overdraft_used=0
                    )

                quota_status.append({
                    'allocation': allocation,
                    'quota': user_quota,
                    'period_start': current_period['start'],
                    'period_end': current_period['end']
                })

        return quota_status


class BookingApproval(models.Model):
    """Track multi-tier approval progress for bookings."""
    APPROVAL_STATUS = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('escalated', 'Escalated'),
        ('withdrawn', 'Withdrawn'),
    ]

    booking = models.ForeignKey('Booking', on_delete=models.CASCADE, related_name='approval_steps')
    approval_rule = models.ForeignKey(ApprovalRule, on_delete=models.CASCADE, related_name='booking_approvals')
    tier_level = models.PositiveIntegerField(help_text="Approval tier level (1, 2, 3, etc.)")
    approver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assigned_approvals')
    status = models.CharField(max_length=20, choices=APPROVAL_STATUS, default='pending')

    # Approval details
    approved_at = models.DateTimeField(null=True, blank=True)
    comments = models.TextField(blank=True, help_text="Approver comments")
    conditions = models.TextField(blank=True, help_text="Special conditions for approval")

    # Escalation tracking
    escalated_from = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='escalated_to')
    escalation_reason = models.TextField(blank=True)

    # Timing
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deadline = models.DateTimeField(null=True, blank=True, help_text="Approval deadline")

    class Meta:
        db_table = 'booking_bookingapproval'
        ordering = ['tier_level', 'created_at']
        unique_together = ['booking', 'tier_level', 'approver']

    def __str__(self):
        return f"{self.booking.title} - Tier {self.tier_level} - {self.approver.username}"

    def is_overdue(self):
        """Check if approval is overdue."""
        if not self.deadline or self.status != 'pending':
            return False
        return timezone.now() > self.deadline

    def can_escalate(self):
        """Check if this approval can be escalated."""
        return self.status == 'pending' and self.is_overdue()


class ApprovalTier(models.Model):
    """Define tiers for tiered approval rules."""
    approval_rule = models.ForeignKey(ApprovalRule, on_delete=models.CASCADE, related_name='approval_tiers')
    tier_level = models.PositiveIntegerField()
    name = models.CharField(max_length=100, help_text="Tier name (e.g., 'Department Head', 'Lab Manager')")

    # Approver selection
    approvers = models.ManyToManyField(User, related_name='approval_tiers', blank=True)
    approver_roles = models.JSONField(default=list, help_text="User roles that can approve at this tier")

    # Tier configuration
    requires_all_approvers = models.BooleanField(default=False, help_text="Require approval from all approvers")
    approval_threshold = models.PositiveIntegerField(default=1, help_text="Number of approvals needed")
    auto_approve_conditions = models.JSONField(default=dict, help_text="Conditions for automatic approval")

    # Timing
    approval_deadline_hours = models.PositiveIntegerField(default=48, help_text="Hours to approve before escalation")
    escalation_tier = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='escalated_from_tier')

    class Meta:
        db_table = 'booking_approvaltier'
        ordering = ['approval_rule', 'tier_level']
        unique_together = ['approval_rule', 'tier_level']

    def __str__(self):
        return f"{self.approval_rule.name} - Tier {self.tier_level}: {self.name}"

    def get_eligible_approvers(self, user_profile=None):
        """Get list of users who can approve at this tier."""
        approvers = set(self.approvers.all())

        # Add role-based approvers
        if self.approver_roles:
            from booking.models.core import UserProfile
            role_approvers = User.objects.filter(
                userprofile__role__in=self.approver_roles,
                is_active=True
            )
            approvers.update(role_approvers)

        # Exclude the requesting user if provided
        if user_profile and user_profile.user in approvers:
            approvers.discard(user_profile.user)

        return list(approvers)


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
        if self.resource.training_requirements.filter(is_mandatory=True).exists():
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
                'required': self.resource.training_requirements.filter(is_mandatory=True).exists()
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
                    instructor_notes=f'Auto-enrolled for resource access: {self.resource.name}'
                )
            elif existing_training.status in ['cancelled', 'failed']:
                # Re-enroll if previously cancelled/failed
                existing_training.status = 'enrolled'
                existing_training.instructor_notes = f'Re-enrolled for resource access: {self.resource.name}'
                existing_training.save(update_fields=['status', 'instructor_notes'])

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

    def can_be_approved_by(self, user):
        """Check if the given user can approve this access request."""
        # Lab admins, technicians, and sysadmins can approve requests
        if user.groups.filter(name='Lab Admin').exists():
            return True
        if user.is_staff:
            return True
        try:
            if user.userprofile.role in ['technician', 'sysadmin']:
                return True
        except AttributeError:
            pass

        # Check if user is a responsible person for this resource
        try:
            if hasattr(self.resource, 'responsible_persons'):
                if self.resource.responsible_persons.filter(user=user).exists():
                    return True
        except AttributeError:
            pass

        return False

    def get_potential_approvers(self):
        """Get list of potential approvers for this access request."""
        approvers = []

        # Add lab admins
        from django.contrib.auth.models import Group
        try:
            lab_admin_group = Group.objects.get(name='Lab Admin')
            for user in lab_admin_group.user_set.all():
                approvers.append({
                    'user': user,
                    'user_name': user.get_full_name() or user.username,
                    'role': 'Lab Admin',
                    'reason': 'Lab Administration Rights'
                })
        except Group.DoesNotExist:
            pass

        # Add staff users
        from django.contrib.auth.models import User
        staff_users = User.objects.filter(is_staff=True)
        for user in staff_users:
            if not any(a['user'].id == user.id for a in approvers):
                approvers.append({
                    'user': user,
                    'user_name': user.get_full_name() or user.username,
                    'role': 'Staff',
                    'reason': 'Staff Privileges'
                })

        # Add users with technician or sysadmin roles
        from django.contrib.auth.models import User
        tech_users = User.objects.filter(userprofile__role__in=['technician', 'sysadmin'])
        for user in tech_users:
            if not any(a['user'].id == user.id for a in approvers):
                role_display = user.userprofile.get_role_display() if hasattr(user, 'userprofile') else 'Technician'
                approvers.append({
                    'user': user,
                    'user_name': user.get_full_name() or user.username,
                    'role': role_display,
                    'reason': 'Technical Role'
                })

        # Add resource responsible persons
        if hasattr(self.resource, 'responsible_persons'):
            for responsible_person in self.resource.responsible_persons.all():
                if not any(a['user'].id == responsible_person.user.id for a in approvers):
                    approvers.append({
                        'user': responsible_person.user,
                        'user_name': responsible_person.user.get_full_name() or responsible_person.user.username,
                        'role': 'Resource Manager',
                        'reason': f'Responsible for {self.resource.name}'
                    })

        return approvers

    def get_required_actions(self):
        """Get list of required actions for this access request."""
        actions = []

        if self.status == 'pending':
            # Check prerequisites
            if not self.safety_induction_confirmed:
                actions.append({
                    'title': 'Safety Induction Required',
                    'description': 'User must complete safety induction before access can be granted.',
                    'url': None,
                    'action_text': 'Complete Induction'
                })

            if self.resource.training_requirements.filter(is_mandatory=True).exists() and not self.lab_training_confirmed:
                actions.append({
                    'title': 'Lab Training Required',
                    'description': 'User must complete required training for this resource.',
                    'url': None,
                    'action_text': 'Complete Training'
                })

            if self.resource.requires_risk_assessment and not self.risk_assessment_confirmed:
                actions.append({
                    'title': 'Risk Assessment Required',
                    'description': 'User must submit required risk assessment for this resource.',
                    'url': None,
                    'action_text': 'Submit Assessment'
                })

            # If all prerequisites are met, action is to approve
            if self.prerequisites_met():
                actions.append({
                    'title': 'Ready for Approval',
                    'description': 'All prerequisites have been met. This request can now be approved.',
                    'url': None,
                    'action_text': 'Approve Request'
                })

        return actions

    def check_user_compliance(self):
        """Check user's compliance with training and risk assessment requirements."""
        from django.apps import apps

        compliance = {
            'training_complete': True,
            'missing_training': [],
            'risk_assessments_complete': True,
            'missing_assessments': []
        }

        # Check training requirements
        try:
            UserTraining = apps.get_model('booking', 'UserTraining')
            required_training = self.resource.training_requirements.filter(is_mandatory=True)

            for req in required_training:
                # Check if access type requires this training
                if req.required_for_access_types and self.access_type not in req.required_for_access_types:
                    continue

                # Check if user has completed this training
                user_training = UserTraining.objects.filter(
                    user=self.user,
                    training_course=req.training_course,
                    status='completed',
                    passed=True
                ).first()

                if not user_training or (hasattr(user_training, 'is_expired') and user_training.is_expired):
                    compliance['training_complete'] = False
                    compliance['missing_training'].append(req.training_course)
        except Exception:
            # If there's an error checking training, assume incomplete
            compliance['training_complete'] = False

        # Check risk assessment requirements
        if self.resource.requires_risk_assessment:
            try:
                UserRiskAssessment = apps.get_model('booking', 'UserRiskAssessment')
                required_assessments = self.resource.risk_assessments.filter(
                    is_mandatory=True,
                    is_active=True
                )

                for assessment in required_assessments:
                    user_assessment = UserRiskAssessment.objects.filter(
                        user=self.user,
                        risk_assessment=assessment,
                        status='approved'
                    ).first()

                    if not user_assessment:
                        compliance['risk_assessments_complete'] = False
                        compliance['missing_assessments'].append(assessment)
            except Exception:
                # If there's an error checking assessments, assume incomplete
                compliance['risk_assessments_complete'] = False

        return compliance

# =============================================================================
# QUOTA-BASED APPROVAL MODELS
# =============================================================================

class QuotaAllocation(models.Model):
    """Define quota allocations for users/roles/resources."""
    QUOTA_TYPES = [
        ('time_based', 'Time-Based (Hours)'),
        ('booking_count', 'Booking Count'),
        ('cost_based', 'Cost-Based'),
    ]

    PERIOD_TYPES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    # Scope definition
    resource = models.ForeignKey('Resource', on_delete=models.CASCADE, null=True, blank=True, related_name='quota_allocations')
    resource_type = models.CharField(max_length=50, blank=True, help_text='Apply to all resources of this type')
    user_roles = models.JSONField(default=list, help_text='User roles this allocation applies to')
    specific_users = models.ManyToManyField(User, blank=True, related_name='quota_allocations')

    # Quota configuration
    quota_type = models.CharField(max_length=20, choices=QUOTA_TYPES, default='time_based')
    quota_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text='Quota amount (hours, count, cost)')
    period_type = models.CharField(max_length=20, choices=PERIOD_TYPES, default='monthly')

    # Advanced settings
    allow_overdraft = models.BooleanField(default=False, help_text='Allow usage to exceed quota')
    overdraft_limit = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Maximum overdraft allowed')
    auto_approve_within_quota = models.BooleanField(default=True)
    require_approval_over_quota = models.BooleanField(default=True)

    # Renewal settings
    auto_renew = models.BooleanField(default=True)
    grace_period_days = models.IntegerField(default=0, help_text='Days of grace period after quota expires')

    # Metadata
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=100, help_text='Higher priority allocations override lower ones')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_quota_allocations')

    class Meta:
        db_table = 'booking_quotaallocation'
        ordering = ['-priority', 'created_at']

    def __str__(self):
        scope = f'{self.resource.name}' if self.resource else f'{self.resource_type or "All Resources"}'
        return f'{self.name} - {scope} ({self.quota_amount} {self.get_quota_type_display()}/{self.get_period_type_display()})'

    def applies_to_user(self, user_profile):
        """Check if this allocation applies to a specific user."""
        if not self.is_active:
            return False

        # Check specific users
        if self.specific_users.filter(id=user_profile.user.id).exists():
            return True

        # Check user roles
        if self.user_roles and user_profile.role in self.user_roles:
            return True

        return False

    def applies_to_resource(self, resource):
        """Check if this allocation applies to a specific resource."""
        if self.resource and self.resource == resource:
            return True

        if self.resource_type and resource.resource_type == self.resource_type:
            return True

        # If no specific resource/type, applies to all
        if not self.resource and not self.resource_type:
            return True

        return False


class UserQuota(models.Model):
    """Track individual user quota status and usage."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quotas')
    allocation = models.ForeignKey(QuotaAllocation, on_delete=models.CASCADE, related_name='user_quotas')

    # Current period tracking
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    # Usage tracking
    used_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reserved_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='Amount reserved by pending bookings')

    # Overdraft tracking
    overdraft_used = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Status
    is_active = models.BooleanField(default=True)
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'booking_userquota'
        unique_together = ['user', 'allocation', 'period_start']
        ordering = ['-period_start']

    def __str__(self):
        return f'{self.user.username} - {self.allocation.name} ({self.period_start.date()} to {self.period_end.date()})'

    @property
    def available_amount(self):
        """Calculate available quota amount."""
        return max(0, self.allocation.quota_amount - self.used_amount - self.reserved_amount)

    @property
    def total_usage(self):
        """Total usage including overdraft."""
        return self.used_amount + self.overdraft_used

    @property
    def usage_percentage(self):
        """Usage as percentage of quota."""
        if self.allocation.quota_amount > 0:
            return (self.total_usage / self.allocation.quota_amount) * 100
        return 0

    def can_allocate(self, amount):
        """Check if the specified amount can be allocated."""
        if self.available_amount >= amount:
            return True

        # Check overdraft allowance
        if self.allocation.allow_overdraft:
            overdraft_needed = amount - self.available_amount
            return self.overdraft_used + overdraft_needed <= self.allocation.overdraft_limit

        return False

    def allocate_usage(self, amount, is_reservation=False):
        """Allocate usage from the quota."""
        if not self.can_allocate(amount):
            raise ValueError('Insufficient quota available')

        if is_reservation:
            self.reserved_amount += amount
        else:
            if amount <= self.available_amount:
                self.used_amount += amount
            else:
                # Use available quota first, then overdraft
                overdraft_amount = amount - self.available_amount
                self.used_amount = self.allocation.quota_amount
                self.overdraft_used += overdraft_amount

        self.save()

    def release_reservation(self, amount):
        """Release a previously reserved amount."""
        self.reserved_amount = max(0, self.reserved_amount - amount)
        self.save()

    def is_expired(self):
        """Check if this quota period has expired."""
        return timezone.now() > self.period_end


class QuotaUsageLog(models.Model):
    """Log individual quota usage events for auditing."""
    user_quota = models.ForeignKey(UserQuota, on_delete=models.CASCADE, related_name='usage_logs')
    booking = models.ForeignKey('Booking', on_delete=models.CASCADE, null=True, blank=True, related_name='quota_usage_logs')

    # Usage details
    amount_used = models.DecimalField(max_digits=10, decimal_places=2)
    usage_type = models.CharField(max_length=20, choices=[
        ('booking', 'Booking Usage'),
        ('reservation', 'Reservation'),
        ('release', 'Reservation Release'),
        ('refund', 'Usage Refund'),
        ('adjustment', 'Manual Adjustment'),
    ], default='booking')

    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='quota_usage_logs')

    class Meta:
        db_table = 'booking_quotausagelog'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user_quota.user.username} - {self.usage_type} - {self.amount_used} ({self.created_at.date()})'


class ApprovalDelegate(models.Model):
    """Approval delegation for single-level approvals."""
    DELEGATION_TYPES = [
        ('temporary', 'Temporary Delegation'),
        ('permanent', 'Permanent Delegation'),
        ('conditional', 'Conditional Delegation'),
    ]

    DELEGATION_STATUS = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('expired', 'Expired'),
    ]

    # Core delegation information
    delegator = models.ForeignKey(User, on_delete=models.CASCADE, related_name='delegations_given', help_text="User delegating approval authority")
    delegate = models.ForeignKey(User, on_delete=models.CASCADE, related_name='delegations_received', help_text="User receiving approval authority")

    # Delegation scope
    approval_rule = models.ForeignKey(ApprovalRule, on_delete=models.CASCADE, null=True, blank=True, help_text="Specific rule to delegate, or all if empty")
    resource = models.ForeignKey('Resource', on_delete=models.CASCADE, null=True, blank=True, help_text="Specific resource to delegate, or all if empty")

    # Delegation details
    delegation_type = models.CharField(max_length=20, choices=DELEGATION_TYPES, default='temporary')
    status = models.CharField(max_length=20, choices=DELEGATION_STATUS, default='active')

    # Time constraints
    start_date = models.DateTimeField(help_text="When delegation becomes active")
    end_date = models.DateTimeField(null=True, blank=True, help_text="When delegation expires (null = permanent)")

    # Conditional constraints
    conditions = models.JSONField(default=dict, help_text="Conditions under which delegation is valid")
    max_delegations = models.PositiveIntegerField(null=True, blank=True, help_text="Maximum number of approvals delegate can make")
    used_delegations = models.PositiveIntegerField(default=0, help_text="Number of approvals delegate has made")

    # Metadata
    reason = models.TextField(help_text="Reason for delegation")
    notify_delegator = models.BooleanField(default=True, help_text="Send notifications to delegator when delegate acts")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='delegations_created')

    class Meta:
        db_table = 'booking_approvaldelegate'
        unique_together = ['delegator', 'delegate', 'approval_rule', 'resource']
        ordering = ['-created_at']

    def __str__(self):
        scope = ""
        if self.approval_rule:
            scope += f" for {self.approval_rule.name}"
        if self.resource:
            scope += f" on {self.resource.name}"
        return f'{self.delegator.username} → {self.delegate.username}{scope}'

    def is_valid(self):
        """Check if delegation is currently valid."""
        if self.status != 'active':
            return False

        now = timezone.now()
        if now < self.start_date:
            return False

        if self.end_date and now > self.end_date:
            self.status = 'expired'
            self.save()
            return False

        if self.max_delegations and self.used_delegations >= self.max_delegations:
            return False

        return True

    def can_approve(self, booking=None, approval_rule=None, resource=None):
        """Check if delegate can approve a specific request."""
        if not self.is_valid():
            return False

        # Check rule scope
        if self.approval_rule and approval_rule and self.approval_rule != approval_rule:
            return False

        # Check resource scope
        if self.resource and resource and self.resource != resource:
            return False

        # Check conditions
        if self.conditions and booking:
            # Add custom condition evaluation logic here
            pass

        return True


class ApprovalEscalation(models.Model):
    """Escalation rules for overdue approvals."""
    ESCALATION_ACTIONS = [
        ('notify', 'Send Notification'),
        ('delegate', 'Auto-delegate to Substitute'),
        ('auto_approve', 'Auto-approve with Conditions'),
        ('escalate_manager', 'Escalate to Manager'),
        ('escalate_admin', 'Escalate to Administrator'),
    ]

    # Core escalation configuration
    approval_rule = models.ForeignKey(ApprovalRule, on_delete=models.CASCADE, related_name='escalations')

    # Escalation triggers
    timeout_hours = models.PositiveIntegerField(help_text="Hours before escalation triggers")
    business_hours_only = models.BooleanField(default=True, help_text="Count only business hours for timeout")

    # Escalation actions
    action = models.CharField(max_length=20, choices=ESCALATION_ACTIONS)
    substitute_approver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='escalation_substitutes', help_text="User to escalate to")

    # Conditions and metadata
    conditions = models.JSONField(default=dict, help_text="Conditions for escalation")
    notification_template = models.TextField(blank=True, help_text="Custom notification template")
    priority = models.PositiveIntegerField(default=1, help_text="Escalation priority order")
    is_active = models.BooleanField(default=True)

    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='escalations_created')

    class Meta:
        db_table = 'booking_approvalescalation'
        ordering = ['priority', 'timeout_hours']

    def __str__(self):
        return f'{self.approval_rule.name} - {self.get_action_display()} after {self.timeout_hours}h'


class SingleApprovalRequest(models.Model):
    """Enhanced tracking for single-level approval requests."""
    APPROVAL_STATUS = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('delegated', 'Delegated'),
        ('escalated', 'Escalated'),
        ('expired', 'Expired'),
    ]

    PRIORITY_LEVELS = [
        ('low', 'Low Priority'),
        ('normal', 'Normal Priority'),
        ('high', 'High Priority'),
        ('urgent', 'Urgent'),
    ]

    # Core request information
    booking = models.OneToOneField('Booking', on_delete=models.CASCADE, related_name='single_approval')
    approval_rule = models.ForeignKey(ApprovalRule, on_delete=models.CASCADE)
    requester = models.ForeignKey(User, on_delete=models.CASCADE, related_name='approval_requests')

    # Approval assignment
    assigned_approver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='single_approval_assignments', help_text="Originally assigned approver")
    current_approver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='current_approvals', help_text="Current approver (may be delegate)")

    # Request details
    status = models.CharField(max_length=20, choices=APPROVAL_STATUS, default='pending')
    priority = models.CharField(max_length=20, choices=PRIORITY_LEVELS, default='normal')
    requested_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField(null=True, blank=True, help_text="Expected approval deadline")

    # Response details
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approvals_given')
    response_comments = models.TextField(blank=True)

    # Delegation tracking
    delegation = models.ForeignKey(ApprovalDelegate, on_delete=models.SET_NULL, null=True, blank=True, help_text="Delegation used if applicable")

    # Escalation tracking
    escalated_at = models.DateTimeField(null=True, blank=True)
    escalation_reason = models.TextField(blank=True)
    escalated_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='escalated_approvals')

    # Metadata
    approval_data = models.JSONField(default=dict, help_text="Additional approval context data")
    reminders_sent = models.PositiveIntegerField(default=0, help_text="Number of reminder notifications sent")
    last_reminder_sent = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'booking_singleapprovalrequest'
        ordering = ['-requested_at']

    def __str__(self):
        return f'{self.booking} - {self.status} ({self.current_approver.username})'

    def is_overdue(self):
        """Check if approval request is overdue."""
        if not self.due_date or self.status not in ['pending', 'delegated']:
            return False
        return timezone.now() > self.due_date

    def time_remaining(self):
        """Calculate time remaining for approval."""
        if not self.due_date:
            return None
        remaining = self.due_date - timezone.now()
        return remaining if remaining.total_seconds() > 0 else timedelta(0)

    def delegate_to(self, delegate_user, delegation):
        """Delegate approval to another user."""
        self.current_approver = delegate_user
        self.delegation = delegation
        self.status = 'delegated'
        self.save()

    def escalate_to(self, escalated_user, reason="Timeout escalation"):
        """Escalate approval to another user."""
        self.escalated_to = escalated_user
        self.current_approver = escalated_user
        self.escalated_at = timezone.now()
        self.escalation_reason = reason
        self.status = 'escalated'
        self.save()


class ApprovalNotificationTemplate(models.Model):
    """Customizable notification templates for approval workflows."""
    TEMPLATE_TYPES = [
        ('approval_request', 'Approval Request'),
        ('approval_reminder', 'Approval Reminder'),
        ('approval_approved', 'Approval Granted'),
        ('approval_rejected', 'Approval Rejected'),
        ('approval_delegated', 'Approval Delegated'),
        ('approval_escalated', 'Approval Escalated'),
        ('approval_expired', 'Approval Expired'),
    ]

    DELIVERY_METHODS = [
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('in_app', 'In-App Notification'),
        ('all', 'All Methods'),
    ]

    # Template identification
    name = models.CharField(max_length=200)
    template_type = models.CharField(max_length=30, choices=TEMPLATE_TYPES)
    approval_rule = models.ForeignKey(ApprovalRule, on_delete=models.CASCADE, null=True, blank=True, help_text="Specific rule, or global if empty")

    # Template content
    subject_template = models.CharField(max_length=500, help_text="Email subject or notification title")
    body_template = models.TextField(help_text="Message body with placeholder variables")

    # Delivery configuration
    delivery_method = models.CharField(max_length=20, choices=DELIVERY_METHODS, default='email')
    send_to_requester = models.BooleanField(default=True)
    send_to_approver = models.BooleanField(default=True)
    send_to_delegator = models.BooleanField(default=False, help_text="Send to original delegator if delegated")

    # Timing
    send_immediately = models.BooleanField(default=True)
    delay_minutes = models.PositiveIntegerField(default=0, help_text="Delay before sending")

    # Template variables help
    available_variables = models.JSONField(default=dict, help_text="Available template variables and descriptions")

    # Metadata
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='notification_templates_created')

    class Meta:
        db_table = 'booking_approvalnotificationtemplate'
        unique_together = ['template_type', 'approval_rule']
        ordering = ['template_type', 'name']

    def __str__(self):
        scope = f" ({self.approval_rule.name})" if self.approval_rule else " (Global)"
        return f'{self.get_template_type_display()}{scope}'

    def render(self, context):
        """Render template with provided context variables."""
        from django.template import Template, Context

        subject = Template(self.subject_template).render(Context(context))
        body = Template(self.body_template).render(Context(context))

        return {
            'subject': subject,
            'body': body,
            'delivery_method': self.delivery_method
        }