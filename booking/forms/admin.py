# booking/forms/admin.py
"""
Administrative forms for the Aperture Booking system.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django import forms
from ..models import AboutPage, EmailConfiguration, SMSConfiguration


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


class SMSConfigurationForm(forms.ModelForm):
    """Form for creating and editing SMS configurations."""
    
    class Meta:
        model = SMSConfiguration
        fields = [
            'name', 'description', 'is_enabled', 'twilio_account_sid', 'twilio_auth_token',
            'twilio_phone_number', 'message_character_limit', 'retry_count', 'is_active'
        ]
        
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Production Twilio SMS'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description of this configuration'
            }),
            'is_enabled': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'twilio_account_sid': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
            }),
            'twilio_auth_token': forms.PasswordInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your Twilio Auth Token'
            }),
            'twilio_phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+1234567890'
            }),
            'message_character_limit': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 160,
                'max': 1600,
                'step': 1
            }),
            'retry_count': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'max': 10,
                'step': 1
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add help text and required indicators
        self.fields['name'].help_text = "A descriptive name for this SMS configuration"
        self.fields['description'].help_text = "Optional description of this SMS configuration"
        self.fields['is_enabled'].help_text = "Enable SMS notifications globally"
        self.fields['twilio_account_sid'].help_text = "Your Twilio Account SID (starts with AC)"
        self.fields['twilio_auth_token'].help_text = "Your Twilio Auth Token"
        self.fields['twilio_phone_number'].help_text = "Twilio phone number in international format (+1234567890)"
        self.fields['message_character_limit'].help_text = "Maximum characters per SMS (default: 1600)"
        self.fields['retry_count'].help_text = "Number of retry attempts for failed messages"
        self.fields['is_active'].help_text = "Make this the active SMS configuration"
        
        # Handle password field for existing configurations
        if self.instance.pk and self.instance.twilio_auth_token:
            self.fields['twilio_auth_token'].widget.attrs['placeholder'] = '••••••••'
            self.fields['twilio_auth_token'].help_text = "Leave blank to keep current auth token"
            self.fields['twilio_auth_token'].required = False
    
    def clean_twilio_phone_number(self):
        phone_number = self.cleaned_data.get('twilio_phone_number')
        if phone_number and not phone_number.startswith('+'):
            raise forms.ValidationError("Phone number must be in international format starting with '+'")
        return phone_number
    
    def clean_twilio_account_sid(self):
        account_sid = self.cleaned_data.get('twilio_account_sid')
        if account_sid and not account_sid.startswith('AC'):
            raise forms.ValidationError("Twilio Account SID must start with 'AC'")
        return account_sid
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Handle auth token field - only update if a new token was provided
        if not self.cleaned_data.get('twilio_auth_token') and self.instance.pk:
            # Keep the existing auth token
            instance.twilio_auth_token = self.instance.twilio_auth_token
        
        if commit:
            instance.save()
        
        return instance


class SMSConfigurationTestForm(forms.Form):
    """Form for testing SMS configurations."""
    
    test_phone_number = forms.CharField(
        label="Test Phone Number",
        help_text="Phone number to send the test SMS to (international format: +1234567890)",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+1234567890'
        })
    )
    
    test_type = forms.ChoiceField(
        label="Test Type",
        choices=[
            ('validate', 'Validate Credentials Only'),
            ('send_sms', 'Send Test SMS'),
        ],
        initial='validate',
        help_text="Choose whether to validate credentials or send an actual test SMS",
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    
    def __init__(self, *args, **kwargs):
        self.configuration = kwargs.pop('configuration', None)
        super().__init__(*args, **kwargs)
        
        # Make phone number required if sending SMS
        if self.data.get('test_type') == 'send_sms':
            self.fields['test_phone_number'].required = True
    
    def clean_test_phone_number(self):
        test_type = self.cleaned_data.get('test_type')
        phone_number = self.cleaned_data.get('test_phone_number')
        
        if test_type == 'send_sms':
            if not phone_number:
                raise forms.ValidationError("Phone number is required for sending test SMS")
            if not phone_number.startswith('+'):
                raise forms.ValidationError("Phone number must be in international format starting with '+'")
        
        return phone_number