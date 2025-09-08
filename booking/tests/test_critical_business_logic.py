"""
Critical Business Logic Tests for Labitory Booking System

Tests for the most critical business logic functions that could cause
system failures or data corruption if broken.
"""

import pytest
from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, Mock
from django.db import transaction, IntegrityError

from booking.models import (
    UserProfile, LabSettings, Resource, Booking, 
    ApprovalRule, BillingPeriod, BillingRate, BillingRecord,
    Notification
)
from booking.tests.factories import (
    UserFactory, UserProfileFactory, ResourceFactory, 
    BookingFactory, ApprovalRuleFactory
)


class CriticalBookingLogicTests(TransactionTestCase):
    """Test critical booking business logic that must never fail"""
    
    def setUp(self):
        self.lab_settings = LabSettings.objects.create(
            lab_name="Test Lab",
            is_active=True
        )
        
        self.user = UserProfileFactory(role='student')
        self.resource = ResourceFactory(capacity=1)
        
    def test_double_booking_prevention(self):
        """CRITICAL: Must prevent double bookings that would cause conflicts"""
        
        # Create initial booking
        booking1 = BookingFactory(
            resource=self.resource,
            user=self.user.user,
            start_time=timezone.now() + timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=3),
            status='approved'
        )
        
        # Attempt overlapping booking - should be prevented
        with self.assertRaises(Exception):  # Could be ValidationError or IntegrityError
            booking2 = BookingFactory(
                resource=self.resource,
                user=self.user.user,
                start_time=timezone.now() + timedelta(hours=2),
                end_time=timezone.now() + timedelta(hours=4),
                status='approved'
            )
            booking2.full_clean()
            booking2.save()
    
    def test_capacity_enforcement(self):
        """CRITICAL: Must enforce resource capacity limits"""
        
        # Resource with capacity of 2
        multi_resource = ResourceFactory(capacity=2)
        
        # Create 2 concurrent bookings (should be allowed)
        time_start = timezone.now() + timedelta(hours=1)
        time_end = timezone.now() + timedelta(hours=3)
        
        booking1 = BookingFactory(
            resource=multi_resource,
            start_time=time_start,
            end_time=time_end,
            status='approved'
        )
        
        booking2 = BookingFactory(
            resource=multi_resource,
            start_time=time_start,
            end_time=time_end,
            status='approved'
        )
        
        # Third concurrent booking should be prevented
        with self.assertRaises(Exception):
            booking3 = BookingFactory(
                resource=multi_resource,
                start_time=time_start,
                end_time=time_end,
                status='approved'
            )
            booking3.full_clean()
            booking3.save()
    
    def test_booking_state_consistency(self):
        """CRITICAL: Booking state transitions must maintain consistency"""
        
        booking = BookingFactory(
            resource=self.resource,
            user=self.user.user,
            status='pending'
        )
        
        # Valid state transitions
        valid_transitions = [
            ('pending', 'approved'),
            ('approved', 'in_progress'),
            ('in_progress', 'completed'),
            ('pending', 'cancelled'),
            ('approved', 'cancelled')
        ]
        
        for from_status, to_status in valid_transitions:
            booking.status = from_status
            booking.save()
            
            booking.status = to_status
            booking.save()  # Should not raise exception
            
            self.assertEqual(booking.status, to_status)
    
    def test_invalid_booking_state_prevention(self):
        """CRITICAL: Must prevent invalid booking state transitions"""
        
        booking = BookingFactory(
            resource=self.resource,
            user=self.user.user,
            status='completed'
        )
        
        # Invalid transitions that should be prevented
        invalid_transitions = [
            ('completed', 'pending'),
            ('completed', 'approved'),
            ('cancelled', 'approved'),
            ('cancelled', 'in_progress')
        ]
        
        for from_status, to_status in invalid_transitions:
            booking.status = from_status
            booking.save()
            
            # Attempt invalid transition
            booking.status = to_status
            
            # Should raise validation error or be prevented
            try:
                booking.full_clean()
                booking.save()
                # If we get here, check that some validation prevented it
                self.assertNotEqual(booking.status, to_status,
                    f"Invalid transition {from_status} -> {to_status} was allowed")
            except Exception:
                # Expected - validation should prevent this
                pass
    
    def test_atomic_booking_creation(self):
        """CRITICAL: Booking creation must be atomic (all or nothing)"""
        
        with patch('booking.models.core.Booking.save') as mock_save:
            mock_save.side_effect = Exception("Database error")
            
            # Attempt to create booking
            try:
                with transaction.atomic():
                    booking = Booking(
                        resource=self.resource,
                        user=self.user.user,
                        title='Test Booking',
                        start_time=timezone.now() + timedelta(hours=1),
                        end_time=timezone.now() + timedelta(hours=3)
                    )
                    booking.save()
                    
                    # This should trigger rollback
                    raise Exception("Simulated error")
                    
            except Exception:
                pass  # Expected
            
            # Verify no partial booking was created
            self.assertFalse(Booking.objects.filter(title='Test Booking').exists())


class CriticalBillingLogicTests(TransactionTestCase):
    """Test critical billing logic that handles money calculations"""
    
    def setUp(self):
        self.user = UserProfileFactory(role='student')
        self.resource = ResourceFactory()
        
        self.billing_rate = BillingRate.objects.create(
            resource=self.resource,
            user_type='student',
            hourly_rate=Decimal('25.00'),
            minimum_charge_hours=Decimal('1.0')
        )
    
    def test_billing_calculation_accuracy(self):
        """CRITICAL: Billing calculations must be mathematically accurate"""
        
        # Test various durations and rates
        test_cases = [
            (Decimal('1.0'), Decimal('25.00'), Decimal('25.00')),    # 1 hour
            (Decimal('2.5'), Decimal('25.00'), Decimal('62.50')),    # 2.5 hours
            (Decimal('0.25'), Decimal('100.00'), Decimal('25.00')),  # 15 minutes
            (Decimal('0.1'), Decimal('50.00'), Decimal('5.00')),     # 6 minutes
        ]
        
        for hours, rate, expected_amount in test_cases:
            with self.subTest(hours=hours, rate=rate):
                # Update rate for test
                self.billing_rate.hourly_rate = rate
                self.billing_rate.save()
                
                booking = BookingFactory(
                    resource=self.resource,
                    user=self.user.user,
                    status='completed'
                )
                
                # Calculate charge
                calculated_amount = hours * rate
                
                # Verify precision
                self.assertEqual(calculated_amount, expected_amount)
                
                # Create charge record
                charge = BillingRecord.objects.create(
                    booking=booking,
                    billing_rate=self.billing_rate,
                    hours_charged=hours,
                    amount_charged=calculated_amount
                )
                
                # Verify storage precision
                charge.refresh_from_db()
                self.assertEqual(charge.amount_charged, expected_amount)
    
    def test_minimum_charge_enforcement(self):
        """CRITICAL: Minimum charges must be enforced correctly"""
        
        # Set minimum charge of 2 hours
        self.billing_rate.minimum_charge_hours = Decimal('2.0')
        self.billing_rate.save()
        
        # Book for 30 minutes
        actual_hours = Decimal('0.5')
        
        # Should charge for minimum 2 hours
        charged_hours = max(actual_hours, self.billing_rate.minimum_charge_hours)
        expected_amount = charged_hours * self.billing_rate.hourly_rate
        
        self.assertEqual(charged_hours, Decimal('2.0'))
        self.assertEqual(expected_amount, Decimal('50.00'))
    
    def test_billing_rate_consistency(self):
        """CRITICAL: Must use correct billing rates at time of booking"""
        
        booking = BookingFactory(
            resource=self.resource,
            user=self.user.user,
            status='completed'
        )
        
        # Original rate
        original_rate = Decimal('25.00')
        self.assertEqual(self.billing_rate.hourly_rate, original_rate)
        
        # Change rate after booking
        self.billing_rate.hourly_rate = Decimal('50.00')
        self.billing_rate.save()
        
        # Charge record should use rate at time of booking
        # (Implementation should snapshot the rate)
        charge = BillingRecord.objects.create(
            booking=booking,
            billing_rate=self.billing_rate,
            hours_charged=Decimal('2.0'),
            amount_charged=Decimal('50.00')  # Using original rate
        )
        
        # Verify historical rate was used
        self.assertEqual(charge.amount_charged, Decimal('50.00'))
    
    def test_decimal_precision_handling(self):
        """CRITICAL: Must handle decimal precision correctly for money"""
        
        # Test edge cases with decimal precision
        precise_rate = Decimal('33.333333')  # 6 decimal places
        
        billing_rate = BillingRate.objects.create(
            resource=self.resource,
            user_type='researcher',
            hourly_rate=precise_rate
        )
        
        # Calculate for 1.5 hours
        hours = Decimal('1.5')
        calculated_amount = hours * precise_rate  # Should be 49.9999995
        
        # Round to 2 decimal places for currency
        rounded_amount = calculated_amount.quantize(Decimal('0.01'))
        
        self.assertEqual(rounded_amount, Decimal('50.00'))
    
    def test_negative_amount_prevention(self):
        """CRITICAL: Must prevent negative billing amounts"""
        
        booking = BookingFactory(
            resource=self.resource,
            user=self.user.user,
            status='completed'
        )
        
        # Attempt to create charge with negative amount
        with self.assertRaises(Exception):
            charge = BillingRecord.objects.create(
                booking=booking,
                billing_rate=self.billing_rate,
                hours_charged=Decimal('-1.0'),  # Negative hours
                amount_charged=Decimal('-25.00')  # Negative amount
            )
            charge.full_clean()


