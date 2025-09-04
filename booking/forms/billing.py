"""
Billing forms for the Labitory application.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django import forms
from django.core.exceptions import ValidationError
from ..models.billing import BillingRate, BillingPeriod
from ..models.resources import Resource
from ..models.core import Department


class BillingRateForm(forms.ModelForm):
    """Form for creating and editing billing rates."""
    
    class Meta:
        model = BillingRate
        fields = [
            'resource', 'rate_type', 'hourly_rate', 'priority', 'is_active',
            'minimum_charge_minutes', 'rounding_minutes',
            'user_type', 'department',
            'applies_from_time', 'applies_to_time', 
            'applies_weekdays_only', 'applies_weekends_only',
            'valid_from', 'valid_until'
        ]
        widgets = {
            'resource': forms.Select(attrs={'class': 'form-select'}),
            'rate_type': forms.Select(attrs={'class': 'form-select'}),
            'hourly_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'priority': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'value': '1'}),
            'minimum_charge_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'value': '0'}),
            'rounding_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'value': '1'}),
            'user_type': forms.Select(attrs={'class': 'form-select'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'applies_from_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'applies_to_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'applies_weekdays_only': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'applies_weekends_only': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'checked': True}),
            'valid_from': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'valid_until': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter resources to only billable ones for new rates
        if not self.instance.pk:
            self.fields['resource'].queryset = Resource.objects.filter(is_billable=True)
        
        # Make department optional
        self.fields['department'].empty_label = "All Departments"
        self.fields['department'].required = False
        
        # Add help text
        self.fields['priority'].help_text = "Higher priority rates are applied first when multiple rates match"
        self.fields['minimum_charge_minutes'].help_text = "Minimum billable time in minutes (0 = no minimum)"
        self.fields['rounding_minutes'].help_text = "Round usage time up to nearest X minutes"
        self.fields['applies_from_time'].help_text = "Optional: Rate only applies from this time"
        self.fields['applies_to_time'].help_text = "Optional: Rate only applies until this time"
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate time range
        from_time = cleaned_data.get('applies_from_time')
        to_time = cleaned_data.get('applies_to_time')
        
        if from_time and to_time and from_time >= to_time:
            raise ValidationError("From time must be before to time.")
        
        # Validate date range
        valid_from = cleaned_data.get('valid_from')
        valid_until = cleaned_data.get('valid_until')
        
        if valid_from and valid_until and valid_from >= valid_until:
            raise ValidationError("Valid from date must be before valid until date.")
        
        # Validate weekday/weekend exclusivity
        weekdays_only = cleaned_data.get('applies_weekdays_only')
        weekends_only = cleaned_data.get('applies_weekends_only')
        
        if weekdays_only and weekends_only:
            raise ValidationError("Rate cannot apply to both weekdays only and weekends only.")
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set created_by if this is a new instance and commit is True
        if not instance.pk and commit and hasattr(self, '_user'):
            instance.created_by = self._user
        
        if commit:
            instance.save()
        
        return instance