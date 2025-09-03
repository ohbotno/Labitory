# booking/views/modules/maintenance.py
"""
Maintenance management views for the Labitory.

This module handles maintenance period management and calendar integration.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core.paginator import Paginator
from django.db.models import Q

from ...models import Maintenance, Resource, UserProfile


def is_lab_admin(user):
    """Check if user has lab admin permissions."""
    if not user.is_authenticated:
        return False
    try:
        return user.userprofile.role in ['technician', 'sysadmin']
    except UserProfile.DoesNotExist:
        return False


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_maintenance_view(request):
    """Display and manage maintenance periods for lab administrators."""
    
    # Get filter parameters
    resource_filter = request.GET.get('resource', '')
    type_filter = request.GET.get('type', '')
    search_query = request.GET.get('search', '')
    
    # Base queryset
    maintenance_list = Maintenance.objects.select_related('resource', 'created_by').order_by('-start_time')
    
    # Apply filters
    if resource_filter:
        maintenance_list = maintenance_list.filter(resource_id=resource_filter)
    
    if type_filter:
        maintenance_list = maintenance_list.filter(maintenance_type=type_filter)
    
    if search_query:
        maintenance_list = maintenance_list.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(resource__name__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(maintenance_list, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get resources and maintenance types for filters
    resources = Resource.objects.filter(is_active=True).order_by('name')
    maintenance_types = Maintenance.MAINTENANCE_TYPES
    
    return render(request, 'booking/lab_admin/maintenance.html', {
        'page_obj': page_obj,
        'resources': resources,
        'maintenance_types': maintenance_types,
        'current_filters': {
            'resource': resource_filter,
            'type': type_filter,
            'search': search_query,
        },
    })


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_add_maintenance_view(request):
    """Add a new maintenance period."""
    
    if request.method == 'POST':
        try:
            # Get form data
            title = request.POST.get('title')
            resource_id = request.POST.get('resource')
            description = request.POST.get('description', '')
            start_time = parse_datetime(request.POST.get('start_time'))
            end_time = parse_datetime(request.POST.get('end_time'))
            
            # Make datetimes timezone-aware if they're not already
            if start_time and timezone.is_naive(start_time):
                start_time = timezone.make_aware(start_time)
            if end_time and timezone.is_naive(end_time):
                end_time = timezone.make_aware(end_time)
            
            maintenance_type = request.POST.get('maintenance_type')
            blocks_booking = request.POST.get('blocks_booking') == 'true'
            is_recurring = request.POST.get('is_recurring') == 'true'
            recurring_pattern = request.POST.get('recurring_pattern') if is_recurring else None
            
            # Validation
            if not all([title, resource_id, start_time, end_time, maintenance_type]):
                return JsonResponse({
                    'success': False, 
                    'error': 'All required fields must be provided'
                })
            
            if start_time >= end_time:
                return JsonResponse({
                    'success': False, 
                    'error': 'Start time must be before end time'
                })
            
            # Get resource
            try:
                resource = Resource.objects.get(id=resource_id)
            except Resource.DoesNotExist:
                return JsonResponse({
                    'success': False, 
                    'error': 'Resource not found'
                })
            
            # Create maintenance
            maintenance = Maintenance.objects.create(
                title=title,
                resource=resource,
                description=description,
                start_time=start_time,
                end_time=end_time,
                maintenance_type=maintenance_type,
                blocks_booking=blocks_booking,
                is_recurring=is_recurring,
                recurring_pattern=recurring_pattern,
                created_by=request.user
            )
            
            return JsonResponse({
                'success': True, 
                'message': f'Maintenance period "{title}" created successfully',
                'maintenance_id': maintenance.id
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    # GET request - return form data
    resources = Resource.objects.filter(is_active=True).order_by('name')
    maintenance_types = Maintenance.MAINTENANCE_TYPES
    
    return JsonResponse({
        'resources': [{'id': r.id, 'name': r.name} for r in resources],
        'maintenance_types': [[k, v] for k, v in maintenance_types],
    })


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_edit_maintenance_view(request, maintenance_id):
    """Edit or view an existing maintenance period."""
    maintenance = get_object_or_404(Maintenance, id=maintenance_id)
    
    if request.method == 'GET':
        # Return maintenance data for viewing/editing
        maintenance_data = {
            'id': maintenance.id,
            'title': maintenance.title,
            'description': maintenance.description,
            'resource_id': maintenance.resource.id,
            'resource_name': maintenance.resource.name,
            'start_time': maintenance.start_time.strftime('%Y-%m-%dT%H:%M'),
            'end_time': maintenance.end_time.strftime('%Y-%m-%dT%H:%M'),
            'maintenance_type': maintenance.maintenance_type,
            'blocks_booking': maintenance.blocks_booking,
            'is_recurring': maintenance.is_recurring,
            'recurring_pattern': maintenance.recurring_pattern,
            'created_by': maintenance.created_by.get_full_name() or maintenance.created_by.username,
            'created_at': maintenance.created_at.strftime('%Y-%m-%d %H:%M'),
        }
        
        return JsonResponse({'success': True, 'maintenance': maintenance_data})
    
    elif request.method == 'POST':
        try:
            # Update maintenance data
            maintenance.title = request.POST.get('title', maintenance.title)
            maintenance.description = request.POST.get('description', maintenance.description)
            
            # Update times if provided
            start_time = request.POST.get('start_time')
            end_time = request.POST.get('end_time')
            
            if start_time:
                start_time = parse_datetime(start_time)
                if start_time and timezone.is_naive(start_time):
                    start_time = timezone.make_aware(start_time)
                maintenance.start_time = start_time
            
            if end_time:
                end_time = parse_datetime(end_time)
                if end_time and timezone.is_naive(end_time):
                    end_time = timezone.make_aware(end_time)
                maintenance.end_time = end_time
            
            # Validate times
            if maintenance.start_time >= maintenance.end_time:
                return JsonResponse({
                    'success': False, 
                    'error': 'Start time must be before end time'
                })
            
            # Update other fields
            if 'maintenance_type' in request.POST:
                maintenance.maintenance_type = request.POST.get('maintenance_type')
            
            if 'blocks_booking' in request.POST:
                maintenance.blocks_booking = request.POST.get('blocks_booking') == 'true'
            
            if 'is_recurring' in request.POST:
                maintenance.is_recurring = request.POST.get('is_recurring') == 'true'
                maintenance.recurring_pattern = request.POST.get('recurring_pattern') if maintenance.is_recurring else None
            
            maintenance.save()
            
            return JsonResponse({
                'success': True, 
                'message': f'Maintenance period "{maintenance.title}" updated successfully'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_delete_maintenance_view(request, maintenance_id):
    """Delete a maintenance period."""
    maintenance = get_object_or_404(Maintenance, id=maintenance_id)
    
    if request.method == 'POST':
        try:
            maintenance_title = maintenance.title
            maintenance.delete()
            return JsonResponse({
                'success': True, 
                'message': f'Maintenance period "{maintenance_title}" deleted successfully'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@login_required
def download_maintenance_invitation(request, maintenance_id):
    """Download a calendar invitation for a specific maintenance period."""
    from booking.calendar_sync import ICSCalendarGenerator, create_ics_response
    
    maintenance = get_object_or_404(Maintenance, id=maintenance_id)
    
    # Generate ICS invitation
    generator = ICSCalendarGenerator(request)
    ics_content = generator.generate_maintenance_invitation(maintenance)
    
    # Create filename
    safe_title = maintenance.title.replace(' ', '-').replace('/', '-')
    filename = f"maintenance-{safe_title}-{maintenance.start_time.strftime('%Y%m%d')}.ics"
    
    return create_ics_response(ics_content, filename)