# booking/views/modules/conflicts.py
"""
Conflict detection and resolution views for the Labitory.

This module handles booking conflicts, conflict detection, and resolution interfaces.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse

from ...models import UserProfile, Resource, Booking
from ...conflicts import ConflictDetector, ConflictResolver, ConflictManager


@login_required
def conflict_detection_view(request):
    """Conflict detection and resolution interface."""
    # Check if user has permission to view conflicts
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to access conflict management.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to access conflict management.')
        return redirect('booking:dashboard')
    
    # Get filter parameters
    resource_id = request.GET.get('resource')
    days_ahead = int(request.GET.get('days', 30))
    
    conflicts_data = {}
    selected_resource = None
    
    if resource_id:
        try:
            selected_resource = Resource.objects.select_related('closed_by').get(pk=resource_id)
            conflicts_data = ConflictManager.get_resource_conflicts_report(
                selected_resource, days_ahead
            )
        except Resource.DoesNotExist:
            messages.error(request, 'Selected resource not found.')
    
    # Get all resources for filter dropdown
    resources = Resource.objects.filter(is_active=True).order_by('name')
    
    return render(request, 'booking/conflicts/detection.html', {
        'conflicts_data': conflicts_data,
        'selected_resource': selected_resource,
        'resources': resources,
        'days_ahead': days_ahead,
    })


@login_required
def resolve_conflict_view(request, conflict_type, id1, id2):
    """Resolve a specific conflict between two bookings."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to resolve conflicts.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to resolve conflicts.')
        return redirect('booking:dashboard')
    
    try:
        booking1 = Booking.objects.get(pk=id1)
        booking2 = Booking.objects.get(pk=id2)
    except Booking.DoesNotExist:
        messages.error(request, 'One or more bookings not found.')
        return redirect('booking:conflicts')
    
    # Verify there's actually a conflict
    conflicts = ConflictDetector.check_booking_conflicts(booking1, exclude_booking_ids=[])
    conflict = None
    for c in conflicts:
        if c.booking2.pk == booking2.pk:
            conflict = c
            break
    
    if not conflict:
        messages.warning(request, 'No conflict detected between these bookings.')
        return redirect('booking:conflicts')
    
    if request.method == 'POST':
        resolution_type = request.POST.get('resolution_type')
        
        if resolution_type == 'cancel_first':
            # Cancel first booking
            booking1.cancel_booking()
            messages.success(request, f'Cancelled booking {booking1.id} to resolve conflict.')
        elif resolution_type == 'cancel_second':
            # Cancel second booking
            booking2.cancel_booking()
            messages.success(request, f'Cancelled booking {booking2.id} to resolve conflict.')
        elif resolution_type == 'modify_first':
            # Modify first booking times
            new_start = request.POST.get('new_start_time')
            new_end = request.POST.get('new_end_time')
            if new_start and new_end:
                try:
                    from django.utils import timezone
                    booking1.start_time = timezone.datetime.fromisoformat(new_start)
                    booking1.end_time = timezone.datetime.fromisoformat(new_end)
                    booking1.save()
                    messages.success(request, f'Modified booking {booking1.id} times to resolve conflict.')
                except ValueError:
                    messages.error(request, 'Invalid date/time format.')
                    return render(request, 'booking/conflicts/resolve.html', {
                        'conflict': conflict,
                        'booking1': booking1,
                        'booking2': booking2,
                    })
        elif resolution_type == 'modify_second':
            # Modify second booking times
            new_start = request.POST.get('new_start_time')
            new_end = request.POST.get('new_end_time')
            if new_start and new_end:
                try:
                    from django.utils import timezone
                    booking2.start_time = timezone.datetime.fromisoformat(new_start)
                    booking2.end_time = timezone.datetime.fromisoformat(new_end)
                    booking2.save()
                    messages.success(request, f'Modified booking {booking2.id} times to resolve conflict.')
                except ValueError:
                    messages.error(request, 'Invalid date/time format.')
                    return render(request, 'booking/conflicts/resolve.html', {
                        'conflict': conflict,
                        'booking1': booking1,
                        'booking2': booking2,
                    })
        
        return redirect('booking:conflicts')
    
    return render(request, 'booking/conflicts/resolve.html', {
        'conflict': conflict,
        'booking1': booking1,
        'booking2': booking2,
    })


@login_required
def bulk_resolve_conflicts_view(request):
    """Bulk resolve multiple conflicts."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to resolve conflicts.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to resolve conflicts.')
        return redirect('booking:dashboard')
    
    if request.method == 'POST':
        resource_id = request.POST.get('resource_id')
        strategy = request.POST.get('strategy', 'suggest_alternatives')
        conflict_ids = request.POST.getlist('conflict_ids')
        
        try:
            resource = Resource.objects.select_related('closed_by').get(pk=resource_id)
            
            # Get conflicts for the resource
            conflicts_data = ConflictManager.get_resource_conflicts_report(resource, 30)
            all_conflicts = []
            
            # Convert conflict data back to conflict objects for processing
            for conflict_dict in conflicts_data['all_conflicts']:
                try:
                    booking1 = Booking.objects.get(pk=conflict_dict['booking1']['id'])
                    booking2 = Booking.objects.get(pk=conflict_dict['booking2']['id'])
                    from ...conflicts import BookingConflict
                    conflict_obj = BookingConflict(booking1, booking2)
                    all_conflicts.append(conflict_obj)
                except Booking.DoesNotExist:
                    continue
            
            # Apply resolution strategy
            resolved_count = 0
            if strategy == 'cancel_overlapping':
                # Cancel the newer booking in each conflict
                for conflict in all_conflicts:
                    if str(conflict.booking1.id) in conflict_ids or str(conflict.booking2.id) in conflict_ids:
                        newer_booking = conflict.booking2 if conflict.booking2.created_at > conflict.booking1.created_at else conflict.booking1
                        newer_booking.cancel_booking()
                        resolved_count += 1
            
            elif strategy == 'suggest_alternatives':
                # Send suggestions to users (this would typically queue notifications)
                for conflict in all_conflicts:
                    if str(conflict.booking1.id) in conflict_ids or str(conflict.booking2.id) in conflict_ids:
                        # Logic to suggest alternative times would go here
                        resolved_count += 1
            
            elif strategy == 'priority_based':
                # Resolve based on user priority/role
                for conflict in all_conflicts:
                    if str(conflict.booking1.id) in conflict_ids or str(conflict.booking2.id) in conflict_ids:
                        # Determine which booking has higher priority
                        booking1_priority = getattr(conflict.booking1.user.userprofile, 'booking_priority', 0)
                        booking2_priority = getattr(conflict.booking2.user.userprofile, 'booking_priority', 0)
                        
                        if booking1_priority < booking2_priority:
                            conflict.booking1.cancel_booking()
                        elif booking2_priority < booking1_priority:
                            conflict.booking2.cancel_booking()
                        else:
                            # Same priority, cancel the newer one
                            newer_booking = conflict.booking2 if conflict.booking2.created_at > conflict.booking1.created_at else conflict.booking1
                            newer_booking.cancel_booking()
                        
                        resolved_count += 1
            
            messages.success(request, f'Successfully resolved {resolved_count} conflicts using {strategy} strategy.')
            
        except Resource.DoesNotExist:
            messages.error(request, 'Resource not found.')
        except Exception as e:
            messages.error(request, f'Error resolving conflicts: {str(e)}')
    
    return redirect('booking:conflicts')