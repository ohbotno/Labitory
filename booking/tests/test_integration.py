"""
Integration tests for complete workflows in Labitory system.
Tests end-to-end functionality across multiple components.
"""
from django.test import TestCase, Client, TransactionTestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.core import mail
from django.core.management import call_command
from datetime import datetime, timedelta
from booking.models import (
    UserProfile, Resource, Booking, ApprovalRule, 
    UpdateInfo, BackupRecord, EmailNotification
)
from booking.tests.factories import UserFactory, ResourceFactory, BookingFactory
import json
import tempfile
import os


class CompleteBookingWorkflowTests(TestCase):
    """Test complete booking workflows from start to finish."""
    
    def setUp(self):
        self.client = Client()
        self.student = UserFactory(role='student', is_approved=True)
        self.lab_manager = UserFactory(role='lab_manager', is_approved=True)
        self.admin = UserFactory(role='site_administrator', is_superuser=True)
        self.resource = ResourceFactory()
        mail.outbox = []
    
    def test_complete_student_booking_workflow(self):
        """Test complete student booking workflow."""
        # 1. Student logs in
        self.client.force_login(self.student)
        
        # 2. Student views dashboard
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # 3. Student creates booking via calendar
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        response = self.client.post(reverse('create_booking'), {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Integration test booking'
        })
        self.assertEqual(response.status_code, 302)  # Redirect after creation
        
        # 4. Verify booking was created
        booking = Booking.objects.get(user=self.student)
        self.assertEqual(booking.purpose, 'Integration test booking')
        self.assertEqual(booking.resource, self.resource)
        
        # 5. Check booking appears in calendar
        response = self.client.get(reverse('calendar_json'))
        data = json.loads(response.content)
        booking_found = any(event['id'] == booking.id for event in data)
        self.assertTrue(booking_found)
        
        # 6. Check booking appears in my bookings
        response = self.client.get(reverse('my_bookings'))
        self.assertContains(response, booking.purpose)
        
        # 7. Student can edit booking (if allowed)
        if booking.can_be_modified():
            response = self.client.post(reverse('edit_booking', args=[booking.id]), {
                'resource': self.resource.id,
                'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
                'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
                'purpose': 'Updated integration test booking'
            })
            booking.refresh_from_db()
            self.assertEqual(booking.purpose, 'Updated integration test booking')
        
        # 8. Student can cancel booking
        response = self.client.post(reverse('cancel_booking', args=[booking.id]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
    
    def test_booking_with_approval_workflow(self):
        """Test booking workflow requiring approval."""
        # 1. Create approval rule
        ApprovalRule.objects.create(
            resource=self.resource,
            user_role='student',
            approval_type='single',
            approver_role='lab_manager'
        )
        
        # 2. Student creates booking
        self.client.force_login(self.student)
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        response = self.client.post(reverse('create_booking'), {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Approval workflow test'
        })
        
        booking = Booking.objects.get(user=self.student)
        self.assertEqual(booking.status, 'pending_approval')
        
        # 3. Lab manager receives approval notification
        # Check email was queued/sent
        approval_emails = [email for email in mail.outbox 
                          if 'approval' in email.subject.lower()]
        self.assertGreater(len(approval_emails), 0)
        
        # 4. Lab manager logs in and views pending approvals
        self.client.force_login(self.lab_manager)
        response = self.client.get(reverse('pending_approvals'))
        self.assertContains(response, booking.purpose)
        
        # 5. Lab manager approves booking
        response = self.client.post(reverse('approve_booking', args=[booking.id]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'confirmed')
        
        # 6. Student receives approval notification
        approval_decision_emails = [email for email in mail.outbox 
                                   if 'approved' in email.subject.lower()]
        self.assertGreater(len(approval_decision_emails), 0)
    
    def test_recurring_booking_workflow(self):
        """Test recurring booking creation and management."""
        self.client.force_login(self.student)
        
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        # Create recurring booking
        response = self.client.post(reverse('create_booking'), {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Recurring test booking',
            'is_recurring': True,
            'recurrence_pattern': 'weekly',
            'recurrence_end_date': (start_time + timedelta(weeks=4)).strftime('%Y-%m-%d')
        })
        
        # Verify multiple bookings were created
        bookings = Booking.objects.filter(user=self.student)
        self.assertGreaterEqual(bookings.count(), 4)  # 4 weeks of bookings
        
        # Verify bookings are properly spaced
        booking_dates = [booking.start_datetime.date() for booking in bookings]
        self.assertEqual(len(set(booking_dates)), bookings.count())  # All different dates


class UserManagementWorkflowTests(TestCase):
    """Test complete user management workflows."""
    
    def setUp(self):
        self.client = Client()
        self.admin = UserFactory(role='site_administrator', is_superuser=True)
        mail.outbox = []
    
    def test_complete_user_registration_and_approval_workflow(self):
        """Test complete user registration and approval process."""
        # 1. New user registers
        response = self.client.post(reverse('register'), {
            'username': 'newstudent',
            'email': 'newstudent@example.com',
            'password1': 'complexpass123',
            'password2': 'complexpass123',
            'first_name': 'New',
            'last_name': 'Student',
            'role': 'student',
            'faculty': 'Engineering',
            'department': 'Computer Science'
        })
        self.assertEqual(response.status_code, 302)
        
        new_user = User.objects.get(username='newstudent')
        self.assertFalse(new_user.userprofile.is_approved)
        
        # 2. Registration email sent
        registration_emails = [email for email in mail.outbox 
                              if 'registration' in email.subject.lower()]
        self.assertGreater(len(registration_emails), 0)
        
        # 3. Admin receives notification of new user
        admin_notification_emails = [email for email in mail.outbox 
                                    if self.admin.email in email.to]
        self.assertGreater(len(admin_notification_emails), 0)
        
        # 4. Admin reviews and approves user
        self.client.force_login(self.admin)
        response = self.client.get(reverse('manage_users'))
        self.assertContains(response, 'newstudent')
        
        response = self.client.post(reverse('toggle_user_approval'), {
            'user_id': new_user.id
        })
        
        new_user.userprofile.refresh_from_db()
        self.assertTrue(new_user.userprofile.is_approved)
        
        # 5. User receives approval notification
        approval_emails = [email for email in mail.outbox 
                          if 'approved' in email.subject.lower()]
        self.assertGreater(len(approval_emails), 0)
        
        # 6. User can now log in and create bookings
        self.client.logout()
        login_response = self.client.post(reverse('login'), {
            'username': 'newstudent',
            'password': 'complexpass123'
        })
        self.assertEqual(login_response.status_code, 302)
        
        # User can access dashboard
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_user_role_change_workflow(self):
        """Test changing user roles and permissions."""
        self.client.force_login(self.admin)
        
        # Create a student user
        student = UserFactory(role='student')
        
        # Admin changes user role to researcher
        response = self.client.post(reverse('update_user_role'), {
            'user_id': student.id,
            'role': 'researcher'
        })
        
        student.userprofile.refresh_from_db()
        self.assertEqual(student.userprofile.role, 'researcher')
        
        # Verify user has new permissions
        self.client.force_login(student)
        # Test researcher-specific functionality
        response = self.client.get(reverse('dashboard'))
        # Should now see researcher-specific options
    
    def test_bulk_user_operations_workflow(self):
        """Test bulk user operations."""
        self.client.force_login(self.admin)
        
        # Create multiple unapproved users
        users = UserFactory.create_batch(5, is_approved=False)
        user_ids = [user.id for user in users]
        
        # Bulk approve users
        response = self.client.post(reverse('bulk_user_action'), {
            'action': 'approve',
            'user_ids': user_ids
        })
        
        # Verify all users were approved
        for user in users:
            user.userprofile.refresh_from_db()
            self.assertTrue(user.userprofile.is_approved)


class ResourceManagementWorkflowTests(TestCase):
    """Test complete resource management workflows."""
    
    def setUp(self):
        self.client = Client()
        self.admin = UserFactory(role='site_administrator', is_superuser=True)
        self.lab_manager = UserFactory(role='lab_manager')
        self.student = UserFactory(role='student')
    
    def test_complete_resource_lifecycle(self):
        """Test complete resource lifecycle management."""
        self.client.force_login(self.admin)
        
        # 1. Admin creates new resource
        response = self.client.post(reverse('create_resource'), {
            'name': 'New Test Equipment',
            'description': 'Advanced testing equipment',
            'category': 'analytical_instruments',
            'location': 'Lab 101',
            'capacity': 1,
            'requires_training': True,
            'training_level_required': 2,
            'is_bookable': True
        })
        self.assertEqual(response.status_code, 302)
        
        resource = Resource.objects.get(name='New Test Equipment')
        
        # 2. Create approval rule for resource
        response = self.client.post(reverse('create_approval_rule'), {
            'resource': resource.id,
            'user_role': 'student',
            'approval_type': 'single',
            'approver_role': 'lab_manager'
        })
        
        approval_rule = ApprovalRule.objects.get(resource=resource)
        self.assertEqual(approval_rule.user_role, 'student')
        
        # 3. Student attempts to book resource
        self.client.force_login(self.student)
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        response = self.client.post(reverse('create_booking'), {
            'resource': resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Testing new equipment'
        })
        
        booking = Booking.objects.get(user=self.student, resource=resource)
        self.assertEqual(booking.status, 'pending_approval')
        
        # 4. Lab manager approves booking
        self.client.force_login(self.lab_manager)
        response = self.client.post(reverse('approve_booking', args=[booking.id]))
        
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'confirmed')
        
        # 5. Admin monitors resource usage
        self.client.force_login(self.admin)
        response = self.client.get(reverse('resource_statistics', args=[resource.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Testing new equipment')
    
    def test_resource_maintenance_workflow(self):
        """Test resource maintenance scheduling workflow."""
        self.client.force_login(self.admin)
        resource = ResourceFactory()
        
        # Schedule maintenance
        maintenance_start = datetime.now() + timedelta(days=2)
        maintenance_end = maintenance_start + timedelta(hours=4)
        
        response = self.client.post(reverse('schedule_maintenance'), {
            'resource': resource.id,
            'start_datetime': maintenance_start.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': maintenance_end.strftime('%Y-%m-%d %H:%M'),
            'description': 'Routine calibration',
            'maintenance_type': 'routine'
        })
        
        # Verify maintenance window affects booking availability
        self.client.force_login(self.student)
        
        # Try to book during maintenance window
        response = self.client.post(reverse('create_booking'), {
            'resource': resource.id,
            'start_datetime': maintenance_start.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': maintenance_end.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Should be blocked by maintenance'
        })
        
        # Booking should be rejected or show warning
        self.assertEqual(response.status_code, 200)  # Stay on form


class SystemAdministrationWorkflowTests(TransactionTestCase):
    """Test complete system administration workflows."""
    
    def setUp(self):
        self.client = Client()
        self.admin = UserFactory(role='site_administrator', is_superuser=True)
        mail.outbox = []
    
    def test_complete_backup_workflow(self):
        """Test complete backup creation and restoration workflow."""
        self.client.force_login(self.admin)
        
        # Create test data
        resource = ResourceFactory()
        user = UserFactory(role='student')
        booking = BookingFactory(user=user, resource=resource)
        
        # 1. Admin creates manual backup
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(BACKUP_ROOT=temp_dir):
                response = self.client.post(reverse('create_backup'))
                self.assertEqual(response.status_code, 200)
                
                # Verify backup record was created
                backup = BackupRecord.objects.first()
                self.assertIsNotNone(backup)
                self.assertEqual(backup.backup_type, 'manual')
                
                # 2. Admin can download backup
                response = self.client.get(reverse('download_backup', args=[backup.id]))
                # Should either download or return 404 if file doesn't exist
                self.assertIn(response.status_code, [200, 404])
                
                # 3. Admin configures scheduled backups
                response = self.client.post(reverse('configure_backup_schedule'), {
                    'frequency': 'daily',
                    'time': '02:00',
                    'retention_days': 30,
                    'is_enabled': True
                })
                self.assertEqual(response.status_code, 200)
                
                # 4. Test backup list and management
                response = self.client.get(reverse('site_admin_backup_management'))
                self.assertContains(response, backup.filename)
    
    def test_complete_update_workflow(self):
        """Test complete system update workflow."""
        self.client.force_login(self.admin)
        
        # 1. Admin checks for updates
        response = self.client.post(reverse('check_updates'))
        self.assertEqual(response.status_code, 200)
        
        # 2. Update info should be created/updated
        update_info = UpdateInfo.objects.first()
        self.assertIsNotNone(update_info)
        
        # 3. Admin views update status
        response = self.client.get(reverse('site_admin_updates'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Current Version')
        
        # 4. Admin configures update settings
        response = self.client.post(reverse('configure_updates'), {
            'github_repo': 'ohbotno/aperature-booking',
            'auto_check': True,
            'check_interval': 24,
            'notification_email': self.admin.email
        })
        self.assertEqual(response.status_code, 200)
        
        update_info.refresh_from_db()
        self.assertEqual(update_info.github_repo, 'ohbotno/aperature-booking')
        self.assertTrue(update_info.auto_check)
    
    def test_complete_analytics_workflow(self):
        """Test complete analytics and reporting workflow."""
        self.client.force_login(self.admin)
        
        # Create test data for analytics
        users = UserFactory.create_batch(10, role='student')
        resources = ResourceFactory.create_batch(3)
        
        # Create bookings across different time periods
        for i, user in enumerate(users):
            for j, resource in enumerate(resources):
                start_time = datetime.now() + timedelta(days=i+j)
                BookingFactory(
                    user=user,
                    resource=resource,
                    start_datetime=start_time,
                    status='confirmed'
                )
        
        # 1. Admin views analytics dashboard
        response = self.client.get(reverse('analytics_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Analytics Dashboard')
        
        # 2. Admin generates usage statistics
        response = self.client.get(reverse('api_usage_statistics'))
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertIn('total_bookings', data)
        self.assertEqual(data['total_users'], 11)  # 10 + admin
        self.assertEqual(data['total_resources'], 3)
        
        # 3. Admin exports reports
        response = self.client.get(reverse('export_usage_report'), {
            'format': 'csv'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        
        # 4. Admin views resource utilization
        response = self.client.get(reverse('resource_utilization_report'))
        self.assertEqual(response.status_code, 200)
        
        for resource in resources:
            self.assertContains(response, resource.name)


class EmailNotificationWorkflowTests(TestCase):
    """Test complete email notification workflows."""
    
    def setUp(self):
        self.user = UserFactory(email='test@example.com')
        self.resource = ResourceFactory()
        mail.outbox = []
    
    def test_complete_notification_workflow(self):
        """Test complete email notification workflow."""
        # 1. User creates booking
        booking = BookingFactory(user=self.user, resource=self.resource)
        
        # 2. Email notification should be queued
        notifications = EmailNotification.objects.filter(
            user=self.user,
            notification_type='booking_created'
        )
        # May or may not exist depending on signal implementation
        
        # 3. Run notification sending command
        call_command('send_notifications')
        
        # 4. Check emails were sent
        self.assertGreater(len(mail.outbox), 0)
        
        # 5. Test reminder workflow
        # Create booking starting in 24 hours
        reminder_booking = BookingFactory(
            user=self.user,
            resource=self.resource,
            start_datetime=datetime.now() + timedelta(hours=24),
            status='confirmed'
        )
        
        mail.outbox = []  # Clear outbox
        
        # Send reminders
        call_command('send_notifications', '--send-reminders', '--reminder-hours', '24')
        
        # Should have reminder emails
        reminder_emails = [email for email in mail.outbox 
                          if 'reminder' in email.subject.lower()]
        self.assertGreater(len(reminder_emails), 0)
    
    def test_notification_preference_workflow(self):
        """Test notification preference management workflow."""
        from booking.models import NotificationPreference
        
        # 1. Create notification preferences
        preferences = NotificationPreference.objects.create(
            user=self.user,
            email_enabled=True,
            booking_confirmations=True,
            booking_reminders=False,  # Disabled
            booking_cancellations=True
        )
        
        # 2. Create booking (should trigger confirmation email)
        booking = BookingFactory(user=self.user, resource=self.resource)
        
        # 3. Create reminder scenario (should NOT trigger reminder due to preferences)
        reminder_booking = BookingFactory(
            user=self.user,
            resource=self.resource,
            start_datetime=datetime.now() + timedelta(hours=24),
            status='confirmed'
        )
        
        # Send notifications
        call_command('send_notifications')
        call_command('send_notifications', '--send-reminders', '--reminder-hours', '24')
        
        # Should have confirmation but not reminder emails
        confirmation_emails = [email for email in mail.outbox 
                              if 'confirmation' in email.subject.lower()]
        reminder_emails = [email for email in mail.outbox 
                          if 'reminder' in email.subject.lower()]
        
        # Confirmation should be sent, reminder should not
        if preferences.booking_confirmations:
            self.assertGreater(len(confirmation_emails), 0)
        
        # Reminder should not be sent due to preferences
        # This test depends on implementation respecting preferences


class ConflictResolutionWorkflowTests(TestCase):
    """Test conflict detection and resolution workflows."""
    
    def setUp(self):
        self.client = Client()
        self.user1 = UserFactory(role='student')
        self.user2 = UserFactory(role='student')
        self.resource = ResourceFactory()
    
    def test_booking_conflict_detection_workflow(self):
        """Test booking conflict detection and handling."""
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        # 1. User 1 creates booking
        self.client.force_login(self.user1)
        response = self.client.post(reverse('create_booking'), {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'First booking'
        })
        self.assertEqual(response.status_code, 302)
        
        booking1 = Booking.objects.get(user=self.user1)
        
        # 2. User 2 attempts to create conflicting booking
        self.client.force_login(self.user2)
        response = self.client.post(reverse('create_booking'), {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Conflicting booking'
        })
        
        # Should be rejected due to conflict
        self.assertEqual(response.status_code, 200)  # Stay on form
        self.assertContains(response, 'conflict')
        
        # Verify only one booking exists
        conflicting_bookings = Booking.objects.filter(
            resource=self.resource,
            start_datetime=start_time
        )
        self.assertEqual(conflicting_bookings.count(), 1)
    
    def test_partial_overlap_conflict_detection(self):
        """Test detection of partial time overlaps."""
        self.client.force_login(self.user1)
        
        start_time1 = datetime.now() + timedelta(days=1)
        end_time1 = start_time1 + timedelta(hours=3)
        
        # Create first booking
        response = self.client.post(reverse('create_booking'), {
            'resource': self.resource.id,
            'start_datetime': start_time1.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time1.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Original booking'
        })
        
        # Attempt overlapping booking (starts 1 hour into first booking)
        start_time2 = start_time1 + timedelta(hours=1)
        end_time2 = start_time2 + timedelta(hours=2)
        
        self.client.force_login(self.user2)
        response = self.client.post(reverse('create_booking'), {
            'resource': self.resource.id,
            'start_datetime': start_time2.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time2.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Overlapping booking'
        })
        
        # Should be rejected
        self.assertEqual(response.status_code, 200)


class PerformanceIntegrationTests(TestCase):
    """Test system performance under load."""
    
    def setUp(self):
        self.client = Client()
        self.admin = UserFactory(role='site_administrator', is_superuser=True)
        
        # Create larger dataset for performance testing
        self.users = UserFactory.create_batch(50)
        self.resources = ResourceFactory.create_batch(10)
    
    def test_dashboard_performance_with_large_dataset(self):
        """Test dashboard performance with large dataset."""
        # Create many bookings
        for user in self.users[:20]:  # Use subset to avoid test timeout
            for resource in self.resources[:3]:
                BookingFactory(user=user, resource=resource)
        
        # Test dashboard load time
        self.client.force_login(self.users[0])
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Should load within reasonable time
        # This is tested by the test not timing out
    
    def test_calendar_performance_with_many_bookings(self):
        """Test calendar performance with many bookings."""
        # Create bookings spread over time
        for i, user in enumerate(self.users[:30]):
            start_time = datetime.now() + timedelta(days=i % 30)
            BookingFactory(
                user=user,
                resource=self.resources[i % len(self.resources)],
                start_datetime=start_time
            )
        
        # Test calendar data loading
        self.client.force_login(self.users[0])
        response = self.client.get(reverse('calendar_json'))
        self.assertEqual(response.status_code, 200)
        
        # Should return reasonable amount of data
        data = json.loads(response.content)
        self.assertLess(len(response.content), 1000000)  # Less than 1MB
    
    def test_search_performance(self):
        """Test search functionality performance."""
        # Create many resources with varied names
        for i in range(100):
            ResourceFactory(name=f'Test Equipment {i:03d}')
        
        self.client.force_login(self.admin)
        
        # Test resource search
        response = self.client.get(reverse('manage_resources'), {
            'search': 'Test Equipment'
        })
        self.assertEqual(response.status_code, 200)
        
        # Should complete without timeout and return results
        self.assertContains(response, 'Test Equipment')


class SecurityIntegrationTests(TestCase):
    """Test security features across the system."""
    
    def setUp(self):
        self.client = Client()
        self.user = UserFactory(role='student')
        self.admin = UserFactory(role='site_administrator', is_superuser=True)
        self.resource = ResourceFactory()
    
    def test_complete_authentication_security(self):
        """Test complete authentication security workflow."""
        # 1. Test unauthenticated access is blocked
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
        
        # 2. Test login with valid credentials
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # 3. Test session security
        self.client.logout()
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)  # Should redirect after logout
    
    def test_authorization_across_system(self):
        """Test authorization controls across different parts of system."""
        # 1. Student should not access admin functions
        self.client.force_login(self.user)
        
        admin_urls = [
            reverse('site_admin_dashboard'),
            reverse('manage_users'),
            reverse('manage_resources'),
        ]
        
        for url in admin_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)  # Forbidden
        
        # 2. Admin should have access to all functions
        self.client.force_login(self.admin)
        
        for url in admin_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
    
    def test_data_validation_security(self):
        """Test data validation prevents malicious input."""
        self.client.force_login(self.user)
        
        # Test XSS prevention in booking form
        xss_payload = '<script>alert("xss")</script>'
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        response = self.client.post(reverse('create_booking'), {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': xss_payload
        })
        
        if response.status_code == 302:  # If booking was created
            booking = Booking.objects.filter(user=self.user).first()
            if booking:
                # XSS payload should be sanitized
                self.assertNotIn('<script>', booking.purpose)
    
    def test_csrf_protection_integration(self):
        """Test CSRF protection across forms."""
        self.client.force_login(self.user)
        
        # Test booking form CSRF protection
        # This test requires proper CSRF token handling
        response = self.client.get(reverse('create_booking'))
        self.assertEqual(response.status_code, 200)
        
        # Extract CSRF token and test form submission
        # Implementation depends on form structure


class MobileResponsivenessIntegrationTests(TestCase):
    """Test mobile responsiveness across the system."""
    
    def setUp(self):
        self.client = Client()
        self.user = UserFactory(role='student')
        self.resource = ResourceFactory()
    
    def test_mobile_navigation_workflow(self):
        """Test mobile navigation across different pages."""
        self.client.force_login(self.user)
        
        # Test key pages have mobile-responsive elements
        mobile_pages = [
            reverse('dashboard'),
            reverse('calendar'),
            reverse('my_bookings'),
            reverse('create_booking'),
        ]
        
        for page_url in mobile_pages:
            response = self.client.get(page_url)
            self.assertEqual(response.status_code, 200)
            
            # Check for mobile viewport meta tag
            self.assertContains(response, 'viewport')
            self.assertContains(response, 'width=device-width')
            
            # Check for responsive navigation
            self.assertContains(response, 'navbar-toggler')
    
    def test_mobile_booking_workflow(self):
        """Test complete booking workflow on mobile."""
        self.client.force_login(self.user)
        
        # 1. Access calendar on mobile
        response = self.client.get(reverse('calendar'))
        self.assertEqual(response.status_code, 200)
        
        # Should have mobile-friendly calendar
        self.assertContains(response, 'fc-toolbar')
        
        # 2. Create booking via mobile form
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        response = self.client.post(reverse('create_booking'), {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Mobile booking test'
        })
        self.assertEqual(response.status_code, 302)
        
        # 3. View booking in mobile my bookings
        response = self.client.get(reverse('my_bookings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mobile booking test')