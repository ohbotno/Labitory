# booking/views/modules/templates.py
"""
Booking template management views for the Labitory.

This module handles booking templates, bulk operations, and template-related functionality.

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
from django.utils import timezone
from django.db.models import Q

from ...models import (
    BookingTemplate, Booking, UserProfile, Resource
)
from ...forms import (
    BookingTemplateForm, CreateBookingFromTemplateForm, SaveAsTemplateForm
)


@login_required
def template_edit_view(request, pk):
    """Edit a booking template."""
    template = get_object_or_404(BookingTemplate, pk=pk)
    
    # Check if user can edit this template
    if template.user != request.user:
        messages.error(request, 'You can only edit your own templates.')
        return redirect('booking:templates')
    
    if request.method == 'POST':
        form = BookingTemplateForm(request.POST, instance=template, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Template "{template.name}" updated successfully.')
            return redirect('booking:templates')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BookingTemplateForm(instance=template, user=request.user)
    
    return render(request, 'booking/template_form.html', {
        'form': form,
        'template': template,
        'title': 'Edit Template',
    })


@login_required
def template_delete_view(request, pk):
    """Delete a booking template."""
    template = get_object_or_404(BookingTemplate, pk=pk)
    
    # Check if user can delete this template
    if template.user != request.user:
        messages.error(request, 'You can only delete your own templates.')
        return redirect('booking:templates')
    
    if request.method == 'POST':
        template_name = template.name
        template.delete()
        messages.success(request, f'Template "{template_name}" deleted successfully.')
        return redirect('booking:templates')
    
    return render(request, 'booking/template_confirm_delete.html', {
        'template': template,
    })


@login_required
def create_booking_from_template_view(request):
    """Create a booking from a template."""
    if request.method == 'POST':
        form = CreateBookingFromTemplateForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                booking = form.create_booking()
                booking.save()
                messages.success(request, f'Booking "{booking.title}" created from template.')
                return redirect('booking:booking_detail', pk=booking.pk)
            except Exception as e:
                messages.error(request, f'Error creating booking: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CreateBookingFromTemplateForm(user=request.user)
    
    return render(request, 'booking/create_from_template.html', {
        'form': form,
    })


@login_required
def save_booking_as_template_view(request, booking_pk):
    """Save an existing booking as a template."""
    booking = get_object_or_404(Booking, pk=booking_pk)
    
    # Check if user owns the booking
    if booking.user != request.user:
        messages.error(request, 'You can only save your own bookings as templates.')
        return redirect('booking:booking_detail', pk=booking_pk)
    
    if request.method == 'POST':
        form = SaveAsTemplateForm(request.POST)
        if form.is_valid():
            try:
                template = booking.save_as_template(
                    template_name=form.cleaned_data['name'],
                    template_description=form.cleaned_data['description'],
                    is_public=form.cleaned_data['is_public']
                )
                messages.success(request, f'Booking saved as template "{template.name}".')
                return redirect('booking:templates')
            except Exception as e:
                messages.error(request, f'Error saving template: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # Pre-fill form with booking data
        initial_data = {
            'name': f"{booking.title} Template",
            'description': f"Template based on booking: {booking.title}",
        }
        form = SaveAsTemplateForm(initial=initial_data)
    
    return render(request, 'booking/save_as_template.html', {
        'form': form,
        'booking': booking,
    })


@login_required
def bulk_booking_operations_view(request):
    """Bulk operations on multiple bookings."""
    if request.method == 'POST':
        action = request.POST.get('action')
        booking_ids = request.POST.getlist('booking_ids')
        
        if not booking_ids:
            messages.error(request, 'No bookings selected.')
            return redirect('booking:dashboard')
        
        try:
            user_profile = request.user.userprofile
        except UserProfile.DoesNotExist:
            messages.error(request, 'User profile not found.')
            return redirect('booking:dashboard')
        
        # Get bookings that user has permission to modify
        if user_profile.role in ['technician', 'sysadmin']:
            bookings = Booking.objects.filter(pk__in=booking_ids)
        else:
            bookings = Booking.objects.filter(pk__in=booking_ids, user=request.user)
        
        if not bookings.exists():
            messages.error(request, 'No bookings found or you do not have permission to modify them.')
            return redirect('booking:dashboard')
        
        success_count = 0
        error_count = 0
        errors = []
        
        if action == 'cancel':
            for booking in bookings:
                if booking.can_be_cancelled:
                    booking.status = 'cancelled'
                    booking.save()
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f'{booking.title} - Cannot be cancelled')
            
            if success_count > 0:
                messages.success(request, f'Successfully cancelled {success_count} booking(s).')
            if error_count > 0:
                messages.warning(request, f'{error_count} booking(s) could not be cancelled: {", ".join(errors[:3])}')
        
        elif action == 'approve' and user_profile.role in ['technician', 'sysadmin']:
            for booking in bookings:
                if booking.status == 'pending':
                    booking.status = 'approved'
                    booking.approved_by = request.user
                    booking.approved_at = timezone.now()
                    booking.save()
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f'{booking.title} - Not pending')
            
            if success_count > 0:
                messages.success(request, f'Successfully approved {success_count} booking(s).')
            if error_count > 0:
                messages.warning(request, f'{error_count} booking(s) could not be approved: {", ".join(errors[:3])}')
        
        elif action == 'reject' and user_profile.role in ['technician', 'sysadmin']:
            for booking in bookings:
                if booking.status == 'pending':
                    booking.status = 'rejected'
                    booking.save()
                    success_count += 1
                else:
                    error_count += 1
                    errors.append(f'{booking.title} - Not pending')
            
            if success_count > 0:
                messages.success(request, f'Successfully rejected {success_count} booking(s).')
            if error_count > 0:
                messages.warning(request, f'{error_count} booking(s) could not be rejected: {", ".join(errors[:3])}')
        
        elif action == 'save_as_template' and user_profile.role in ['technician', 'sysadmin']:
            template_name = request.POST.get('template_name', 'Bulk Template')
            for booking in bookings:
                try:
                    template = booking.save_as_template(
                        template_name=f"{template_name} - {booking.title}",
                        template_description=f"Template created from booking {booking.title}",
                        is_public=False
                    )
                    success_count += 1
                except Exception as e:
                    error_count += 1
                    errors.append(f'{booking.title} - {str(e)}')
            
            if success_count > 0:
                messages.success(request, f'Successfully created {success_count} template(s).')
            if error_count > 0:
                messages.warning(request, f'{error_count} booking(s) could not be saved as templates: {", ".join(errors[:3])}')
        
        else:
            messages.error(request, 'Invalid action or insufficient permissions.')
    
    return redirect('booking:dashboard')


@login_required
def booking_management_view(request):
    """Management interface for bookings with bulk operations."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to access booking management.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to access booking management.')
        return redirect('booking:dashboard')
    
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    resource_filter = request.GET.get('resource', '')
    user_filter = request.GET.get('user', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Build query
    bookings = Booking.objects.select_related('user', 'resource').all()
    
    if status_filter:
        bookings = bookings.filter(status=status_filter)
    
    if resource_filter:
        bookings = bookings.filter(resource_id=resource_filter)
    
    if user_filter:
        bookings = bookings.filter(
            Q(user__username__icontains=user_filter) |
            Q(user__first_name__icontains=user_filter) |
            Q(user__last_name__icontains=user_filter)
        )
    
    if date_from:
        try:
            from django.utils import timezone
            from_date = timezone.datetime.fromisoformat(date_from)
            bookings = bookings.filter(start_time__gte=from_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            from django.utils import timezone
            to_date = timezone.datetime.fromisoformat(date_to)
            bookings = bookings.filter(end_time__lte=to_date)
        except ValueError:
            pass
    
    # Order by most recent first
    bookings = bookings.order_by('-created_at')
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(bookings, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get resources and status choices for filters
    resources = Resource.objects.filter(is_active=True).order_by('name')
    status_choices = Booking.STATUS_CHOICES
    
    return render(request, 'booking/management/bookings.html', {
        'page_obj': page_obj,
        'resources': resources,
        'status_choices': status_choices,
        'current_filters': {
            'status': status_filter,
            'resource': resource_filter,
            'user': user_filter,
            'date_from': date_from,
            'date_to': date_to,
        },
    })