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
from booking.tests.factories import UserFactory, ResourceFactory, BookingFactory, UserProfileFactory
import json


class HomePageTests(TestCase):
    """Test home page functionality."""
    
    def setUp(self):
        self.client = Client()
    
    def test_home_page_redirects_to_calendar(self):
        """Test home page redirects to calendar."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        # Follow redirect to see if it eventually loads
        response = self.client.get('/', follow=True)
        self.assertEqual(response.status_code, 200)
    
    def test_home_page_has_navigation_after_redirect(self):
        """Test navigation links are present after redirect."""
        response = self.client.get('/', follow=True)
        self.assertContains(response, 'Login')


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
        response = self.client.get(reverse('booking:register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Email')
        self.assertContains(response, 'Password')


class DashboardTests(TestCase):
    """Test dashboard functionality."""
    
    def setUp(self):
        self.user_profile = UserProfileFactory(role='student')
        self.user = self.user_profile.user
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_dashboard_requires_login(self):
        """Test dashboard requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('booking:dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_dashboard_loads_for_authenticated_user(self):
        """Test dashboard loads for authenticated users."""
        response = self.client.get(reverse('booking:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.get_full_name())


class CalendarTests(TestCase):
    """Test calendar functionality."""
    
    def setUp(self):
        self.user_profile = UserProfileFactory(role='student')
        self.user = self.user_profile.user
        self.resource = ResourceFactory()
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_calendar_page_loads(self):
        """Test calendar page loads correctly."""
        response = self.client.get(reverse('booking:calendar'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'calendar')


class BookingTests(TestCase):
    """Test booking functionality."""
    
    def setUp(self):
        self.user_profile = UserProfileFactory(role='student')
        self.user = self.user_profile.user
        self.resource = ResourceFactory()
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_my_bookings_page(self):
        """Test my bookings page displays correctly."""
        # Create some bookings
        BookingFactory(user=self.user, resource=self.resource)
        
        response = self.client.get(reverse('booking:my_bookings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.resource.name)
    
    def test_create_booking_page(self):
        """Test create booking page displays correctly."""
        response = self.client.get(reverse('booking:create_booking'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Resource')


class ResourceTests(TestCase):
    """Test resource functionality."""
    
    def setUp(self):
        self.user_profile = UserProfileFactory(role='student')
        self.user = self.user_profile.user
        self.resource = ResourceFactory()
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_resources_list_page(self):
        """Test resources list page displays correctly."""
        response = self.client.get(reverse('booking:resources_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.resource.name)
    
    def test_resource_detail_page(self):
        """Test resource detail page displays correctly."""
        response = self.client.get(reverse('booking:resource_detail', args=[self.resource.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.resource.name)


class ProfileTests(TestCase):
    """Test profile functionality."""
    
    def setUp(self):
        self.user_profile = UserProfileFactory(role='student')
        self.user = self.user_profile.user
        self.client = Client()
        self.client.force_login(self.user)
    
    def test_profile_page_loads(self):
        """Test profile page displays correctly."""
        response = self.client.get(reverse('booking:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.email)


class AboutPageTests(TestCase):
    """Test about page functionality."""
    
    def test_about_page_loads(self):
        """Test about page loads without authentication."""
        response = self.client.get(reverse('booking:about'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'About')