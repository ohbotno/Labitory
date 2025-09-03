# booking/views/modules/bookings.py
"""
Booking-related views for the Aperture Booking system.

This file is part of the Aperture Booking.
Copyright (C) 2025 Aperture Booking Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperture-booking.org/commercial
"""

import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime, timedelta

from ...models import Booking, BookingTemplate, UserProfile
from ...forms import (
    BookingForm, RecurringBookingForm, BookingTemplateForm, 
    CreateBookingFromTemplateForm, SaveAsTemplateForm
)
from ...recurring import RecurringBookingGenerator


@login_required
def create_booking_view(request):
    """Create a new booking."""
    conflicts_detected = False
    conflicting_bookings = []
    
    if request.method == 'POST':
        form = BookingForm(request.POST, user=request.user)
        
        # Check if this is a conflict override attempt
        override_conflicts = request.POST.get('override_conflicts') == 'true'
        
        # Debug logging
        logger = logging.getLogger('booking')
        logger.debug(f"Create booking POST data: {request.POST}")
        logger.debug(f"User: {request.user}, is_superuser: {request.user.is_superuser}, is_staff: {request.user.is_staff}")
        logger.debug(f"Override conflicts: {override_conflicts}")
        
        if form.is_valid():
            try:
                booking = form.save(commit=False)
                booking.user = request.user
                
                # Handle conflict override if requested
                if override_conflicts and form.cleaned_data.get('override_conflicts'):
                    override_message = form.cleaned_data.get('override_message', '')
                    conflicts = form.get_conflicts()
                    
                    # Process each conflicting booking
                    from booking.notifications import BookingNotifications
                    notification_service = BookingNotifications()
                    
                    for conflicting_booking in conflicts:
                        notification_service.booking_overridden(
                            conflicting_booking, 
                            booking, 
                            override_message
                        )
                
                booking.save()
                messages.success(request, f'Booking "{booking.title}" created successfully.')
                return redirect('booking:booking_detail', pk=booking.pk)
                
            except Exception as e:
                messages.error(request, f'Error creating booking: {str(e)}')
        else:
            # Check if form validation failed due to conflicts
            if hasattr(form, '_conflicts'):
                conflicts_detected = True
                conflicting_bookings = form._conflicts
            
            # Add error messages (excluding conflict messages for privileged users)
            for field, errors in form.errors.items():
                for error in errors:
                    # Skip conflict error messages for privileged users as we handle them specially
                    if not (conflicts_detected and form._can_override_conflicts() and 'conflict detected' in error.lower()):
                        messages.error(request, f'{field.replace("_", " ").title()}: {error}')
    else:
        form = BookingForm(user=request.user)
    
    context = {
        'form': form,
        'conflicts_detected': conflicts_detected,
        'conflicting_bookings': conflicting_bookings,
        'can_override': hasattr(form, '_can_override_conflicts') and form._can_override_conflicts(),
    }
    
    return render(request, 'booking/create_booking.html', context)


