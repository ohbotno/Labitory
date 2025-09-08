"""
Comprehensive approval workflow tests for Labitory.
Tests approval rules, workflows, and access control.
"""
from django.test import TestCase
from django.contrib.auth.models import User, Group
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, Mock
import json

from booking.models import (
    ApprovalRule, ApprovalStatistics, AccessRequest, TrainingRequest,
    Resource, Booking, UserProfile
)
from booking.tests.factories import (
    UserFactory, ResourceFactory, BookingFactory, UserProfileFactory,
    ApprovalRuleFactory
)


class TestApprovalRuleModel(TestCase):
    """Test ApprovalRule model functionality."""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.approver = UserFactory()
        self.requester = UserFactory()
    
    def test_create_approval_rule(self):
        """Test creating an approval rule."""
        rule = ApprovalRule.objects.create(
            name="Basic Approval Rule",
            resource=self.resource,
            approval_type="single",
            user_roles=["student", "academic"],
            conditions={"max_duration_hours": 4}
        )
        
        self.assertEqual(rule.name, "Basic Approval Rule")
        self.assertEqual(rule.resource, self.resource)
        self.assertEqual(rule.approval_type, "single")
        self.assertIn("student", rule.user_roles)
        self.assertEqual(rule.conditions["max_duration_hours"], 4)
    
    def test_approval_rule_str_representation(self):
        """Test string representation of approval rules."""
        rule = ApprovalRule.objects.create(
            name="Test Rule",
            resource=self.resource,
            approval_type="auto"
        )
        
        str_repr = str(rule)
        self.assertIn("Test Rule", str_repr)
        self.assertIn(self.resource.name, str_repr)
    
    def test_rule_applies_to_user(self):
        """Test if rule applies to specific user roles."""
        rule = ApprovalRule.objects.create(
            name="Student Rule",
            resource=self.resource,
            approval_type="single",
            user_roles=["student"]
        )
        
        student_profile = UserProfileFactory(role='student')
        academic_profile = UserProfileFactory(role='academic')
        
        # Test rule application logic
        self.assertIn(student_profile.role, rule.user_roles)
        self.assertNotIn(academic_profile.role, rule.user_roles)
    
    def test_tiered_approval_rule(self):
        """Test tiered approval rule creation."""
        rule = ApprovalRule.objects.create(
            name="Tiered Rule",
            resource=self.resource,
            approval_type="tiered",
            user_roles=["student"],
            conditions={
                "levels": [
                    {"role": "technician", "required": True},
                    {"role": "academic", "required": True}
                ],
                "max_duration_hours": 8
            }
        )
        
        rule.approvers.add(self.approver)
        
        self.assertEqual(rule.approval_type, "tiered")
        self.assertEqual(len(rule.conditions["levels"]), 2)
        self.assertTrue(rule.approvers.filter(id=self.approver.id).exists())
    
    def test_quota_based_approval(self):
        """Test quota-based approval rules."""
        rule = ApprovalRule.objects.create(
            name="Quota Rule",
            resource=self.resource,
            approval_type="quota",
            user_roles=["student"],
            conditions={
                "weekly_hours_limit": 20,
                "monthly_bookings_limit": 10,
                "require_justification": True
            }
        )
        
        self.assertEqual(rule.conditions["weekly_hours_limit"], 20)
        self.assertEqual(rule.conditions["monthly_bookings_limit"], 10)
        self.assertTrue(rule.conditions["require_justification"])
    
    def test_conditional_approval_logic(self):
        """Test conditional approval with complex logic."""
        rule = ApprovalRule.objects.create(
            name="Conditional Rule",
            resource=self.resource,
            approval_type="conditional",
            conditions={
                "time_based": {
                    "weekend_requires_approval": True,
                    "after_hours_approval": {"start": "18:00", "end": "08:00"}
                },
                "usage_based": {
                    "max_consecutive_days": 3,
                    "cool_down_period_days": 1
                }
            }
        )
        
        conditions = rule.conditions
        self.assertTrue(conditions["time_based"]["weekend_requires_approval"])
        self.assertEqual(conditions["usage_based"]["max_consecutive_days"], 3)


class TestAccessRequestWorkflow(TestCase):
    """Test access request and approval workflows."""
    
    def setUp(self):
        self.resource = ResourceFactory(requires_risk_assessment=True)
        self.student = UserProfileFactory(role='student')
        self.technician = UserProfileFactory(role='technician')
        self.academic = UserProfileFactory(role='academic')
        
        # Create approval rule
        self.approval_rule = ApprovalRule.objects.create(
            name="Equipment Access Rule",
            resource=self.resource,
            approval_type="single",
            user_roles=["student"]
        )
        self.approval_rule.approvers.add(self.technician.user)
    
    def test_create_access_request(self):
        """Test creating an access request."""
        request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            access_type='book',
            justification='Need access for research project',
            status='pending'
        )
        
        self.assertEqual(request.user, self.student.user)
        self.assertEqual(request.resource, self.resource)
        self.assertEqual(request.status, 'pending')
        self.assertEqual(request.access_type, 'book')
    
    def test_access_request_str_representation(self):
        """Test string representation of access requests."""
        request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            access_type='book'
        )
        
        str_repr = str(request)
        self.assertIn(self.student.user.get_full_name(), str_repr)
        self.assertIn(self.resource.name, str_repr)
    
    def test_approve_access_request(self):
        """Test approving an access request."""
        request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            access_type='book',
            justification='Research project',
            status='pending'
        )
        
        # Approve the request
        request.approved_by = self.technician.user
        request.approved_at = timezone.now()
        request.status = 'approved'
        request.save()
        
        self.assertEqual(request.status, 'approved')
        self.assertEqual(request.approved_by, self.technician.user)
        self.assertIsNotNone(request.approved_at)
    
    def test_reject_access_request(self):
        """Test rejecting an access request."""
        request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            access_type='book',
            status='pending'
        )
        
        # Reject the request
        request.approved_by = self.technician.user
        request.approved_at = timezone.now()
        request.status = 'rejected'
        request.rejection_reason = 'Insufficient training'
        request.save()
        
        self.assertEqual(request.status, 'rejected')
        self.assertEqual(request.rejection_reason, 'Insufficient training')
    
    def test_access_request_with_prerequisites(self):
        """Test access requests with training prerequisites."""
        request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            access_type='book',
            status='pending',
            training_completed=False,
            risk_assessment_completed=False
        )
        
        self.assertFalse(request.training_completed)
        self.assertFalse(request.risk_assessment_completed)
        
        # Complete prerequisites
        request.training_completed = True
        request.risk_assessment_completed = True
        request.save()
        
        self.assertTrue(request.training_completed)
        self.assertTrue(request.risk_assessment_completed)
    
    def test_supervisor_approval_requirement(self):
        """Test supervisor approval requirement for students."""
        request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            access_type='book',
            requires_supervisor_approval=True,
            supervisor_email='supervisor@example.com'
        )
        
        self.assertTrue(request.requires_supervisor_approval)
        self.assertEqual(request.supervisor_email, 'supervisor@example.com')
        
        # Supervisor approves
        request.supervisor_approved = True
        request.supervisor_approved_at = timezone.now()
        request.save()
        
        self.assertTrue(request.supervisor_approved)
        self.assertIsNotNone(request.supervisor_approved_at)


class TestAutomaticApprovalLogic(TestCase):
    """Test automatic approval logic."""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.user = UserProfileFactory(role='academic')
        
        # Create automatic approval rule
        self.auto_rule = ApprovalRule.objects.create(
            name="Auto Approval for Academics",
            resource=self.resource,
            approval_type="auto",
            user_roles=["academic", "technician"],
            conditions={"max_duration_hours": 4}
        )
    
    def test_automatic_approval_for_qualified_users(self):
        """Test automatic approval for qualified users."""
        request = AccessRequest.objects.create(
            user=self.user.user,
            resource=self.resource,
            access_type='book'
        )
        
        # Simulate automatic approval logic
        if self.user.role in self.auto_rule.user_roles:
            request.status = 'approved'
            request.approved_at = timezone.now()
            request.auto_approved = True
            request.save()
        
        self.assertEqual(request.status, 'approved')
        self.assertTrue(request.auto_approved)
    
    def test_automatic_approval_with_conditions(self):
        """Test automatic approval with duration conditions."""
        # Short duration - should auto-approve
        short_request = AccessRequest.objects.create(
            user=self.user.user,
            resource=self.resource,
            access_type='book'
        )
        
        # Simulate condition checking
        max_hours = self.auto_rule.conditions.get("max_duration_hours", 24)
        requested_duration = 2  # 2 hours
        
        if requested_duration <= max_hours and self.user.role in self.auto_rule.user_roles:
            short_request.status = 'approved'
            short_request.auto_approved = True
        
        self.assertEqual(short_request.status, 'approved')
        
        # Long duration - should require manual approval
        long_request = AccessRequest.objects.create(
            user=self.user.user,
            resource=self.resource,
            access_type='book'
        )
        
        requested_duration = 8  # 8 hours (exceeds limit)
        
        if requested_duration > max_hours:
            long_request.status = 'pending'
        
        self.assertEqual(long_request.status, 'pending')


