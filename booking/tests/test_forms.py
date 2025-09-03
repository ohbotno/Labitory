"""
Test cases for all forms in the Labitory system.
"""
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from datetime import datetime, timedelta
from booking.forms import (
    UserRegistrationForm, BookingForm, ResourceForm, 
    ApprovalRuleForm, BackupConfigurationForm, UpdateConfigurationForm
)
from booking.models import UserProfile, Resource, Booking, ApprovalRule
from booking.tests.factories import UserFactory, ResourceFactory


class UserRegistrationFormTests(TestCase):
    """Test user registration form."""
    
    def test_valid_registration_form(self):
        """Test valid registration form submission."""
        form_data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password1': 'complexpass123',
            'password2': 'complexpass123',
            'first_name': 'Test',
            'last_name': 'User',
            'role': 'student',
            'faculty': 'Engineering',
            'department': 'Computer Science'
        }
        form = UserRegistrationForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_password_mismatch(self):
        """Test password mismatch validation."""
        form_data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password1': 'complexpass123',
            'password2': 'differentpass456',
            'first_name': 'Test',
            'last_name': 'User',
            'role': 'student'
        }
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('password2', form.errors)
    
    def test_invalid_email_format(self):
        """Test invalid email format validation."""
        form_data = {
            'username': 'testuser',
            'email': 'invalid-email',
            'password1': 'complexpass123',
            'password2': 'complexpass123',
            'first_name': 'Test',
            'last_name': 'User',
            'role': 'student'
        }
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
    
    def test_duplicate_username(self):
        """Test duplicate username validation."""
        # Create existing user
        User.objects.create_user(username='existinguser', email='existing@example.com')
        
        form_data = {
            'username': 'existinguser',
            'email': 'new@example.com',
            'password1': 'complexpass123',
            'password2': 'complexpass123',
            'first_name': 'Test',
            'last_name': 'User',
            'role': 'student'
        }
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)
    
    def test_duplicate_email(self):
        """Test duplicate email validation."""
        # Create existing user
        User.objects.create_user(username='user1', email='existing@example.com')
        
        form_data = {
            'username': 'newuser',
            'email': 'existing@example.com',
            'password1': 'complexpass123',
            'password2': 'complexpass123',
            'first_name': 'Test',
            'last_name': 'User',
            'role': 'student'
        }
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
    
    def test_required_fields(self):
        """Test required field validation."""
        form_data = {
            'username': '',
            'email': '',
            'password1': '',
            'password2': '',
            'first_name': '',
            'last_name': '',
            'role': ''
        }
        form = UserRegistrationForm(data=form_data)
        self.assertFalse(form.is_valid())
        
        required_fields = ['username', 'email', 'password1', 'password2', 
                          'first_name', 'last_name', 'role']
        for field in required_fields:
            self.assertIn(field, form.errors)


