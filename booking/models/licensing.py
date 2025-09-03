"""
Licensing and branding models for the Labitory.

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
from .resources import Resource


class LicenseConfiguration(models.Model):
    """
    License configuration for white-label deployments.
    Supports both open source (honor system) and commercial licensing.
    """
    LICENSE_TYPES = [
        ('open_source', 'Open Source (GPL-3.0)'),
        ('basic_commercial', 'Basic Commercial White Label'),
        ('premium_commercial', 'Premium Commercial White Label'),
        ('enterprise', 'Enterprise License'),
    ]
    
    # License identification
    license_key = models.CharField(
        max_length=255, 
        unique=True,
        help_text="Unique license key for this installation"
    )
    license_type = models.CharField(
        max_length=50, 
        choices=LICENSE_TYPES,
        default='open_source'
    )
    
    # Organization details
    organization_name = models.CharField(
        max_length=200,
        help_text="Name of the licensed organization"
    )
    organization_slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="URL-safe identifier for custom theming"
    )
    contact_email = models.EmailField(
        help_text="Primary contact for license holder"
    )
    
    # License restrictions
    allowed_domains = models.JSONField(
        default=list,
        help_text="List of domains where this license is valid"
    )
    max_users = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum number of active users (null = unlimited)"
    )
    max_resources = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum number of resources (null = unlimited)"
    )
    
    # Feature enablement
    features_enabled = models.JSONField(
        default=dict,
        help_text="JSON object defining which features are enabled"
    )
    
    # License validity
    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="License expiration date (null = no expiration)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this license is currently active"
    )
    
    # Validation tracking
    last_validation = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time license was validated"
    )
    validation_failures = models.PositiveIntegerField(
        default=0,
        help_text="Count of recent validation failures"
    )
    
    # Support and updates
    support_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Support and updates expiration date"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_licenseconfiguration'
        verbose_name = "License Configuration"
        verbose_name_plural = "License Configurations"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.organization_name} ({self.get_license_type_display()})"
    
    def is_valid(self):
        """Check if license is currently valid."""
        if not self.is_active:
            return False
        
        if self.expires_at and self.expires_at < timezone.now():
            return False
            
        return True
    
    def get_enabled_features(self):
        """Get list of enabled features based on license type."""
        base_features = {
            'basic_booking': True,
            'user_management': True,
            'resource_management': True,
            'email_notifications': True,
        }
        
        if self.license_type == 'open_source':
            base_features.update({
                'custom_branding': False,
                'white_label': False,
                'advanced_reports': False,
                'api_access': True,
                'premium_support': False,
            })
        elif self.license_type == 'basic_commercial':
            base_features.update({
                'custom_branding': True,
                'white_label': True,
                'advanced_reports': False,
                'api_access': True,
                'premium_support': True,
            })
        elif self.license_type == 'premium_commercial':
            base_features.update({
                'custom_branding': True,
                'white_label': True,
                'advanced_reports': True,
                'api_access': True,
                'premium_support': True,
                'custom_integrations': True,
            })
        elif self.license_type == 'enterprise':
            base_features.update({
                'custom_branding': True,
                'white_label': True,
                'advanced_reports': True,
                'api_access': True,
                'premium_support': True,
                'custom_integrations': True,
                'multi_tenant': True,
                'priority_support': True,
            })
        
        # Merge with custom features from JSON field
        base_features.update(self.features_enabled)
        return base_features
    
    def check_usage_limits(self):
        """Check if current usage exceeds license limits."""
        issues = []
        
        if self.max_users:
            active_users = User.objects.filter(is_active=True).count()
            if active_users > self.max_users:
                issues.append(f"User limit exceeded: {active_users}/{self.max_users}")
        
        if self.max_resources:
            active_resources = Resource.objects.filter(is_active=True).count()
            if active_resources > self.max_resources:
                issues.append(f"Resource limit exceeded: {active_resources}/{self.max_resources}")
        
        return issues


class BrandingConfiguration(models.Model):
    """
    Customization and branding settings for white-label deployments.
    """
    # Link to license
    license = models.OneToOneField(
        LicenseConfiguration,
        on_delete=models.CASCADE,
        related_name='branding'
    )
    
    # Basic branding
    app_title = models.CharField(
        max_length=100,
        default='Labitory',
        help_text="Application name shown in browser title and headers"
    )
    company_name = models.CharField(
        max_length=200,
        help_text="Company/organization name"
    )
    
    # Visual branding
    logo_primary = models.ImageField(
        upload_to='branding/logos/',
        null=True,
        blank=True,
        help_text="Primary logo (displayed in header)"
    )
    logo_favicon = models.ImageField(
        upload_to='branding/favicons/',
        null=True,
        blank=True,
        help_text="Favicon (16x16 or 32x32 pixels)"
    )
    
    # Color scheme
    color_primary = models.CharField(
        max_length=7,
        default='#007bff',
        help_text="Primary brand color (hex format)"
    )
    color_secondary = models.CharField(
        max_length=7,
        default='#6c757d',
        help_text="Secondary brand color (hex format)"
    )
    color_accent = models.CharField(
        max_length=7,
        default='#28a745',
        help_text="Accent color for highlights and buttons"
    )
    
    # Content customization
    welcome_message = models.TextField(
        blank=True,
        help_text="Custom welcome message for the homepage"
    )
    footer_text = models.TextField(
        blank=True,
        help_text="Custom footer text"
    )
    custom_css = models.TextField(
        blank=True,
        help_text="Additional CSS for custom styling"
    )
    
    # Contact information
    support_email = models.EmailField(
        blank=True,
        help_text="Support contact email"
    )
    support_phone = models.CharField(
        max_length=50,
        blank=True,
        help_text="Support contact phone"
    )
    website_url = models.URLField(
        blank=True,
        help_text="Organization website URL"
    )
    
    # Email customization
    email_from_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Name shown in 'From' field of emails"
    )
    email_signature = models.TextField(
        blank=True,
        help_text="Signature added to notification emails"
    )
    
    # Feature toggles
    show_powered_by = models.BooleanField(
        default=True,
        help_text="Show 'Powered by Labitory' in footer"
    )
    enable_public_registration = models.BooleanField(
        default=True,
        help_text="Allow public user registration"
    )
    enable_guest_booking = models.BooleanField(
        default=False,
        help_text="Allow guest bookings without registration"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'booking_brandingconfiguration'
        verbose_name = "Branding Configuration"
        verbose_name_plural = "Branding Configurations"
    
    def __str__(self):
        return f"Branding for {self.company_name}"
    
    def get_css_variables(self):
        """Generate CSS custom properties for theming."""
        return {
            '--primary-color': self.color_primary,
            '--secondary-color': self.color_secondary,
            '--accent-color': self.color_accent,
        }


class LicenseValidationLog(models.Model):
    """
    Log of license validation attempts for monitoring and troubleshooting.
    """
    VALIDATION_TYPES = [
        ('startup', 'Application Startup'),
        ('periodic', 'Periodic Check'),
        ('feature_access', 'Feature Access'),
        ('admin_manual', 'Manual Admin Check'),
    ]
    
    RESULT_TYPES = [
        ('success', 'Validation Successful'),
        ('expired', 'License Expired'),
        ('invalid_key', 'Invalid License Key'),
        ('domain_mismatch', 'Domain Not Allowed'),
        ('usage_exceeded', 'Usage Limits Exceeded'),
        ('network_error', 'Network/Server Error'),
        ('not_found', 'License Not Found'),
    ]
    
    license = models.ForeignKey(
        LicenseConfiguration,
        on_delete=models.CASCADE,
        related_name='validation_logs'
    )
    
    validation_type = models.CharField(
        max_length=20,
        choices=VALIDATION_TYPES
    )
    result = models.CharField(
        max_length=20,
        choices=RESULT_TYPES
    )
    
    # Validation details
    domain_checked = models.CharField(
        max_length=255,
        blank=True,
        help_text="Domain that was validated"
    )
    user_agent = models.TextField(
        blank=True,
        help_text="Browser/client user agent"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of validation request"
    )
    
    # Error details
    error_message = models.TextField(
        blank=True,
        help_text="Error message if validation failed"
    )
    
    # Performance tracking
    response_time = models.FloatField(
        null=True,
        blank=True,
        help_text="Validation response time in seconds"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'booking_licensevalidationlog'
        verbose_name = "License Validation Log"
        verbose_name_plural = "License Validation Logs"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['license', '-created_at']),
            models.Index(fields=['result', '-created_at']),
        ]
    
    def __str__(self):
        return f"{self.license.organization_name} - {self.get_result_display()} ({self.created_at})"