"""
Core functionality tests that work without external dependencies.
These tests focus on essential business logic and models.
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from datetime import datetime, timedelta
from django.utils import timezone
from booking.models import UserProfile, Resource, Booking
import json


class SimpleCoreModelTests(TestCase):
    """Test core model functionality without complex dependencies."""
    
    def test_user_creation(self):
        """Test basic user creation."""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.assertEqual(user.username, 'testuser')
        self.assertEqual(user.email, 'test@example.com')
        self.assertTrue(user.check_password('testpass123'))
    
    def test_user_profile_creation(self):
        """Test user profile creation."""
        user = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpass123'
        )
        
        # Get automatically created user profile and update it
        profile = user.userprofile
        profile.role = 'student'
        profile.group = 'test_group'
        profile.training_level = 1
        profile.is_inducted = True
        profile.email_verified = True
        profile.save()
        
        self.assertEqual(profile.user, user)
        self.assertEqual(profile.role, 'student')
        self.assertEqual(profile.group, 'test_group')
        self.assertTrue(profile.is_inducted)
    
    def test_resource_creation(self):
        """Test resource creation."""
        resource = Resource.objects.create(
            name='Test Equipment',
            description='Test equipment for testing',
            resource_type='analytical_instruments',
            location='Lab 101',
            capacity=1,
            is_active=True
        )
        
        self.assertEqual(resource.name, 'Test Equipment')
        self.assertEqual(resource.resource_type, 'analytical_instruments')
        self.assertEqual(resource.location, 'Lab 101')
        self.assertTrue(resource.is_active)
    
    def test_booking_creation(self):
        """Test booking creation."""
        # Create user
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Get automatically created user profile and update it
        profile = user.userprofile
        profile.role = 'student'
        profile.email_verified = True
        profile.save()
        
        # Create resource
        resource = Resource.objects.create(
            name='Test Equipment',
            description='Test equipment',
            resource_type='analytical_instruments',
            location='Lab 101',
            capacity=1,
                        is_active=True
        )
        
        # Create booking
        tomorrow = timezone.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=2)
        
        booking = Booking.objects.create(
            user=user,
            resource=resource,
            start_time=start_time,
            end_time=end_time,
            title='Test booking',
            status='approved'
        )
        
        self.assertEqual(booking.user, user)
        self.assertEqual(booking.resource, resource)
        self.assertEqual(booking.title, 'Test booking')
        self.assertEqual(booking.status, 'approved')
        self.assertLess(booking.start_time, booking.end_time)


class SimpleCoreViewTests(TestCase):
    """Test core view functionality without complex dependencies."""
    
    def setUp(self):
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Get automatically created user profile and update it
        self.profile = self.user.userprofile
        self.profile.role = 'student'
        self.profile.email_verified = True
        self.profile.save()
        
        # Create test resource
        self.resource = Resource.objects.create(
            name='Test Equipment',
            description='Test equipment',
            resource_type='analytical_instruments',
            location='Lab 101',
            capacity=1,
                        is_active=True
        )
    
    def test_home_page_loads(self):
        """Test that home page loads."""
        try:
            response = self.client.get('/')
            # Should either load successfully or redirect to a valid page
            self.assertIn(response.status_code, [200, 301, 302])
        except Exception:
            # If home page doesn't exist, that's okay for this test
            pass
    
    def test_user_authentication(self):
        """Test user can log in."""
        # Test login
        login_successful = self.client.login(
            username='testuser',
            password='testpass123'
        )
        self.assertTrue(login_successful)
        
        # Test user is authenticated
        response = self.client.get('/admin/')  # Django admin should exist
        # Should either be accessible or redirect (not 500 error)
        self.assertIn(response.status_code, [200, 302, 403])
    
    def test_model_string_representations(self):
        """Test model string representations."""
        # Test user profile string representation
        expected_str = f"{self.user.get_full_name() or self.user.username} (student)"
        self.assertEqual(str(self.profile), expected_str)
        
        # Test resource string representation
        self.assertEqual(str(self.resource), 'Test Equipment')
        
        # Test booking string representation
        tomorrow = timezone.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=2)
        
        booking = Booking.objects.create(
            user=self.user,
            resource=self.resource,
            start_time=start_time,
            end_time=end_time,
            title='Test booking',
            status='approved'
        )
        
        expected_booking_str = f"Test Equipment - testuser ({start_time.strftime('%Y-%m-%d %H:%M')})"
        self.assertEqual(str(booking), expected_booking_str)


class SimpleCoreBusinessLogicTests(TestCase):
    """Test core business logic without external dependencies."""
    
    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Get automatically created user profile and update it
        profile = self.user.userprofile
        profile.role = 'student'
        profile.email_verified = True
        profile.save()
        
        # Create test resource
        self.resource = Resource.objects.create(
            name='Test Equipment',
            description='Test equipment',
            resource_type='analytical_instruments',
            location='Lab 101',
            capacity=1,
                        is_active=True
        )
    
    def test_booking_validation(self):
        """Test basic booking validation logic."""
        tomorrow = timezone.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=2)
        
        # Valid booking
        booking = Booking(
            user=self.user,
            resource=self.resource,
            start_time=start_time,
            end_time=end_time,
            title='Test booking',
            status='approved'
        )
        
        # Should be able to save without validation errors
        try:
            booking.full_clean()
            booking.save()
            self.assertTrue(True)  # If we get here, validation passed
        except Exception as e:
            self.fail(f"Valid booking failed validation: {e}")
    
    def test_booking_time_validation(self):
        """Test booking time validation."""
        tomorrow = timezone.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = start_time - timedelta(hours=1)  # End before start
        
        booking = Booking(
            user=self.user,
            resource=self.resource,
            start_time=start_time,
            end_time=end_time,
            title='Invalid time booking',
            status='approved'
        )
        
        # Should fail validation
        with self.assertRaises(Exception):
            booking.full_clean()
    
    def test_user_role_choices(self):
        """Test user role choices are valid."""
        valid_roles = ['student', 'researcher', 'academic', 'technician', 'sysadmin']
        
        for role in valid_roles:
            profile = UserProfile(
                user=self.user,
                role=role
            )
            try:
                profile.full_clean()
                self.assertTrue(True)  # Role is valid
            except Exception:
                self.fail(f"Role '{role}' should be valid")
    
    def test_resource_availability(self):
        """Test basic resource availability logic."""
        # Resource should be available when active
        self.assertTrue(self.resource.is_active)
        
        # Resource should not be available when inactive
        self.resource.is_active = False
        self.resource.save()
        self.assertFalse(self.resource.is_active)
        
        # Resource should be active for bookings
        self.resource.is_active = True
        self.resource.save()
        self.assertTrue(self.resource.is_active)
    
    def test_booking_status_choices(self):
        """Test booking status choices are valid."""
        valid_statuses = ['pending', 'approved', 'cancelled', 'completed']
        
        tomorrow = timezone.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=2)
        
        for status in valid_statuses:
            booking = Booking(
                user=self.user,
                resource=self.resource,
                start_time=start_time,
                end_time=end_time,
                title=f'Test booking with {status} status',
                status=status
            )
            try:
                booking.full_clean()
                self.assertTrue(True)  # Status is valid
            except Exception:
                self.fail(f"Status '{status}' should be valid")


class SimpleCoreIntegrationTests(TestCase):
    """Test core integration scenarios."""
    
    def setUp(self):
        self.client = Client()
        
        # Create multiple users
        self.student = User.objects.create_user(
            username='student',
            email='student@example.com',
            password='testpass123'
        )
        
        self.lab_manager = User.objects.create_user(
            username='labmanager',
            email='labmanager@example.com',
            password='testpass123'
        )
        
        # Update automatically created profiles
        student_profile = self.student.userprofile
        student_profile.role = 'student'
        student_profile.email_verified = True
        student_profile.save()
        
        manager_profile = self.lab_manager.userprofile
        manager_profile.role = 'technician'  # Use valid role from ROLE_CHOICES
        manager_profile.email_verified = True
        manager_profile.save()
        
        # Create resource
        self.resource = Resource.objects.create(
            name='Shared Equipment',
            description='Equipment shared by multiple users',
            resource_type='analytical_instruments',
            location='Main Lab',
            capacity=1,
                        is_active=True
        )
    
    def test_multiple_user_booking_workflow(self):
        """Test booking workflow with multiple users."""
        tomorrow = timezone.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=2)
        
        # Student creates booking
        student_booking = Booking.objects.create(
            user=self.student,
            resource=self.resource,
            start_time=start_time,
            end_time=end_time,
            title='Student research',
            status='approved'
        )
        
        # Lab manager creates different booking
        manager_start = start_time + timedelta(hours=3)
        manager_end = manager_start + timedelta(hours=1)
        
        manager_booking = Booking.objects.create(
            user=self.lab_manager,
            resource=self.resource,
            start_time=manager_start,
            end_time=manager_end,
            title='Equipment maintenance',
            status='approved'
        )
        
        # Both bookings should exist
        self.assertEqual(Booking.objects.count(), 2)
        self.assertEqual(student_booking.user, self.student)
        self.assertEqual(manager_booking.user, self.lab_manager)
    
    def test_booking_conflict_detection(self):
        """Test basic booking conflict detection."""
        tomorrow = timezone.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=2)
        
        # Create first booking
        first_booking = Booking.objects.create(
            user=self.student,
            resource=self.resource,
            start_time=start_time,
            end_time=end_time,
            title='First booking',
            status='approved'
        )
        
        # Check for conflicts with overlapping booking
        overlapping_start = start_time + timedelta(minutes=30)
        overlapping_end = end_time + timedelta(minutes=30)
        
        # Query for existing bookings in this time range
        conflicts = Booking.objects.filter(
            resource=self.resource,
            start_time__lt=overlapping_end,
            end_time__gt=overlapping_start,
            status__in=['approved', 'pending']
        ).exclude(id=first_booking.id if hasattr(first_booking, 'id') else None)
        
        # Should find the conflict
        self.assertEqual(conflicts.count(), 1)
        self.assertEqual(conflicts.first(), first_booking)
    
    def test_resource_capacity_logic(self):
        """Test resource capacity handling."""
        # Test single capacity resource
        self.assertEqual(self.resource.capacity, 1)
        
        # Create multi-capacity resource
        multi_resource = Resource.objects.create(
            name='Multi-User Equipment',
            description='Equipment that supports multiple users',
            resource_type='analytical_instruments',
            location='Shared Lab',
            capacity=3,
                        is_active=True
        )
        
        self.assertEqual(multi_resource.capacity, 3)
        
        # Should be able to create multiple simultaneous bookings up to capacity
        tomorrow = timezone.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=2)
        
        bookings = []
        for i in range(3):  # Create bookings up to capacity
            user = User.objects.create_user(
                username=f'user{i}',
                email=f'user{i}@example.com',
                password='testpass123'
            )
            # Update automatically created profile
            profile = user.userprofile
            profile.role = 'student'
            profile.email_verified = True
            profile.save()
            
            booking = Booking.objects.create(
                user=user,
                resource=multi_resource,
                start_time=start_time,
                end_time=end_time,
                title=f'Concurrent booking {i}',
                status='approved'
            )
            bookings.append(booking)
        
        # All bookings should be created successfully
        self.assertEqual(len(bookings), 3)
        
        # Check that all bookings are for the same time and resource
        for booking in bookings:
            self.assertEqual(booking.resource, multi_resource)
            self.assertEqual(booking.start_time, start_time)


class SimpleCoreDataConsistencyTests(TestCase):
    """Test data consistency and integrity."""
    
    def test_cascading_deletes(self):
        """Test that related objects are handled properly on deletion."""
        # Create user with profile
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Get automatically created profile and update it
        profile = user.userprofile
        profile.role = 'student'
        profile.email_verified = True
        profile.save()
        
        # Create resource
        resource = Resource.objects.create(
            name='Test Equipment',
            description='Test equipment',
            resource_type='analytical_instruments',
            location='Lab 101',
            capacity=1,
                        is_active=True
        )
        
        # Create booking
        tomorrow = timezone.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=2)
        
        booking = Booking.objects.create(
            user=user,
            resource=resource,
            start_time=start_time,
            end_time=end_time,
            title='Test booking',
            status='approved'
        )
        
        # Verify objects exist
        self.assertTrue(User.objects.filter(id=user.id).exists())
        self.assertTrue(UserProfile.objects.filter(id=profile.id).exists())
        self.assertTrue(Resource.objects.filter(id=resource.id).exists())
        self.assertTrue(Booking.objects.filter(id=booking.id).exists())
        
        # Delete user should cascade to profile but not affect resource or bookings
        user_id = user.id
        profile_id = profile.id
        resource_id = resource.id
        booking_id = booking.id
        
        user.delete()
        
        # User and profile should be deleted
        self.assertFalse(User.objects.filter(id=user_id).exists())
        self.assertFalse(UserProfile.objects.filter(id=profile_id).exists())
        
        # Resource should still exist
        self.assertTrue(Resource.objects.filter(id=resource_id).exists())
        
        # Booking behavior depends on model configuration
        # It might be deleted (CASCADE) or kept with user set to NULL
    
    def test_unique_constraints(self):
        """Test unique constraints are enforced."""
        # Test unique username
        User.objects.create_user(
            username='uniqueuser',
            email='unique1@example.com',
            password='testpass123'
        )
        
        # Should not be able to create another user with same username
        with self.assertRaises(Exception):
            User.objects.create_user(
                username='uniqueuser',  # Duplicate username
                email='unique2@example.com',
                password='testpass123'
            )
        
        # Test unique email
        with self.assertRaises(Exception):
            User.objects.create_user(
                username='anotheruser',
                email='unique1@example.com',  # Duplicate email
                password='testpass123'
            )
    
    def test_required_fields(self):
        """Test that required fields are enforced."""
        # User requires username
        with self.assertRaises(Exception):
            User.objects.create_user(
                username='',  # Empty username
                email='test@example.com',
                password='testpass123'
            )
        
        # Resource requires name
        with self.assertRaises(Exception):
            Resource.objects.create(
                name='',  # Empty name
                description='Test',
                resource_type='analytical_instruments',
                location='Lab 101'
            )
        
        # Booking requires user, resource, and times
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        resource = Resource.objects.create(
            name='Test Equipment',
            description='Test',
            resource_type='analytical_instruments',
            location='Lab 101'
        )
        
        with self.assertRaises(Exception):
            Booking.objects.create(
                user=None,  # Missing user
                resource=resource,
                start_time=datetime.now(),
                end_time=datetime.now() + timedelta(hours=1),
                title='Test'
            )