"""Test cases for booking models."""
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import timedelta

from booking.models import UserProfile, Resource, Booking, BookingTemplate, ApprovalRule
from booking.tests.factories import (
    UserFactory, UserProfileFactory, ResourceFactory, 
    BookingFactory, BookingTemplateFactory, ApprovalRuleFactory
)


class TestUserProfile(TestCase):
    """Test UserProfile model functionality."""
    
    def test_user_profile_creation(self):
        """Test creating a user profile."""
        profile = UserProfileFactory()
        self.assertTrue(profile.user.username)
        self.assertEqual(profile.role, 'student')
        self.assertTrue(profile.email_verified)
    
    def test_user_profile_str(self):
        """Test UserProfile string representation."""
        profile = UserProfileFactory(user__username="testuser", user__first_name="Test", user__last_name="User")
        expected = "Test User (student)"
        self.assertEqual(str(profile), expected)
    
    def test_role_permissions(self):
        """Test role-based permission methods."""
        student = UserProfileFactory(role='student')
        academic = UserProfileFactory(role='academic')
        technician = UserProfileFactory(role='technician')
        
        # Test priority booking permissions
        self.assertFalse(student.can_book_priority)
        self.assertTrue(academic.can_book_priority)
        self.assertTrue(technician.can_book_priority)
        
        # Test recurring booking permissions
        self.assertFalse(student.can_create_recurring)
        self.assertTrue(academic.can_create_recurring)
        self.assertTrue(technician.can_create_recurring)


class TestResource(TestCase):
    """Test Resource model functionality."""
    
    def test_resource_creation(self):
        """Test creating a resource."""
        resource = ResourceFactory()
        self.assertTrue(resource.name)
        self.assertEqual(resource.resource_type, 'instrument')
        self.assertEqual(resource.capacity, 1)
        self.assertTrue(resource.is_active)
    
    def test_resource_str(self):
        """Test Resource string representation."""
        resource = ResourceFactory(name="Test Robot", resource_type="robot")
        self.assertIn("Test Robot", str(resource))
        self.assertIn("Robot", str(resource))
    
    def test_user_can_access_resource(self):
        """Test user access to resources based on training."""
        basic_resource = ResourceFactory(required_training_level=1)
        advanced_resource = ResourceFactory(required_training_level=3)
        
        basic_user = UserProfileFactory(training_level=1)
        advanced_user = UserProfileFactory(training_level=3)
        
        # Basic user can access basic resource
        self.assertTrue(basic_resource.is_available_for_user(basic_user))
        # Basic user cannot access advanced resource
        self.assertFalse(advanced_resource.is_available_for_user(basic_user))
        # Advanced user can access both
        self.assertTrue(basic_resource.is_available_for_user(advanced_user))
        self.assertTrue(advanced_resource.is_available_for_user(advanced_user))
    
    def test_induction_requirements(self):
        """Test induction requirement checking."""
        resource = ResourceFactory(requires_induction=True)
        
        inducted_user = UserProfileFactory(is_inducted=True)
        non_inducted_user = UserProfileFactory(is_inducted=False)
        
        self.assertTrue(resource.is_available_for_user(inducted_user))
        self.assertFalse(resource.is_available_for_user(non_inducted_user))


class TestBooking(TestCase):
    """Test Booking model functionality."""
    
    def test_booking_creation(self):
        """Test creating a booking."""
        booking = BookingFactory()
        self.assertTrue(booking.title)
        self.assertEqual(booking.status, 'pending')
        self.assertLess(booking.start_time, booking.end_time)
    
    def test_booking_str(self):
        """Test Booking string representation."""
        start_time = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
        booking = BookingFactory(title="Test Booking", start_time=start_time)
        expected_date = start_time.strftime('%Y-%m-%d %H:%M')
        expected = f"Test Booking - {booking.resource.name} ({expected_date})"
        self.assertEqual(str(booking), expected)
    
    def test_booking_duration(self):
        """Test booking duration calculation."""
        start = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
        end = start + timedelta(hours=3)
        booking = BookingFactory(start_time=start, end_time=end)
        self.assertEqual(booking.duration, timedelta(hours=3))
    
    def test_booking_validation_time_order(self):
        """Test that booking end time must be after start time."""
        start = timezone.now() + timedelta(days=1)
        end = start - timedelta(hours=1)  # End before start
        
        with self.assertRaises(ValidationError):
            booking = BookingFactory(start_time=start, end_time=end)
            booking.full_clean()
    
    def test_booking_validation_working_hours(self):
        """Test booking time validation within working hours."""
        # Create booking outside working hours (before 9 AM)
        start = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)
        end = start + timedelta(hours=1)
        
        with self.assertRaises(ValidationError):
            booking = BookingFactory(start_time=start, end_time=end)
            booking.full_clean()
    
    def test_booking_validation_max_duration(self):
        """Test booking duration validation against resource limits."""
        resource = ResourceFactory(max_booking_hours=4)
        start = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
        end = start + timedelta(hours=6)  # Exceeds 4-hour limit
        
        with self.assertRaises(ValidationError):
            booking = BookingFactory(
                resource=resource,
                start_time=start,
                end_time=end
            )
            booking.full_clean()
    
    def test_booking_conflict_detection(self):
        """Test booking conflict detection."""
        resource = ResourceFactory()
        start = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
        end = start + timedelta(hours=2)
        
        # Create first booking
        booking1 = BookingFactory(
            resource=resource,
            start_time=start,
            end_time=end,
            status='approved'
        )
        
        # Create overlapping booking (not saved yet)
        overlap_start = start + timedelta(hours=1)
        overlap_end = end + timedelta(hours=1)
        booking2 = BookingFactory.build(
            resource=resource,
            start_time=overlap_start,
            end_time=overlap_end
        )
        
        # Check for conflicts
        has_conflicts = booking2.has_conflicts()
        self.assertTrue(has_conflicts)
    
    def test_can_be_cancelled_by_user(self):
        """Test booking cancellation permissions."""
        user = UserProfileFactory()
        future_time = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
        booking = BookingFactory(
            user=user.user, 
            status='pending',
            start_time=future_time,
            end_time=future_time + timedelta(hours=2)
        )
        
        # Pending booking in future can be cancelled
        self.assertTrue(booking.can_be_cancelled)
        
        # Approved booking in future can be cancelled
        booking.status = 'approved'
        self.assertTrue(booking.can_be_cancelled)
        
        # Cancelled booking cannot be cancelled again
        booking.status = 'cancelled'
        self.assertFalse(booking.can_be_cancelled)
        
        # Past booking cannot be cancelled  
        past_time = timezone.now() - timedelta(hours=1)
        past_booking = BookingFactory.build(
            user=user.user,
            status='pending',
            start_time=past_time,
            end_time=past_time + timedelta(hours=1)
        )
        self.assertFalse(past_booking.can_be_cancelled)


class TestBookingTemplate(TestCase):
    """Test BookingTemplate model functionality."""
    
    def test_template_creation(self):
        """Test creating a booking template."""
        template = BookingTemplateFactory()
        self.assertTrue(template.name)
        self.assertEqual(template.duration_hours, 2)
    
    def test_template_str(self):
        """Test BookingTemplate string representation."""
        resource = ResourceFactory(name="Test Lab")
        template = BookingTemplateFactory(name="Weekly Meeting", resource=resource)
        expected = "Weekly Meeting - Test Lab"
        self.assertEqual(str(template), expected)
    
    def test_template_usage_tracking(self):
        """Test template usage count tracking."""
        template = BookingTemplateFactory()
        initial_count = template.use_count
        
        # Use the template's method to create a booking
        start_time = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
        template.create_booking_from_template(start_time)
        template.refresh_from_db()
        
        self.assertEqual(template.use_count, initial_count + 1)


class TestApprovalRule(TestCase):
    """Test ApprovalRule model functionality."""
    
    def test_approval_rule_creation(self):
        """Test creating an approval rule."""
        rule = ApprovalRuleFactory()
        self.assertTrue(rule.name)
        self.assertEqual(rule.approval_type, 'auto')
        self.assertTrue(rule.is_active)
    
    def test_approval_rule_str(self):
        """Test ApprovalRule string representation."""
        resource = ResourceFactory(name="Test Robot")
        rule = ApprovalRuleFactory(name="Auto Approve Students", resource=resource)
        expected = "Auto Approve Students - Test Robot"
        self.assertEqual(str(rule), expected)
    
    def test_applies_to_user(self):
        """Test if approval rule applies to a user."""
        resource = ResourceFactory()
        rule = ApprovalRuleFactory(
            resource=resource,
            approval_type='auto',
            user_roles=['student']
        )
        
        student_user = UserProfileFactory(role='student')
        academic_user = UserProfileFactory(role='academic')
        
        self.assertTrue(rule.applies_to_user(student_user))
        self.assertFalse(rule.applies_to_user(academic_user))
    
    def test_applies_to_all_users(self):
        """Test approval rule that applies to all users."""
        resource = ResourceFactory()
        rule = ApprovalRuleFactory(
            resource=resource,
            approval_type='auto',
            user_roles=[]  # Empty list means all users
        )
        
        student_user = UserProfileFactory(role='student')
        academic_user = UserProfileFactory(role='academic')
        
        self.assertTrue(rule.applies_to_user(student_user))
        self.assertTrue(rule.applies_to_user(academic_user))
    
    def test_inactive_rule(self):
        """Test that inactive rules don't apply."""
        resource = ResourceFactory()
        rule = ApprovalRuleFactory(
            resource=resource,
            approval_type='auto',
            is_active=False
        )
        
        user = UserProfileFactory(role='student')
        self.assertFalse(rule.applies_to_user(user))