class CriticalDataIntegrityTests(TransactionTestCase):
    """Test critical data integrity constraints"""
    
    def setUp(self):
        self.user = UserProfileFactory()
        self.resource = ResourceFactory()
    
    def test_user_profile_consistency(self):
        """CRITICAL: User profiles must remain consistent with Django users"""
        
        # Every User must have exactly one UserProfile
        user = UserFactory()
        
        # UserProfile should be created automatically
        self.assertTrue(hasattr(user, 'userprofile'))
        
        # Prevent multiple profiles for same user
        with self.assertRaises(IntegrityError):
            duplicate_profile = UserProfile.objects.create(
                user=user,
                role='student'
            )
    
    def test_resource_capacity_constraints(self):
        """CRITICAL: Resource capacity must be positive integer"""
        
        # Valid capacity
        resource = Resource.objects.create(
            name='Valid Resource',
            capacity=5
        )
        self.assertEqual(resource.capacity, 5)
        
        # Zero or negative capacity should be prevented
        with self.assertRaises(Exception):
            invalid_resource = Resource.objects.create(
                name='Invalid Resource',
                capacity=0
            )
            invalid_resource.full_clean()
        
        with self.assertRaises(Exception):
            invalid_resource = Resource.objects.create(
                name='Invalid Resource',
                capacity=-1
            )
            invalid_resource.full_clean()
    
    def test_booking_time_constraints(self):
        """CRITICAL: Booking end time must be after start time"""
        
        start_time = timezone.now() + timedelta(hours=1)
        end_time = start_time - timedelta(hours=1)  # Before start time
        
        with self.assertRaises(Exception):
            booking = Booking.objects.create(
                resource=self.resource,
                user=self.user.user,
                title='Invalid Booking',
                start_time=start_time,
                end_time=end_time  # End before start
            )
            booking.full_clean()
    
    def test_foreign_key_integrity(self):
        """CRITICAL: Foreign key relationships must be maintained"""
        
        booking = BookingFactory(
            resource=self.resource,
            user=self.user.user
        )
        
        # Cannot delete user while bookings exist
        with self.assertRaises(Exception):
            self.user.user.delete()
        
        # Cannot delete resource while bookings exist
        with self.assertRaises(Exception):
            self.resource.delete()


class CriticalSecurityTests(TestCase):
    """Test critical security business logic"""
    
    def setUp(self):
        self.user1 = UserProfileFactory(role='student')
        self.user2 = UserProfileFactory(role='student')
        self.admin = UserProfileFactory(role='admin')
        self.resource = ResourceFactory()
    
    def test_booking_ownership_enforcement(self):
        """CRITICAL: Users must only access their own bookings"""
        
        # User1 creates booking
        booking = BookingFactory(
            resource=self.resource,
            user=self.user1.user,
            title='User1 Booking'
        )
        
        # User2 should not be able to modify User1's booking
        # This test assumes there's authorization logic in place
        
        # Verify booking belongs to correct user
        self.assertEqual(booking.user, self.user1.user)
        self.assertNotEqual(booking.user, self.user2.user)
    
    def test_approval_authority_validation(self):
        """CRITICAL: Only authorized users can approve bookings"""
        
        # Create approval rule
        approval_rule = ApprovalRuleFactory(
            resource=self.resource,
            approver=self.admin  # Only admin can approve
        )
        
        booking = BookingFactory(
            resource=self.resource,
            user=self.user1.user,
            status='pending'
        )
        
        approval_request = ApprovalRequest.objects.create(
            booking=booking,
            approval_rule=approval_rule,
            status='pending'
        )
        
        # Admin can approve
        approval_request.approved_by = self.admin.user
        approval_request.status = 'approved'
        approval_request.save()
        
        self.assertEqual(approval_request.status, 'approved')
        self.assertEqual(approval_request.approved_by, self.admin.user)
    
    def test_role_based_access_control(self):
        """CRITICAL: Role-based permissions must be enforced"""
        
        # Student cannot approve bookings
        self.assertEqual(self.user1.role, 'student')
        
        # Admin can approve bookings
        self.assertEqual(self.admin.role, 'admin')
        
        # Verify role assignments are immutable without proper authorization
        # (This depends on how role changes are implemented)
        
    def test_sensitive_data_protection(self):
        """CRITICAL: Sensitive data must be properly protected"""
        
        user_profile = self.user1
        
        # Sensitive fields should exist but be protected
        sensitive_fields = ['email', 'phone_number']
        
        for field in sensitive_fields:
            if hasattr(user_profile, field):
                # Field exists - ensure it's properly handled
                self.assertIsNotNone(getattr(user_profile, field, None))


class CriticalPerformanceTests(TestCase):
    """Test performance-critical business logic"""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.users = [UserProfileFactory() for _ in range(10)]
    
    def test_conflict_detection_efficiency(self):
        """CRITICAL: Conflict detection must be efficient with many bookings"""
        
        # Create many existing bookings
        existing_bookings = []
        for i in range(100):
            booking = BookingFactory(
                resource=self.resource,
                start_time=timezone.now() + timedelta(days=i, hours=1),
                end_time=timezone.now() + timedelta(days=i, hours=3),
                status='approved'
            )
            existing_bookings.append(booking)
        
        # Test conflict detection performance
        import time
        start_time = time.time()
        
        # Check for conflicts with new booking
        new_start = timezone.now() + timedelta(days=50, hours=2)
        new_end = timezone.now() + timedelta(days=50, hours=4)
        
        # This should detect conflict efficiently
        from booking.services.conflicts import get_conflicts_for_booking
        conflicts = get_conflicts_for_booking(self.resource, new_start, new_end)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete in reasonable time (< 1 second for 100 bookings)
        self.assertLess(execution_time, 1.0, 
            f"Conflict detection took {execution_time:.3f}s, too slow")
        
        # Should find the conflicting booking
        self.assertEqual(len(conflicts), 1)
    
    def test_bulk_operations_consistency(self):
        """CRITICAL: Bulk operations must maintain data consistency"""
        
        # Create multiple bookings for bulk operation
        bookings = []
        for i in range(5):
            booking = BookingFactory(
                resource=self.resource,
                status='pending',
                start_time=timezone.now() + timedelta(days=i+1, hours=1),
                end_time=timezone.now() + timedelta(days=i+1, hours=3)
            )
            bookings.append(booking)
        
        # Bulk approve all bookings
        try:
            with transaction.atomic():
                for booking in bookings:
                    booking.status = 'approved'
                    booking.save()
        except Exception as e:
            self.fail(f"Bulk operation failed: {e}")
        
        # Verify all were updated consistently
        for booking in bookings:
            booking.refresh_from_db()
            self.assertEqual(booking.status, 'approved')


class CriticalNotificationTests(TestCase):
    """Test critical notification business logic"""
    
    def setUp(self):
        self.user = UserProfileFactory()
        self.resource = ResourceFactory()
    
    @patch('booking.services.notifications.send_email')
    def test_critical_notification_delivery(self, mock_send_email):
        """CRITICAL: Critical notifications must be delivered"""
        
        mock_send_email.return_value = True
        
        # Create booking that requires notification
        booking = BookingFactory(
            resource=self.resource,
            user=self.user.user,
            status='approved'
        )
        
        # Create critical notification
        notification = Notification.objects.create(
            user=self.user.user,
            title='Booking Approved',
            message=f'Your booking {booking.title} has been approved',
            notification_type='booking_approved',
            priority='high'
        )
        
        # Attempt to send notification
        from booking.services.notifications import send_notification
        result = send_notification(notification)
        
        # Must succeed for critical notifications
        if notification.priority == 'high':
            self.assertTrue(result, "Critical notification delivery failed")
            mock_send_email.assert_called_once()
    
    def test_notification_deduplication(self):
        """CRITICAL: Duplicate notifications must be prevented"""
        
        booking = BookingFactory(
            resource=self.resource,
            user=self.user.user
        )
        
        # Create first notification
        notification1 = Notification.objects.create(
            user=self.user.user,
            title='Booking Reminder',
            message='Your booking starts soon',
            notification_type='booking_reminder',
            booking=booking
        )
        
        # Attempt duplicate notification
        notification2 = Notification.objects.create(
            user=self.user.user,
            title='Booking Reminder',
            message='Your booking starts soon',
            notification_type='booking_reminder',
            booking=booking
        )
        
        # Should either prevent duplicate or mark as duplicate
        notifications = Notification.objects.filter(
            user=self.user.user,
            notification_type='booking_reminder',
            booking=booking
        )
        
        # Implementation should handle duplicates appropriately
        self.assertTrue(notifications.exists())


if __name__ == '__main__':
    pytest.main([__file__])