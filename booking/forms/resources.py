# booking/forms/resources.py
"""
Resource-related forms for the Aperture Booking system.

This file is part of the Aperture Booking.
Copyright (C) 2025 Aperture Booking Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperture-booking.org/commercial
"""

from django import forms
from django.utils import timezone

from ..models import (
    Resource, AccessRequest, ResourceResponsible, ChecklistItem,
    RiskAssessment, UserRiskAssessment, TrainingCourse, UserTraining, ResourceIssue
)


class AccessRequestForm(forms.ModelForm):
    """Form for requesting access to a resource."""
    
    class Meta:
        model = AccessRequest
        fields = ['justification']
        widgets = {
            'justification': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 4,
                'placeholder': 'Please explain why you need access to this resource...'
            }),
        }

    def clean_justification(self):
        justification = self.cleaned_data['justification']
        if len(justification.strip()) < 10:
            raise forms.ValidationError("Please provide a more detailed justification (at least 10 characters).")
        return justification.strip()


class ResourceForm(forms.ModelForm):
    """Form for creating and editing resources."""
    
    class Meta:
        model = Resource
        fields = [
            'name', 'resource_type', 'description', 'location',
            'capacity', 'max_booking_hours', 'required_training_level',
            'requires_induction', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'resource_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_booking_hours': forms.NumberInput(attrs={'class': 'form-control'}),
            'required_training_level': forms.Select(attrs={'class': 'form-control'}),
            'requires_induction': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ResourceResponsibleForm(forms.ModelForm):
    """Form for assigning resource responsibilities."""
    
    class Meta:
        model = ResourceResponsible
        fields = ['user', 'resource', 'role_type', 'can_approve_access']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-control'}),
            'resource': forms.Select(attrs={'class': 'form-control'}),
            'role_type': forms.Select(attrs={'class': 'form-control'}),
            'can_approve_access': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ChecklistItemForm(forms.ModelForm):
    """Form for creating checklist items."""
    
    class Meta:
        model = ChecklistItem
        fields = ['title', 'description', 'item_type', 'category', 'is_required']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'item_type': forms.Select(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'is_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class AccessRequestReviewForm(forms.ModelForm):
    """Form for reviewing access requests."""
    DECISION_CHOICES = [
        ('approve', 'Approve'),
        ('reject', 'Reject'),
    ]
    
    decision = forms.ChoiceField(choices=DECISION_CHOICES, widget=forms.Select(attrs={'class': 'form-control'}))
    
    class Meta:
        model = AccessRequest
        fields = ['decision']


class RiskAssessmentForm(forms.ModelForm):
    """Form for creating risk assessments."""
    
    class Meta:
        model = RiskAssessment
        fields = ['title', 'description', 'risk_level', 'assessment_type']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'risk_level': forms.Select(attrs={'class': 'form-control'}),
            'assessment_type': forms.Select(attrs={'class': 'form-control'}),
        }


class UserRiskAssessmentForm(forms.ModelForm):
    """Form for user risk assessments."""
    
    class Meta:
        model = UserRiskAssessment
        fields = ['user', 'risk_assessment', 'status']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-control'}),
            'risk_assessment': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }


class TrainingCourseForm(forms.ModelForm):
    """Form for creating training courses."""
    
    class Meta:
        model = TrainingCourse
        fields = ['title', 'code', 'description', 'course_type', 'delivery_method']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'course_type': forms.Select(attrs={'class': 'form-control'}),
            'delivery_method': forms.Select(attrs={'class': 'form-control'}),
        }


class UserTrainingEnrollForm(forms.ModelForm):
    """Form for enrolling users in training."""
    
    class Meta:
        model = UserTraining
        fields = ['user', 'training_course', 'status']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-control'}),
            'training_course': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }


class ResourceIssueReportForm(forms.ModelForm):
    """Form for reporting resource issues."""
    
    class Meta:
        model = ResourceIssue
        fields = ['title', 'description', 'severity']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'severity': forms.Select(attrs={'class': 'form-control'}),
        }


class ResourceIssueUpdateForm(forms.ModelForm):
    """Form for updating resource issues."""
    
    class Meta:
        model = ResourceIssue
        fields = ['status', 'category']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
        }


class IssueFilterForm(forms.Form):
    """Form for filtering issues."""
    STATUS_CHOICES = [
        ('', 'All Statuses'),
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('in_progress', 'In Progress'),
    ]
    
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False, 
                              widget=forms.Select(attrs={'class': 'form-control'}))
    priority = forms.ChoiceField(required=False, 
                               widget=forms.Select(attrs={'class': 'form-control'}))


# Additional forms can be added here as models are verified