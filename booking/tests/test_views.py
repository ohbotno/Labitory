"""
Comprehensive view tests for Labitory system.
Tests all pages, forms, and user interactions.
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core import mail
from datetime import datetime, timedelta
from booking.models import (
    UserProfile, Resource, Booking, ApprovalRule, 
    UpdateInfo, BackupSchedule
)
from booking.tests.factories import UserFactory, ResourceFactory, BookingFactory
import json


class HomePageTests(TestCase):
    """Test home page functionality."""
    
    def setUp(self):
        self.client = Client()
    
    def test_home_page_loads(self):
        """Test home page loads without errors."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Labitory')
    
    def test_home_page_navigation_links(self):
        """Test navigation links are present."""
        response = self.client.get('/')
        self.assertContains(response, 'Login')
        self.assertContains(response, 'Register')
    
    def test_home_page_responsive_elements(self):
        """Test responsive design elements are present."""
        response = self.client.get('/')
        self.assertContains(response, 'navbar-toggler')  # Mobile menu toggle
        self.assertContains(response, 'container-fluid')  # Responsive container


class AuthenticationTests(TestCase):
    """Test authentication functionality."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        self.user.userprofile.role = 'student'
        self.user.userprofile.is_approved = True
        self.user.userprofile.save()
    
    def test_login_page_loads(self):
        """Test login page displays correctly."""
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Username')
        self.assertContains(response, 'Password')
    
    def test_valid_login(self):
        """Test login with valid credentials."""
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, 302)  # Redirect after login
    
    def test_invalid_login(self):
        """Test login with invalid credentials."""
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, 200)  # Stay on login page
        self.assertContains(response, 'Please enter a correct username and password')
    
    def test_registration_page_loads(self):
        """Test registration page displays correctly."""
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Email')
        self.assertContains(response, 'Password')
        self.assertContains(response, 'Role')
    
    def test_user_registration(self):
        """Test user registration process."""
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'complexpass123',
            'password2': 'complexpass123',
            'first_name': 'New',
            'last_name': 'User',
            'role': 'student',
            'faculty': 'Engineering',
            'department': 'Computer Science'
        })
        self.assertEqual(response.status_code, 302)  # Redirect after registration
        self.assertTrue(User.objects.filter(username='newuser').exists())
    
    def test_password_reset_page(self):
        """Test password reset functionality."""
        response = self.client.get(reverse('password_reset'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Email')
    
    def test_password_reset_email(self):
        """Test password reset email is sent."""
        response = self.client.post(reverse('password_reset'), {
            'email': 'test@example.com'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Password reset', mail.outbox[0].subject)


class DashboardTests(TestCase):
    """Test dashboard functionality."""
    
    def setUp(self):
        self.user = UserFactory(role='student')
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_dashboard_requires_login(self):
        """Test dashboard requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_dashboard_loads_for_authenticated_user(self):
        """Test dashboard loads for authenticated users."""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.get_full_name())
    
    def test_dashboard_widgets_display(self):
        """Test dashboard widgets display correctly."""
        # Create some bookings for the user
        resource = ResourceFactory()
        BookingFactory(user=self.user, resource=resource)
        
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Recent Bookings')
        self.assertContains(response, 'Quick Actions')
    
    def test_dashboard_quick_actions(self):
        """Test dashboard quick action links."""
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'New Booking')
        self.assertContains(response, 'View Calendar')
        self.assertContains(response, 'My Bookings')


class CalendarTests(TestCase):
    """Test calendar functionality."""
    
    def setUp(self):
        self.user = UserFactory(role='student')
        self.resource = ResourceFactory()
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_calendar_page_loads(self):
        """Test calendar page loads correctly."""
        response = self.client.get(reverse('calendar'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'calendar')
    
    def test_calendar_resource_filter(self):
        """Test resource filtering on calendar."""
        response = self.client.get(reverse('calendar'))
        self.assertContains(response, self.resource.name)
    
    def test_calendar_json_data(self):
        """Test calendar JSON data endpoint."""
        # Create a booking
        booking = BookingFactory(user=self.user, resource=self.resource)
        
        response = self.client.get(reverse('calendar_json'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertGreater(len(data), 0)
    
    def test_calendar_booking_creation(self):
        """Test booking creation from calendar."""
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        response = self.client.post(reverse('create_booking_ajax'), {
            'resource': self.resource.id,
            'start_datetime': start_time.isoformat(),
            'end_datetime': end_time.isoformat(),
            'purpose': 'Test booking from calendar'
        })
        self.assertEqual(response.status_code, 200)


class BookingTests(TestCase):
    """Test booking functionality."""
    
    def setUp(self):
        self.user = UserFactory(role='student')
        self.resource = ResourceFactory()
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_my_bookings_page(self):
        """Test my bookings page displays correctly."""
        # Create some bookings
        BookingFactory(user=self.user, resource=self.resource)
        
        response = self.client.get(reverse('my_bookings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.resource.name)
    
    def test_create_booking_page(self):
        """Test create booking page displays correctly."""
        response = self.client.get(reverse('create_booking'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Resource')
        self.assertContains(response, 'Start Date')
        self.assertContains(response, 'Purpose')
    
    def test_booking_creation(self):
        """Test booking creation functionality."""
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        response = self.client.post(reverse('create_booking'), {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Test booking creation'
        })
        self.assertEqual(response.status_code, 302)  # Redirect after creation
        self.assertTrue(Booking.objects.filter(user=self.user).exists())
    
    def test_booking_validation(self):
        """Test booking validation rules."""
        # Test booking in the past
        past_time = datetime.now() - timedelta(hours=1)
        end_time = past_time + timedelta(hours=2)
        
        response = self.client.post(reverse('create_booking'), {
            'resource': self.resource.id,
            'start_datetime': past_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Test past booking'
        })
        self.assertEqual(response.status_code, 200)  # Stay on form due to validation error
    
    def test_booking_conflict_detection(self):
        """Test booking conflict detection."""
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        # Create existing booking
        BookingFactory(
            resource=self.resource,
            start_datetime=start_time,
            end_datetime=end_time
        )
        
        # Try to create conflicting booking
        response = self.client.post(reverse('create_booking'), {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Conflicting booking'
        })
        self.assertEqual(response.status_code, 200)  # Stay on form due to conflict
    
    def test_booking_cancellation(self):
        """Test booking cancellation functionality."""
        booking = BookingFactory(user=self.user, resource=self.resource)
        
        response = self.client.post(reverse('cancel_booking', args=[booking.id]))
        self.assertEqual(response.status_code, 302)
        
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')


class AccountSettingsTests(TestCase):
    """Test account settings functionality."""
    
    def setUp(self):
        self.user = UserFactory(role='student')
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_account_settings_page(self):
        """Test account settings page loads."""
        response = self.client.get(reverse('account_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.first_name)
        self.assertContains(response, self.user.email)
    
    def test_profile_update(self):
        """Test profile information update."""
        response = self.client.post(reverse('account_settings'), {
            'first_name': 'Updated',
            'last_name': 'Name',
            'email': 'updated@example.com'
        })
        self.assertEqual(response.status_code, 302)
        
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')
        self.assertEqual(self.user.email, 'updated@example.com')
    
    def test_password_change(self):
        """Test password change functionality."""
        response = self.client.post(reverse('password_change'), {
            'old_password': 'testpass123',
            'new_password1': 'newpass456',
            'new_password2': 'newpass456'
        })
        self.assertEqual(response.status_code, 302)


class AdminTests(TestCase):
    """Test admin functionality."""
    
    def setUp(self):
        self.admin_user = UserFactory(role='site_administrator', is_superuser=True)
        self.regular_user = UserFactory(role='student')
        self.resource = ResourceFactory()
        self.client = Client()
    
    def test_admin_access_control(self):
        """Test admin pages require proper permissions."""
        # Test without login
        response = self.client.get(reverse('site_admin_dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
        
        # Test with regular user
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse('site_admin_dashboard'))
        self.assertEqual(response.status_code, 403)  # Forbidden
        
        # Test with admin user
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('site_admin_dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_site_admin_dashboard(self):
        """Test site admin dashboard displays correctly."""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('site_admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Site Administration')
        self.assertContains(response, 'User Management')
        self.assertContains(response, 'Resource Management')
    
    def test_user_management(self):
        """Test user management functionality."""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('manage_users'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.regular_user.username)
    
    def test_resource_management(self):
        """Test resource management functionality."""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('manage_resources'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.resource.name)
    
    def test_backup_management(self):
        """Test backup management functionality."""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('site_admin_backup_management'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create Backup')
    
    def test_update_system(self):
        """Test update system functionality."""
        self.client.force_login(self.admin_user)
        
        # Create update info
        UpdateInfo.objects.create(
            current_version='1.0.0',
            available_version='1.0.1',
            github_repo='ohbotno/aperature-booking'
        )
        
        response = self.client.get(reverse('site_admin_updates'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Current Version')
        self.assertContains(response, 'Check for Updates')


class ApprovalWorkflowTests(TestCase):
    """Test approval workflow functionality."""
    
    def setUp(self):
        self.student = UserFactory(role='student')
        self.lab_manager = UserFactory(role='lab_manager')
        self.resource = ResourceFactory()
        self.client = Client()
        
        # Create approval rule requiring lab manager approval
        ApprovalRule.objects.create(
            resource=self.resource,
            user_role='student',
            approval_type='single',
            approver_role='lab_manager'
        )
    
    def test_booking_requires_approval(self):
        """Test booking requiring approval."""
        self.client.force_login(self.student)
        
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        response = self.client.post(reverse('create_booking'), {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Test approval workflow'
        })
        
        booking = Booking.objects.get(user=self.student)
        self.assertEqual(booking.status, 'pending_approval')
    
    def test_approval_process(self):
        """Test approval process functionality."""
        # Create pending booking
        booking = BookingFactory(
            user=self.student,
            resource=self.resource,
            status='pending_approval'
        )
        
        self.client.force_login(self.lab_manager)
        response = self.client.post(reverse('approve_booking', args=[booking.id]))
        self.assertEqual(response.status_code, 302)
        
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'confirmed')


class EmailNotificationTests(TestCase):
    """Test email notification functionality."""
    
    def setUp(self):
        self.user = UserFactory(role='student')
        self.resource = ResourceFactory()
        mail.outbox = []  # Clear email outbox
    
    def test_booking_confirmation_email(self):
        """Test booking confirmation email is sent."""
        booking = BookingFactory(
            user=self.user,
            resource=self.resource,
            status='confirmed'
        )
        
        # Email should be sent automatically via signal
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Booking Confirmed', mail.outbox[0].subject)
        self.assertIn(self.user.email, mail.outbox[0].to)
    
    def test_booking_reminder_email(self):
        """Test booking reminder email functionality."""
        # Create booking starting in 24 hours
        start_time = datetime.now() + timedelta(hours=24)
        booking = BookingFactory(
            user=self.user,
            resource=self.resource,
            start_datetime=start_time,
            status='confirmed'
        )
        
        # Clear previous emails
        mail.outbox = []
        
        # Run reminder command
        from django.core.management import call_command
        call_command('send_notifications', '--send-reminders', '--reminder-hours', '24')
        
        self.assertGreater(len(mail.outbox), 0)


class SecurityTests(TestCase):
    """Test security features."""
    
    def setUp(self):
        self.user = UserFactory(role='student')
        self.admin_user = UserFactory(role='site_administrator')
        self.client = Client()
    
    def test_csrf_protection(self):
        """Test CSRF protection is enabled."""
        self.client.force_login(self.user)
        
        # POST without CSRF token should fail
        response = self.client.post(reverse('create_booking'), {
            'resource': ResourceFactory().id,
            'purpose': 'Test CSRF'
        }, HTTP_X_CSRFTOKEN='invalid')
        self.assertEqual(response.status_code, 403)
    
    def test_permission_based_access(self):
        """Test permission-based access control."""
        resource = ResourceFactory()
        
        # Student should be able to create bookings
        self.client.force_login(self.user)
        response = self.client.get(reverse('create_booking'))
        self.assertEqual(response.status_code, 200)
        
        # Student should not access admin pages
        response = self.client.get(reverse('site_admin_dashboard'))
        self.assertEqual(response.status_code, 403)
    
    def test_data_validation(self):
        """Test input validation and sanitization."""
        self.client.force_login(self.user)
        
        # Test XSS prevention
        response = self.client.post(reverse('create_booking'), {
            'resource': ResourceFactory().id,
            'purpose': '<script>alert("xss")</script>',
            'start_datetime': '2024-01-01 10:00',
            'end_datetime': '2024-01-01 12:00'
        })
        
        if response.status_code == 302:  # If booking was created
            booking = Booking.objects.latest('created_at')
            self.assertNotIn('<script>', booking.purpose)


class MobileResponsivenessTests(TestCase):
    """Test mobile responsiveness."""
    
    def setUp(self):
        self.user = UserFactory(role='student')
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_mobile_viewport_meta_tag(self):
        """Test mobile viewport meta tag is present."""
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'viewport')
        self.assertContains(response, 'width=device-width')
    
    def test_responsive_navigation(self):
        """Test responsive navigation elements."""
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'navbar-toggler')
        self.assertContains(response, 'collapse')
    
    def test_mobile_calendar_elements(self):
        """Test mobile-specific calendar elements."""
        response = self.client.get(reverse('calendar'))
        self.assertContains(response, 'fc-toolbar')  # FullCalendar mobile toolbar


class ErrorHandlingTests(TestCase):
    """Test error handling."""
    
    def setUp(self):
        self.client = Client()
    
    def test_404_page(self):
        """Test custom 404 page."""
        response = self.client.get('/nonexistent-page/')
        self.assertEqual(response.status_code, 404)
    
    def test_500_error_handling(self):
        """Test 500 error handling."""
        # This would need to be tested with a view that intentionally raises an exception
        # For now, just ensure the test framework can handle it
        pass
    
    def test_form_validation_errors(self):
        """Test form validation error display."""
        user = UserFactory(role='student')
        self.client.force_login(user)
        
        # Submit invalid booking form
        response = self.client.post(reverse('create_booking'), {
            'resource': '',  # Missing required field
            'purpose': 'Test validation'
        })
        self.assertEqual(response.status_code, 200)  # Stay on form
        self.assertContains(response, 'This field is required')


class PerformanceTests(TestCase):
    """Test performance aspects."""
    
    def setUp(self):
        self.user = UserFactory(role='student')
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_dashboard_query_efficiency(self):
        """Test dashboard doesn't have N+1 query problems."""
        # Create multiple bookings
        resource = ResourceFactory()
        for i in range(10):
            BookingFactory(user=self.user, resource=resource)
        
        # Test with query counting
        from django.test.utils import override_settings
        from django.db import connection
        
        connection.queries_log.clear()
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Should not have excessive queries
        self.assertLess(len(connection.queries), 20)
    
    def test_calendar_data_pagination(self):
        """Test calendar data is properly paginated/limited."""
        resource = ResourceFactory()
        
        # Create many bookings
        for i in range(100):
            BookingFactory(resource=resource)
        
        response = self.client.get(reverse('calendar_json'))
        self.assertEqual(response.status_code, 200)
        
        # Response should be reasonable size
        self.assertLess(len(response.content), 1000000)  # Less than 1MB


class IntegrationTests(TestCase):
    """Test end-to-end workflows."""
    
    def setUp(self):
        self.student = UserFactory(role='student')
        self.lab_manager = UserFactory(role='lab_manager')
        self.admin = UserFactory(role='site_administrator')
        self.resource = ResourceFactory()
        self.client = Client()
    
    def test_complete_booking_workflow(self):
        """Test complete booking workflow from creation to completion."""
        # Student creates booking
        self.client.force_login(self.student)
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        response = self.client.post(reverse('create_booking'), {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Integration test booking'
        })
        
        booking = Booking.objects.get(user=self.student)
        self.assertTrue(booking.id)
        
        # Check booking appears in calendar
        response = self.client.get(reverse('calendar_json'))
        data = json.loads(response.content)
        booking_found = any(event['id'] == booking.id for event in data)
        self.assertTrue(booking_found)
        
        # Check booking appears in my bookings
        response = self.client.get(reverse('my_bookings'))
        self.assertContains(response, booking.purpose)
    
    def test_admin_system_configuration_workflow(self):
        """Test admin system configuration workflow."""
        self.client.force_login(self.admin)
        
        # Access admin dashboard
        response = self.client.get(reverse('site_admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Create new resource
        response = self.client.post(reverse('manage_resources'), {
            'name': 'Integration Test Resource',
            'description': 'Created during integration test',
            'category': 'test',
            'location': 'Test Lab'
        })
        
        # Verify resource was created
        self.assertTrue(Resource.objects.filter(name='Integration Test Resource').exists())
        
        # Test backup creation
        response = self.client.post(reverse('create_backup'))
        self.assertEqual(response.status_code, 200)


class BrowserCompatibilityTests(TestCase):
    """Test browser compatibility aspects."""
    
    def setUp(self):
        self.user = UserFactory(role='student')
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_javascript_dependencies(self):
        """Test JavaScript dependencies are properly loaded."""
        response = self.client.get(reverse('calendar'))
        
        # Check for essential JavaScript libraries
        self.assertContains(response, 'jquery')
        self.assertContains(response, 'bootstrap')
        self.assertContains(response, 'fullcalendar')
    
    def test_css_framework_loading(self):
        """Test CSS framework is properly loaded."""
        response = self.client.get(reverse('dashboard'))
        
        # Check for Bootstrap CSS
        self.assertContains(response, 'bootstrap')
        self.assertContains(response, 'container')
    
    def test_progressive_enhancement(self):
        """Test progressive enhancement features."""
        response = self.client.get(reverse('create_booking'))
        
        # Form should work without JavaScript
        self.assertContains(response, '<form')
        self.assertContains(response, 'method="post"')
        self.assertContains(response, 'submit')