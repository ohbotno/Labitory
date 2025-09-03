# booking/forms/bookings.py
"""
Booking-related forms for the Aperture Booking system.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django import forms
from django.utils import timezone
from datetime import datetime, timedelta
from ..models import Booking, BookingTemplate, Resource, UserProfile
from ..recurring import RecurringBookingPattern


class BookingForm(forms.ModelForm):
    """Form for creating and editing bookings."""
    
    # Override fields for better widget control
    start_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'})
    )
    end_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'})
    )
    override_conflicts = forms.BooleanField(
        required=False,
        widget=forms.HiddenInput()
    )
    override_message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        help_text="Explain why you're overriding conflicts (required for override)"
    )
    
    class Meta:
        model = Booking
        fields = [
            'resource', 'title', 'description',
            'start_time', 'end_time', 'shared_with_group',
            'notes', 'override_conflicts', 'override_message'
        ]
        widgets = {
            'resource': forms.Select(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'shared_with_group': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        self._conflicts = []
        super().__init__(*args, **kwargs)
        
        # Filter resources to show only those available to the user
        if user:
            try:
                user_profile = user.userprofile
                available_resources = []
                for resource in Resource.objects.filter(is_active=True):
                    if resource.is_available_for_user(user_profile):
                        available_resources.append(resource.pk)
                self.fields['resource'].queryset = Resource.objects.filter(pk__in=available_resources)
            except UserProfile.DoesNotExist:
                self.fields['resource'].queryset = Resource.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        resource = cleaned_data.get('resource')
        
        # Validate time range
        if start_time and end_time:
            if start_time >= end_time:
                raise forms.ValidationError("End time must be after start time.")
            
            # Check if booking is in the past
            if start_time < timezone.now():
                raise forms.ValidationError("Cannot create bookings in the past.")
            
            # Check resource max booking hours
            if resource and resource.max_booking_hours:
                duration = (end_time - start_time).total_seconds() / 3600
                if duration > resource.max_booking_hours:
                    raise forms.ValidationError(
                        f"Booking duration ({duration:.1f}h) exceeds maximum allowed "
                        f"({resource.max_booking_hours}h) for this resource."
                    )
        
        # Check for conflicts
        if resource and start_time and end_time:
            conflicts = self._check_conflicts(resource, start_time, end_time)
            if conflicts:
                self._conflicts = conflicts
                if not (self._can_override_conflicts() and cleaned_data.get('override_conflicts')):
                    conflict_details = []
                    for conflict in conflicts:
                        conflict_details.append(
                            f"'{conflict.title}' by {conflict.user.get_full_name()} "
                            f"({conflict.start_time.strftime('%Y-%m-%d %H:%M')} - "
                            f"{conflict.end_time.strftime('%Y-%m-%d %H:%M')})"
                        )
                    raise forms.ValidationError(
                        f"Time conflict detected with existing booking(s): {', '.join(conflict_details)}"
                    )
                elif cleaned_data.get('override_conflicts') and not cleaned_data.get('override_message'):
                    raise forms.ValidationError("Override message is required when overriding conflicts.")
        
        return cleaned_data

    def _check_conflicts(self, resource, start_time, end_time):
        """Check for booking conflicts."""
        conflicts = Booking.objects.filter(
            resource=resource,
            start_time__lt=end_time,
            end_time__gt=start_time,
            status__in=['pending', 'approved', 'in_progress']
        )
        
        # Exclude current booking if editing
        if self.instance.pk:
            conflicts = conflicts.exclude(pk=self.instance.pk)
        
        return list(conflicts)

    def _can_override_conflicts(self):
        """Check if user can override conflicts."""
        if not self.user:
            return False
        
        try:
            user_profile = self.user.userprofile
            return user_profile.role in ['technician', 'sysadmin']
        except UserProfile.DoesNotExist:
            return False

    def get_conflicts(self):
        """Get detected conflicts."""
        return self._conflicts


class RecurringBookingForm(forms.Form):
    """Form for creating recurring bookings."""
    
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('biweekly', 'Bi-weekly'),
        ('monthly', 'Monthly'),
    ]
    
    frequency = forms.ChoiceField(
        choices=FREQUENCY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    interval = forms.IntegerField(
        min_value=1,
        max_value=12,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Repeat every X periods (e.g., every 2 weeks)"
    )
    
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        help_text="When should the recurring series end?"
    )
    
    max_occurrences = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Maximum number of bookings to create (optional)"
    )
    
    days_of_week = forms.MultipleChoiceField(
        choices=[
            (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'),
            (3, 'Thursday'), (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday')
        ],
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        help_text="Select days of the week (for weekly/bi-weekly patterns)"
    )

    def clean(self):
        cleaned_data = super().clean()
        frequency = cleaned_data.get('frequency')
        end_date = cleaned_data.get('end_date')
        days_of_week = cleaned_data.get('days_of_week')
        
        if end_date and end_date <= timezone.now().date():
            raise forms.ValidationError("End date must be in the future.")
        
        if frequency in ['weekly', 'biweekly'] and not days_of_week:
            raise forms.ValidationError("Please select at least one day of the week.")
        
        return cleaned_data


class BookingTemplateForm(forms.ModelForm):
    """Form for creating booking templates."""
    
    class Meta:
        model = BookingTemplate
        fields = [
            'name', 'resource', 'title_template', 'description_template',
            'duration_hours', 'duration_minutes', 'shared_with_group'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'resource': forms.Select(attrs={'class': 'form-control'}),
            'title_template': forms.TextInput(attrs={'class': 'form-control'}),
            'description_template': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'duration_hours': forms.NumberInput(attrs={'class': 'form-control'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-control'}),
            'shared_with_group': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        
        # Filter resources to show only those available to the user
        if user:
            try:
                user_profile = user.userprofile
                available_resources = []
                for resource in Resource.objects.filter(is_active=True):
                    if resource.is_available_for_user(user_profile):
                        available_resources.append(resource.pk)
                self.fields['resource'].queryset = Resource.objects.filter(pk__in=available_resources)
            except UserProfile.DoesNotExist:
                self.fields['resource'].queryset = Resource.objects.none()


class CreateBookingFromTemplateForm(forms.Form):
    """Form for creating a booking from a template."""
    
    template = forms.ModelChoiceField(
        queryset=BookingTemplate.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label="Select a template"
    )
    
    start_time = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'})
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        
        # Show only user's templates
        if user:
            self.fields['template'].queryset = BookingTemplate.objects.filter(user=user)

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        
        if start_time and start_time < timezone.now():
            raise forms.ValidationError("Cannot create bookings in the past.")
        
        return cleaned_data

    def save(self):
        """Create booking from template."""
        template = self.cleaned_data['template']
        start_time = self.cleaned_data['start_time']
        
        # Calculate end time based on estimated duration
        end_time = start_time + timedelta(hours=template.estimated_duration)
        
        booking = Booking.objects.create(
            user=self.user,
            resource=template.resource,
            title=template.title,
            description=template.description,
            purpose=template.purpose,
            start_time=start_time,
            end_time=end_time,
            shared_with_group=template.shared_with_group,
        )
        
        return booking


class SaveAsTemplateForm(forms.Form):
    """Form for saving a booking as a template."""
    
    template_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text="Give this template a descriptive name"
    )

    def clean_template_name(self):
        name = self.cleaned_data['template_name']
        if len(name.strip()) < 3:
            raise forms.ValidationError("Template name must be at least 3 characters long.")
        return name.strip()