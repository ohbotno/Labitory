# booking/forms/maintenance.py
"""
Maintenance-related forms for the Aperture Booking system.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django import forms
from django.contrib.auth.models import User

from ..models import (
    Resource, Maintenance, MaintenanceVendor, MaintenanceDocument, MaintenanceAlert
)


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