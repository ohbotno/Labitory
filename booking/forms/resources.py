# booking/forms/resources.py
"""
Resource-related forms for the Aperture Booking system.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django import forms
from django.utils import timezone

from ..models import (
    Resource, AccessRequest, ResourceResponsible, ChecklistItem, ResourceChecklistItem,
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


class ResourceRiskAssessmentUploadForm(forms.Form):
    """Form for uploading risk assessment documents for a resource."""

    assessment_file = forms.FileField(
        label="Risk Assessment Document",
        help_text="Upload your risk assessment document (PDF, Word, Excel, etc.) - Max 20MB",
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.doc,.docx,.xls,.xlsx,.txt'
        })
    )

    title = forms.CharField(
        max_length=200,
        label="Assessment Title",
        help_text="Brief title describing this risk assessment",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., Chemical Safety Risk Assessment'
        })
    )

    description = forms.CharField(
        label="Description",
        help_text="Brief description of what this assessment covers",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Describe the hazards and risks addressed in this assessment...'
        }),
        required=False
    )

    user_declaration = forms.BooleanField(
        label="I confirm that I have read and understand the risk assessment and will follow all control measures outlined in this document",
        help_text="Please tick this box to confirm your understanding and agreement",
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        }),
        required=True
    )

    def clean_assessment_file(self):
        file = self.cleaned_data['assessment_file']
        if file:
            # Check file size (20MB limit)
            if file.size > 20 * 1024 * 1024:
                raise forms.ValidationError("File size cannot exceed 20MB.")

            # Check file extension
            allowed_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt']
            file_extension = '.' + file.name.split('.')[-1].lower()
            if file_extension not in allowed_extensions:
                raise forms.ValidationError("Please upload a PDF, Word, Excel, or text file.")

        return file


class ResourceForm(forms.ModelForm):
    """Form for creating and editing resources."""
    
    
    class Meta:
        model = Resource
        fields = [
            'name', 'resource_type', 'description', 'url', 'location',
            'image', 'capacity', 'max_booking_hours',
            'requires_induction', 'requires_risk_assessment', 'requires_checkout_checklist',
            'checkout_checklist_title', 'checkout_checklist_description',
            'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'resource_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com/resource-info'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_booking_hours': forms.NumberInput(attrs={'class': 'form-control'}),
            'requires_induction': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requires_risk_assessment': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'requires_checkout_checklist': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'checkout_checklist_title': forms.TextInput(attrs={'class': 'form-control'}),
            'checkout_checklist_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
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

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.resource = kwargs.pop('resource', None)
        self.booking = kwargs.pop('booking', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = ResourceIssue
        fields = ['title', 'description', 'severity', 'category', 'specific_location', 'image', 'blocks_resource_use']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'severity': forms.Select(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'specific_location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Front panel, Left side, Screen, etc.'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'blocks_resource_use': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user:
            instance.reported_by = self.user
        if self.resource:
            instance.resource = self.resource
        if self.booking:
            instance.related_booking = self.booking
        if commit:
            instance.save()
        return instance


class ResourceIssueUpdateForm(forms.ModelForm):
    """Form for updating resource issues."""

    class Meta:
        model = ResourceIssue
        fields = [
            'status', 'assigned_to', 'is_urgent', 'admin_notes',
            'resolution_description', 'estimated_repair_cost', 'actual_repair_cost'
        ]
        widgets = {
            'status': forms.Select(attrs={'class': 'form-control'}),
            'assigned_to': forms.Select(attrs={'class': 'form-control'}),
            'is_urgent': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'admin_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Internal notes for technicians...'}),
            'resolution_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Provide an update on the issue status, progress made, or resolution details...'
            }),
            'estimated_repair_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'actual_repair_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
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


class ResourceChecklistConfigForm(forms.Form):
    """Form for configuring which checklist items are assigned to a resource."""
    
    def __init__(self, resource, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.resource = resource
        
        # Get all available checklist items
        available_items = ChecklistItem.objects.all().order_by('category', 'title')
        
        # Get currently assigned items
        assigned_items = ResourceChecklistItem.objects.filter(
            resource=resource
        ).select_related('checklist_item')
        
        assigned_dict = {item.checklist_item.id: item for item in assigned_items}
        
        # Create fields for each available item
        for item in available_items:
            field_name = f"item_{item.id}"
            assignment = assigned_dict.get(item.id)
            
            # Checkbox to include/exclude item
            self.fields[f"{field_name}_enabled"] = forms.BooleanField(
                required=False,
                initial=assignment is not None and assignment.is_active,
                label=f"{item.get_category_display()}: {item.title}",
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
            )
            
            # Order field
            self.fields[f"{field_name}_order"] = forms.IntegerField(
                required=False,
                initial=assignment.order if assignment else 0,
                widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': 0}),
                label="Order"
            )
            
            # Required override
            self.fields[f"{field_name}_required"] = forms.BooleanField(
                required=False,
                initial=assignment.is_required if assignment else item.is_required,
                label="Required",
                widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
            )
    
    def save(self):
        """Save the checklist configuration for the resource."""
        from django.utils import timezone
        
        # Get all existing assignments
        existing_assignments = {
            assignment.checklist_item.id: assignment 
            for assignment in ResourceChecklistItem.objects.filter(resource=self.resource)
        }
        
        # Process each item
        for field_name, value in self.cleaned_data.items():
            if field_name.endswith('_enabled'):
                item_id = int(field_name.split('_')[1])
                
                # Get related field values
                enabled = value
                order = self.cleaned_data.get(f"item_{item_id}_order", 0)
                required = self.cleaned_data.get(f"item_{item_id}_required", True)
                
                if enabled:
                    # Create or update assignment
                    assignment = existing_assignments.get(item_id)
                    if assignment:
                        assignment.is_active = True
                        assignment.order = order
                        assignment.is_required_override = required
                        assignment.override_required = (required != assignment.checklist_item.is_required)
                        assignment.save()
                    else:
                        # Create new assignment
                        ResourceChecklistItem.objects.create(
                            resource=self.resource,
                            checklist_item_id=item_id,
                            order=order,
                            is_active=True,
                            override_required=(required != ChecklistItem.objects.get(id=item_id).is_required),
                            is_required_override=required,
                            created_at=timezone.now()
                        )
                else:
                    # Disable or remove assignment
                    assignment = existing_assignments.get(item_id)
                    if assignment:
                        assignment.is_active = False
                        assignment.save()


# Additional forms can be added here as models are verified