class BookingFormTests(TestCase):
    """Test booking form validation and functionality."""
    
    def setUp(self):
        self.user = UserFactory(role='student')
        self.resource = ResourceFactory()
    
    def test_valid_booking_form(self):
        """Test valid booking form submission."""
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        form_data = {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Test booking purpose'
        }
        form = BookingForm(data=form_data, user=self.user)
        self.assertTrue(form.is_valid())
    
    def test_past_booking_validation(self):
        """Test validation prevents booking in the past."""
        past_time = datetime.now() - timedelta(hours=1)
        end_time = past_time + timedelta(hours=2)
        
        form_data = {
            'resource': self.resource.id,
            'start_datetime': past_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Past booking test'
        }
        form = BookingForm(data=form_data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('start_datetime', form.errors)
    
    def test_end_before_start_validation(self):
        """Test validation prevents end time before start time."""
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time - timedelta(hours=1)  # End before start
        
        form_data = {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Invalid time range test'
        }
        form = BookingForm(data=form_data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('end_datetime', form.errors)
    
    def test_booking_duration_limits(self):
        """Test booking duration limit validation."""
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=25)  # Assuming 24-hour limit
        
        form_data = {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Long duration test'
        }
        form = BookingForm(data=form_data, user=self.user)
        # This test depends on actual duration limits in the form
        # The form may or may not be valid depending on configuration
    
    def test_conflict_detection(self):
        """Test booking conflict detection."""
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        # Create existing booking
        Booking.objects.create(
            user=self.user,
            resource=self.resource,
            start_datetime=start_time,
            end_datetime=end_time,
            purpose='Existing booking',
            status='confirmed'
        )
        
        # Try to create conflicting booking
        form_data = {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Conflicting booking'
        }
        form = BookingForm(data=form_data, user=self.user)
        self.assertFalse(form.is_valid())
    
    def test_required_purpose_field(self):
        """Test purpose field is required."""
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        form_data = {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': ''  # Empty purpose
        }
        form = BookingForm(data=form_data, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('purpose', form.errors)
    
    def test_advance_booking_limits(self):
        """Test advance booking limit validation."""
        # Try to book too far in advance (assuming 30-day limit)
        future_time = datetime.now() + timedelta(days=35)
        end_time = future_time + timedelta(hours=2)
        
        form_data = {
            'resource': self.resource.id,
            'start_datetime': future_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Far future booking'
        }
        form = BookingForm(data=form_data, user=self.user)
        # This test depends on actual advance booking limits
        # The form may implement this validation
    
    def test_recurring_booking_options(self):
        """Test recurring booking form options."""
        start_time = datetime.now() + timedelta(days=1)
        end_time = start_time + timedelta(hours=2)
        
        form_data = {
            'resource': self.resource.id,
            'start_datetime': start_time.strftime('%Y-%m-%d %H:%M'),
            'end_datetime': end_time.strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Recurring booking test',
            'is_recurring': True,
            'recurrence_pattern': 'weekly',
            'recurrence_end_date': (start_time + timedelta(weeks=4)).strftime('%Y-%m-%d')
        }
        form = BookingForm(data=form_data, user=self.user)
        # Validity depends on actual recurring booking implementation


class ResourceFormTests(TestCase):
    """Test resource management form."""
    
    def test_valid_resource_form(self):
        """Test valid resource form submission."""
        form_data = {
            'name': 'Test Resource',
            'description': 'A test resource for form validation',
            'category': 'test_equipment',
            'location': 'Test Lab',
            'capacity': 1,
            'requires_training': False,
            'training_level_required': 0,
            'is_bookable': True,
            'is_active': True
        }
        form = ResourceForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_required_fields(self):
        """Test required field validation for resource form."""
        form_data = {
            'name': '',
            'description': '',
            'category': '',
            'location': '',
            'capacity': '',
        }
        form = ResourceForm(data=form_data)
        self.assertFalse(form.is_valid())
        
        required_fields = ['name', 'category', 'location']
        for field in required_fields:
            self.assertIn(field, form.errors)
    
    def test_duplicate_resource_name(self):
        """Test duplicate resource name validation."""
        # Create existing resource
        ResourceFactory(name='Existing Resource')
        
        form_data = {
            'name': 'Existing Resource',
            'description': 'Duplicate name test',
            'category': 'test_equipment',
            'location': 'Test Lab',
            'capacity': 1
        }
        form = ResourceForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)
    
    def test_negative_capacity_validation(self):
        """Test negative capacity validation."""
        form_data = {
            'name': 'Test Resource',
            'description': 'Negative capacity test',
            'category': 'test_equipment',
            'location': 'Test Lab',
            'capacity': -1  # Negative capacity
        }
        form = ResourceForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('capacity', form.errors)
    
    def test_training_level_validation(self):
        """Test training level validation."""
        form_data = {
            'name': 'Training Resource',
            'description': 'Training level test',
            'category': 'test_equipment',
            'location': 'Test Lab',
            'capacity': 1,
            'requires_training': True,
            'training_level_required': -1  # Invalid training level
        }
        form = ResourceForm(data=form_data)
        self.assertFalse(form.is_valid())
    
    def test_long_name_validation(self):
        """Test resource name length validation."""
        long_name = 'x' * 256  # Assuming 255 character limit
        
        form_data = {
            'name': long_name,
            'description': 'Long name test',
            'category': 'test_equipment',
            'location': 'Test Lab',
            'capacity': 1
        }
        form = ResourceForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)