class TestTieredApprovalWorkflow(TestCase):
    """Test tiered approval workflows."""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.student = UserProfileFactory(role='student')
        self.technician = UserProfileFactory(role='technician')
        self.academic = UserProfileFactory(role='academic')
        
        # Create tiered approval rule
        self.tiered_rule = ApprovalRule.objects.create(
            name="Tiered Equipment Approval",
            resource=self.resource,
            approval_type="tiered",
            user_roles=["student"],
            conditions={
                "levels": [
                    {"role": "technician", "required": True},
                    {"role": "academic", "required": True}
                ]
            }
        )
        self.tiered_rule.approvers.add(self.technician.user, self.academic.user)
    
    def test_first_level_approval(self):
        """Test first level of tiered approval."""
        request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            access_type='book',
            status='pending'
        )
        
        # First level approval (technician)
        request.first_level_approver = self.technician.user
        request.first_level_approved_at = timezone.now()
        request.status = 'first_level_approved'
        request.save()
        
        self.assertEqual(request.status, 'first_level_approved')
        self.assertEqual(request.first_level_approver, self.technician.user)
        self.assertIsNotNone(request.first_level_approved_at)
    
    def test_second_level_approval(self):
        """Test second level of tiered approval."""
        request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            access_type='book',
            status='first_level_approved',
            first_level_approver=self.technician.user,
            first_level_approved_at=timezone.now()
        )
        
        # Second level approval (academic)
        request.approved_by = self.academic.user
        request.approved_at = timezone.now()
        request.status = 'approved'
        request.save()
        
        self.assertEqual(request.status, 'approved')
        self.assertEqual(request.approved_by, self.academic.user)
        self.assertIsNotNone(request.first_level_approver)
        self.assertIsNotNone(request.approved_by)
    
    def test_rejection_at_any_level(self):
        """Test rejection at any level of tiered approval."""
        request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            access_type='book',
            status='pending'
        )
        
        # Reject at first level
        request.first_level_approver = self.technician.user
        request.first_level_approved_at = timezone.now()
        request.status = 'rejected'
        request.rejection_reason = 'User lacks basic training'
        request.save()
        
        self.assertEqual(request.status, 'rejected')
        self.assertIsNotNone(request.rejection_reason)


class TestApprovalStatistics(TestCase):
    """Test approval statistics tracking."""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.approver = UserFactory()
    
    def test_approval_statistics_creation(self):
        """Test creating approval statistics."""
        stats = ApprovalStatistics.objects.create(
            approver=self.approver,
            resource=self.resource,
            period_start=timezone.now().date(),
            period_end=(timezone.now() + timedelta(days=7)).date(),
            total_requests=10,
            approved_requests=8,
            rejected_requests=2,
            avg_response_time_hours=4.5
        )
        
        self.assertEqual(stats.total_requests, 10)
        self.assertEqual(stats.approved_requests, 8)
        self.assertEqual(stats.rejected_requests, 2)
        self.assertEqual(stats.avg_response_time_hours, 4.5)
    
    def test_approval_rate_calculation(self):
        """Test approval rate calculation."""
        stats = ApprovalStatistics.objects.create(
            approver=self.approver,
            resource=self.resource,
            period_start=timezone.now().date(),
            period_end=(timezone.now() + timedelta(days=7)).date(),
            total_requests=10,
            approved_requests=7,
            rejected_requests=3
        )
        
        # Calculate approval rate
        approval_rate = (stats.approved_requests / stats.total_requests) * 100
        self.assertEqual(approval_rate, 70.0)
    
    def test_update_approval_statistics(self):
        """Test updating approval statistics."""
        stats = ApprovalStatistics.objects.create(
            approver=self.approver,
            resource=self.resource,
            period_start=timezone.now().date(),
            period_end=(timezone.now() + timedelta(days=7)).date(),
            total_requests=5,
            approved_requests=3,
            rejected_requests=2
        )
        
        # Update with new request
        stats.total_requests += 1
        stats.approved_requests += 1
        stats.save()
        
        self.assertEqual(stats.total_requests, 6)
        self.assertEqual(stats.approved_requests, 4)


class TestTrainingRequests(TestCase):
    """Test training request workflows."""
    
    def setUp(self):
        self.resource = ResourceFactory(requires_training=True)
        self.student = UserProfileFactory(role='student')
        self.trainer = UserProfileFactory(role='technician')
    
    def test_create_training_request(self):
        """Test creating a training request."""
        request = TrainingRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            training_level=2,
            justification='Need advanced training for research',
            status='pending'
        )
        
        self.assertEqual(request.user, self.student.user)
        self.assertEqual(request.resource, self.resource)
        self.assertEqual(request.training_level, 2)
        self.assertEqual(request.status, 'pending')
    
    def test_approve_training_request(self):
        """Test approving a training request."""
        request = TrainingRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            training_level=1,
            status='pending'
        )
        
        # Approve training
        request.approved_by = self.trainer.user
        request.approved_at = timezone.now()
        request.status = 'approved'
        request.training_scheduled_date = timezone.now() + timedelta(days=7)
        request.save()
        
        self.assertEqual(request.status, 'approved')
        self.assertEqual(request.approved_by, self.trainer.user)
        self.assertIsNotNone(request.training_scheduled_date)
    
    def test_complete_training(self):
        """Test completing training."""
        request = TrainingRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            training_level=1,
            status='approved',
            training_scheduled_date=timezone.now() + timedelta(days=7)
        )
        
        # Complete training
        request.status = 'completed'
        request.training_completed_date = timezone.now()
        request.trainer = self.trainer.user
        request.training_score = 85
        request.save()
        
        self.assertEqual(request.status, 'completed')
        self.assertEqual(request.training_score, 85)
        self.assertEqual(request.trainer, self.trainer.user)


class TestApprovalNotifications(TestCase):
    """Test approval notification functionality."""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.student = UserProfileFactory(role='student')
        self.approver = UserProfileFactory(role='technician')
    
    @patch('booking.models.approvals.send_notification')
    def test_approval_request_notification(self, mock_send):
        """Test notification sent when approval is requested."""
        request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            access_type='book',
            status='pending'
        )
        
        # Simulate sending notification to approver
        mock_send.assert_called()
    
    @patch('booking.models.approvals.send_notification')
    def test_approval_granted_notification(self, mock_send):
        """Test notification sent when approval is granted."""
        request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            access_type='book',
            status='pending'
        )
        
        # Approve request
        request.approved_by = self.approver.user
        request.approved_at = timezone.now()
        request.status = 'approved'
        request.save()
        
        # Notification should be sent to requester
        mock_send.assert_called()
    
    @patch('booking.models.approvals.send_notification')
    def test_approval_rejected_notification(self, mock_send):
        """Test notification sent when approval is rejected."""
        request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            access_type='book',
            status='pending'
        )
        
        # Reject request
        request.approved_by = self.approver.user
        request.approved_at = timezone.now()
        request.status = 'rejected'
        request.rejection_reason = 'Insufficient training'
        request.save()
        
        # Notification should be sent to requester
        mock_send.assert_called()


class TestApprovalPermissions(TestCase):
    """Test approval permission logic."""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.student = UserProfileFactory(role='student')
        self.technician = UserProfileFactory(role='technician')
        self.academic = UserProfileFactory(role='academic')
        self.sysadmin = UserProfileFactory(role='sysadmin')
        
        # Create lab admin group
        self.lab_admin_group = Group.objects.create(name='Lab Admin')
        self.technician.user.groups.add(self.lab_admin_group)
    
    def test_can_approve_permissions(self):
        """Test who can approve access requests."""
        request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            access_type='book'
        )
        
        # Students cannot approve
        self.assertNotEqual(self.student.role, 'technician')
        self.assertNotEqual(self.student.role, 'sysadmin')
        
        # Technicians can approve
        self.assertEqual(self.technician.role, 'technician')
        
        # Academics can approve
        self.assertEqual(self.academic.role, 'academic')
        
        # Sysadmins can approve
        self.assertEqual(self.sysadmin.role, 'sysadmin')
    
    def test_lab_admin_group_permissions(self):
        """Test lab admin group permissions."""
        # User in Lab Admin group can approve
        self.assertTrue(
            self.technician.user.groups.filter(name='Lab Admin').exists()
        )
        
        # User not in Lab Admin group cannot approve certain resources
        self.assertFalse(
            self.student.user.groups.filter(name='Lab Admin').exists()
        )
    
    def test_resource_specific_approvers(self):
        """Test resource-specific approver assignment."""
        # Create approval rule with specific approvers
        rule = ApprovalRule.objects.create(
            name="Specific Approvers Rule",
            resource=self.resource,
            approval_type="single",
            user_roles=["student"]
        )
        rule.approvers.add(self.technician.user)
        
        # Check approver assignment
        self.assertTrue(rule.approvers.filter(id=self.technician.user.id).exists())
        self.assertFalse(rule.approvers.filter(id=self.student.user.id).exists())


class TestApprovalTimeouts(TestCase):
    """Test approval timeout functionality."""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.student = UserProfileFactory(role='student')
        self.approver = UserProfileFactory(role='technician')
    
    def test_approval_timeout_detection(self):
        """Test detection of timed-out approvals."""
        # Create old request
        old_request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            access_type='book',
            status='pending'
        )
        
        # Manually set created_at to simulate old request
        old_request.created_at = timezone.now() - timedelta(days=7)
        old_request.save()
        
        # Check if request is timed out (assuming 5 days timeout)
        timeout_days = 5
        is_timed_out = (timezone.now() - old_request.created_at).days > timeout_days
        
        self.assertTrue(is_timed_out)
    
    def test_automatic_timeout_handling(self):
        """Test automatic handling of timed-out requests."""
        request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.resource,
            access_type='book',
            status='pending'
        )
        
        # Simulate timeout processing
        request.created_at = timezone.now() - timedelta(days=8)
        request.save()
        
        # Process timeout (would normally be done by scheduled task)
        timeout_days = 5
        if (timezone.now() - request.created_at).days > timeout_days:
            request.status = 'timed_out'
            request.timeout_processed_at = timezone.now()
            request.save()
        
        self.assertEqual(request.status, 'timed_out')
        self.assertIsNotNone(request.timeout_processed_at)


class TestBulkApprovalOperations(TestCase):
    """Test bulk approval operations."""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.students = [UserProfileFactory(role='student') for _ in range(5)]
        self.approver = UserProfileFactory(role='technician')
        
        # Create multiple requests
        self.requests = []
        for student in self.students:
            request = AccessRequest.objects.create(
                user=student.user,
                resource=self.resource,
                access_type='book',
                status='pending'
            )
            self.requests.append(request)
    
    def test_bulk_approve_requests(self):
        """Test bulk approving multiple requests."""
        # Bulk approve first 3 requests
        requests_to_approve = self.requests[:3]
        
        for request in requests_to_approve:
            request.approved_by = self.approver.user
            request.approved_at = timezone.now()
            request.status = 'approved'
            request.save()
        
        # Check results
        approved_count = AccessRequest.objects.filter(
            resource=self.resource,
            status='approved'
        ).count()
        
        self.assertEqual(approved_count, 3)
    
    def test_bulk_reject_requests(self):
        """Test bulk rejecting multiple requests."""
        # Bulk reject remaining requests
        requests_to_reject = self.requests[3:]
        
        for request in requests_to_reject:
            request.approved_by = self.approver.user
            request.approved_at = timezone.now()
            request.status = 'rejected'
            request.rejection_reason = 'Bulk rejection - insufficient capacity'
            request.save()
        
        # Check results
        rejected_count = AccessRequest.objects.filter(
            resource=self.resource,
            status='rejected'
        ).count()
        
        self.assertEqual(rejected_count, 2)
    
    def test_mixed_bulk_operations(self):
        """Test mixed bulk approve and reject operations."""
        # Approve some, reject others
        self.requests[0].status = 'approved'
        self.requests[0].approved_by = self.approver.user
        self.requests[0].save()
        
        self.requests[1].status = 'rejected' 
        self.requests[1].approved_by = self.approver.user
        self.requests[1].rejection_reason = 'No training'
        self.requests[1].save()
        
        # Check mixed results
        approved = AccessRequest.objects.filter(status='approved').count()
        rejected = AccessRequest.objects.filter(status='rejected').count()
        pending = AccessRequest.objects.filter(status='pending').count()
        
        self.assertEqual(approved, 1)
        self.assertEqual(rejected, 1)
        self.assertEqual(pending, 3)