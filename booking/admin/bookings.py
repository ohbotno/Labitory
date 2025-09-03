# booking/admin/bookings.py
"""
Booking-related admin configuration for the Aperture Booking system.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django.contrib import admin
from ..models import Booking, BookingAttendee, ApprovalRule, BookingHistory, BookingTemplate


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('title', 'resource', 'user', 'start_time', 'end_time', 'status', 'checkin_status', 'is_checked_in')
    list_filter = ('status', 'resource__resource_type', 'is_recurring', 'shared_with_group', 'no_show', 'auto_checked_out')
    search_fields = ('title', 'description', 'user__username', 'resource__name')
    readonly_fields = ('created_at', 'updated_at', 'approved_at', 'checked_in_at', 'checked_out_at', 'actual_start_time', 'actual_end_time')
    date_hierarchy = 'start_time'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'resource', 'user', 'status')
        }),
        ('Scheduling', {
            'fields': ('start_time', 'end_time', 'is_recurring', 'recurring_pattern')
        }),
        ('Sharing & Attendees', {
            'fields': ('shared_with_group', 'notes')
        }),
        ('Approval', {
            'fields': ('approved_by', 'approved_at'),
            'classes': ('collapse',)
        }),
        ('Check-in/Check-out', {
            'fields': ('checked_in_at', 'checked_out_at', 'actual_start_time', 'actual_end_time', 'no_show', 'auto_checked_out'),
            'classes': ('collapse',)
        }),
        ('System Fields', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['mark_no_show', 'auto_check_out_selected']
    
    def is_checked_in(self, obj):
        return obj.is_checked_in
    is_checked_in.boolean = True
    is_checked_in.short_description = 'Checked In'
    
    def checkin_status(self, obj):
        return obj.checkin_status
    checkin_status.short_description = 'Status'
    
    def mark_no_show(self, request, queryset):
        """Mark selected bookings as no-show."""
        from ..checkin_service import checkin_service
        
        count = 0
        for booking in queryset:
            if not booking.checked_in_at and not booking.no_show:
                try:
                    success, message = checkin_service.mark_no_show(booking.id, request.user, "Marked by admin")
                    if success:
                        count += 1
                except Exception:
                    pass
        
        self.message_user(request, f'Marked {count} bookings as no-show.')
    mark_no_show.short_description = 'Mark selected bookings as no-show'
    
    def auto_check_out_selected(self, request, queryset):
        """Auto check-out selected bookings."""
        count = 0
        for booking in queryset:
            if booking.is_checked_in:
                try:
                    if booking.auto_check_out():
                        count += 1
                except Exception:
                    pass
        
        self.message_user(request, f'Auto checked-out {count} bookings.')
    auto_check_out_selected.short_description = 'Auto check-out selected bookings'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('resource', 'user', 'approved_by')


@admin.register(BookingAttendee)
class BookingAttendeeAdmin(admin.ModelAdmin):
    list_display = ('booking', 'user', 'is_primary', 'added_at')
    list_filter = ('is_primary',)
    search_fields = ('booking__title', 'user__username')


@admin.register(ApprovalRule)
class ApprovalRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'resource', 'approval_type', 'is_active', 'priority')
    list_filter = ('approval_type', 'is_active')
    search_fields = ('name', 'resource__name')
    filter_horizontal = ('approvers',)


@admin.register(BookingHistory)
class BookingHistoryAdmin(admin.ModelAdmin):
    list_display = ('booking', 'user', 'action', 'timestamp')
    list_filter = ('action',)
    search_fields = ('booking__title', 'user__username', 'action')
    readonly_fields = ('timestamp',)
    date_hierarchy = 'timestamp'


@admin.register(BookingTemplate)
class BookingTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'resource', 'created_at')
    list_filter = ('resource__resource_type', 'shared_with_group')
    search_fields = ('name', 'title', 'user__username', 'resource__name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Template Information', {
            'fields': ('name', 'user', 'resource')
        }),
        ('Booking Details', {
            'fields': ('title', 'description', 'purpose', 'estimated_duration')
        }),
        ('Settings', {
            'fields': ('shared_with_group',)
        }),
        ('System Fields', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )