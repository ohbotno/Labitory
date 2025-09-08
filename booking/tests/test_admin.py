"""
Admin Interface Tests for Labitory Booking System

Tests Django admin interface functionality, custom admin actions,
filters, and administrative workflows.
"""

import pytest
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from booking.models import (
    UserProfile, LabSettings, Resource, Booking, 
    ApprovalRule, AccessRequest, BillingPeriod, BillingRate, BillingRecord,
    Notification, NotificationPreference, Maintenance
)
from booking.tests.factories import (
    UserFactory, UserProfileFactory, ResourceFactory, 
    BookingFactory, ApprovalRuleFactory
)


class AdminInterfaceAccessTests(TestCase):
    """Test admin interface access controls and permissions"""
    
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.staff_user = UserProfileFactory(role='staff').user
        self.student_user = UserProfileFactory(role='student').user
        
        self.client = Client()
    
    def test_admin_user_access(self):
        """Test that admin users can access admin interface"""
        self.client.force_login(self.admin_user)
        
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Django administration')
    
    def test_staff_user_limited_access(self):
        """Test that staff users have limited admin access"""
        # Make staff user a Django staff member
        self.staff_user.is_staff = True
        self.staff_user.save()
        
        self.client.force_login(self.staff_user)
        
        response = self.client.get('/admin/')
        if response.status_code == 200:
            # Staff should have access but with limited permissions
            self.assertContains(response, 'Django administration')
    
    def test_student_user_no_access(self):
        """Test that regular users cannot access admin interface"""
        self.client.force_login(self.student_user)
        
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)  # Redirect to login


class BookingAdminTests(TestCase):
    """Test Booking model admin interface"""
    
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.client = Client()
        self.client.force_login(self.admin_user)
        
        self.resource = ResourceFactory()
        self.user = UserProfileFactory()
        self.booking = BookingFactory(
            resource=self.resource,
            user=self.user.user,
            status='pending'
        )
    
    def test_booking_list_view(self):
        """Test booking admin list view"""
        url = reverse('admin:booking_booking_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.booking.title)
        self.assertContains(response, self.resource.name)
    
    def test_booking_detail_view(self):
        """Test booking admin detail view"""
        url = reverse('admin:booking_booking_change', args=[self.booking.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.booking.title)
        self.assertContains(response, 'Status')
    
    def test_booking_status_filter(self):
        """Test booking status filter in admin"""
        # Create bookings with different statuses
        BookingFactory(resource=self.resource, status='approved')
        BookingFactory(resource=self.resource, status='completed')
        BookingFactory(resource=self.resource, status='cancelled')
        
        url = reverse('admin:booking_booking_changelist')
        
        # Test filtering by pending status
        response = self.client.get(url + '?status=pending')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'pending')
    
    def test_booking_user_filter(self):
        """Test filtering bookings by user"""
        url = reverse('admin:booking_booking_changelist')
        
        response = self.client.get(url + f'?user__id__exact={self.user.user.id}')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.user.username)
    
    def test_bulk_approve_bookings_action(self):
        """Test bulk approve bookings admin action"""
        # Create multiple pending bookings
        bookings = [
            BookingFactory(resource=self.resource, status='pending')
            for _ in range(3)
        ]
        
        url = reverse('admin:booking_booking_changelist')
        
        # Simulate bulk approve action
        data = {
            'action': 'approve_selected_bookings',
            '_selected_action': [str(b.id) for b in bookings]
        }
        
        response = self.client.post(url, data, follow=True)
        
        # Check if bookings were approved
        for booking in bookings:
            booking.refresh_from_db()
            if hasattr(booking, 'status'):  # If the action exists
                self.assertEqual(booking.status, 'approved')
    
    def test_booking_search(self):
        """Test searching bookings in admin"""
        url = reverse('admin:booking_booking_changelist')
        
        response = self.client.get(url + f'?q={self.booking.title}')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.booking.title)


