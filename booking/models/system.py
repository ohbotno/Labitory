"""
System configuration models for the Labitory.

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
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import datetime, time, timedelta
import json
import calendar


class SystemSetting(models.Model):
    """System-wide configuration settings."""
    
    SETTING_TYPES = [
        ('string', 'Text String'),
        ('integer', 'Integer'),
        ('boolean', 'True/False'),
        ('json', 'JSON Data'),
        ('float', 'Decimal Number'),
    ]
    
    key = models.CharField(max_length=100, unique=True, help_text="Setting identifier")
    value = models.TextField(help_text="Setting value (stored as text)")
    value_type = models.CharField(max_length=10, choices=SETTING_TYPES, default='string')
    description = models.TextField(help_text="What this setting controls")
    category = models.CharField(max_length=50, default='general', help_text="Setting category")
    is_editable = models.BooleanField(default=True, help_text="Can be modified through admin")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_systemsetting'
        ordering = ['category', 'key']
    
    def __str__(self):
        return f"{self.key} = {self.value}"
    
    def clean(self):
        """Validate value based on type."""
        if self.value_type == 'integer':
            try:
                int(self.value)
            except ValueError:
                raise ValidationError({'value': 'Must be a valid integer'})
        elif self.value_type == 'float':
            try:
                float(self.value)
            except ValueError:
                raise ValidationError({'value': 'Must be a valid decimal number'})
        elif self.value_type == 'boolean':
            if self.value.lower() not in ['true', 'false', '1', '0']:
                raise ValidationError({'value': 'Must be true/false or 1/0'})
        elif self.value_type == 'json':
            try:
                json.loads(self.value)
            except json.JSONDecodeError:
                raise ValidationError({'value': 'Must be valid JSON'})
    
    def get_value(self):
        """Get typed value."""
        if self.value_type == 'integer':
            return int(self.value)
        elif self.value_type == 'float':
            return float(self.value)
        elif self.value_type == 'boolean':
            return self.value.lower() in ['true', '1']
        elif self.value_type == 'json':
            return json.loads(self.value)
        else:
            return self.value
    
    @classmethod
    def get_setting(cls, key, default=None):
        """Get a setting value by key."""
        try:
            setting = cls.objects.get(key=key)
            return setting.get_value()
        except cls.DoesNotExist:
            return default
    
    @classmethod
    def set_setting(cls, key, value, value_type='string', description='', category='general'):
        """Set a setting value."""
        if value_type == 'json' and not isinstance(value, str):
            value = json.dumps(value)
        elif value_type == 'boolean':
            value = 'true' if value else 'false'
        else:
            value = str(value)
        
        setting, created = cls.objects.update_or_create(
            key=key,
            defaults={
                'value': value,
                'value_type': value_type,
                'description': description,
                'category': category
            }
        )
        return setting


class PDFExportSettings(models.Model):
    """PDF export configuration settings."""
    
    QUALITY_CHOICES = [
        ('high', 'High Quality (2x scale)'),
        ('medium', 'Medium Quality (1.5x scale)'),
        ('low', 'Low Quality (1x scale)'),
    ]
    
    ORIENTATION_CHOICES = [
        ('landscape', 'Landscape'),
        ('portrait', 'Portrait'),
    ]
    
    name = models.CharField(max_length=100, unique=True, help_text="Configuration name")
    is_default = models.BooleanField(default=False, help_text="Use as default configuration")
    
    # Export settings
    default_quality = models.CharField(max_length=10, choices=QUALITY_CHOICES, default='high')
    default_orientation = models.CharField(max_length=10, choices=ORIENTATION_CHOICES, default='landscape')
    include_header = models.BooleanField(default=True, help_text="Include enhanced header")
    include_footer = models.BooleanField(default=True, help_text="Include enhanced footer")
    include_legend = models.BooleanField(default=True, help_text="Include status legend")
    include_details = models.BooleanField(default=True, help_text="Include booking details in footer")
    preserve_colors = models.BooleanField(default=True, help_text="Maintain booking status colors")
    multi_page_support = models.BooleanField(default=True, help_text="Split large calendars across pages")
    compress_pdf = models.BooleanField(default=False, help_text="Compress PDF (smaller file size)")
    
    # Custom styling
    header_logo_url = models.URLField(blank=True, help_text="URL to logo image for PDF header")
    custom_css = models.TextField(blank=True, help_text="Custom CSS for PDF export")
    watermark_text = models.CharField(max_length=100, blank=True, help_text="Watermark text")
    
    # Metadata
    author_name = models.CharField(max_length=100, blank=True, help_text="Default author name")
    organization_name = models.CharField(max_length=100, blank=True, help_text="Organization name")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_pdfexportsettings'
        ordering = ['-is_default', 'name']
    
    def __str__(self):
        default_marker = " (Default)" if self.is_default else ""
        return f"{self.name}{default_marker}"
    
    def save(self, *args, **kwargs):
        # Ensure only one default configuration
        if self.is_default:
            PDFExportSettings.objects.filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_default_config(cls):
        """Get the default PDF export configuration."""
        try:
            return cls.objects.get(is_default=True)
        except cls.DoesNotExist:
            # Create default configuration if none exists
            return cls.objects.create(
                name="Default Configuration",
                is_default=True,
                default_quality='high',
                default_orientation='landscape',
                include_header=True,
                include_footer=True,
                include_legend=True,
                include_details=True,
                preserve_colors=True,
                multi_page_support=True,
                compress_pdf=False,
                organization_name="Labitory"
            )
    
    def to_json(self):
        """Convert settings to JSON for frontend use."""
        return {
            'name': self.name,
            'defaultQuality': self.default_quality,
            'defaultOrientation': self.default_orientation,
            'includeHeader': self.include_header,
            'includeFooter': self.include_footer,
            'includeLegend': self.include_legend,
            'includeDetails': self.include_details,
            'preserveColors': self.preserve_colors,
            'multiPageSupport': self.multi_page_support,
            'compressPdf': self.compress_pdf,
            'headerLogoUrl': self.header_logo_url,
            'customCss': self.custom_css,
            'watermarkText': self.watermark_text,
            'authorName': self.author_name,
            'organizationName': self.organization_name
        }


class UpdateInfo(models.Model):
    """Track application updates and version information."""
    
    STATUS_CHOICES = [
        ('checking', 'Checking for Updates'),
        ('available', 'Update Available'),
        ('downloading', 'Downloading Update'),
        ('ready', 'Ready to Install'),
        ('installing', 'Installing Update'),
        ('completed', 'Update Completed'),
        ('failed', 'Update Failed'),
        ('up_to_date', 'Up to Date'),
    ]
    
    current_version = models.CharField(max_length=50, help_text="Currently installed version")
    latest_version = models.CharField(max_length=50, blank=True, help_text="Latest available version")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='up_to_date')
    
    # Release information
    release_url = models.URLField(blank=True, help_text="GitHub release URL")
    release_notes = models.TextField(blank=True, help_text="Release notes/changelog")
    release_date = models.DateTimeField(null=True, blank=True)
    download_url = models.URLField(blank=True, help_text="Download URL for the release")
    
    # Update tracking
    last_check = models.DateTimeField(auto_now=True)
    download_progress = models.IntegerField(default=0, help_text="Download progress percentage")
    error_message = models.TextField(blank=True, help_text="Error message if update failed")
    
    # Settings
    auto_check_enabled = models.BooleanField(default=True, help_text="Automatically check for updates")
    github_repo = models.CharField(max_length=100, default="ohbotno/aperature-booking", 
                                 help_text="GitHub repository (username/repo-name)")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_updateinfo'
        verbose_name = "Update Information"
        verbose_name_plural = "Update Information"
    
    def __str__(self):
        return f"Version {self.current_version} -> {self.latest_version or 'Unknown'}"
    
    @classmethod
    def get_instance(cls):
        """Get or create the singleton update info instance."""
        from labitory import __version__
        instance, created = cls.objects.get_or_create(
            id=1,
            defaults={
                'current_version': __version__,  # Use version from __init__.py
                'github_repo': 'ohbotno/Labitory'
            }
        )
        return instance
    
    def is_update_available(self):
        """Check if an update is available."""
        if not self.latest_version or not self.current_version:
            return False
        return self.latest_version != self.current_version
    
    def can_install_update(self):
        """Check if update can be installed."""
        return self.status == 'ready' and self.is_update_available()


class UpdateHistory(models.Model):
    """Track update installation history."""
    
    RESULT_CHOICES = [
        ('success', 'Successful'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    from_version = models.CharField(max_length=50)
    to_version = models.CharField(max_length=50)
    result = models.CharField(max_length=20, choices=RESULT_CHOICES)
    
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    # Backup information
    backup_created = models.BooleanField(default=False)
    backup_path = models.CharField(max_length=500, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'booking_updatehistory'
        verbose_name = "Update History"
        verbose_name_plural = "Update History"
        ordering = ['-started_at']
    
    def __str__(self):
        return f"Update {self.from_version} -> {self.to_version} ({self.result})"
    
    @property
    def duration(self):
        """Calculate update duration."""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None


class BackupSchedule(models.Model):
    """Model for managing automated backup schedules."""
    
    FREQUENCY_CHOICES = [
        ('disabled', 'Disabled'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]
    
    DAY_OF_WEEK_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    # Basic scheduling
    name = models.CharField(max_length=200, default="Automated Backup")
    enabled = models.BooleanField(default=True)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='weekly')
    
    # Time settings
    backup_time = models.TimeField(default='02:00', help_text="Time of day to run backup (24-hour format)")
    day_of_week = models.IntegerField(
        choices=DAY_OF_WEEK_CHOICES, 
        default=6,  # Sunday
        help_text="Day of week for weekly backups"
    )
    day_of_month = models.IntegerField(
        default=1,
        help_text="Day of month for monthly backups (1-28)"
    )
    
    # Backup options
    include_media = models.BooleanField(default=True, help_text="Include media files in automated backups")
    include_database = models.BooleanField(default=True, help_text="Include database in automated backups")
    include_configuration = models.BooleanField(default=True, help_text="Include configuration analysis in automated backups")
    
    # Retention settings
    max_backups_to_keep = models.IntegerField(
        default=7,
        help_text="Maximum number of automated backups to keep (older ones will be deleted)"
    )
    retention_days = models.IntegerField(
        default=30,
        help_text="Days to keep automated backups before deletion"
    )
    
    # Status tracking
    last_run = models.DateTimeField(null=True, blank=True)
    last_success = models.DateTimeField(null=True, blank=True)
    last_backup_name = models.CharField(max_length=255, blank=True)
    consecutive_failures = models.IntegerField(default=0)
    total_runs = models.IntegerField(default=0)
    total_successes = models.IntegerField(default=0)
    
    # Error tracking
    last_error = models.TextField(blank=True)
    notification_email = models.EmailField(
        blank=True,
        help_text="Email to notify on backup failures (leave blank to disable)"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Backup Schedule"
        verbose_name_plural = "Backup Schedules"
    
    def __str__(self):
        status = "Enabled" if self.enabled else "Disabled"
        return f"{self.name} ({self.frequency}, {status})"
    
    def clean(self):
        """Validate backup schedule settings."""
        if self.day_of_month < 1 or self.day_of_month > 28:
            raise ValidationError("Day of month must be between 1 and 28")
        
        if self.max_backups_to_keep < 1:
            raise ValidationError("Must keep at least 1 backup")
        
        if self.retention_days < 1:
            raise ValidationError("Retention period must be at least 1 day")
        
        if not any([self.include_database, self.include_media, self.include_configuration]):
            raise ValidationError("At least one backup component must be selected")
    
    def get_next_run_time(self):
        """Calculate the next scheduled run time."""
        if not self.enabled or self.frequency == 'disabled':
            return None
        
        now = timezone.now()
        today = now.date()
        
        # Ensure backup_time is a time object
        backup_time = self.backup_time
        if isinstance(backup_time, str):
            try:
                # Parse string format like "14:30" or "02:00"
                hour, minute = backup_time.split(':')
                backup_time = time(int(hour), int(minute))
            except (ValueError, AttributeError):
                # Fallback to default time if parsing fails
                backup_time = time(2, 0)  # 2:00 AM
        
        current_time = now.time()
        
        if self.frequency == 'daily':
            # Next run is today if time hasn't passed, otherwise tomorrow
            next_date = today
            if current_time > backup_time:
                next_date = today + timedelta(days=1)
                
        elif self.frequency == 'weekly':
            # Find next occurrence of the specified day of week
            days_ahead = self.day_of_week - today.weekday()
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            next_date = today + timedelta(days=days_ahead)
            
            # If it's the target day but time hasn't passed yet, use today
            if days_ahead == 7 and current_time <= backup_time:
                next_date = today
                
        elif self.frequency == 'monthly':
            # Find next occurrence of the specified day of month
            if today.day < self.day_of_month and current_time <= backup_time:
                # This month, day hasn't passed yet
                next_date = today.replace(day=self.day_of_month)
            else:
                # Next month
                if today.month == 12:
                    next_month = today.replace(year=today.year + 1, month=1, day=self.day_of_month)
                else:
                    next_month = today.replace(month=today.month + 1, day=self.day_of_month)
                next_date = next_month
        
        else:
            return None
        
        return timezone.make_aware(datetime.combine(next_date, backup_time))
    
    def should_run_now(self):
        """Check if backup should run now based on schedule."""
        if not self.enabled or self.frequency == 'disabled':
            return False
        
        next_run = self.get_next_run_time()
        if not next_run:
            return False
        
        now = timezone.now()
        # Allow a 5-minute window for execution
        return abs((now - next_run).total_seconds()) <= 300
    
    def record_run(self, success=True, backup_name='', error_message=''):
        """Record the results of a backup run."""
        now = timezone.now()
        self.last_run = now
        self.total_runs += 1
        
        if success:
            self.last_success = now
            self.last_backup_name = backup_name
            self.total_successes += 1
            self.consecutive_failures = 0
            self.last_error = ''
        else:
            self.consecutive_failures += 1
            self.last_error = error_message
        
        self.save(update_fields=['last_run', 'last_success', 'last_backup_name', 
                                'total_runs', 'total_successes', 'consecutive_failures', 'last_error'])
    
    @property
    def success_rate(self):
        """Calculate backup success rate as percentage."""
        if self.total_runs == 0:
            return 0
        return round((self.total_successes / self.total_runs) * 100, 1)
    
    @property
    def is_healthy(self):
        """Check if backup schedule is considered healthy."""
        if not self.enabled:
            return True
        
        # More than 3 consecutive failures is concerning
        if self.consecutive_failures > 3:
            return False
        
        # No successful backup in the last 7 days (for enabled schedules)
        if self.last_success:
            days_since_success = (timezone.now() - self.last_success).days
            if days_since_success > 7:
                return False
        elif self.total_runs > 0:
            # Has run but never succeeded
            return False
        
        return True