@login_required
def booking_detail_view(request, pk):
    """View booking details."""
    booking = get_object_or_404(Booking, pk=pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        if (booking.user != request.user and 
            user_profile.role not in ['technician', 'sysadmin'] and
            not booking.shared_with_group):
            messages.error(request, 'You do not have permission to view this booking.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        if booking.user != request.user:
            messages.error(request, 'You do not have permission to view this booking.')
            return redirect('booking:dashboard')
    
    # Handle POST requests (e.g., cancellation)
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'cancel':
            # Check if user can cancel this booking
            if (booking.user == request.user or 
                (hasattr(request.user, 'userprofile') and 
                 request.user.userprofile.role in ['technician', 'sysadmin'])):
                
                if booking.can_be_cancelled:
                    booking.status = 'cancelled'
                    booking.save()
                    messages.success(request, 'Booking cancelled successfully.')
                else:
                    messages.error(request, 'This booking cannot be cancelled.')
            else:
                messages.error(request, 'You do not have permission to cancel this booking.')
    
    return render(request, 'booking/booking_detail.html', {'booking': booking})


@login_required
def my_bookings_view(request):
    """View current user's bookings."""
    bookings = Booking.objects.filter(user=request.user).order_by('-start_time')
    
    # Filter by status if provided
    status_filter = request.GET.get('status')
    if status_filter and status_filter != 'all':
        bookings = bookings.filter(status=status_filter)
    
    # Pagination
    paginator = Paginator(bookings, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'booking_statuses': ['pending', 'approved', 'in_progress', 'completed', 'cancelled'],
    }
    
    return render(request, 'booking/my_bookings.html', context)


@login_required
def edit_booking_view(request, pk):
    """Edit an existing booking."""
    booking = get_object_or_404(Booking, pk=pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        if (booking.user != request.user and 
            user_profile.role not in ['technician', 'sysadmin']):
            messages.error(request, 'You do not have permission to edit this booking.')
            return redirect('booking:booking_detail', pk=booking.pk)
    except UserProfile.DoesNotExist:
        if booking.user != request.user:
            messages.error(request, 'You do not have permission to edit this booking.')
            return redirect('booking:booking_detail', pk=booking.pk)
    
    # Check if booking can be edited
    if not booking.can_be_modified:
        messages.error(request, 'This booking cannot be modified.')
        return redirect('booking:booking_detail', pk=booking.pk)
    
    if request.method == 'POST':
        form = BookingForm(request.POST, instance=booking, user=request.user)
        if form.is_valid():
            booking = form.save()
            messages.success(request, f'Booking "{booking.title}" updated successfully.')
            return redirect('booking:booking_detail', pk=booking.pk)
    else:
        form = BookingForm(instance=booking, user=request.user)
    
    return render(request, 'booking/edit_booking.html', {
        'form': form,
        'booking': booking,
    })


@login_required
def cancel_booking_view(request, pk):
    """Cancel a booking."""
    booking = get_object_or_404(Booking, pk=pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        if (booking.user != request.user and 
            user_profile.role not in ['technician', 'sysadmin']):
            messages.error(request, 'You do not have permission to cancel this booking.')
            return redirect('booking:booking_detail', pk=booking.pk)
    except UserProfile.DoesNotExist:
        if booking.user != request.user:
            messages.error(request, 'You do not have permission to cancel this booking.')
            return redirect('booking:booking_detail', pk=booking.pk)
    
    if request.method == 'POST':
        if booking.can_be_cancelled:
            cancellation_reason = request.POST.get('cancellation_reason', '')
            booking.status = 'cancelled'
            if cancellation_reason:
                booking.notes = f"{booking.notes}\n\nCancellation reason: {cancellation_reason}".strip()
            booking.save()
            
            messages.success(request, 'Booking cancelled successfully.')
            return redirect('booking:my_bookings')
        else:
            messages.error(request, 'This booking cannot be cancelled.')
    
    return render(request, 'booking/cancel_booking.html', {'booking': booking})


@login_required
def duplicate_booking_view(request, pk):
    """Duplicate an existing booking."""
    original_booking = get_object_or_404(Booking, pk=pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        if (original_booking.user != request.user and 
            user_profile.role not in ['technician', 'sysadmin']):
            messages.error(request, 'You do not have permission to duplicate this booking.')
            return redirect('booking:booking_detail', pk=original_booking.pk)
    except UserProfile.DoesNotExist:
        if original_booking.user != request.user:
            messages.error(request, 'You do not have permission to duplicate this booking.')
            return redirect('booking:booking_detail', pk=original_booking.pk)
    
    if request.method == 'POST':
        form = BookingForm(request.POST, user=request.user)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.user = request.user
            booking.save()
            
            messages.success(request, f'Booking "{booking.title}" duplicated successfully.')
            return redirect('booking:booking_detail', pk=booking.pk)
    else:
        # Pre-populate form with original booking data
        initial_data = {
            'resource': original_booking.resource,
            'title': f"Copy of {original_booking.title}",
            'description': original_booking.description,
            'purpose': original_booking.purpose,
            'shared_with_group': original_booking.shared_with_group,
        }
        form = BookingForm(initial=initial_data, user=request.user)
    
    return render(request, 'booking/duplicate_booking.html', {
        'form': form,
        'original_booking': original_booking,
    })


# Template-related views
@login_required
def template_list_view(request):
    """List user's booking templates."""
    templates = BookingTemplate.objects.filter(user=request.user).order_by('-created_at')
    
    paginator = Paginator(templates, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'booking/template_list.html', {'page_obj': page_obj})


@login_required
def template_create_view(request):
    """Create a new booking template."""
    if request.method == 'POST':
        form = BookingTemplateForm(request.POST, user=request.user)
        if form.is_valid():
            template = form.save(commit=False)
            template.user = request.user
            template.save()
            messages.success(request, f'Template "{template.name}" created successfully.')
            return redirect('booking:template_list')
    else:
        form = BookingTemplateForm(user=request.user)
    
    return render(request, 'booking/template_create.html', {'form': form})


@login_required
def create_booking_from_template_view(request):
    """Create a booking from a template."""
    if request.method == 'POST':
        form = CreateBookingFromTemplateForm(request.POST, user=request.user)
        if form.is_valid():
            booking = form.save()
            messages.success(request, f'Booking "{booking.title}" created from template.')
            return redirect('booking:booking_detail', pk=booking.pk)
    else:
        form = CreateBookingFromTemplateForm(user=request.user)
    
    return render(request, 'booking/create_from_template.html', {'form': form})


@login_required
def save_booking_as_template_view(request, booking_pk):
    """Save a booking as a template."""
    booking = get_object_or_404(Booking, pk=booking_pk, user=request.user)
    
    if request.method == 'POST':
        form = SaveAsTemplateForm(request.POST)
        if form.is_valid():
            template = BookingTemplate.objects.create(
                user=request.user,
                name=form.cleaned_data['template_name'],
                resource=booking.resource,
                title=booking.title,
                description=booking.description,
                purpose=booking.purpose,
                estimated_duration=booking.estimated_duration,
                shared_with_group=booking.shared_with_group,
            )
            messages.success(request, f'Booking saved as template "{template.name}".')
            return redirect('booking:template_list')
    else:
        form = SaveAsTemplateForm(initial={'template_name': f"{booking.title} Template"})
    
    return render(request, 'booking/save_as_template.html', {
        'form': form,
        'booking': booking,
    })