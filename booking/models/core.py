"""
Core models for the Labitory.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
import pytz


class AboutPage(models.Model):
    """Admin-configurable about page content."""
    title = models.CharField(max_length=200, default="About Our Lab")
    content = models.TextField(
        help_text="Main content for the about page. HTML is allowed."
    )
    facility_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    operating_hours = models.TextField(
        blank=True,
        help_text="Describe your normal operating hours"
    )
    policies_url = models.URLField(
        blank=True,
        help_text="Link to detailed policies document"
    )
    emergency_contact = models.CharField(max_length=200, blank=True)
    safety_information = models.TextField(
        blank=True,
        help_text="Important safety information for lab users"
    )
    image = models.ImageField(
        upload_to='about_page/',
        blank=True,
        null=True,
        help_text="Optional image to display alongside the content"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only one AboutPage can be active at a time"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'booking_aboutpage'
        verbose_name = "About Page"
        verbose_name_plural = "About Pages"

    def __str__(self):
        return f"{self.title} ({'Active' if self.is_active else 'Inactive'})"

    def save(self, *args, **kwargs):
        if self.is_active:
            AboutPage.objects.filter(is_active=True).update(is_active=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_active(cls):
        """Get the currently active about page."""
        return cls.objects.filter(is_active=True).first()


class LabSettings(models.Model):
    """Lab customization settings for the free version."""
    
    lab_name = models.CharField(
        max_length=100, 
        default="Labitory",
        help_text="Name of your lab or facility (displayed throughout the application)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only one LabSettings instance can be active at a time"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Lab Settings"
        verbose_name_plural = "Lab Settings"
        db_table = "booking_labsettings"
    
    def __str__(self):
        return f"Lab Settings: {self.lab_name}"
    
    def save(self, *args, **kwargs):
        if self.is_active:
            LabSettings.objects.filter(is_active=True).update(is_active=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_active(cls):
        """Get the currently active lab settings."""
        return cls.objects.filter(is_active=True).first()
    
    @classmethod
    def get_lab_name(cls):
        """Get the current lab name, with fallback to default."""
        settings = cls.get_active()
        return settings.lab_name if settings else "Labitory"


class Faculty(models.Model):
    """Academic faculties."""
    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=10, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'booking_faculty'
        verbose_name_plural = 'Faculties'
        ordering = ['name']
    
    def __str__(self):
        return self.name


class College(models.Model):
    """Academic colleges within faculties."""
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=10)
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='colleges')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'booking_college'
        unique_together = [['faculty', 'code'], ['faculty', 'name']]
        ordering = ['faculty__name', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.faculty.name})"


class Department(models.Model):
    """Academic departments within colleges."""
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=10)
    college = models.ForeignKey(College, on_delete=models.CASCADE, related_name='departments')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'booking_department'
        unique_together = [['college', 'code'], ['college', 'name']]
        ordering = ['college__faculty__name', 'college__name', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.college.name})"


class UserProfile(models.Model):
    """Extended user profile with role and group information."""
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('researcher', 'Researcher'),
        ('academic', 'Academic'),
        ('technician', 'Technician'),
        ('sysadmin', 'System Administrator'),
    ]
    
    STUDENT_LEVEL_CHOICES = [
        ('undergraduate', 'Undergraduate'),
        ('postgraduate', 'Postgraduate'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    
    # Academic structure
    faculty = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, blank=True)
    college = models.ForeignKey(College, on_delete=models.SET_NULL, null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Research/academic group
    group = models.CharField(max_length=100, blank=True, help_text="Research group or class")
    
    # Role-specific fields
    student_id = models.CharField(max_length=50, blank=True, null=True, help_text="Student ID number")
    student_level = models.CharField(
        max_length=20, 
        choices=STUDENT_LEVEL_CHOICES, 
        blank=True, 
        null=True,
        help_text="Academic level (for students only)"
    )
    staff_number = models.CharField(max_length=50, blank=True, null=True, help_text="Staff ID number")
    
    # Contact and system fields
    phone = models.CharField(max_length=20, blank=True)
    training_level = models.PositiveIntegerField(default=1)
    is_inducted = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    first_login = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text="Timestamp of user's first login"
    )
    
    # Timezone and localization
    timezone = models.CharField(
        max_length=50, 
        default='UTC',
        help_text="User's preferred timezone"
    )
    date_format = models.CharField(
        max_length=20,
        choices=[
            ('DD/MM/YYYY', 'DD/MM/YYYY (European)'),
            ('MM/DD/YYYY', 'MM/DD/YYYY (US)'),
            ('YYYY-MM-DD', 'YYYY-MM-DD (ISO)'),
            ('DD-MM-YYYY', 'DD-MM-YYYY'),
            ('DD.MM.YYYY', 'DD.MM.YYYY (German)'),
        ],
        default='DD/MM/YYYY',
        help_text="Preferred date format"
    )
    time_format = models.CharField(
        max_length=10,
        choices=[
            ('24h', '24-hour (13:30)'),
            ('12h', '12-hour (1:30 PM)'),
        ],
        default='24h',
        help_text="Preferred time format"
    )
    
    # Theme preference
    theme_preference = models.CharField(
        max_length=10,
        choices=[
            ('light', 'Light'),
            ('dark', 'Dark'),
            ('system', 'System'),
        ],
        default='system',
        help_text="Preferred theme (light, dark, or follow system)"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'booking_userprofile'

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.role})"
    
    def clean(self):
        """Validate the user profile data."""
        super().clean()
        
        # Validate academic hierarchy
        if self.department and not self.college:
            raise ValidationError("College is required when department is specified.")
        if self.college and not self.faculty:
            raise ValidationError("Faculty is required when college is specified.")
        if self.department and self.department.college != self.college:
            raise ValidationError("Department must belong to the selected college.")
        if self.college and self.college.faculty != self.faculty:
            raise ValidationError("College must belong to the selected faculty.")
        
        # Role-specific validations
        if self.role == 'student':
            if not self.student_level:
                raise ValidationError("Student level is required for student role.")
        else:
            # Clear student-specific fields for non-students
            if self.student_level:
                raise ValidationError("Student level should only be set for student role.")
        
        # Staff role validations
        staff_roles = ['researcher', 'academic', 'technician', 'sysadmin']
        if self.role in staff_roles:
            if not self.staff_number:
                raise ValidationError(f"Staff number is required for {self.get_role_display()} role.")
        else:
            # Clear staff-specific fields for non-staff
            if self.staff_number:
                raise ValidationError("Staff number should only be set for staff roles.")

    @property
    def can_book_priority(self):
        """Check if user has priority booking privileges."""
        return self.role in ['academic', 'technician', 'sysadmin']

    @property
    def can_create_recurring(self):
        """Check if user can create recurring bookings."""
        return self.role in ['researcher', 'academic', 'technician', 'sysadmin']
    
    @property
    def academic_path(self):
        """Get full academic path as string."""
        parts = []
        if self.faculty:
            parts.append(self.faculty.name)
        if self.college:
            parts.append(self.college.name)
        if self.department:
            parts.append(self.department.name)
        return " > ".join(parts) if parts else "Not specified"
    
    def get_timezone(self):
        """Get user's timezone as a pytz timezone object."""
        try:
            return pytz.timezone(self.timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            return pytz.UTC
    
    def to_user_timezone(self, dt):
        """Convert a datetime to user's timezone."""
        if not dt:
            return dt
        
        user_tz = self.get_timezone()
        
        # If datetime is naive, assume it's in UTC
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, pytz.UTC)
        
        return dt.astimezone(user_tz)
    
    def from_user_timezone(self, dt):
        """Convert a datetime from user's timezone to UTC."""
        if not dt:
            return dt
        
        user_tz = self.get_timezone()
        
        # If datetime is naive, assume it's in user's timezone
        if timezone.is_naive(dt):
            dt = user_tz.localize(dt)
        
        return dt.astimezone(pytz.UTC)
    
    def format_datetime(self, dt):
        """Format datetime according to user preferences."""
        if not dt:
            return ""
        
        # Convert to user timezone
        user_dt = self.to_user_timezone(dt)
        
        # Format date
        date_formats = {
            'DD/MM/YYYY': '%d/%m/%Y',
            'MM/DD/YYYY': '%m/%d/%Y',
            'YYYY-MM-DD': '%Y-%m-%d',
            'DD-MM-YYYY': '%d-%m-%Y',
            'DD.MM.YYYY': '%d.%m.%Y',
        }
        date_format = date_formats.get(self.date_format, '%d/%m/%Y')
        
        # Format time
        time_format = '%H:%M' if self.time_format == '24h' else '%I:%M %p'
        
        return user_dt.strftime(f"{date_format} {time_format}")
    
    def format_date(self, dt):
        """Format date according to user preferences."""
        if not dt:
            return ""
        
        user_dt = self.to_user_timezone(dt)
        
        date_formats = {
            'DD/MM/YYYY': '%d/%m/%Y',
            'MM/DD/YYYY': '%m/%d/%Y',
            'YYYY-MM-DD': '%Y-%m-%d',
            'DD-MM-YYYY': '%d-%m-%Y',
            'DD.MM.YYYY': '%d.%m.%Y',
        }
        date_format = date_formats.get(self.date_format, '%d/%m/%Y')
        
        return user_dt.strftime(date_format)
    
    def format_time(self, dt):
        """Format time according to user preferences."""
        if not dt:
            return ""
        
        user_dt = self.to_user_timezone(dt)
        time_format = '%H:%M' if self.time_format == '24h' else '%I:%M %p'
        
        return user_dt.strftime(time_format)
    
    @classmethod
    def get_available_timezones(cls):
        """Get list of common timezones for selection."""
        
        # Common timezones that institutions might use
        common_timezones = [
            'UTC',
            'Europe/London',
            'Europe/Paris',
            'Europe/Berlin',
            'Europe/Rome',
            'Europe/Madrid',
            'Europe/Amsterdam',
            'Europe/Brussels',
            'Europe/Vienna',
            'Europe/Prague',
            'Europe/Warsaw',
            'Europe/Stockholm',
            'Europe/Helsinki',
            'Europe/Athens',
            'US/Eastern',
            'US/Central',
            'US/Mountain',
            'US/Pacific',
            'America/New_York',
            'America/Chicago',
            'America/Denver',
            'America/Los_Angeles',
            'America/Toronto',
            'America/Vancouver',
            'Australia/Sydney',
            'Australia/Melbourne',
            'Australia/Perth',
            'Asia/Tokyo',
            'Asia/Shanghai',
            'Asia/Singapore',
            'Asia/Hong_Kong',
            'Asia/Seoul',
            'Asia/Mumbai',
            'Asia/Dubai',
        ]
        
        # Return as choices for forms
        return [(tz, tz.replace('_', ' ')) for tz in common_timezones]