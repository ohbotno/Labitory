# booking/forms/admin.py
"""
Administrative forms for the Aperture Booking system.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django import forms
from ..models import AboutPage


class AboutPageEditForm(forms.ModelForm):
    """Form for editing the about page."""
    
    class Meta:
        model = AboutPage
        fields = [
            'title', 'facility_name', 'content', 'contact_email', 
            'contact_phone', 'address', 'emergency_contact',
            'operating_hours', 'policies_url', 'safety_information',
            'is_active'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'facility_name': forms.TextInput(attrs={'class': 'form-control'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 10}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'emergency_contact': forms.TextInput(attrs={'class': 'form-control'}),
            'operating_hours': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'policies_url': forms.URLInput(attrs={'class': 'form-control'}),
            'safety_information': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }