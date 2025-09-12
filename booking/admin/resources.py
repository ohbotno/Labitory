# booking/admin/resources.py
"""
Resource-related admin configuration for the Aperture Booking system.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django.contrib import admin
from ..models import (
    Resource, ResourceAccess, AccessRequest, ResourceResponsible,
    ResourceChecklistItem, ChecklistItem, Maintenance
)


class ResourceChecklistItemInline(admin.TabularInline):
    """Inline admin for resource checklist items."""
    model = ResourceChecklistItem
    extra = 0
    fields = ('checklist_item', 'is_required', 'order')
    ordering = ('order',)


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    """Enhanced Resource admin with checklist configuration."""
    
    list_display = [
        'name', 'resource_type', 'location', 'capacity', 'is_active', 
        'requires_checkout_checklist', 'checklist_items_count'
    ]
    
    list_filter = [
        'resource_type', 'is_active', 'requires_induction', 'requires_checkout_checklist'
    ]
    
    search_fields = ['name', 'description', 'location']
    
    fieldsets = [
        ('Basic Information', {
            'fields': ('name', 'resource_type', 'description', 'location', 'image')
        }),
        ('Booking Configuration', {
            'fields': ('capacity', 'max_booking_hours', 'is_active')
        }),
        ('Access Requirements', {
            'fields': ('required_training_level', 'requires_induction'),
            'classes': ('collapse',)
        }),
        ('Checkout Checklist', {
            'fields': ('requires_checkout_checklist', 'checkout_checklist_title', 'checkout_checklist_description'),
            'description': 'Configure whether users must complete a checklist before checking out'
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    ]
    
    readonly_fields = ['created_at', 'updated_at']
    
    inlines = [ResourceChecklistItemInline]
    
    def checklist_items_count(self, obj):
        """Show the number of active checklist items for this resource."""
        return obj.checklist_items.filter(is_active=True).count()
    
    checklist_items_count.short_description = 'Checklist Items'


@admin.register(ResourceAccess)
class ResourceAccessAdmin(admin.ModelAdmin):
    list_display = ('user', 'resource', 'granted_by', 'granted_at', 'is_active')
    list_filter = ('is_active', 'resource__resource_type')
    search_fields = ('user__username', 'user__email', 'resource__name', 'granted_by__username')
    readonly_fields = ('granted_at',)
    date_hierarchy = 'granted_at'


@admin.register(AccessRequest)
class AccessRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'resource', 'status', 'created_at', 'reviewed_by', 'reviewed_at')
    list_filter = ('status', 'resource__resource_type', 'created_at')
    search_fields = ('user__username', 'user__email', 'resource__name', 'reason')
    readonly_fields = ('created_at', 'reviewed_at')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Request Information', {
            'fields': ('user', 'resource', 'reason', 'status')
        }),
        ('Review Information', {
            'fields': ('reviewed_by', 'reviewed_at', 'review_notes'),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        })
    )
    
    actions = ['approve_requests', 'deny_requests']
    
    def approve_requests(self, request, queryset):
        """Bulk approve access requests."""
        count = 0
        for access_request in queryset.filter(status='pending'):
            try:
                access_request.approve(request.user, "Approved via admin bulk action")
                count += 1
            except Exception as e:
                self.message_user(request, f'Error approving request {access_request.id}: {str(e)}', level='ERROR')
        
        self.message_user(request, f'Approved {count} access requests.')
    approve_requests.short_description = 'Approve selected requests'
    
    def deny_requests(self, request, queryset):
        """Bulk deny access requests."""
        count = 0
        for access_request in queryset.filter(status='pending'):
            try:
                access_request.reject(request.user, "Rejected via admin bulk action")
                count += 1
            except Exception as e:
                self.message_user(request, f'Error rejecting request {access_request.id}: {str(e)}', level='ERROR')
        
        self.message_user(request, f'Rejected {count} access requests.')
    deny_requests.short_description = 'Reject selected requests'


@admin.register(ResourceResponsible)
class ResourceResponsibleAdmin(admin.ModelAdmin):
    list_display = ('user', 'resource', 'role_type', 'can_approve_access')
    list_filter = ('role_type', 'can_approve_access', 'resource__resource_type')
    search_fields = ('user__username', 'user__email', 'resource__name')
    readonly_fields = ()
    # date_hierarchy = 'assigned_at'


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'item_type', 'is_required', 'category')
    list_filter = ('item_type', 'is_required', 'category')
    search_fields = ('title', 'description')
    readonly_fields = ()
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'item_type')
        }),
        ('Configuration', {
            'fields': ('is_required', 'category')
        }),
        ('Options (for choice-based items)', {
            'fields': ('options',),
            'description': 'JSON array of options for dropdown/radio items'
        }),
        # ('System Information', {
        #     'fields': ('created_at', 'updated_at'),
        #     'classes': ('collapse',)
        # })
    )


@admin.register(Maintenance)
class MaintenanceAdmin(admin.ModelAdmin):
    list_display = ('resource', 'maintenance_type', 'start_time', 'status', 'priority')
    list_filter = ('maintenance_type', 'status', 'start_time', 'priority')
    search_fields = ('resource__name', 'title')
    readonly_fields = ()
    date_hierarchy = 'start_time'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('resource', 'title', 'description', 'maintenance_type')
        }),
        ('Scheduling', {
            'fields': ('scheduled_date', 'estimated_duration', 'priority')
        }),
        ('Assignment', {
            'fields': ('assigned_technician', 'status')
        }),
        ('Completion', {
            'fields': ('completed_at', 'completion_notes', 'cost'),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['mark_completed', 'schedule_maintenance']
    
    def mark_completed(self, request, queryset):
        """Mark selected maintenance as completed."""
        from django.utils import timezone
        count = queryset.filter(status__in=['pending', 'in_progress']).update(
            status='completed',
            completed_at=timezone.now()
        )
        self.message_user(request, f'Marked {count} maintenance tasks as completed.')
    mark_completed.short_description = 'Mark selected as completed'