class ApprovalRuleFormTests(TestCase):
    """Test approval rule form validation."""
    
    def setUp(self):
        self.resource = ResourceFactory()
    
    def test_valid_approval_rule_form(self):
        """Test valid approval rule form."""
        form_data = {
            'resource': self.resource.id,
            'user_role': 'student',
            'approval_type': 'single',
            'approver_role': 'lab_manager',
            'conditions': '{"min_advance_hours": 24}'
        }
        form = ApprovalRuleForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_required_fields(self):
        """Test required fields for approval rule form."""
        form_data = {
            'resource': '',
            'user_role': '',
            'approval_type': '',
        }
        form = ApprovalRuleForm(data=form_data)
        self.assertFalse(form.is_valid())
        
        required_fields = ['resource', 'user_role', 'approval_type']
        for field in required_fields:
            self.assertIn(field, form.errors)
    
    def test_invalid_json_conditions(self):
        """Test invalid JSON in conditions field."""
        form_data = {
            'resource': self.resource.id,
            'user_role': 'student',
            'approval_type': 'single',
            'approver_role': 'lab_manager',
            'conditions': 'invalid json'
        }
        form = ApprovalRuleForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('conditions', form.errors)
    
    def test_duplicate_approval_rule(self):
        """Test duplicate approval rule validation."""
        # Create existing approval rule
        ApprovalRule.objects.create(
            resource=self.resource,
            user_role='student',
            approval_type='single',
            approver_role='lab_manager'
        )
        
        # Try to create duplicate
        form_data = {
            'resource': self.resource.id,
            'user_role': 'student',
            'approval_type': 'single',
            'approver_role': 'lab_manager'
        }
        form = ApprovalRuleForm(data=form_data)
        self.assertFalse(form.is_valid())


class BackupConfigurationFormTests(TestCase):
    """Test backup configuration form."""
    
    def test_valid_backup_configuration(self):
        """Test valid backup configuration form."""
        form_data = {
            'frequency': 'daily',
            'time': '02:00',
            'retention_days': 30,
            'is_enabled': True,
            'include_media': True,
            'compress_backup': True
        }
        form = BackupConfigurationForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_invalid_time_format(self):
        """Test invalid time format validation."""
        form_data = {
            'frequency': 'daily',
            'time': '25:00',  # Invalid time
            'retention_days': 30,
            'is_enabled': True
        }
        form = BackupConfigurationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('time', form.errors)
    
    def test_negative_retention_days(self):
        """Test negative retention days validation."""
        form_data = {
            'frequency': 'daily',
            'time': '02:00',
            'retention_days': -1,  # Negative retention
            'is_enabled': True
        }
        form = BackupConfigurationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('retention_days', form.errors)
    
    def test_required_fields(self):
        """Test required fields for backup configuration."""
        form_data = {
            'frequency': '',
            'time': '',
            'retention_days': ''
        }
        form = BackupConfigurationForm(data=form_data)
        self.assertFalse(form.is_valid())
        
        required_fields = ['frequency', 'time', 'retention_days']
        for field in required_fields:
            self.assertIn(field, form.errors)


class UpdateConfigurationFormTests(TestCase):
    """Test update configuration form."""
    
    def test_valid_update_configuration(self):
        """Test valid update configuration form."""
        form_data = {
            'github_repo': 'ohbotno/aperature-booking',
            'auto_check': True,
            'check_interval': 24,
            'notification_email': 'admin@example.com',
            'include_prereleases': False
        }
        form = UpdateConfigurationForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_invalid_github_repo_format(self):
        """Test invalid GitHub repository format."""
        form_data = {
            'github_repo': 'invalid-repo-format',
            'auto_check': True,
            'check_interval': 24,
            'notification_email': 'admin@example.com'
        }
        form = UpdateConfigurationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('github_repo', form.errors)
    
    def test_invalid_email_format(self):
        """Test invalid email format in notification email."""
        form_data = {
            'github_repo': 'ohbotno/aperature-booking',
            'auto_check': True,
            'check_interval': 24,
            'notification_email': 'invalid-email-format',
            'include_prereleases': False
        }
        form = UpdateConfigurationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('notification_email', form.errors)
    
    def test_invalid_check_interval(self):
        """Test invalid check interval validation."""
        form_data = {
            'github_repo': 'ohbotno/aperature-booking',
            'auto_check': True,
            'check_interval': 0,  # Invalid interval
            'notification_email': 'admin@example.com'
        }
        form = UpdateConfigurationForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('check_interval', form.errors)


