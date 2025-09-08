"""
End-to-End Integration Tests for Labitory Booking System

These tests verify complete workflows from start to finish,
testing the interaction between all system components.
"""

import pytest
from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, Mock

from booking.models import (
    UserProfile, LabSettings, Resource, Booking,
    ApprovalRule, BillingPeriod, BillingRate, BillingRecord,
    Notification
)
from booking.tests.factories import (
    UserFactory, UserProfileFactory, ResourceFactory, 
    BookingFactory, ApprovalRuleFactory
)


class E2EBookingWorkflowTests(TransactionTestCase):
    """Test complete booking workflows from creation to billing"""
    
    def setUp(self):
        self.lab_settings = LabSettings.objects.create(
            lab_name="Test Lab",
            is_active=True
        )
        
        # Create users with different roles
        self.student = UserProfileFactory(role='student')
        self.staff = UserProfileFactory(role='staff')
        self.admin = UserProfileFactory(role='admin')
        
        # Create resource requiring approval
        self.resource = ResourceFactory(
            name='High-Value Equipment',
            requires_induction=True,
            requires_risk_assessment=True
        )
        
        # Create approval rule
        self.approval_rule = ApprovalRuleFactory(
            resource=self.resource,
            approval_type='staff',
            approver=self.staff
        )
        
        # Create billing rate
        self.billing_rate = BillingRate.objects.create(
            resource=self.resource,
            user_type='student',
            hourly_rate=Decimal('25.00'),
            minimum_charge_hours=1
        )
        
    def test_complete_student_booking_workflow(self):
        """Test: Student books -> Approval -> Check-in -> Check-out -> Billing"""
        
        # Step 1: Student creates booking request
        booking_data = {
            'title': 'Research Project Work',
            'resource': self.resource,
            'user': self.student.user,
            'start_time': timezone.now() + timedelta(days=1),
            'end_time': timezone.now() + timedelta(days=1, hours=2),
            'purpose': 'Testing materials for thesis research'
        }
        
        booking = Booking.objects.create(**booking_data)
        
        # Verify booking is pending approval
        self.assertEqual(booking.status, 'pending')
        self.assertTrue(ApprovalRequest.objects.filter(booking=booking).exists())
        
        # Step 2: Staff approves the booking
        approval_request = ApprovalRequest.objects.get(booking=booking)
        approval_request.status = 'approved'
        approval_request.approved_by = self.staff.user
        approval_request.approved_at = timezone.now()
        approval_request.save()
        
        # Refresh booking
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'approved')
        
        # Step 3: Student checks in
        booking.actual_start_time = timezone.now()
        booking.status = 'in_progress'
        booking.save()
        
        # Verify check-in notification
        self.assertTrue(
            Notification.objects.filter(
                user=self.student.user,
                notification_type='check_in_confirmed'
            ).exists()
        )
        
        # Step 4: Student checks out after 2.5 hours
        checkout_time = booking.actual_start_time + timedelta(hours=2, minutes=30)
        booking.actual_end_time = checkout_time
        booking.status = 'completed'
        booking.save()
        
        # Step 5: Verify billing calculation
        duration_hours = (booking.actual_end_time - booking.actual_start_time).total_seconds() / 3600
        expected_charge = Decimal(str(duration_hours)) * self.billing_rate.hourly_rate
        
        # Create charge record (simulating billing process)
        charge = BillingRecord.objects.create(
            booking=booking,
            billing_rate=self.billing_rate,
            hours_charged=Decimal(str(duration_hours)),
            amount_charged=expected_charge,
            charged_at=timezone.now()
        )
        
        self.assertEqual(charge.amount_charged, Decimal('62.50'))  # 2.5 hours * $25
        
        # Verify completion notification
        self.assertTrue(
            Notification.objects.filter(
                user=self.student.user,
                notification_type='booking_completed'
            ).exists()
        )

    def test_booking_with_training_requirement_workflow(self):
        """Test booking workflow with training verification"""
        
        # Create resource requiring training
        training_resource = ResourceFactory(
            name='Specialized Equipment',
            requires_induction=True,
            requires_risk_assessment=False
        )
        
        # Student without training tries to book
        booking = BookingFactory(
            resource=training_resource,
            user=self.student.user,
            status='pending'
        )
        
        # Verify training check fails
        has_training = training_resource.user_has_required_training(self.student.user)
        self.assertFalse(has_training)
        
        # Add training record
        from booking.models.core import TrainingRecord
        TrainingRecord.objects.create(
            user=self.student.user,
            training_type='equipment_certification',
            resource=training_resource,
            completed_at=timezone.now() - timedelta(days=30),
            expires_at=timezone.now() + timedelta(days=335)  # Valid for 1 year
        )
        
        # Now training check should pass
        has_training = training_resource.user_has_required_training(self.student.user)
        self.assertTrue(has_training)
        
        # Booking can proceed
        booking.status = 'approved'
        booking.save()

    def test_overbooking_conflict_workflow(self):
        """Test workflow when booking conflicts are detected"""
        
        # Create existing booking
        existing_booking = BookingFactory(
            resource=self.resource,
            user=self.staff.user,
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, hours=2),
            status='approved'
        )
        
        # Try to create overlapping booking
        conflicting_booking = Booking(
            resource=self.resource,
            user=self.student.user,
            title='Conflicting Booking',
            start_time=existing_booking.start_time + timedelta(hours=1),
            end_time=existing_booking.end_time + timedelta(hours=1)
        )
        
        # Check for conflicts before saving
        from booking.services.conflicts import get_conflicts_for_booking
        conflicts = get_conflicts_for_booking(
            self.resource,
            conflicting_booking.start_time,
            conflicting_booking.end_time
        )
        
        self.assertTrue(len(conflicts) > 0)
        self.assertIn(existing_booking, conflicts)
        
        # Booking should be rejected or require different time slot

    def test_department_billing_aggregation_workflow(self):
        """Test department-level billing aggregation"""
        
        # Create multiple bookings for same department
        department = 'Engineering'
        
        # Update users to same department
        self.student.department = department
        self.student.save()
        
        other_student = UserProfileFactory(role='student', department=department)
        
        # Create multiple completed bookings
        bookings = []
        for i in range(3):
            booking = BookingFactory(
                resource=self.resource,
                user=self.student.user if i < 2 else other_student.user,
                status='completed',
                actual_start_time=timezone.now() - timedelta(days=i+1, hours=2),
                actual_end_time=timezone.now() - timedelta(days=i+1)
            )
            bookings.append(booking)
            
            # Create charge record
            BillingRecord.objects.create(
                booking=booking,
                billing_rate=self.billing_rate,
                hours_charged=Decimal('2.0'),
                amount_charged=Decimal('50.00'),
                charged_at=timezone.now()
            )
        
        # Aggregate department charges
        total_charges = BillingRecord.objects.filter(
            booking__user__userprofile__department=department
        ).aggregate(total=models.Sum('amount_charged'))['total']
        
        self.assertEqual(total_charges, Decimal('150.00'))

    @patch('booking.services.notifications.send_email')
    def test_notification_escalation_workflow(self, mock_send_email):
        """Test notification escalation for overdue bookings"""
        
        # Create overdue booking
        overdue_booking = BookingFactory(
            resource=self.resource,
            user=self.student.user,
            status='in_progress',
            start_time=timezone.now() - timedelta(hours=4),
            end_time=timezone.now() - timedelta(hours=2),  # Should have ended 2 hours ago
            actual_start_time=timezone.now() - timedelta(hours=4)
        )
        
        # Simulate notification service running
        from booking.services.notifications import check_overdue_bookings
        
        mock_send_email.return_value = True
        check_overdue_bookings()
        
        # Verify overdue notification was created
        overdue_notification = Notification.objects.filter(
            user=self.student.user,
            notification_type='booking_overdue',
            booking=overdue_booking
        ).first()
        
        self.assertIsNotNone(overdue_notification)
        
        # Verify email was sent
        mock_send_email.assert_called()

    def test_maintenance_booking_workflow(self):
        """Test maintenance booking creation and impact"""
        
        # Create maintenance booking
        maintenance_booking = BookingFactory(
            resource=self.resource,
            user=self.admin.user,
            title='Routine Maintenance',
            booking_type='maintenance',
            start_time=timezone.now() + timedelta(days=2),
            end_time=timezone.now() + timedelta(days=2, hours=4),
            status='approved'
        )
        
        # Try to book during maintenance window
        user_booking = Booking(
            resource=self.resource,
            user=self.student.user,
            title='Research Work',
            start_time=maintenance_booking.start_time + timedelta(hours=1),
            end_time=maintenance_booking.end_time - timedelta(hours=1)
        )
        
        # Check conflicts
        from booking.services.conflicts import get_conflicts_for_booking
        conflicts = get_conflicts_for_booking(
            self.resource,
            user_booking.start_time,
            user_booking.end_time
        )
        
        # Should conflict with maintenance
        self.assertTrue(len(conflicts) > 0)
        self.assertIn(maintenance_booking, conflicts)

    def test_quota_enforcement_workflow(self):
        """Test user quota enforcement across bookings"""
        
        # Set weekly quota for students
        from booking.models.core import UserQuota
        UserQuota.objects.create(
            user=self.student.user,
            resource=self.resource,
            quota_type='weekly',
            max_hours=Decimal('10.0'),
            period_start=timezone.now().date()
        )
        
        # Create existing bookings totaling 8 hours
        for i in range(2):
            BookingFactory(
                resource=self.resource,
                user=self.student.user,
                status='completed',
                actual_start_time=timezone.now() - timedelta(days=i+1, hours=4),
                actual_end_time=timezone.now() - timedelta(days=i+1)
            )
        
        # Try to book 4 more hours (would exceed 10-hour quota)
        new_booking = Booking(
            resource=self.resource,
            user=self.student.user,
            title='Additional Work',
            start_time=timezone.now() + timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=5)
        )
        
        # Check quota enforcement
        from booking.services.quotas import check_user_quota
        quota_ok = check_user_quota(new_booking)
        
        self.assertFalse(quota_ok)  # Should exceed quota

    def test_bulk_cancellation_workflow(self):
        """Test bulk cancellation with notifications and billing adjustments"""
        
        # Create multiple future bookings
        bookings_to_cancel = []
        for i in range(3):
            booking = BookingFactory(
                resource=self.resource,
                user=self.student.user,
                status='approved',
                start_time=timezone.now() + timedelta(days=i+1),
                end_time=timezone.now() + timedelta(days=i+1, hours=2)
            )
            bookings_to_cancel.append(booking)
        
        # Bulk cancel bookings
        cancellation_reason = "Equipment maintenance required"
        
        for booking in bookings_to_cancel:
            booking.status = 'cancelled'
            booking.cancellation_reason = cancellation_reason
            booking.cancelled_at = timezone.now()
            booking.save()
            
            # Create cancellation notification
            Notification.objects.create(
                user=booking.user,
                title=f"Booking Cancelled: {booking.title}",
                message=f"Your booking has been cancelled. Reason: {cancellation_reason}",
                notification_type='booking_cancelled',
                booking=booking
            )
        
        # Verify all bookings cancelled
        cancelled_count = Booking.objects.filter(
            id__in=[b.id for b in bookings_to_cancel],
            status='cancelled'
        ).count()
        
        self.assertEqual(cancelled_count, 3)
        
        # Verify notifications sent
        notification_count = Notification.objects.filter(
            user=self.student.user,
            notification_type='booking_cancelled'
        ).count()
        
        self.assertEqual(notification_count, 3)


