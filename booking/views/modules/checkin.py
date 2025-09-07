# booking/views/modules/checkin.py
"""
Check-in and check-out views for the Aperture Booking system.

This file is part of the Aperture Booking.
Copyright (C) 2025 Aperture Booking Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperture-booking.org/commercial
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta

from ...models import Booking, UserProfile, Resource
from ...services.checkin_service import checkin_service


@login_required
def checkin_view(request, booking_id):
    """Check in to a booking."""
    booking = get_object_or_404(Booking, id=booking_id)
    
    # Check if user can check in
    try:
        user_profile = request.user.userprofile
        can_checkin = (
            booking.user == request.user or
            booking.attendees.filter(id=request.user.id).exists() or
            user_profile.role in ['technician', 'sysadmin']
        )
    except UserProfile.DoesNotExist:
        can_checkin = booking.user == request.user
    
    if not can_checkin:
        messages.error(request, 'You do not have permission to check in to this booking.')
        return redirect('booking:booking_detail', pk=booking_id)
    
    if request.method == 'POST':
        notes = request.POST.get('notes', '')
        
        # Get client info for tracking
        ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        success, message = checkin_service.check_in_booking(
            booking_id=booking_id,
            user=request.user,
            notes=notes,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        
        return redirect('booking:booking_detail', pk=booking_id)
    
    return render(request, 'booking/checkin.html', {
        'booking': booking,
    })


@login_required
def checkout_view(request, booking_id):
    """Check out of a booking."""
    booking = get_object_or_404(Booking, id=booking_id)
    
    # Check if user can check out
    try:
        user_profile = request.user.userprofile
        can_checkout = (
            booking.user == request.user or
            booking.attendees.filter(id=request.user.id).exists() or
            user_profile.role in ['technician', 'sysadmin']
        )
    except UserProfile.DoesNotExist:
        can_checkout = booking.user == request.user
    
    if not can_checkout:
        messages.error(request, 'You do not have permission to check out of this booking.')
        return redirect('booking:booking_detail', pk=booking_id)
    
    if request.method == 'POST':
        notes = request.POST.get('notes', '')
        
        # Get client info for tracking
        ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        success, message = checkin_service.check_out_booking(
            booking_id=booking_id,
            user=request.user,
            notes=notes,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        
        return redirect('booking:booking_detail', pk=booking_id)
    
    return render(request, 'booking/checkout.html', {
        'booking': booking,
    })


@login_required
def checkin_status_view(request):
    """View current check-in status for user's bookings."""
    # Get user's bookings for today
    today = timezone.now().date()
    user_bookings = Booking.objects.filter(
        Q(user=request.user) | Q(attendees=request.user),
        start_time__date=today,
        status__in=['approved', 'confirmed']
    ).select_related('resource').distinct().order_by('start_time')
    
    # Get currently checked in bookings
    checked_in_bookings = Booking.objects.filter(
        Q(user=request.user) | Q(attendees=request.user),
        checked_in_at__isnull=False,
        checked_out_at__isnull=True
    ).select_related('resource').distinct()
    
    return render(request, 'booking/checkin_status.html', {
        'user_bookings': user_bookings,
        'checked_in_bookings': checked_in_bookings,
        'today': today,
    })


@login_required
def resource_checkin_status_view(request, resource_id):
    """View current check-in status for a specific resource (managers only)."""
    resource = get_object_or_404(Resource, id=resource_id)
    
    # Check if user has permission
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to view resource check-in status.')
            return redirect('booking:calendar')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to view resource check-in status.')
        return redirect('booking:calendar')
    
    # Get current check-ins for this resource
    current_checkins = checkin_service.get_current_checkins(resource)
    
    # Get today's bookings for this resource
    today = timezone.now().date()
    today_bookings = Booking.objects.filter(
        resource=resource,
        start_time__date=today,
        status__in=['approved', 'confirmed']
    ).select_related('user').order_by('start_time')
    
    # Get overdue check-ins and check-outs for this resource
    overdue_checkins = [b for b in checkin_service.get_overdue_checkins() if b.resource == resource]
    overdue_checkouts = [b for b in checkin_service.get_overdue_checkouts() if b.resource == resource]
    
    return render(request, 'booking/resource_checkin_status.html', {
        'resource': resource,
        'current_checkins': current_checkins,
        'today_bookings': today_bookings,
        'overdue_checkins': overdue_checkins,
        'overdue_checkouts': overdue_checkouts,
        'today': today,
    })


# API Views for Check-in/Check-out
@login_required
def api_checkin_booking(request, booking_id):
    """API endpoint for checking in to a booking."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    success, message = checkin_service.check_in_booking(
        booking_id=booking_id,
        user=request.user,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    
    if success:
        return JsonResponse({'success': True, 'message': message})
    else:
        return JsonResponse({'success': False, 'message': message}, status=400)


@login_required  
def api_checkout_booking(request, booking_id):
    """API endpoint for checking out of a booking."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    success, message = checkin_service.check_out_booking(
        booking_id=booking_id,
        user=request.user,
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    
    if success:
        return JsonResponse({'success': True, 'message': message})
    else:
        return JsonResponse({'success': False, 'message': message}, status=400)


@login_required
def usage_analytics_view(request):
    """View usage analytics (managers only)."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to view usage analytics.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to view usage analytics.')
        return redirect('booking:dashboard')
    
    # Get filter parameters
    resource_id = request.GET.get('resource')
    days = int(request.GET.get('days', 30))
    
    # Calculate date range
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)
    
    # Get analytics
    resource = None
    if resource_id:
        try:
            resource = Resource.objects.get(id=resource_id)
        except Resource.DoesNotExist:
            pass
    
    analytics = checkin_service.get_usage_analytics(
        resource=resource,
        start_date=start_date,
        end_date=end_date
    )
    
    # Get all resources for filter
    resources = Resource.objects.filter(is_active=True).order_by('name')
    
    return render(request, 'booking/usage_analytics.html', {
        'analytics': analytics,
        'resource': resource,
        'resources': resources,
        'days': days,
        'start_date': start_date,
        'end_date': end_date,
    })