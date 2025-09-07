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
        action = request.POST.get('action')
        
        if action == 'cancel_booking1':
            if booking1.can_be_cancelled:
                booking1.status = 'cancelled'
                booking1.save()
                messages.success(request, f'Cancelled booking: {booking1.title}')
            else:
                messages.error(request, f'Cannot cancel booking: {booking1.title}')
                
        elif action == 'cancel_booking2':
            if booking2.can_be_cancelled:
                booking2.status = 'cancelled'
                booking2.save()
                messages.success(request, f'Cancelled booking: {booking2.title}')
            else:
                messages.error(request, f'Cannot cancel booking: {booking2.title}')
                
        elif action == 'reschedule_booking1':
            new_start = request.POST.get('new_start_time')
            new_end = request.POST.get('new_end_time')
            if new_start and new_end:
                try:
                    from django.utils import timezone
                    booking1.start_time = timezone.datetime.fromisoformat(new_start.replace('T', ' '))
                    booking1.end_time = timezone.datetime.fromisoformat(new_end.replace('T', ' '))
                    booking1.save()
                    messages.success(request, f'Rescheduled booking: {booking1.title}')
                except Exception as e:
                    messages.error(request, f'Error rescheduling booking: {str(e)}')
            else:
                messages.error(request, 'Invalid time values provided.')
                
        elif action == 'reschedule_booking2':
            new_start = request.POST.get('new_start_time')
            new_end = request.POST.get('new_end_time')
            if new_start and new_end:
                try:
                    from django.utils import timezone
                    booking2.start_time = timezone.datetime.fromisoformat(new_start.replace('T', ' '))
                    booking2.end_time = timezone.datetime.fromisoformat(new_end.replace('T', ' '))
                    booking2.save()
                    messages.success(request, f'Rescheduled booking: {booking2.title}')
                except Exception as e:
                    messages.error(request, f'Error rescheduling booking: {str(e)}')
            else:
                messages.error(request, 'Invalid time values provided.')
        
        return redirect('booking:conflicts')
    
    # Generate suggestions for resolution
    try:
        user1_profile = booking1.user.userprofile
        user2_profile = booking2.user.userprofile
        
        suggestions1 = ConflictResolver.suggest_alternative_times(booking1, [conflict])
        suggestions2 = ConflictResolver.suggest_alternative_times(booking2, [conflict])
        
        alt_resources1 = ConflictResolver.suggest_alternative_resources(booking1, user1_profile)
        alt_resources2 = ConflictResolver.suggest_alternative_resources(booking2, user2_profile)
    except:
        suggestions1 = suggestions2 = []
        alt_resources1 = alt_resources2 = []
    
    return render(request, 'booking/resolve_conflict.html', {
        'conflict': conflict,
        'booking1': booking1,
        'booking2': booking2,
        'suggestions1': suggestions1,
        'suggestions2': suggestions2,
        'alt_resources1': alt_resources1,
        'alt_resources2': alt_resources2,
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
            
            # Filter to selected conflicts if specified
            if conflict_ids:
                selected_conflicts = []
                for conflict in all_conflicts:
                    conflict_id = f"{conflict.booking1.pk}_{conflict.booking2.pk}"
                    if conflict_id in conflict_ids:
                        selected_conflicts.append(conflict)
                all_conflicts = selected_conflicts
            
            # Bulk resolve
            if all_conflicts:
                resolution_results = ConflictManager.bulk_resolve_conflicts(
                    all_conflicts, strategy
                )
                
                messages.success(
                    request, 
                    f"Processed {len(all_conflicts)} conflicts. "
                    f"{resolution_results['summary']['auto_resolvable']} can be auto-resolved, "
                    f"{resolution_results['summary']['manual_review']} need manual review."
                )
            else:
                messages.warning(request, 'No conflicts selected for resolution.')
                
        except Resource.DoesNotExist:
            messages.error(request, 'Resource not found.')
        except Exception as e:
            messages.error(request, f'Error processing conflicts: {str(e)}')
    
    return redirect('booking:conflicts')