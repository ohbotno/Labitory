# booking/forms/security.py
"""
Forms for security-related functionality.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django import forms
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from ..models import APIToken, SecurityEvent, DataAccessLog


class APITokenCreateForm(forms.Form):
    """
    Form for creating new API tokens.
    """
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'required': True
        }),
        help_text="Select the user for whom to create the token"
    )
    
    expires_in_days = forms.ChoiceField(
        choices=[
            (7, '7 days'),
            (30, '30 days'),
            (90, '90 days'),
            (365, '1 year'),
            (0, 'Never (not recommended)')
        ],
        initial=30,
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Token expiration time"
    )
    
    description = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Token purpose/description'
        }),
        help_text="Brief description of the token's purpose"
    )


class APITokenSearchForm(forms.Form):
    """
    Form for searching and filtering API tokens.
    """
    username = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by username'
        })
    )
    
    token_type = forms.ChoiceField(
        choices=[('', 'All Types')] + APIToken.TOKEN_TYPES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    status = forms.ChoiceField(
        choices=[
            ('', 'All Statuses'),
            ('active', 'Active'),
            ('expired', 'Expired'),
            ('revoked', 'Revoked')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class SecurityEventFilterForm(forms.Form):
    """
    Form for filtering security events.
    """
    event_type = forms.ChoiceField(
        choices=[('', 'All Event Types')] + SecurityEvent.EVENT_TYPES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    username = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by username'
        })
    )
    
    ip_address = forms.GenericIPAddressField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Filter by IP address'
        })
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


class AuditLogFilterForm(forms.Form):
    """
    Enhanced form for filtering audit logs.
    """
    action = forms.ChoiceField(
        choices=[('', 'All Actions')] + [
            ('CREATE', 'Create'),
            ('UPDATE', 'Update'),
            ('DELETE', 'Delete'),
            ('LOGIN', 'Login'),
            ('LOGOUT', 'Logout'),
            ('API_ACCESS', 'API Access'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    username = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by username'
        })
    )
    
    table_name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Filter by table/model'
        })
    )
    
    ip_address = forms.GenericIPAddressField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Filter by IP address'
        })
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


class GDPRRequestForm(forms.Form):
    """
    Form for GDPR data requests.
    """
    REQUEST_TYPES = [
        ('export', 'Data Export'),
        ('deletion', 'Data Deletion'),
        ('correction', 'Data Correction'),
        ('portability', 'Data Portability'),
    ]
    
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    request_type = forms.ChoiceField(
        choices=REQUEST_TYPES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Reason for this request'
        }),
        help_text="Provide justification for this data request"
    )
    
    include_deleted = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Include soft-deleted records in export"
    )


class DataExportForm(forms.Form):
    """
    Form for configuring data exports.
    """
    EXPORT_FORMATS = [
        ('csv', 'CSV'),
        ('json', 'JSON'),
        ('xml', 'XML'),
    ]
    
    export_format = forms.ChoiceField(
        choices=EXPORT_FORMATS,
        initial='csv',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    include_personal_data = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Include personal data (name, email, phone)"
    )
    
    include_booking_history = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Include booking history"
    )
    
    include_security_logs = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Include security and audit logs"
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        help_text="Export data from this date (optional)"
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        help_text="Export data until this date (optional)"
    )


class EncryptionConfigForm(forms.Form):
    """
    Form for configuring field-level encryption.
    """
    ENCRYPTION_FIELDS = [
        ('user_profile.phone_number', 'Phone Numbers'),
        ('user_profile.emergency_contact', 'Emergency Contacts'),
        ('booking.notes', 'Booking Notes'),
        ('maintenance.notes', 'Maintenance Notes'),
    ]
    
    fields_to_encrypt = forms.MultipleChoiceField(
        choices=ENCRYPTION_FIELDS,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        help_text="Select fields to encrypt"
    )
    
    rotation_schedule = forms.ChoiceField(
        choices=[
            ('never', 'Never'),
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly'),
            ('yearly', 'Yearly'),
        ],
        initial='quarterly',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Automatic key rotation schedule"
    )


class APIKeyGenerateForm(forms.Form):
    """
    Form for generating HMAC API signing keys.
    """
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by('username'),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    key_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Key identifier/name'
        }),
        help_text="Friendly name for this signing key"
    )
    
    permissions = forms.MultipleChoiceField(
        choices=[
            ('read', 'Read Access'),
            ('write', 'Write Access'),
            ('admin', 'Admin Access'),
        ],
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        help_text="API permissions for this key"
    )
    
    expires_in_days = forms.ChoiceField(
        choices=[
            (30, '30 days'),
            (90, '90 days'),
            (365, '1 year'),
            (0, 'Never expires')
        ],
        initial=365,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class SecurityConfigForm(forms.Form):
    """
    Form for configuring security settings.
    """
    # Rate limiting settings
    api_rate_limit = forms.IntegerField(
        min_value=1,
        max_value=10000,
        initial=100,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="API requests per hour per user"
    )
    
    login_rate_limit = forms.IntegerField(
        min_value=1,
        max_value=100,
        initial=5,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Login attempts per 15 minutes per IP"
    )
    
    # Session settings
    session_timeout_minutes = forms.IntegerField(
        min_value=5,
        max_value=1440,  # 24 hours
        initial=60,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Session timeout in minutes"
    )
    
    # Security monitoring
    enable_security_monitoring = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Enable real-time security monitoring"
    )
    
    suspicious_activity_threshold = forms.IntegerField(
        min_value=1,
        max_value=100,
        initial=10,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Number of failed attempts before flagging as suspicious"
    )
    
    # JWT settings
    jwt_access_token_lifetime = forms.IntegerField(
        min_value=1,
        max_value=60,  # 1 hour max
        initial=15,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="JWT access token lifetime in minutes"
    )
    
    jwt_refresh_token_lifetime = forms.IntegerField(
        min_value=1,
        max_value=30,  # 30 days max
        initial=7,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="JWT refresh token lifetime in days"
    )