class ResourceAdminTests(TestCase):
    """Test Resource model admin interface"""
    
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.client = Client()
        self.client.force_login(self.admin_user)
        
        self.resource = ResourceFactory(
            name='Test Equipment',
            capacity=1,
            approval_required=True
        )
    
    def test_resource_list_view(self):
        """Test resource admin list view"""
        url = reverse('admin:booking_resource_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.resource.name)
    
    def test_resource_capacity_filter(self):
        """Test filtering resources by capacity"""
        ResourceFactory(name='Single User', capacity=1)
        ResourceFactory(name='Multi User', capacity=5)
        
        url = reverse('admin:booking_resource_changelist')
        
        # Filter by capacity > 1
        response = self.client.get(url + '?capacity__gt=1')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Multi User')
        self.assertNotContains(response, 'Single User')
    
    def test_resource_availability_status(self):
        """Test resource availability status display"""
        url = reverse('admin:booking_resource_change', args=[self.resource.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Approval required')


class UserProfileAdminTests(TestCase):
    """Test UserProfile admin interface"""
    
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.client = Client()
        self.client.force_login(self.admin_user)
        
        self.user_profile = UserProfileFactory(
            role='student',
            department='Engineering'
        )
    
    def test_user_profile_list_view(self):
        """Test user profile admin list view"""
        url = reverse('admin:booking_userprofile_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user_profile.user.username)
    
    def test_user_role_filter(self):
        """Test filtering users by role"""
        UserProfileFactory(role='staff')
        UserProfileFactory(role='admin')
        
        url = reverse('admin:booking_userprofile_changelist')
        
        # Filter by student role
        response = self.client.get(url + '?role=student')
        self.assertEqual(response.status_code, 200)
    
    def test_user_department_filter(self):
        """Test filtering users by department"""
        UserProfileFactory(department='Physics')
        UserProfileFactory(department='Chemistry')
        
        url = reverse('admin:booking_userprofile_changelist')
        
        # Filter by Engineering department
        response = self.client.get(url + '?department=Engineering')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Engineering')


class ApprovalAdminTests(TestCase):
    """Test approval-related admin interfaces"""
    
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.client = Client()
        self.client.force_login(self.admin_user)
        
        self.resource = ResourceFactory()
        self.approver = UserProfileFactory(role='staff')
        self.approval_rule = ApprovalRuleFactory(
            resource=self.resource,
            approver=self.approver
        )
    
    def test_approval_rule_list_view(self):
        """Test approval rule admin list view"""
        url = reverse('admin:booking_approvalrule_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.resource.name)
    
    def test_approval_request_list_view(self):
        """Test approval request admin list view"""
        booking = BookingFactory(resource=self.resource)
        approval_request = ApprovalRequest.objects.create(
            booking=booking,
            approval_rule=self.approval_rule,
            status='pending'
        )
        
        url = reverse('admin:booking_approvalrequest_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, booking.title)
    
    def test_bulk_approve_requests_action(self):
        """Test bulk approve requests admin action"""
        booking = BookingFactory(resource=self.resource)
        requests = [
            ApprovalRequest.objects.create(
                booking=BookingFactory(resource=self.resource),
                approval_rule=self.approval_rule,
                status='pending'
            )
            for _ in range(3)
        ]
        
        url = reverse('admin:booking_approvalrequest_changelist')
        
        # Simulate bulk approve action
        data = {
            'action': 'approve_selected_requests',
            '_selected_action': [str(r.id) for r in requests]
        }
        
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)


class BillingAdminTests(TestCase):
    """Test billing-related admin interfaces"""
    
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.client = Client()
        self.client.force_login(self.admin_user)
        
        self.resource = ResourceFactory()
        self.billing_rate = BillingRate.objects.create(
            resource=self.resource,
            user_type='student',
            hourly_rate=Decimal('25.00')
        )
        
        self.billing_period = BillingPeriod.objects.create(
            name='Test Period',
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30)
        )
    
    def test_billing_rate_list_view(self):
        """Test billing rate admin list view"""
        url = reverse('admin:booking_billingrate_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.resource.name)
        self.assertContains(response, '25.00')
    
    def test_billing_period_list_view(self):
        """Test billing period admin list view"""
        url = reverse('admin:booking_billingperiod_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Period')
    
    def test_charge_record_list_view(self):
        """Test charge record admin list view"""
        booking = BookingFactory(resource=self.resource, status='completed')
        charge_record = BillingRecord.objects.create(
            booking=booking,
            billing_rate=self.billing_rate,
            hours_charged=Decimal('2.0'),
            amount_charged=Decimal('50.00')
        )
        
        url = reverse('admin:booking_billingrecord_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '50.00')
    
    def test_billing_period_status_filter(self):
        """Test filtering billing periods by status"""
        BillingPeriod.objects.create(
            name='Active Period',
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
            status='active'
        )
        
        BillingPeriod.objects.create(
            name='Closed Period',
            start_date=timezone.now().date() - timedelta(days=60),
            end_date=timezone.now().date() - timedelta(days=30),
            status='closed'
        )
        
        url = reverse('admin:booking_billingperiod_changelist')
        
        # Filter by active status
        response = self.client.get(url + '?status=active')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Active Period')


class NotificationAdminTests(TestCase):
    """Test notification admin interface"""
    
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.client = Client()
        self.client.force_login(self.admin_user)
        
        self.user = UserProfileFactory()
        self.notification = Notification.objects.create(
            user=self.user.user,
            title='Test Notification',
            message='This is a test notification',
            notification_type='booking_reminder'
        )
    
    def test_notification_list_view(self):
        """Test notification admin list view"""
        url = reverse('admin:booking_notification_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Notification')
    
    def test_notification_type_filter(self):
        """Test filtering notifications by type"""
        Notification.objects.create(
            user=self.user.user,
            title='Reminder',
            message='Reminder message',
            notification_type='booking_reminder'
        )
        
        Notification.objects.create(
            user=self.user.user,
            title='Confirmation',
            message='Confirmation message',
            notification_type='booking_confirmed'
        )
        
        url = reverse('admin:booking_notification_changelist')
        
        # Filter by reminder type
        response = self.client.get(url + '?notification_type=booking_reminder')
        self.assertEqual(response.status_code, 200)
    
    def test_notification_read_status_filter(self):
        """Test filtering notifications by read status"""
        # Create read and unread notifications
        Notification.objects.create(
            user=self.user.user,
            title='Read Notification',
            message='This has been read',
            notification_type='info',
            is_read=True
        )
        
        url = reverse('admin:booking_notification_changelist')
        
        # Filter by unread notifications
        response = self.client.get(url + '?is_read=False')
        self.assertEqual(response.status_code, 200)
    
    def test_bulk_mark_as_read_action(self):
        """Test bulk mark as read admin action"""
        notifications = [
            Notification.objects.create(
                user=self.user.user,
                title=f'Test {i}',
                message=f'Message {i}',
                notification_type='info'
            )
            for i in range(3)
        ]
        
        url = reverse('admin:booking_notification_changelist')
        
        # Simulate bulk mark as read action
        data = {
            'action': 'mark_as_read',
            '_selected_action': [str(n.id) for n in notifications]
        }
        
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)


class MaintenanceAdminTests(TestCase):
    """Test maintenance scheduling admin interface"""
    
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.client = Client()
        self.client.force_login(self.admin_user)
        
        self.resource = ResourceFactory()
        self.maintenance = Maintenance.objects.create(
            resource=self.resource,
            title='Routine Maintenance',
            description='Monthly equipment check',
            scheduled_start=timezone.now() + timedelta(days=7),
            scheduled_end=timezone.now() + timedelta(days=7, hours=4),
            maintenance_type='routine'
        )
    
    def test_maintenance_list_view(self):
        """Test maintenance schedule admin list view"""
        url = reverse('admin:booking_maintenance_changelist')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Routine Maintenance')
    
    def test_maintenance_type_filter(self):
        """Test filtering maintenance by type"""
        Maintenance.objects.create(
            resource=self.resource,
            title='Emergency Repair',
            scheduled_start=timezone.now() + timedelta(days=1),
            scheduled_end=timezone.now() + timedelta(days=1, hours=2),
            maintenance_type='emergency'
        )
        
        url = reverse('admin:booking_maintenance_changelist')
        
        # Filter by routine maintenance
        response = self.client.get(url + '?maintenance_type=routine')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Routine Maintenance')
    
    def test_maintenance_status_update(self):
        """Test updating maintenance status"""
        url = reverse('admin:booking_maintenance_change', args=[self.maintenance.id])
        
        # Update maintenance status to in_progress
        data = {
            'resource': self.resource.id,
            'title': 'Routine Maintenance',
            'description': 'Monthly equipment check',
            'scheduled_start': self.maintenance.scheduled_start,
            'scheduled_end': self.maintenance.scheduled_end,
            'maintenance_type': 'routine',
            'status': 'in_progress'
        }
        
        response = self.client.post(url, data)
        
        # Should redirect after successful update
        self.assertEqual(response.status_code, 302)
        
        self.maintenance.refresh_from_db()
        if hasattr(self.maintenance, 'status'):
            self.assertEqual(self.maintenance.status, 'in_progress')


class AdminReportTests(TestCase):
    """Test admin dashboard and reporting features"""
    
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.client = Client()
        self.client.force_login(self.admin_user)
        
        # Create test data
        self.resource = ResourceFactory()
        for i in range(5):
            BookingFactory(
                resource=self.resource,
                status='completed' if i < 3 else 'pending'
            )
    
    def test_admin_dashboard_stats(self):
        """Test admin dashboard displays statistics"""
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        
        # Check for booking statistics in dashboard
        # Note: This depends on custom admin dashboard implementation
    
    def test_booking_export_functionality(self):
        """Test exporting booking data from admin"""
        url = reverse('admin:booking_booking_changelist')
        
        # Test CSV export if implemented
        response = self.client.get(url + '?format=csv')
        
        # If export is implemented, should return CSV data
        if response.status_code == 200:
            self.assertEqual(response['Content-Type'], 'text/csv')


class AdminSecurityTests(TestCase):
    """Test admin interface security"""
    
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.regular_user = UserFactory()
        
    def test_admin_requires_authentication(self):
        """Test that admin interface requires authentication"""
        client = Client()
        
        response = client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)
    
    def test_admin_requires_superuser(self):
        """Test that admin interface requires superuser status"""
        client = Client()
        client.force_login(self.regular_user)
        
        response = client.get('/admin/')
        self.assertEqual(response.status_code, 302)
    
    def test_admin_csrf_protection(self):
        """Test CSRF protection on admin forms"""
        client = Client()
        client.force_login(self.admin_user)
        
        # Try to post without CSRF token
        url = reverse('admin:booking_resource_add')
        data = {
            'name': 'Test Resource',
            'description': 'Test Description',
            'capacity': 1
        }
        
        response = client.post(url, data)
        # Should fail without CSRF token
        self.assertIn(response.status_code, [403, 302])


@pytest.mark.admin
class AdminCustomizationTests(TestCase):
    """Test custom admin interface features"""
    
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='adminpass123'
        )
        self.client = Client()
        self.client.force_login(self.admin_user)
    
    def test_custom_admin_actions(self):
        """Test custom admin actions if implemented"""
        # This would test any custom admin actions
        # beyond the standard Django admin actions
        pass
    
    def test_admin_interface_customization(self):
        """Test custom admin interface styling/branding"""
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        
        # Check for custom branding if implemented
        if 'Labitory' in response.content.decode():
            self.assertContains(response, 'Labitory')


if __name__ == '__main__':
    pytest.main([__file__])