# booking/forms/auth.py
"""
Authentication-related forms for the Aperture Booking system.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordResetForm, SetPasswordForm, AuthenticationForm
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.utils import timezone
from datetime import datetime, timedelta

from ..models import (
    UserProfile, EmailVerificationToken, PasswordResetToken, 
    Faculty, College, Department, CalendarSyncPreferences
)
from ..utils.email import get_logo_base64, get_email_branding_context




class UserRegistrationForm(UserCreationForm):
    """Extended user registration form with profile fields."""
    # Use email as username
    email = forms.EmailField(
        required=True,
        label="Email Address",
        help_text="This will be your username for logging in"
    )
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    
    # Exclude sysadmin role from registration - only admins can create sysadmins
    role = forms.ChoiceField(
        choices=[choice for choice in UserProfile.ROLE_CHOICES if choice[0] != 'sysadmin'],
        initial='student'
    )
    
    # Academic structure
    faculty = forms.ModelChoiceField(
        queryset=Faculty.objects.filter(is_active=True),
        required=False,
        empty_label="Select Faculty"
    )
    college = forms.ModelChoiceField(
        queryset=College.objects.none(),  # Will be populated dynamically
        required=False,
        empty_label="Select College"
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.none(),  # Will be populated dynamically
        required=False,
        empty_label="Select Department"
    )
    
    # Research/academic group
    group = forms.CharField(max_length=100, required=False, help_text="Research group or class")
    
    # Role-specific fields
    student_id = forms.CharField(
        max_length=50, 
        required=False, 
        label="Student ID",
        help_text="Required for students"
    )
    student_level = forms.ChoiceField(
        choices=[('', 'Select Level')] + UserProfile.STUDENT_LEVEL_CHOICES,
        required=False,
        label="Student Level",
        help_text="Required for students"
    )
    staff_number = forms.CharField(
        max_length=50, 
        required=False, 
        label="Staff Number",
        help_text="Required for staff members"
    )
    
    # Contact info
    phone = forms.CharField(max_length=20, required=False)

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Remove username field since we're using email
        if 'username' in self.fields:
            del self.fields['username']
        
        # Add CSS classes to all fields
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})
        
        # Set up dynamic choices for college and department
        if 'faculty' in self.data:
            try:
                faculty_id = int(self.data.get('faculty'))
                self.fields['college'].queryset = College.objects.filter(
                    faculty_id=faculty_id, is_active=True
                ).order_by('name')
            except (ValueError, TypeError):
                pass
        
        if 'college' in self.data:
            try:
                college_id = int(self.data.get('college'))
                self.fields['department'].queryset = Department.objects.filter(
                    college_id=college_id, is_active=True
                ).order_by('name')
            except (ValueError, TypeError):
                pass

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        student_id = cleaned_data.get('student_id')
        student_level = cleaned_data.get('student_level')
        staff_number = cleaned_data.get('staff_number')

        # Role-specific validation
        if role == 'student':
            if not student_id:
                self.add_error('student_id', 'Student ID is required for students.')
            if not student_level:
                self.add_error('student_level', 'Student level is required for students.')
        elif role in ['lecturer', 'researcher', 'technician']:
            if not staff_number:
                self.add_error('staff_number', f'Staff number is required for {role}s.')

        return cleaned_data

    def save(self, commit=True):
        # Use email as username
        user = super().save(commit=False)
        user.username = self.cleaned_data['email']
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        
        # User starts as inactive until email verification
        user.is_active = False
        
        if commit:
            user.save()
            
            # Since the User post_save signal creates a UserProfile automatically,
            # we need to get and update the existing profile instead of creating a new one
            try:
                profile = user.userprofile
            except UserProfile.DoesNotExist:
                # Fallback: create profile if signal didn't work for some reason
                profile = UserProfile.objects.create(user=user)
            
            # Update profile with form data
            profile.role = self.cleaned_data['role']
            profile.faculty = self.cleaned_data.get('faculty')
            profile.college = self.cleaned_data.get('college')
            profile.department = self.cleaned_data.get('department')
            profile.group = self.cleaned_data.get('group', '')
            profile.student_id = self.cleaned_data.get('student_id', '')
            profile.student_level = self.cleaned_data.get('student_level', '')
            profile.staff_number = self.cleaned_data.get('staff_number', '')
            profile.phone = self.cleaned_data.get('phone', '')
            profile.email_verified = False
            profile.save()
            
            # Create email verification token
            token = EmailVerificationToken.objects.create(user=user)
            
            # Send verification email
            self.send_verification_email(user, token)
        
        return user

    def send_verification_email(self, user, token):
        """Send email verification email."""
        try:
            from django.contrib.sites.models import Site
            current_site = Site.objects.get_current()
            
            # Get logo for email
            logo_base64 = get_logo_base64()
            
            context = {
                'user': user,
                'domain': current_site.domain,
                'token': token.token,
                'logo_base64': logo_base64,
                'site_name': current_site.name,
            }
            
            # Render email content
            html_message = render_to_string('registration/verification_email.html', context)
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject=f'Verify your email for {current_site.name}',
                message=plain_message,
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception as e:
            # Log the error but don't raise it to avoid breaking registration
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send verification email: {e}")


class UserProfileForm(forms.ModelForm):
    """Form for editing user profile."""
    
    class Meta:
        model = UserProfile
        fields = [
            'role', 'faculty', 'college', 'department', 'group',
            'student_id', 'student_level', 'staff_number', 'phone',
            'theme_preference'
        ]
        widgets = {
            'theme_preference': forms.Select(choices=[
                ('light', 'Light'),
                ('dark', 'Dark'),
                ('system', 'System'),
            ]),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add CSS classes
        for field_name, field in self.fields.items():
            field.widget.attrs.update({'class': 'form-control'})
        
        # Set up dynamic choices for college and department
        if self.instance and self.instance.faculty:
            self.fields['college'].queryset = College.objects.filter(
                faculty=self.instance.faculty, is_active=True
            ).order_by('name')
            
            if self.instance.college:
                self.fields['department'].queryset = Department.objects.filter(
                    college=self.instance.college, is_active=True
                ).order_by('name')


class CustomPasswordResetForm(PasswordResetForm):
    """Custom password reset form using our token system."""
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        
        # Check if user exists and is active
        try:
            user = User.objects.get(email=email)
            if not user.is_active:
                raise forms.ValidationError(
                    "This account is inactive. Please contact support."
                )
        except User.DoesNotExist:
            raise forms.ValidationError(
                "No user found with this email address."
            )
        
        return email

    def save(self, domain_override=None, subject_template_name=None,
             email_template_name=None, use_https=False, token_generator=None,
             from_email=None, request=None, html_email_template_name=None,
             extra_email_context=None):
        """Generate password reset token and send email."""
        email = self.cleaned_data['email']
        
        try:
            user = User.objects.get(email=email)
            
            # Delete any existing unused tokens
            PasswordResetToken.objects.filter(user=user, is_used=False).delete()
            
            # Create new password reset token
            token = PasswordResetToken.objects.create(user=user)
            
            # Send reset email
            self.send_reset_email(user, token, request)
            
        except User.DoesNotExist:
            # Silently fail for security reasons
            pass

    def send_reset_email(self, user, token, request=None):
        """Send password reset email."""
        try:
            from django.contrib.sites.models import Site
            current_site = Site.objects.get_current()
            
            # Get logo for email
            logo_base64 = get_logo_base64()
            
            context = {
                'user': user,
                'domain': current_site.domain,
                'token': token.token,
                'logo_base64': logo_base64,
                'site_name': current_site.name,
            }
            
            # Render email content
            html_message = render_to_string('registration/password_reset_email.html', context)
            plain_message = strip_tags(html_message)
            
            send_mail(
                subject=f'Password Reset for {current_site.name}',
                message=plain_message,
                html_message=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send password reset email: {e}")


class CustomSetPasswordForm(SetPasswordForm):
    """Custom set password form."""
    pass


class CustomAuthenticationForm(AuthenticationForm):
    """Custom authentication form with email as username."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Change username field label to email
        self.fields['username'].label = 'Email Address'
        self.fields['username'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Enter your email address'
        })
        self.fields['password'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Enter your password'
        })

    def clean_username(self):
        """Allow login with email address."""
        username = self.cleaned_data.get('username')
        
        # If username looks like email, try to find user by email
        if '@' in username:
            try:
                user = User.objects.get(email=username)
                return user.username
            except User.DoesNotExist:
                pass
        
        return username


class CalendarSyncPreferencesForm(forms.ModelForm):
    """Form for managing calendar sync preferences."""
    
    class Meta:
        model = CalendarSyncPreferences
        fields = [
            'auto_sync_timing',
            'sync_future_bookings_only',
            'sync_cancelled_bookings',
            'sync_pending_bookings',
            'conflict_resolution',
            'event_prefix',
            'include_resource_in_title',
            'include_description',
            'set_event_location',
            'notify_sync_errors',
            'notify_sync_success',
        ]
        widgets = {
            'auto_sync_timing': forms.Select(attrs={
                'class': 'form-select'
            }),
            'conflict_resolution': forms.Select(attrs={
                'class': 'form-select'
            }),
            'event_prefix': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '[Lab] '
            }),
            'sync_future_bookings_only': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'sync_cancelled_bookings': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'sync_pending_bookings': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'include_resource_in_title': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'include_description': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'set_event_location': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'notify_sync_errors': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'notify_sync_success': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        help_texts = {
            'auto_sync_timing': 'How often to automatically sync your bookings with Google Calendar',
            'conflict_resolution': 'What to do when there are conflicts between Labitory and Google Calendar',
            'event_prefix': 'Text to add before Google Calendar event titles (optional)',
        }