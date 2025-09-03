"""
Checklist models for the Labitory.

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
from django.core.exceptions import ValidationError
from .resources import Resource
from .bookings import Booking


class ChecklistItem(models.Model):
    """Individual checklist item that can be assigned to resources."""
    
    ITEM_TYPES = [
        ('checkbox', 'Checkbox (Yes/No)'),
        ('text', 'Text Input'),
        ('number', 'Number Input'),
        ('select', 'Dropdown Selection'),
        ('textarea', 'Long Text'),
    ]
    
    CATEGORY_CHOICES = [
        ('safety', 'Safety Check'),
        ('equipment', 'Equipment Status'),
        ('cleanliness', 'Cleanliness'),
        ('documentation', 'Documentation'),
        ('maintenance', 'Maintenance Check'),
        ('other', 'Other'),
    ]
    
    title = models.CharField(max_length=200, help_text="Question or instruction text")
    description = models.TextField(blank=True, help_text="Additional description or guidance")
    item_type = models.CharField(max_length=20, choices=ITEM_TYPES, default='checkbox')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    is_required = models.BooleanField(default=True, help_text="Must be completed to proceed")
    
    # For select/dropdown items
    options = models.JSONField(
        blank=True,
        null=True,
        help_text="JSON array of options for select items, e.g. ['Good', 'Needs Attention', 'Damaged']"
    )
    
    # For validation
    min_value = models.FloatField(null=True, blank=True, help_text="Minimum value for number inputs")
    max_value = models.FloatField(null=True, blank=True, help_text="Maximum value for number inputs")
    max_length = models.IntegerField(null=True, blank=True, help_text="Maximum length for text inputs")
    
    # System fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_checklist_items'
    )
    
    class Meta:
        db_table = 'booking_checklistitem'
        ordering = ['category', 'title']
    
    def __str__(self):
        return f"{self.get_category_display()}: {self.title}"
    
    def clean(self):
        """Validate the checklist item configuration."""
        if self.item_type == 'select' and not self.options:
            raise ValidationError("Select items must have options defined")
        
        if self.item_type == 'number':
            if self.min_value is not None and self.max_value is not None:
                if self.min_value >= self.max_value:
                    raise ValidationError("Min value must be less than max value")


class ResourceChecklistItem(models.Model):
    """Links checklist items to specific resources with ordering."""
    
    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name='checklist_items'
    )
    checklist_item = models.ForeignKey(
        ChecklistItem,
        on_delete=models.CASCADE,
        related_name='resource_assignments'
    )
    order = models.PositiveIntegerField(default=0, help_text="Display order (lower numbers first)")
    is_active = models.BooleanField(default=True, help_text="Include this item in the checklist")
    
    # Override settings per resource
    override_required = models.BooleanField(
        default=False,
        help_text="Override the default required setting for this resource"
    )
    is_required_override = models.BooleanField(
        default=True,
        help_text="Required setting when override is enabled"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'booking_resourcechecklistitem'
        ordering = ['order', 'checklist_item__category', 'checklist_item__title']
        unique_together = ['resource', 'checklist_item']
    
    def __str__(self):
        return f"{self.resource.name} - {self.checklist_item.title}"
    
    @property
    def is_required(self):
        """Get the effective required status for this item."""
        if self.override_required:
            return self.is_required_override
        return self.checklist_item.is_required


class ChecklistResponse(models.Model):
    """User responses to checklist items during checkout."""
    
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name='checklist_responses'
    )
    checklist_item = models.ForeignKey(
        ChecklistItem,
        on_delete=models.CASCADE,
        related_name='responses'
    )
    
    # Response data
    text_response = models.TextField(blank=True, help_text="Text/textarea responses")
    number_response = models.FloatField(null=True, blank=True, help_text="Number responses")
    boolean_response = models.BooleanField(null=True, blank=True, help_text="Checkbox responses")
    select_response = models.CharField(max_length=200, blank=True, help_text="Selected option")
    
    # Metadata
    completed_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Validation status
    is_valid = models.BooleanField(default=True, help_text="Whether the response passes validation")
    validation_notes = models.TextField(blank=True, help_text="Notes about validation issues")
    
    class Meta:
        db_table = 'booking_checklistresponse'
        unique_together = ['booking', 'checklist_item']
        ordering = ['-completed_at']
    
    def __str__(self):
        return f"{self.booking} - {self.checklist_item.title}"
    
    def get_response_value(self):
        """Get the actual response value based on item type."""
        item_type = self.checklist_item.item_type
        
        if item_type == 'checkbox':
            return self.boolean_response
        elif item_type == 'number':
            return self.number_response
        elif item_type == 'select':
            return self.select_response
        else:  # text, textarea
            return self.text_response
    
    def validate_response(self):
        """Validate the response against the checklist item constraints."""
        item = self.checklist_item
        value = self.get_response_value()
        
        # Required field validation
        if item.is_required and value in [None, '', False]:
            self.is_valid = False
            self.validation_notes = "This field is required"
            return False
        
        # Type-specific validation
        if item.item_type == 'number' and self.number_response is not None:
            if item.min_value is not None and self.number_response < item.min_value:
                self.is_valid = False
                self.validation_notes = f"Value must be at least {item.min_value}"
                return False
            if item.max_value is not None and self.number_response > item.max_value:
                self.is_valid = False
                self.validation_notes = f"Value must be at most {item.max_value}"
                return False
        
        if item.item_type in ['text', 'textarea'] and self.text_response:
            if item.max_length and len(self.text_response) > item.max_length:
                self.is_valid = False
                self.validation_notes = f"Text must be {item.max_length} characters or less"
                return False
        
        if item.item_type == 'select' and self.select_response:
            if item.options and self.select_response not in item.options:
                self.is_valid = False
                self.validation_notes = "Invalid selection"
                return False
        
        self.is_valid = True
        self.validation_notes = ""
        return True