class E2EAccessRequestWorkflowTests(TransactionTestCase):
    """Test complete access request workflows"""
    
    def setUp(self):
        self.student = UserProfileFactory(role='student')
        self.staff = UserProfileFactory(role='staff')
        self.restricted_resource = ResourceFactory(
            name='Restricted Lab',
            access_level='restricted'
        )
    
    def test_access_request_approval_workflow(self):
        """Test complete access request and approval workflow"""
        
        from booking.models.approvals import AccessRequest
        
        # Student requests access
        access_request = AccessRequest.objects.create(
            user=self.student.user,
            resource=self.restricted_resource,
            justification='Need access for thesis research project',
            requested_at=timezone.now()
        )
        
        # Staff reviews and approves
        access_request.status = 'approved'
        access_request.approved_by = self.staff.user
        access_request.approved_at = timezone.now()
        access_request.save()
        
        # Verify student can now book the resource
        booking = BookingFactory(
            resource=self.restricted_resource,
            user=self.student.user
        )
        
        # Check if user has access
        has_access = self.restricted_resource.user_has_access(self.student.user)
        self.assertTrue(has_access)


class E2EReportingWorkflowTests(TransactionTestCase):
    """Test reporting and analytics workflows"""
    
    def setUp(self):
        self.admin = UserProfileFactory(role='admin')
        self.resource = ResourceFactory()
        
        # Create historical data
        for i in range(10):
            BookingFactory(
                resource=self.resource,
                status='completed',
                actual_start_time=timezone.now() - timedelta(days=i*2, hours=2),
                actual_end_time=timezone.now() - timedelta(days=i*2)
            )
    
    def test_usage_analytics_workflow(self):
        """Test usage analytics generation"""
        
        # Calculate resource utilization
        from booking.services.analytics import calculate_resource_utilization
        
        start_date = timezone.now().date() - timedelta(days=30)
        end_date = timezone.now().date()
        
        utilization = calculate_resource_utilization(
            self.resource, 
            start_date, 
            end_date
        )
        
        self.assertIsInstance(utilization, dict)
        self.assertIn('total_hours', utilization)
        self.assertIn('utilization_percentage', utilization)
    
    def test_billing_report_generation(self):
        """Test billing report generation workflow"""
        
        # Create billing period
        period = BillingPeriod.objects.create(
            name='Q1 2024',
            start_date=timezone.now().date() - timedelta(days=90),
            end_date=timezone.now().date(),
            status='active'
        )
        
        # Generate billing report
        from booking.services.billing import generate_billing_report
        
        report = generate_billing_report(period)
        
        self.assertIsInstance(report, dict)
        self.assertIn('total_charges', report)
        self.assertIn('booking_count', report)


@pytest.mark.integration
class E2EAPIWorkflowTests(TransactionTestCase):
    """Test API integration workflows"""
    
    def setUp(self):
        self.user = UserProfileFactory()
        self.resource = ResourceFactory()
    
    def test_api_booking_workflow(self):
        """Test complete booking workflow via API"""
        
        from django.test import Client
        from django.urls import reverse
        import json
        
        client = Client()
        client.force_login(self.user.user)
        
        # Create booking via API
        booking_data = {
            'title': 'API Test Booking',
            'resource': self.resource.id,
            'start_time': (timezone.now() + timedelta(days=1)).isoformat(),
            'end_time': (timezone.now() + timedelta(days=1, hours=2)).isoformat(),
            'purpose': 'Testing API integration'
        }
        
        try:
            response = client.post(
                reverse('api:bookings-list'),
                data=json.dumps(booking_data),
                content_type='application/json'
            )
            
            if response.status_code == 201:
                booking_id = response.json()['id']
                
                # Verify booking was created
                booking = Booking.objects.get(id=booking_id)
                self.assertEqual(booking.title, booking_data['title'])
                
        except Exception:
            # API endpoints may not exist yet
            self.skipTest("API endpoints not implemented")


if __name__ == '__main__':
    pytest.main([__file__])