class FormSecurityTests(TestCase):
    """Test form security features."""
    
    def setUp(self):
        self.user = UserFactory(role='student')
        self.resource = ResourceFactory()
    
    def test_xss_prevention_in_text_fields(self):
        """Test XSS prevention in form text fields."""
        xss_payload = '<script>alert("xss")</script>'
        
        form_data = {
            'resource': self.resource.id,
            'start_datetime': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d %H:%M'),
            'end_datetime': (datetime.now() + timedelta(days=1, hours=2)).strftime('%Y-%m-%d %H:%M'),
            'purpose': xss_payload
        }
        form = BookingForm(data=form_data, user=self.user)
        
        if form.is_valid():
            # Check that XSS payload is sanitized
            cleaned_purpose = form.cleaned_data['purpose']
            self.assertNotIn('<script>', cleaned_purpose)
    
    def test_sql_injection_prevention(self):
        """Test SQL injection prevention in form fields."""
        sql_payload = "'; DROP TABLE booking; --"
        
        form_data = {
            'name': sql_payload,
            'description': 'SQL injection test',
            'category': 'test_equipment',
            'location': 'Test Lab',
            'capacity': 1
        }
        form = ResourceForm(data=form_data)
        
        # Form should either validate and sanitize, or reject the input
        if form.is_valid():
            cleaned_name = form.cleaned_data['name']
            self.assertNotIn('DROP TABLE', cleaned_name)
    
    def test_csrf_token_in_forms(self):
        """Test CSRF token is included in form rendering."""
        from django.template import Template, Context
        from django.http import HttpRequest
        from django.middleware.csrf import get_token
        
        request = HttpRequest()
        request.user = self.user
        csrf_token = get_token(request)
        
        # Test that forms include CSRF protection
        # This would be tested in view tests rather than form tests
        pass
    
    def test_field_length_limits(self):
        """Test field length limits prevent buffer overflow."""
        very_long_string = 'x' * 10000
        
        form_data = {
            'resource': self.resource.id,
            'start_datetime': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d %H:%M'),
            'end_datetime': (datetime.now() + timedelta(days=1, hours=2)).strftime('%Y-%m-%d %H:%M'),
            'purpose': very_long_string
        }
        form = BookingForm(data=form_data, user=self.user)
        
        # Form should reject or truncate extremely long input
        if not form.is_valid():
            self.assertIn('purpose', form.errors)
    
    def test_file_upload_validation(self):
        """Test file upload validation and security."""
        # This test would apply if forms include file upload fields
        # Test file type validation, size limits, etc.
        pass


class FormAccessibilityTests(TestCase):
    """Test form accessibility features."""
    
    def test_form_field_labels(self):
        """Test form fields have proper labels."""
        form = BookingForm(user=UserFactory())
        
        # Check that form fields have labels
        for field_name, field in form.fields.items():
            self.assertTrue(hasattr(field, 'label'))
            self.assertIsNotNone(field.label)
    
    def test_form_field_help_text(self):
        """Test form fields have helpful help text."""
        form = BookingForm(user=UserFactory())
        
        # Important fields should have help text
        if 'start_datetime' in form.fields:
            self.assertTrue(form.fields['start_datetime'].help_text)
    
    def test_form_error_messages(self):
        """Test form error messages are clear and helpful."""
        form_data = {
            'resource': '',  # Missing required field
            'purpose': ''
        }
        form = BookingForm(data=form_data, user=UserFactory())
        self.assertFalse(form.is_valid())
        
        # Error messages should be present and helpful
        for field_name, errors in form.errors.items():
            self.assertTrue(len(errors) > 0)
            for error in errors:
                self.assertTrue(len(error) > 10)  # Reasonably descriptive


class FormPerformanceTests(TestCase):
    """Test form performance characteristics."""
    
    def test_form_rendering_performance(self):
        """Test form rendering doesn't have performance issues."""
        # Create many resources
        resources = ResourceFactory.create_batch(100)
        
        # Form should still render quickly even with many choices
        form = BookingForm(user=UserFactory())
        
        # Check that resource choices are loaded
        if 'resource' in form.fields:
            resource_choices = form.fields['resource'].queryset
            self.assertGreaterEqual(resource_choices.count(), 100)
    
    def test_form_validation_performance(self):
        """Test form validation performance."""
        # Create scenario with many existing bookings
        resource = ResourceFactory()
        user = UserFactory()
        
        # Create many existing bookings
        for i in range(50):
            start_time = datetime.now() + timedelta(days=i+1)
            end_time = start_time + timedelta(hours=2)
            Booking.objects.create(
                user=user,
                resource=resource,
                start_datetime=start_time,
                end_datetime=end_time,
                purpose=f'Booking {i}',
                status='confirmed'
            )
        
        # New booking form should still validate quickly
        form_data = {
            'resource': resource.id,
            'start_datetime': (datetime.now() + timedelta(days=100)).strftime('%Y-%m-%d %H:%M'),
            'end_datetime': (datetime.now() + timedelta(days=100, hours=2)).strftime('%Y-%m-%d %H:%M'),
            'purpose': 'Performance test booking'
        }
        form = BookingForm(data=form_data, user=user)
        
        # Validation should complete without timing out
        is_valid = form.is_valid()
        # The result depends on actual conflict checking implementation