# booking/admin/core.py
"""
Core admin configuration for the Aperture Booking system.
Includes User profiles, AboutPage, LabSettings, and academic hierarchy.

This file is part of the Aperture Booking.
Copyright (C) 2025 Aperture Booking Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperture-booking.org/commercial
"""

import csv
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.http import HttpResponse

from ..models import (
    AboutPage, LabSettings, UserProfile, 
    Faculty, College, Department
)


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)


# Unregister and re-register User with our customizations
admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(AboutPage)
class AboutPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'facility_name', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'facility_name', 'content')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'facility_name', 'is_active')
        }),
        ('Content', {
            'fields': ('content',),
            'description': 'Main content for the about page. HTML is allowed.'
        }),
        ('Contact Information', {
            'fields': ('contact_email', 'contact_phone', 'address', 'emergency_contact'),
            'classes': ('collapse',)
        }),
        ('Operational Information', {
            'fields': ('operating_hours', 'policies_url', 'safety_information'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_active and AboutPage.objects.filter(is_active=True).count() == 1:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(LabSettings)
class LabSettingsAdmin(admin.ModelAdmin):
    list_display = ('lab_name', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('lab_name',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Lab Customization', {
            'fields': ('lab_name', 'is_active'),
            'description': 'Customize your lab name to be displayed throughout the application.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_active and LabSettings.objects.filter(is_active=True).count() == 1:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    readonly_fields = ('created_at',)


@admin.register(College)
class CollegeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'faculty', 'is_active', 'created_at')
    list_filter = ('faculty', 'is_active')
    search_fields = ('name', 'code', 'faculty__name')
    readonly_fields = ('created_at',)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'college', 'is_active', 'created_at')
    list_filter = ('college__faculty', 'college', 'is_active')
    search_fields = ('name', 'code', 'college__name', 'college__faculty__name')
    readonly_fields = ('created_at',)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'academic_path', 'student_level', 'training_level', 'is_inducted')
    list_filter = ('role', 'faculty', 'college', 'department', 'student_level', 'training_level', 'is_inducted')
    search_fields = (
        'user__username', 'user__email', 'user__first_name', 'user__last_name', 
        'student_id', 'staff_number', 'faculty__name', 'college__name', 'department__name'
    )
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'role')
        }),
        ('Academic Structure', {
            'fields': ('faculty', 'college', 'department', 'group')
        }),
        ('Role-Specific Information', {
            'fields': ('student_id', 'student_level', 'staff_number')
        }),
        ('System Information', {
            'fields': ('training_level', 'is_inducted', 'email_verified', 'phone')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['export_users_csv', 'bulk_assign_group', 'bulk_change_role', 'bulk_set_training_level']
    
    def export_users_csv(self, request, queryset):
        """Export selected users to CSV format."""
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="users_export.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'username', 'email', 'first_name', 'last_name', 'role', 'group',
            'faculty_code', 'college_code', 'department_code', 'student_id',
            'staff_number', 'training_level', 'phone'
        ])
        
        for profile in queryset.select_related('user', 'faculty', 'college', 'department'):
            writer.writerow([
                profile.user.username,
                profile.user.email,
                profile.user.first_name,
                profile.user.last_name,
                profile.role,
                profile.group,
                profile.faculty.code if profile.faculty else '',
                profile.college.code if profile.college else '',
                profile.department.code if profile.department else '',
                profile.student_id or '',
                profile.staff_number or '',
                profile.training_level,
                profile.phone or '',
            ])
        
        return response
    
    export_users_csv.short_description = "Export selected users to CSV"
    
    def bulk_assign_group(self, request, queryset):
        """Bulk assign group to selected users."""
        from django import forms
        from django.shortcuts import render
        
        class GroupAssignForm(forms.Form):
            group = forms.CharField(max_length=100, help_text="Enter the group name to assign")
        
        if 'apply' in request.POST:
            form = GroupAssignForm(request.POST)
            if form.is_valid():
                group = form.cleaned_data['group']
                count = queryset.update(group=group)
                self.message_user(request, f'Successfully assigned group "{group}" to {count} users.')
                return
        else:
            form = GroupAssignForm()
        
        return render(request, 'admin/bulk_assign_group.html', {
            'form': form,
            'queryset': queryset,
            'action_checkbox_name': admin.ACTION_CHECKBOX_NAME,
        })
    
    bulk_assign_group.short_description = "Bulk assign group to selected users"
    
    def academic_path(self, obj):
        """Display the academic path (Faculty > College > Department)."""
        path_parts = []
        if obj.faculty:
            path_parts.append(obj.faculty.name)
        if obj.college:
            path_parts.append(obj.college.name)
        if obj.department:
            path_parts.append(obj.department.name)
        return " > ".join(path_parts) if path_parts else "Not assigned"
    
    academic_path.short_description = "Academic Path"