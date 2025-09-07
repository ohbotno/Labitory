import base64
import os
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
from .models import (
    AboutPage, UserProfile, EmailVerificationToken, PasswordResetToken, Booking, Resource, BookingTemplate, 
    Faculty, College, Department, AccessRequest, RiskAssessment, UserRiskAssessment, 
    TrainingCourse, UserTraining, ResourceResponsible, ResourceIssue,
    Maintenance, MaintenanceVendor, MaintenanceDocument, MaintenanceAlert, EmailConfiguration,
    ChecklistItem, ResourceChecklistItem, ChecklistResponse, CalendarSyncPreferences
)
from .recurring import RecurringBookingPattern


def get_logo_base64():
    """Get the logo as a base64 encoded string for email templates."""
    try:
        # First try to get custom logo from branding configuration
        from .models import LicenseConfiguration
        try:
            license_config = LicenseConfiguration.objects.filter(is_active=True).first()
            if license_config and hasattr(license_config, 'branding') and license_config.branding.logo_primary:
                logo_path = license_config.branding.logo_primary.path
                if os.path.exists(logo_path):
                    with open(logo_path, 'rb') as logo_file:
                        logo_data = logo_file.read()
                        return base64.b64encode(logo_data).decode('utf-8')
        except Exception:
            pass
        
        # Fallback to default logo
        logo_path = os.path.join(settings.STATIC_ROOT or 'static', 'images', 'logo.png')
        if not os.path.exists(logo_path):
            # Fallback to development path
            logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'logo.png')
        
        if os.path.exists(logo_path):
            with open(logo_path, 'rb') as logo_file:
                logo_data = logo_file.read()
                return base64.b64encode(logo_data).decode('utf-8')
    except Exception:
        pass
    return None


def get_email_branding_context():
    """Get branding context for email templates."""
    from .models import LicenseConfiguration, LabSettings
    
    context = {
        'app_title': 'Labitory',
        'company_name': 'Labitory',
        'lab_name': 'Labitory',
        'logo_base64': get_logo_base64(),
        'support_email': 'support@aperature-booking.org',
        'website_url': '',
        'show_powered_by': True,
    }
    
    try:
        # Get lab settings
        lab_name = LabSettings.get_lab_name()
        context['lab_name'] = lab_name
        
        # Get branding from license configuration
        license_config = LicenseConfiguration.objects.filter(is_active=True).first()
        if license_config and hasattr(license_config, 'branding'):
            branding = license_config.branding
            context.update({
                'app_title': branding.app_title,
                'company_name': branding.company_name,
                'support_email': branding.support_email or context['support_email'],
                'website_url': branding.website_url,
                'show_powered_by': branding.show_powered_by,
            })
    except Exception:
        pass
    
    return context


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
                raise forms.ValidationError("Student ID is required for student role.")
            if not student_level:
                raise forms.ValidationError("Student level is required for student role.")
        else:
            # Staff roles need staff number
            if role in ['researcher', 'academic', 'technician']:
                if not staff_number:
                    raise forms.ValidationError(f"Staff number is required for {dict(UserProfile.ROLE_CHOICES)[role]} role.")
        
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        email = self.cleaned_data['email']
        
        # Use email as username
        user.username = email
        user.email = email
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.is_active = False  # Deactivate until email verification
        
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
            profile.student_id = self.cleaned_data.get('student_id', '') if self.cleaned_data['role'] == 'student' else ''
            profile.student_level = self.cleaned_data.get('student_level', '') if self.cleaned_data['role'] == 'student' else ''
            profile.staff_number = self.cleaned_data.get('staff_number', '') if self.cleaned_data['role'] != 'student' else ''
            profile.phone = self.cleaned_data.get('phone', '')
            profile.email_verified = False
            profile.save()
            
            # Create email verification token
            token = EmailVerificationToken.objects.create(user=user)
            
            # Send verification email
            self.send_verification_email(user, token)
            
        return user
    
    def send_verification_email(self, user, token):
        """Send email verification to the user."""
        # Apply active email configuration before sending
        from .models import EmailConfiguration
        active_config = EmailConfiguration.get_active_configuration()
        if active_config:
            active_config.apply_to_settings()
        
        # Get branding context
        branding_context = get_email_branding_context()
        
        subject = f'Verify your {branding_context["app_title"]} account'
        
        # Render email template with branding context
        email_context = {
            'user': user,
            'token': token.token,
            'domain': getattr(settings, 'SITE_DOMAIN', 'localhost:8000'),
            **branding_context  # Include all branding variables
        }
        
        html_message = render_to_string('registration/verification_email.html', email_context)
        plain_message = strip_tags(html_message)
        
        try:
            send_mail(
                subject,
                plain_message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as e:
            # Log error but don't prevent registration
            import logging
            logger = logging.getLogger('booking')
            logger.error(f"Failed to send verification email to {user.email}: {e}")


class UserProfileForm(forms.ModelForm):
    """Form for editing user profile information."""
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)

    class Meta:
        model = UserProfile
        fields = [
            'role', 'faculty', 'college', 'department', 'group', 
            'student_id', 'student_level', 'staff_number', 'phone'
        ]
        widgets = {
            'role': forms.Select(attrs={'class': 'form-control'}),
            'faculty': forms.Select(attrs={'class': 'form-control'}),
            'college': forms.Select(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'group': forms.TextInput(attrs={'class': 'form-control'}),
            'student_id': forms.TextInput(attrs={'class': 'form-control'}),
            'student_level': forms.Select(attrs={'class': 'form-control'}),
            'staff_number': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        # Extract current user to check permissions
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        if self.instance and self.instance.user:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            self.fields['email'].initial = self.instance.user.email
        
        self.fields['first_name'].widget.attrs.update({'class': 'form-control'})
        self.fields['last_name'].widget.attrs.update({'class': 'form-control'})
        self.fields['email'].widget.attrs.update({'class': 'form-control'})
        
        # Restrict role choices based on current user permissions
        if self.current_user:
            # Only superusers or sysadmins can assign sysadmin role
            if not (self.current_user.is_superuser or 
                    (hasattr(self.current_user, 'userprofile') and 
                     self.current_user.userprofile.role == 'sysadmin')):
                # Filter out sysadmin role for non-admin users
                role_choices = [choice for choice in UserProfile.ROLE_CHOICES if choice[0] != 'sysadmin']
                self.fields['role'].choices = role_choices
        
        # Set up dynamic choices for college and department based on existing data
        if self.instance.pk:
            if self.instance.faculty:
                self.fields['college'].queryset = College.objects.filter(
                    faculty=self.instance.faculty, is_active=True
                ).order_by('name')
            if self.instance.college:
                self.fields['department'].queryset = Department.objects.filter(
                    college=self.instance.college, is_active=True
                ).order_by('name')
        
        # Set up dynamic choices based on form data (for validation)
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

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        student_id = cleaned_data.get('student_id')
        student_level = cleaned_data.get('student_level')
        staff_number = cleaned_data.get('staff_number')
        
        # Role-specific validation
        if role == 'student':
            if not student_id:
                raise forms.ValidationError("Student ID is required for student role.")
            if not student_level:
                raise forms.ValidationError("Student level is required for student role.")
        else:
            # Staff roles need staff number
            if role in ['researcher', 'academic', 'technician', 'sysadmin']:
                if not staff_number:
                    raise forms.ValidationError(f"Staff number is required for {dict(UserProfile.ROLE_CHOICES)[role]} role.")
        
        return cleaned_data

    def save(self, commit=True):
        profile = super().save(commit=False)
        if commit:
            # Update username to match email if email changed
            old_email = profile.user.email
            new_email = self.cleaned_data['email']
            
            profile.user.first_name = self.cleaned_data['first_name']
            profile.user.last_name = self.cleaned_data['last_name']
            profile.user.email = new_email
            
            # Update username if email changed
            if old_email != new_email:
                profile.user.username = new_email
            
            profile.user.save()
            profile.save()
        return profile


class CustomPasswordResetForm(PasswordResetForm):
    """Custom password reset form using our token system."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].widget.attrs.update({'class': 'form-control'})
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not User.objects.filter(email=email, is_active=True).exists():
            raise forms.ValidationError("No active account found with this email address.")
        return email
    
    def save(self, request=None, **kwargs):
        """Generate our custom reset token and send email."""
        email = self.cleaned_data['email']
        user = User.objects.get(email=email, is_active=True)
        
        # Clear any existing unused tokens
        PasswordResetToken.objects.filter(user=user, is_used=False).delete()
        
        # Create new token
        token = PasswordResetToken.objects.create(user=user)
        
        # Send reset email
        self.send_reset_email(user, token, request)
        
        return email
    
    def send_reset_email(self, user, token, request=None):
        """Send password reset email."""
        # Apply active email configuration before sending
        from .models import EmailConfiguration
        active_config = EmailConfiguration.get_active_configuration()
        if active_config:
            active_config.apply_to_settings()
        
        # Get branding context
        branding_context = get_email_branding_context()
        
        subject = f'Reset your {branding_context["app_title"]} password'
        
        # Get domain from request or settings
        if request:
            domain = request.get_host()
        else:
            domain = getattr(settings, 'SITE_DOMAIN', 'localhost:8000')
        
        # Render email template with branding context
        email_context = {
            'user': user,
            'token': token.token,
            'domain': domain,
            'protocol': 'https' if getattr(settings, 'USE_HTTPS', False) else 'http',
            **branding_context  # Include all branding variables
        }
        
        html_message = render_to_string('registration/password_reset_email.html', email_context)
        plain_message = strip_tags(html_message)
        
        try:
            send_mail(
                subject,
                plain_message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as e:
            import logging
            logger = logging.getLogger('booking')
            logger.error(f"Failed to send password reset email to {user.email}: {e}")


class CustomSetPasswordForm(SetPasswordForm):
    """Custom set password form with styling."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['new_password1'].widget.attrs.update({'class': 'form-control'})
        self.fields['new_password2'].widget.attrs.update({'class': 'form-control'})


class CustomAuthenticationForm(AuthenticationForm):
    """Custom authentication form with better error messages for inactive users."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': 'form-control'})
        self.fields['password'].widget.attrs.update({'class': 'form-control'})
        # Update labels to reflect that we use email as username
        self.fields['username'].label = 'Email Address'
    
    def confirm_login_allowed(self, user):
        """Override to provide better error messages for inactive users."""
        if not user.is_active:
            # Check if user has unverified email
            try:
                profile = user.userprofile
                if not profile.email_verified:
                    from django.urls import reverse
                    resend_url = reverse('booking:resend_verification')
                    raise forms.ValidationError(
                        f'<strong><i class="bi bi-hourglass-split"></i> Account Awaiting Authorization</strong><br><br>'
                        f'<i class="bi bi-info-circle"></i> Your account registration is currently waiting for administrator approval.<br><br>'
                        f'<i class="bi bi-clock"></i> <strong>What happens next:</strong><br>'
                        f'1. An administrator will review your registration<br>'
                        f'2. You will receive an email once your account is approved<br>'
                        f'3. You can then log in with your credentials<br><br>'
                        f'<i class="bi bi-envelope"></i> <strong>First time?</strong> Make sure you have verified your email address first.<br>'
                        f'<a href="{resend_url}" class="btn btn-sm btn-outline-warning">Resend Verification Email</a><br><br>'
                        f'<small class="text-muted">Please be patient - this process may take 1-2 business days.</small>',
                        code='inactive_unverified'
                    )
            except UserProfile.DoesNotExist:
                pass
            
            # Default inactive message
            raise forms.ValidationError(
                '<strong><i class="bi bi-exclamation-triangle"></i> Account Inactive</strong><br><br>'
                'Your account is inactive. Please contact the administrator for assistance.',
                code='inactive'
            )


class BookingForm(forms.ModelForm):
    """Form for creating and editing bookings."""
    
    # Hidden field for conflict override
    override_conflicts = forms.BooleanField(
        required=False,
        widget=forms.HiddenInput(),
        help_text="Set to true to override booking conflicts (privileged users only)"
    )
    
    # Field for custom override message
    override_message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Enter a message to notify the original booking holder about this override...',
            'style': 'display: none;'
        }),
        help_text="Message to send to the original booking holder when overriding their booking"
    )
    
    class Meta:
        model = Booking
        fields = ['resource', 'title', 'description', 'start_time', 'end_time', 'shared_with_group', 'notes']
        widgets = {
            'resource': forms.Select(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'start_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'shared_with_group': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user:
            # Filter resources based on user permissions
            try:
                user_profile = self.user.userprofile
                available_resources = []
                for resource in Resource.objects.filter(is_active=True, is_closed=False):
                    if resource.is_available_for_user(user_profile):
                        available_resources.append(resource.pk)
                self.fields['resource'].queryset = Resource.objects.filter(pk__in=available_resources)
            except:
                self.fields['resource'].queryset = Resource.objects.filter(is_active=True, is_closed=False)
    
    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        resource = cleaned_data.get('resource')
        override_conflicts = cleaned_data.get('override_conflicts', False)
        override_message = cleaned_data.get('override_message', '')
        
        # Check if resource is closed
        if resource and resource.is_closed:
            raise forms.ValidationError(
                f"The resource '{resource.name}' is temporarily closed for bookings."
                + (f" Reason: {resource.closed_reason}" if resource.closed_reason else "")
            )
        
        if start_time and end_time:
            # Make timezone-aware if needed
            if timezone.is_naive(start_time):
                start_time = timezone.make_aware(start_time)
                cleaned_data['start_time'] = start_time
            
            if timezone.is_naive(end_time):
                end_time = timezone.make_aware(end_time)
                cleaned_data['end_time'] = end_time
            
            if start_time >= end_time:
                raise forms.ValidationError("End time must be after start time.")
            
            # Allow booking up to 5 minutes in the past to account for form submission time
            if start_time < timezone.now() - timedelta(minutes=5):
                raise forms.ValidationError("Cannot book in the past.")
            
            # Check booking window (9 AM - 6 PM) - more lenient check
            if (start_time.hour < 9 or start_time.hour >= 18):
                raise forms.ValidationError("Booking start time must be between 09:00 and 18:00.")
                
            if end_time.hour > 18 or (end_time.hour == 18 and end_time.minute > 0):
                raise forms.ValidationError("Booking must end by 18:00.")
            
            # Check max booking hours if set
            if resource and resource.max_booking_hours:
                duration_hours = (end_time - start_time).total_seconds() / 3600
                if duration_hours > resource.max_booking_hours:
                    raise forms.ValidationError(
                        f"Booking exceeds maximum allowed hours ({resource.max_booking_hours}h)."
                    )
            
            # Check for booking conflicts
            if resource and start_time and end_time:
                try:
                    conflicts = self._check_booking_conflicts(resource, start_time, end_time)
                    
                    if conflicts:
                        # Check if user can override conflicts
                        if self.user and self._can_override_conflicts():
                            if not override_conflicts:
                                # Show conflict information and override option
                                conflict_details = self._format_conflict_details(conflicts)
                                self._conflicts = conflicts  # Store for view to handle
                                raise forms.ValidationError(
                                    f"Booking conflict detected: {conflict_details}. "
                                    "As a privileged user, you can override this conflict."
                                )
                            elif override_conflicts and not override_message.strip():
                                raise forms.ValidationError(
                                    "Please provide a message to notify the original booking holder about this override."
                                )
                        else:
                            # Regular user - cannot override
                            conflict_details = self._format_conflict_details(conflicts)
                            raise forms.ValidationError(
                                f"Booking conflict detected: {conflict_details}. "
                                "Please choose a different time slot."
                            )
                except Exception as e:
                    # Log the error but don't crash the form
                    import logging
                    logger = logging.getLogger('booking')
                    logger.error(f"Error in conflict detection: {e}")
                    # Allow booking to proceed if conflict detection fails
        
        return cleaned_data
    
    def _can_override_conflicts(self):
        """Check if the current user can override booking conflicts."""
        if not self.user:
            return False
        
        # Superusers and staff can always override
        if self.user.is_superuser or self.user.is_staff:
            return True
        
        try:
            profile = self.user.userprofile
            return profile.role in ['lecturer', 'technician', 'lab_manager', 'sysadmin']
        except UserProfile.DoesNotExist:
            # If no profile exists, fall back to Django permissions
            return False
    
    def _check_booking_conflicts(self, resource, start_time, end_time):
        """Check for booking conflicts with the given time slot."""
        conflicts = Booking.objects.filter(
            resource=resource,
            status__in=['approved', 'pending'],
            start_time__lt=end_time,
            end_time__gt=start_time
        )
        
        # Exclude current booking if editing
        if self.instance and self.instance.pk:
            conflicts = conflicts.exclude(pk=self.instance.pk)
        
        return list(conflicts)
    
    def _format_conflict_details(self, conflicts):
        """Format conflict details for user display."""
        if not conflicts:
            return "No conflicts found"
        
        details = []
        for conflict in conflicts:
            user_name = f"{conflict.user.first_name} {conflict.user.last_name}".strip()
            if not user_name:
                user_name = conflict.user.username
            
            time_str = f"{conflict.start_time.strftime('%m/%d %H:%M')} - {conflict.end_time.strftime('%H:%M')}"
            details.append(f"'{conflict.title}' by {user_name} ({time_str})")
        
        return "; ".join(details)
    
    def get_conflicts(self):
        """Get conflicts detected during validation for view processing."""
        return getattr(self, '_conflicts', [])


class RecurringBookingForm(forms.Form):
    """Form for creating recurring bookings."""
    
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]
    
    WEEKDAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    frequency = forms.ChoiceField(
        choices=FREQUENCY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="How often to repeat the booking"
    )
    
    interval = forms.IntegerField(
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Repeat every X periods (e.g., every 2 weeks)"
    )
    
    count = forms.IntegerField(
        min_value=1,
        max_value=52,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Number of occurrences (leave blank to use end date)"
    )
    
    until = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        help_text="End date for recurrence (leave blank to use count)"
    )
    
    weekdays = forms.MultipleChoiceField(
        choices=WEEKDAY_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        help_text="Days of the week (for weekly recurrence)"
    )
    
    skip_conflicts = forms.BooleanField(
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Skip dates that have conflicts with existing bookings"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        frequency = cleaned_data.get('frequency')
        count = cleaned_data.get('count')
        until = cleaned_data.get('until')
        weekdays = cleaned_data.get('weekdays')
        
        if not count and not until:
            raise forms.ValidationError("Either specify a count or an end date.")
        
        if count and until:
            raise forms.ValidationError("Cannot specify both count and end date.")
        
        if frequency == 'weekly' and not weekdays:
            raise forms.ValidationError("Weekly recurrence requires selecting weekdays.")
        
        if until and until <= timezone.now().date():
            raise forms.ValidationError("End date must be in the future.")
        
        return cleaned_data
    
    def create_pattern(self):
        """Create RecurringBookingPattern from form data."""
        cleaned_data = self.cleaned_data
        
        until_datetime = None
        if cleaned_data.get('until'):
            until_datetime = timezone.make_aware(
                datetime.combine(cleaned_data['until'], datetime.min.time())
            )
        
        weekdays = None
        if cleaned_data.get('weekdays'):
            weekdays = [int(day) for day in cleaned_data['weekdays']]
        
        return RecurringBookingPattern(
            frequency=cleaned_data['frequency'],
            interval=cleaned_data['interval'],
            count=cleaned_data.get('count'),
            until=until_datetime,
            by_weekday=weekdays
        )


class BookingTemplateForm(forms.ModelForm):
    """Form for creating and editing booking templates."""
    
    class Meta:
        model = BookingTemplate
        fields = ['name', 'description', 'resource', 'title_template', 'description_template', 
                 'duration_hours', 'duration_minutes', 'preferred_start_time', 
                 'shared_with_group', 'notes_template', 'is_public']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'resource': forms.Select(attrs={'class': 'form-control'}),
            'title_template': forms.TextInput(attrs={'class': 'form-control'}),
            'description_template': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'duration_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 8}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 59, 'step': 15}),
            'preferred_start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'shared_with_group': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes_template': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user:
            # Filter resources based on user permissions
            try:
                user_profile = self.user.userprofile
                available_resources = []
                for resource in Resource.objects.filter(is_active=True, is_closed=False):
                    if resource.is_available_for_user(user_profile):
                        available_resources.append(resource.pk)
                self.fields['resource'].queryset = Resource.objects.filter(pk__in=available_resources)
            except:
                self.fields['resource'].queryset = Resource.objects.filter(is_active=True, is_closed=False)
    
    def clean(self):
        cleaned_data = super().clean()
        duration_hours = cleaned_data.get('duration_hours', 0)
        duration_minutes = cleaned_data.get('duration_minutes', 0)
        
        if duration_hours == 0 and duration_minutes == 0:
            raise forms.ValidationError("Duration must be at least 1 minute.")
        
        # Check max duration
        total_minutes = (duration_hours * 60) + duration_minutes
        if total_minutes > 480:  # 8 hours
            raise forms.ValidationError("Duration cannot exceed 8 hours.")
        
        return cleaned_data


class CreateBookingFromTemplateForm(forms.Form):
    """Form for creating a booking from a template."""
    template = forms.ModelChoiceField(
        queryset=BookingTemplate.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Select a template to use for this booking"
    )
    
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        help_text="Date for the booking"
    )
    
    start_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        help_text="Start time (leave blank to use template's preferred time)"
    )
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user:
            # Show templates accessible to the user
            accessible_templates = []
            for template in BookingTemplate.objects.all():
                if template.is_accessible_by_user(self.user):
                    accessible_templates.append(template.pk)
            
            self.fields['template'].queryset = BookingTemplate.objects.filter(
                pk__in=accessible_templates
            ).order_by('-use_count', 'name')
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        start_time = cleaned_data.get('start_time')
        template = cleaned_data.get('template')
        
        if start_date and start_date <= timezone.now().date():
            raise forms.ValidationError("Booking date must be in the future.")
        
        # Use template's preferred time if none provided
        if not start_time and template and template.preferred_start_time:
            cleaned_data['start_time'] = template.preferred_start_time
        elif not start_time:
            raise forms.ValidationError("Start time is required when template has no preferred time.")
        
        return cleaned_data
    
    def create_booking(self):
        """Create booking from template and form data."""
        template = self.cleaned_data['template']
        start_date = self.cleaned_data['start_date']
        start_time = self.cleaned_data['start_time']
        
        start_datetime = timezone.make_aware(
            datetime.combine(start_date, start_time)
        )
        
        return template.create_booking_from_template(start_datetime, self.user)


class SaveAsTemplateForm(forms.Form):
    """Form for saving a booking as a template."""
    name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text="Name for this template"
    )
    
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        help_text="Optional description for this template"
    )
    
    is_public = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Make this template available to other users"
    )


# Approval Workflow Forms

class AccessRequestForm(forms.ModelForm):
    """Form for requesting access to a resource."""
    
    class Meta:
        model = AccessRequest
        fields = ['access_type', 'justification', 'requested_duration_days', 'supervisor_name', 'supervisor_email']
        widgets = {
            'access_type': forms.Select(attrs={'class': 'form-control'}),
            'justification': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 4, 
                'placeholder': 'Please explain why you need access to this resource...'
            }),
            'requested_duration_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 365,
                'value': 90
            }),
            'supervisor_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Full name of your supervisor'
            }),
            'supervisor_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'supervisor@university.edu'
            })
        }
        help_texts = {
            'access_type': 'Type of access you are requesting',
            'justification': 'Detailed explanation of why you need access',
            'requested_duration_days': 'How many days you need access for (max 1 year)',
            'supervisor_name': 'Name of your academic supervisor (required for students)',
            'supervisor_email': 'Email address of your academic supervisor (required for students)'
        }

    def __init__(self, *args, **kwargs):
        self.resource = kwargs.pop('resource', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.resource:
            # Customize access type choices based on resource
            self.fields['justification'].help_text = f'Explain why you need access to {self.resource.name}'
        
        # Make supervisor fields required for students
        if self.user and hasattr(self.user, 'userprofile') and self.user.userprofile.role == 'student':
            self.fields['supervisor_name'].required = True
            self.fields['supervisor_email'].required = True
        else:
            # Hide supervisor fields for non-students
            self.fields['supervisor_name'].widget = forms.HiddenInput()
            self.fields['supervisor_email'].widget = forms.HiddenInput()
            self.fields['supervisor_name'].required = False
            self.fields['supervisor_email'].required = False
    
    def clean(self):
        """Validate supervisor information for students."""
        cleaned_data = super().clean()
        
        if self.user and hasattr(self.user, 'userprofile') and self.user.userprofile.role == 'student':
            supervisor_name = cleaned_data.get('supervisor_name')
            supervisor_email = cleaned_data.get('supervisor_email')
            
            if not supervisor_name:
                self.add_error('supervisor_name', 'Supervisor name is required for student access requests.')
            
            if not supervisor_email:
                self.add_error('supervisor_email', 'Supervisor email is required for student access requests.')
        
        return cleaned_data


class AccessRequestReviewForm(forms.Form):
    """Form for reviewing access requests."""
    
    DECISION_CHOICES = [
        ('approve', 'Approve'),
        ('reject', 'Reject'),
    ]
    
    decision = forms.ChoiceField(
        choices=DECISION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        help_text="Decision for this access request"
    )
    
    review_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Optional notes about your decision...'
        }),
        help_text="Optional notes to explain your decision"
    )
    
    granted_duration_days = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': 1,
            'max': 365
        }),
        help_text="Days to grant access (leave blank to use requested duration)"
    )


class RiskAssessmentForm(forms.ModelForm):
    """Form for creating risk assessments."""
    
    class Meta:
        model = RiskAssessment
        fields = [
            'title', 'assessment_type', 'description', 'risk_level',
            'hazards_identified', 'control_measures', 'emergency_procedures',
            'ppe_requirements', 'valid_until', 'review_frequency_months',
            'is_mandatory', 'requires_renewal'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'assessment_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'risk_level': forms.Select(attrs={'class': 'form-control'}),
            'emergency_procedures': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'valid_until': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'review_frequency_months': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 60}),
            'is_mandatory': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requires_renewal': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
        help_texts = {
            'title': 'Descriptive title for this risk assessment',
            'assessment_type': 'Category of risk assessment',
            'description': 'Detailed description of the assessment scope',
            'risk_level': 'Overall risk level assessment',
            'valid_until': 'When this assessment expires',
            'review_frequency_months': 'How often to review this assessment',
            'is_mandatory': 'Must be completed before resource access',
            'requires_renewal': 'Requires periodic renewal'
        }

    def __init__(self, *args, **kwargs):
        self.resource = kwargs.pop('resource', None)
        super().__init__(*args, **kwargs)
        
        # Set default values
        if not self.instance.pk:
            self.fields['valid_until'].initial = timezone.now().date() + timedelta(days=365)


class UserRiskAssessmentForm(forms.ModelForm):
    """Form for users to complete risk assessments."""
    
    # Add file upload field
    risk_assessment_file = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.xlsx,.xls,.csv,.pdf,.doc,.docx'
        }),
        help_text='Upload supporting documents (Excel, PDF, Word, etc.)'
    )
    
    class Meta:
        model = UserRiskAssessment
        fields = ['user_declaration']
        widgets = {
            'user_declaration': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'I declare that I have read and understood this risk assessment. I acknowledge the identified hazards and agree to follow all control measures and safety procedures outlined above...'
            })
        }
        help_texts = {
            'user_declaration': 'Required declaration of understanding and acceptance'
        }

    def __init__(self, *args, **kwargs):
        self.risk_assessment = kwargs.pop('risk_assessment', None)
        super().__init__(*args, **kwargs)
        
        # Make user_declaration field required
        self.fields['user_declaration'].required = True
        
        
        if self.risk_assessment:
            # Add dynamic fields based on risk assessment questions
            self.add_assessment_questions()
    
    def add_assessment_questions(self):
        """Add dynamic fields for risk assessment questions."""
        # This would be populated based on the risk assessment's question structure
        # For now, we'll add a basic understanding confirmation
        self.fields['understanding_confirmed'] = forms.BooleanField(
            required=True,
            widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            label='I confirm I have read and understood this risk assessment',
            help_text='You must confirm understanding to proceed'
        )
    
    def clean_user_declaration(self):
        """Validate user declaration field."""
        user_declaration = self.cleaned_data.get('user_declaration')
        if not user_declaration or not user_declaration.strip():
            raise forms.ValidationError('A declaration is required to submit the risk assessment.')
        return user_declaration


class TrainingCourseForm(forms.ModelForm):
    """Form for creating training courses."""
    
    class Meta:
        model = TrainingCourse
        fields = [
            'title', 'code', 'description', 'course_type', 'delivery_method',
            'prerequisite_courses', 'duration_hours', 'max_participants',
            'learning_objectives', 'course_materials', 'assessment_criteria',
            'valid_for_months', 'requires_practical_assessment', 'pass_mark_percentage',
            'instructors', 'is_mandatory'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'course_type': forms.Select(attrs={'class': 'form-control'}),
            'delivery_method': forms.Select(attrs={'class': 'form-control'}),
            'prerequisite_courses': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'duration_hours': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'min': '0.5'}),
            'max_participants': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'valid_for_months': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '60'}),
            'requires_practical_assessment': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'pass_mark_percentage': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '100', 'step': '0.01'}),
            'instructors': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'is_mandatory': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
        help_texts = {
            'code': 'Unique identifier for this course',
            'duration_hours': 'Course duration in hours',
            'max_participants': 'Maximum participants per session',
            'valid_for_months': 'Certificate validity period',
            'pass_mark_percentage': 'Minimum score required to pass',
            'is_mandatory': 'Required for all users'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter instructors to only show qualified users
        self.fields['instructors'].queryset = User.objects.filter(
            userprofile__role__in=['technician', 'academic', 'sysadmin']
        ).order_by('first_name', 'last_name')
        
        # Filter prerequisite courses to exclude self
        if self.instance.pk:
            self.fields['prerequisite_courses'].queryset = TrainingCourse.objects.exclude(pk=self.instance.pk)


class UserTrainingEnrollForm(forms.Form):
    """Form for enrolling in training courses."""
    
    session_preference = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text="Preferred session if multiple options available"
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Any special requirements or notes...'
        }),
        help_text="Optional notes or special requirements"
    )

    def __init__(self, *args, **kwargs):
        self.training_course = kwargs.pop('training_course', None)
        super().__init__(*args, **kwargs)
        
        if self.training_course:
            # Add available sessions if any are scheduled
            self.add_session_choices()
    
    def add_session_choices(self):
        """Add session choices if available."""
        # This would be populated with actual scheduled sessions
        # For now, we'll provide general options
        session_choices = [
            ('', 'No preference'),
            ('morning', 'Morning sessions preferred'),
            ('afternoon', 'Afternoon sessions preferred'),
            ('weekend', 'Weekend sessions preferred')
        ]
        self.fields['session_preference'].choices = session_choices


class ResourceResponsibleForm(forms.ModelForm):
    """Form for assigning resource responsibility."""
    
    class Meta:
        model = ResourceResponsible
        fields = [
            'user', 'role_type', 'can_approve_access', 'can_approve_training',
            'can_conduct_assessments', 'notes'
        ]
        widgets = {
            'user': forms.Select(attrs={'class': 'form-control'}),
            'role_type': forms.Select(attrs={'class': 'form-control'}),
            'can_approve_access': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'can_approve_training': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'can_conduct_assessments': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
        }
        help_texts = {
            'user': 'User to assign responsibility',
            'role_type': 'Type of responsibility',
            'can_approve_access': 'Can approve access requests',
            'can_approve_training': 'Can approve training completions',
            'can_conduct_assessments': 'Can conduct risk assessments',
            'notes': 'Additional notes about this assignment'
        }

    def __init__(self, *args, **kwargs):
        self.resource = kwargs.pop('resource', None)
        super().__init__(*args, **kwargs)
        
        # Filter users to qualified roles only
        self.fields['user'].queryset = User.objects.filter(
            userprofile__role__in=['technician', 'academic', 'sysadmin']
        ).order_by('first_name', 'last_name')


class ResourceForm(forms.ModelForm):
    """Form for creating and editing resources."""
    
    class Meta:
        model = Resource
        fields = [
            'name', 'resource_type', 'description', 'location', 'capacity',
            'required_training_level', 'requires_induction', 'requires_risk_assessment',
            'max_booking_hours', 'is_active', 'image', 'requires_checkout_checklist', 
            'checkout_checklist_title', 'checkout_checklist_description'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'resource_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'required_training_level': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'requires_induction': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requires_risk_assessment': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'max_booking_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'requires_checkout_checklist': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'checkout_checklist_title': forms.TextInput(attrs={'class': 'form-control'}),
            'checkout_checklist_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
        }
        help_texts = {
            'name': 'Enter a descriptive name for the resource',
            'resource_type': 'Select the type of resource',
            'description': 'Optional detailed description of the resource',
            'location': 'Physical location where the resource is located',
            'capacity': 'Maximum number of users who can use this resource simultaneously',
            'required_training_level': 'Minimum training level required to use this resource',
            'requires_induction': 'Check if users need induction before using this resource',
            'requires_risk_assessment': 'Check if users need to complete a risk assessment before accessing this resource',
            'max_booking_hours': 'Maximum duration (in hours) for a single booking. Leave blank for no limit',
            'is_active': 'Uncheck to temporarily disable bookings for this resource',
            'image': 'Upload an image to help users identify this resource',
            'requires_checkout_checklist': 'Require users to complete a checklist before checking out',
            'checkout_checklist_title': 'Title displayed on the checkout checklist form',
            'checkout_checklist_description': 'Instructions or description shown above the checklist'
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set initial values for new resources
        if not self.instance.pk:
            self.fields['is_active'].initial = True
            self.fields['capacity'].initial = 1
            self.fields['required_training_level'].initial = 1
    
    def clean_max_booking_hours(self):
        """Validate max booking hours."""
        max_hours = self.cleaned_data.get('max_booking_hours')
        if max_hours is not None and max_hours < 1:
            raise forms.ValidationError('Maximum booking hours must be at least 1 hour.')
        if max_hours is not None and max_hours > 168:  # 1 week
            raise forms.ValidationError('Maximum booking hours cannot exceed 168 hours (1 week).')
        return max_hours
    
    def clean_capacity(self):
        """Validate capacity."""
        capacity = self.cleaned_data.get('capacity')
        if capacity < 1:
            raise forms.ValidationError('Capacity must be at least 1.')
        if capacity > 100:
            raise forms.ValidationError('Capacity cannot exceed 100.')
        return capacity


class AboutPageEditForm(forms.ModelForm):
    """Form for editing the About page with WYSIWYG editor."""
    
    class Meta:
        model = AboutPage
        fields = [
            'title', 'facility_name', 'content', 'image', 'contact_email', 
            'contact_phone', 'address', 'operating_hours', 
            'policies_url', 'emergency_contact', 'safety_information'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., About Our Research Lab'
            }),
            'facility_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Advanced Materials Research Laboratory'
            }),
            'content': forms.Textarea(attrs={
                'class': 'form-control content-textarea',
                'rows': 15,
                'placeholder': 'Enter the main content for your about page...'
            }),
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'contact_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'contact@university.edu'
            }),
            'contact_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+44 1792 295678'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Building, Room, University\nCity, Postcode'
            }),
            'operating_hours': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Monday - Friday: 9:00 AM - 6:00 PM\nSaturday: 10:00 AM - 4:00 PM\nSunday: Closed'
            }),
            'policies_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://university.edu/lab-policies'
            }),
            'emergency_contact': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Emergency: +44 1792 123456'
            }),
            'safety_information': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Important safety information for lab users...'
            })
        }
        help_texts = {
            'title': 'The main heading for your about page',
            'facility_name': 'Official name of your facility or laboratory',
            'content': 'Main content describing your facility, services, and important information',
            'image': 'Upload an image to display alongside your content (optional)',
            'contact_email': 'Primary contact email for inquiries',
            'contact_phone': 'Primary contact phone number',
            'address': 'Physical address of your facility',
            'operating_hours': 'Normal operating hours and any special schedules',
            'policies_url': 'Link to detailed policies and procedures document',
            'emergency_contact': 'Emergency contact information',
            'safety_information': 'Critical safety information that users must know'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add required field indicators
        for field_name, field in self.fields.items():
            if field.required:
                field.widget.attrs['required'] = True
                if 'placeholder' in field.widget.attrs:
                    field.widget.attrs['placeholder'] += ' *'

    def clean_content(self):
        """Validate content field."""
        content = self.cleaned_data.get('content')
        if not content or not content.strip():
            raise forms.ValidationError('Content is required.')
        return content

    def save(self, commit=True):
        """Override save to ensure only one active AboutPage."""
        instance = super().save(commit=False)
        instance.is_active = True
        if commit:
            # Deactivate all other AboutPages
            AboutPage.objects.filter(is_active=True).update(is_active=False)
            instance.save()
        return instance




# Maintenance Management Forms

class MaintenanceVendorForm(forms.ModelForm):
    """Form for creating/editing maintenance vendors."""
    
    class Meta:
        model = MaintenanceVendor
        fields = [
            'name', 'contact_person', 'email', 'phone', 'address', 'website',
            'specialties', 'certifications', 'service_areas', 'hourly_rate',
            'emergency_rate', 'contract_start_date', 'contract_end_date',
            'is_active', 'notes'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Vendor company name'
            }),
            'contact_person': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Primary contact person'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'contact@vendor.com'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+44 1234 567890'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Full business address'
            }),
            'website': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://vendor-website.com'
            }),
            'hourly_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'emergency_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'contract_start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'contract_end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Additional notes about this vendor...'
            })
        }
        help_texts = {
            'specialties': 'Enter as JSON array, e.g., ["electrical", "mechanical", "calibration"]',
            'certifications': 'Enter as JSON array, e.g., ["ISO 9001", "NIST certified"]',
            'service_areas': 'Enter as JSON array, e.g., ["London", "Southeast England"]',
            'hourly_rate': 'Standard hourly rate (£)',
            'emergency_rate': 'Emergency/after-hours rate (£)',
        }

    def clean_specialties(self):
        """Validate and convert specialties to list if needed."""
        specialties = self.cleaned_data.get('specialties')
        if isinstance(specialties, str):
            try:
                import json
                specialties = json.loads(specialties)
            except json.JSONDecodeError:
                # If not JSON, split by comma
                specialties = [s.strip() for s in specialties.split(',') if s.strip()]
        return specialties or []

    def clean_certifications(self):
        """Validate and convert certifications to list if needed."""
        certifications = self.cleaned_data.get('certifications')
        if isinstance(certifications, str):
            try:
                import json
                certifications = json.loads(certifications)
            except json.JSONDecodeError:
                certifications = [s.strip() for s in certifications.split(',') if s.strip()]
        return certifications or []

    def clean_service_areas(self):
        """Validate and convert service areas to list if needed."""
        service_areas = self.cleaned_data.get('service_areas')
        if isinstance(service_areas, str):
            try:
                import json
                service_areas = json.loads(service_areas)
            except json.JSONDecodeError:
                service_areas = [s.strip() for s in service_areas.split(',') if s.strip()]
        return service_areas or []


class MaintenanceForm(forms.ModelForm):
    """Form for creating/editing maintenance schedules."""
    
    class Meta:
        model = Maintenance
        fields = [
            'resource', 'title', 'description', 'start_time', 'end_time',
            'maintenance_type', 'priority', 'status', 'vendor', 'is_internal',
            'estimated_cost', 'actual_cost', 'labor_hours', 'parts_cost',
            'is_recurring', 'blocks_booking', 'affects_other_resources',
            'assigned_to', 'completion_notes', 'issues_found', 'recommendations'
        ]
        widgets = {
            'resource': forms.Select(attrs={
                'class': 'form-select'
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Brief title for this maintenance'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Detailed description of maintenance work...'
            }),
            'start_time': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'end_time': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'maintenance_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'priority': forms.Select(attrs={
                'class': 'form-select'
            }),
            'status': forms.Select(attrs={
                'class': 'form-select'
            }),
            'vendor': forms.Select(attrs={
                'class': 'form-select'
            }),
            'is_internal': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'estimated_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'actual_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'labor_hours': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.1',
                'min': '0'
            }),
            'parts_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'is_recurring': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'blocks_booking': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'affects_other_resources': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'size': '4'
            }),
            'assigned_to': forms.Select(attrs={
                'class': 'form-select'
            }),
            'completion_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Notes about completion...'
            }),
            'issues_found': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Issues discovered during maintenance...'
            }),
            'recommendations': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Recommendations for future maintenance...'
            })
        }
        help_texts = {
            'estimated_cost': 'Estimated total cost (£)',
            'actual_cost': 'Actual total cost (£)',
            'labor_hours': 'Hours of labor required',
            'parts_cost': 'Cost of parts and materials (£)',
            'blocks_booking': 'Whether this maintenance prevents new bookings',
            'affects_other_resources': 'Other resources affected by this maintenance'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter vendor choices to active vendors only
        self.fields['vendor'].queryset = MaintenanceVendor.objects.filter(is_active=True)
        
        # Filter assigned_to to technicians and sysadmins
        self.fields['assigned_to'].queryset = User.objects.filter(
            userprofile__role__in=['technician', 'sysadmin']
        )


class MaintenanceDocumentForm(forms.ModelForm):
    """Form for uploading maintenance documents."""
    
    class Meta:
        model = MaintenanceDocument
        fields = ['title', 'description', 'document_type', 'file', 'tags', 'is_public', 'version']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Document title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Brief description of this document...'
            }),
            'document_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control'
            }),
            'is_public': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'version': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., v1.0'
            })
        }
        help_texts = {
            'tags': 'Enter as JSON array, e.g., ["manual", "safety", "calibration"]',
            'is_public': 'Whether all users can view this document',
            'version': 'Document version (optional)'
        }

    def clean_tags(self):
        """Validate and convert tags to list if needed."""
        tags = self.cleaned_data.get('tags')
        if isinstance(tags, str):
            try:
                import json
                tags = json.loads(tags)
            except json.JSONDecodeError:
                tags = [s.strip() for s in tags.split(',') if s.strip()]
        return tags or []


class MaintenanceAlertForm(forms.ModelForm):
    """Form for creating maintenance alerts."""
    
    class Meta:
        model = MaintenanceAlert
        fields = [
            'resource', 'alert_type', 'severity', 'title', 'message',
            'recommendation', 'threshold_value', 'actual_value', 'expires_at'
        ]
        widgets = {
            'resource': forms.Select(attrs={
                'class': 'form-select'
            }),
            'alert_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'severity': forms.Select(attrs={
                'class': 'form-select'
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Alert title'
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Detailed alert message...'
            }),
            'recommendation': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Recommended action...'
            }),
            'threshold_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'actual_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01'
            }),
            'expires_at': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            })
        }
        help_texts = {
            'threshold_value': 'Alert threshold value (if applicable)',
            'actual_value': 'Current actual value (if applicable)',
            'expires_at': 'When this alert expires (optional)'
        }


class MaintenanceFilterForm(forms.Form):
    """Form for filtering maintenance records."""
    
    resource = forms.ModelChoiceField(
        queryset=Resource.objects.all(),
        required=False,
        empty_label="All Resources",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    maintenance_type = forms.ChoiceField(
        choices=[('', 'All Types')] + Maintenance.MAINTENANCE_TYPES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + Maintenance.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    priority = forms.ChoiceField(
        choices=[('', 'All Priorities')] + Maintenance.PRIORITY_LEVELS,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    vendor = forms.ModelChoiceField(
        queryset=MaintenanceVendor.objects.filter(is_active=True),
        required=False,
        empty_label="All Vendors",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )


class EmailConfigurationForm(forms.ModelForm):
    """Form for creating and editing email configurations."""
    
    class Meta:
        model = EmailConfiguration
        fields = [
            'name', 'description', 'email_backend', 'email_host', 'email_port',
            'email_use_tls', 'email_use_ssl', 'email_host_user', 'email_host_password',
            'default_from_email', 'server_email', 'email_timeout', 'email_file_path',
            'is_active'
        ]
        
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Production Gmail SMTP'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description of this configuration'
            }),
            'email_backend': forms.Select(attrs={
                'class': 'form-select'
            }),
            'email_host': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., smtp.gmail.com'
            }),
            'email_port': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 65535
            }),
            'email_use_tls': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'email_use_ssl': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'email_host_user': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'SMTP username (usually your email)'
            }),
            'email_host_password': forms.PasswordInput(attrs={
                'class': 'form-control',
                'placeholder': 'SMTP password'
            }),
            'default_from_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'noreply@yourdomain.com'
            }),
            'server_email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'server-errors@yourdomain.com'
            }),
            'email_timeout': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
                'max': 300
            }),
            'email_file_path': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '/tmp/app-messages'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add help text and required indicators
        self.fields['name'].help_text = "A descriptive name for this email configuration"
        self.fields['email_backend'].help_text = "Choose the email backend to use"
        self.fields['email_host'].help_text = "SMTP server hostname (e.g., smtp.gmail.com)"
        self.fields['email_port'].help_text = "Common ports: 587 (TLS), 465 (SSL), 25 (standard)"
        self.fields['email_use_tls'].help_text = "Use TLS encryption (recommended for port 587)"
        self.fields['email_use_ssl'].help_text = "Use SSL encryption (recommended for port 465)"
        self.fields['email_host_user'].help_text = "SMTP username (usually your email address)"
        self.fields['email_host_password'].help_text = "SMTP password or app-specific password"
        self.fields['default_from_email'].help_text = "Default 'from' address for outgoing emails"
        self.fields['server_email'].help_text = "Email address for Django server error messages"
        self.fields['email_timeout'].help_text = "Connection timeout in seconds (default: 10)"
        self.fields['email_file_path'].help_text = "Required for file-based email backend"
        self.fields['is_active'].help_text = "Make this the active email configuration"
        
        # Make certain fields conditional based on backend
        if self.instance.pk and self.instance.email_backend != 'django.core.mail.backends.smtp.EmailBackend':
            # Hide SMTP-specific fields for non-SMTP backends
            smtp_fields = ['email_host', 'email_port', 'email_use_tls', 'email_use_ssl', 
                          'email_host_user', 'email_host_password', 'email_timeout']
            for field in smtp_fields:
                self.fields[field].required = False
        
        # Handle password field for existing configurations
        if self.instance.pk and self.instance.email_host_password:
            self.fields['email_host_password'].widget.attrs['placeholder'] = '••••••••'
            self.fields['email_host_password'].help_text = "Leave blank to keep current password"
            self.fields['email_host_password'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        email_backend = cleaned_data.get('email_backend')
        
        # Validate SMTP-specific fields
        if email_backend == 'django.core.mail.backends.smtp.EmailBackend':
            email_host = cleaned_data.get('email_host')
            if not email_host:
                raise forms.ValidationError("Email host is required for SMTP backend.")
            
            email_use_tls = cleaned_data.get('email_use_tls')
            email_use_ssl = cleaned_data.get('email_use_ssl')
            if email_use_tls and email_use_ssl:
                raise forms.ValidationError("Cannot use both TLS and SSL simultaneously.")
        
        # Validate file-based backend
        elif email_backend == 'django.core.mail.backends.filebased.EmailBackend':
            email_file_path = cleaned_data.get('email_file_path')
            if not email_file_path:
                raise forms.ValidationError("File path is required for file-based email backend.")
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Handle password field - only update if a new password was provided
        if not self.cleaned_data.get('email_host_password') and self.instance.pk:
            # Keep the existing password
            instance.email_host_password = self.instance.email_host_password
        
        if commit:
            instance.save()
        
        return instance


class EmailConfigurationTestForm(forms.Form):
    """Form for testing email configurations."""
    
    test_email = forms.EmailField(
        label="Test Email Address",
        help_text="Email address to send the test email to",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'test@example.com'
        })
    )
    
    def __init__(self, *args, **kwargs):
        self.configuration = kwargs.pop('configuration', None)
        super().__init__(*args, **kwargs)
        
        if self.configuration:
            self.fields['test_email'].initial = self.configuration.default_from_email



class ChecklistItemForm(forms.ModelForm):
    """Form for creating and editing checklist items."""
    
    class Meta:
        model = ChecklistItem
        fields = [
            'title', 'description', 'category', 'item_type', 'is_required',
            'options', 'min_value', 'max_value', 'max_length'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'item_type': forms.Select(attrs={'class': 'form-control'}),
            'is_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'options': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3,
                'placeholder': 'For select items, enter each option on a new line'
            }),
            'min_value': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'max_value': forms.NumberInput(attrs={'class': 'form-control', 'step': 'any'}),
            'max_length': forms.NumberInput(attrs={'class': 'form-control', 'min': 1})
        }
        help_texts = {
            'title': 'The question or instruction text displayed to users',
            'description': 'Additional guidance or explanation (optional)',
            'category': 'Categorize this item for organization',
            'item_type': 'Type of input field for user responses',
            'is_required': 'Must be completed before users can check out',
            'options': 'For select items: enter each option on a new line',
            'min_value': 'Minimum allowed value for number inputs',
            'max_value': 'Maximum allowed value for number inputs',
            'max_length': 'Maximum character length for text inputs'
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Dynamic field visibility based on item type
        if self.instance.pk and self.instance.item_type:
            self._configure_fields_for_type(self.instance.item_type)
    
    def _configure_fields_for_type(self, item_type):
        """Configure field visibility based on item type."""
        # Hide fields that don't apply to this item type
        if item_type != 'select':
            self.fields['options'].widget = forms.HiddenInput()
        
        if item_type not in ['text', 'textarea']:
            self.fields['max_length'].widget = forms.HiddenInput()
            
        if item_type != 'number':
            self.fields['min_value'].widget = forms.HiddenInput()
            self.fields['max_value'].widget = forms.HiddenInput()
    
    def clean_options(self):
        """Parse and validate options for select items."""
        options = self.cleaned_data.get('options', '')
        item_type = self.cleaned_data.get('item_type')
        
        if item_type == 'select':
            if not options:
                raise forms.ValidationError("Select items must have at least one option")
            
            # Parse options from text (one per line)
            option_list = [line.strip() for line in options.split('\n') if line.strip()]
            if len(option_list) < 1:
                raise forms.ValidationError("Select items must have at least one option")
            
            return option_list
        
        return None
    
    def clean(self):
        """Cross-field validation."""
        cleaned_data = super().clean()
        item_type = cleaned_data.get('item_type')
        min_value = cleaned_data.get('min_value')
        max_value = cleaned_data.get('max_value')
        
        # Validate number constraints
        if item_type == 'number' and min_value is not None and max_value is not None:
            if min_value >= max_value:
                raise forms.ValidationError("Minimum value must be less than maximum value")
        
        return cleaned_data


class ResourceChecklistConfigForm(forms.Form):
    """Form for configuring which checklist items are assigned to a resource."""
    
    def __init__(self, resource, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.resource = resource
        
        # Get all available checklist items
        available_items = ChecklistItem.objects.all().order_by('category', 'title')
        
        # Get currently assigned items
        assigned_items = ResourceChecklistItem.objects.filter(
            resource=resource
        ).select_related('checklist_item')
        
        assigned_dict = {item.checklist_item.id: item for item in assigned_items}
        
        # Create fields for each available item
        for item in available_items:
            field_name = f"item_{item.id}"
            assignment = assigned_dict.get(item.id)
            
            # Checkbox to include/exclude item
            self.fields[f"{field_name}_enabled"] = forms.BooleanField(
                required=False,
                initial=assignment is not None and assignment.is_active,
                label=f"{item.get_category_display()}: {item.title}",
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
            )
            
            # Order field
            self.fields[f"{field_name}_order"] = forms.IntegerField(
                required=False,
                initial=assignment.order if assignment else 0,
                widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': 0}),
                label="Order"
            )
            
            # Required override
            self.fields[f"{field_name}_required"] = forms.BooleanField(
                required=False,
                initial=assignment.is_required if assignment else item.is_required,
                label="Required",
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
            )
    
    def save(self):
        """Save the checklist configuration for the resource."""
        from django.utils import timezone
        
        # Get all existing assignments
        existing_assignments = {
            assignment.checklist_item.id: assignment 
            for assignment in ResourceChecklistItem.objects.filter(resource=self.resource)
        }
        
        # Process each item
        for field_name, value in self.cleaned_data.items():
            if field_name.endswith('_enabled'):
                item_id = int(field_name.split('_')[1])
                
                # Get related field values
                enabled = value
                order = self.cleaned_data.get(f"item_{item_id}_order", 0)
                required = self.cleaned_data.get(f"item_{item_id}_required", True)
                
                if enabled:
                    # Create or update assignment
                    assignment = existing_assignments.get(item_id)
                    if assignment:
                        assignment.is_active = True
                        assignment.order = order
                        assignment.is_required_override = required
                        assignment.override_required = (required != assignment.checklist_item.is_required)
                        assignment.save()
                    else:
                        # Create new assignment
                        ResourceChecklistItem.objects.create(
                            resource=self.resource,
                            checklist_item_id=item_id,
                            order=order,
                            is_active=True,
                            override_required=(required != ChecklistItem.objects.get(id=item_id).is_required),
                            is_required_override=required,
                            created_at=timezone.now()
                        )
                else:
                    # Disable or remove assignment
                    assignment = existing_assignments.get(item_id)
                    if assignment:
                        assignment.is_active = False
                        assignment.save()


class ResourceIssueReportForm(forms.ModelForm):
    """Form for users to report issues with resources."""
    
    class Meta:
        model = ResourceIssue
        fields = [
            'title', 'description', 'severity', 'category', 
            'specific_location', 'image', 'blocks_resource_use'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Brief description of the issue'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Please provide as much detail as possible, including when the issue occurred, what you were doing, and any error messages.'
            }),
            'severity': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'specific_location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., "Left arm motor", "Control panel", "Safety switch"'
            }),
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'blocks_resource_use': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.resource = kwargs.pop('resource', None)
        self.booking = kwargs.pop('booking', None)
        super().__init__(*args, **kwargs)
        
        # Customize help text
        self.fields['severity'].help_text = "How severely does this issue affect the resource's functionality?"
        self.fields['category'].help_text = "What type of issue is this?"
        self.fields['blocks_resource_use'].help_text = "Check this if the resource cannot be used safely due to this issue"
        
        # Make some fields required
        self.fields['title'].required = True
        self.fields['description'].required = True
    
    def save(self, commit=True):
        issue = super().save(commit=False)
        if self.user:
            issue.reported_by = self.user
        if self.resource:
            issue.resource = self.resource
        if self.booking:
            issue.related_booking = self.booking
        
        if commit:
            issue.save()
        return issue


class ResourceIssueUpdateForm(forms.ModelForm):
    """Form for technicians/admins to update issue status and details."""
    
    class Meta:
        model = ResourceIssue
        fields = [
            'status', 'assigned_to', 'admin_notes', 'resolution_description',
            'estimated_repair_cost', 'actual_repair_cost', 'is_urgent'
        ]
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
            'admin_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Internal notes for tracking progress...'
            }),
            'resolution_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe how the issue was resolved...'
            }),
            'estimated_repair_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'actual_repair_cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'is_urgent': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Limit assigned_to to technicians and sysadmins
        self.fields['assigned_to'].queryset = User.objects.filter(
            userprofile__role__in=['technician', 'sysadmin']
        ).order_by('first_name', 'last_name')
        
        # Add empty option
        self.fields['assigned_to'].empty_label = "Unassigned"
        
        # Customize help text
        self.fields['is_urgent'].help_text = "Mark as urgent for immediate attention"
        self.fields['estimated_repair_cost'].help_text = "Estimated cost in local currency"
        self.fields['actual_repair_cost'].help_text = "Actual cost after completion"


class IssueFilterForm(forms.Form):
    """Form for filtering issues in the admin interface."""
    
    STATUS_CHOICES = [('', 'All Statuses')] + ResourceIssue.STATUS_CHOICES
    SEVERITY_CHOICES = [('', 'All Severities')] + ResourceIssue.SEVERITY_CHOICES
    CATEGORY_CHOICES = [('', 'All Categories')] + ResourceIssue.CATEGORY_CHOICES
    
    resource = forms.ModelChoiceField(
        queryset=Resource.objects.all(),
        empty_label="All Resources",
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    severity = forms.ChoiceField(
        choices=SEVERITY_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    category = forms.ChoiceField(
        choices=CATEGORY_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.filter(userprofile__role__in=['technician', 'sysadmin']),
        empty_label="All Assignees",
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    is_overdue = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )


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