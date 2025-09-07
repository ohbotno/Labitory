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
from django.db.models import Q
from django.core.cache import cache
from datetime import datetime, timedelta

from ...models import Booking, BookingTemplate, UserProfile, Resource
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
    """User's own bookings with bulk operations."""
    # Get filter parameters
    status_filter = request.GET.get('status', '')
    resource_filter = request.GET.get('resource', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Base queryset - user's own bookings
    bookings = Booking.objects.filter(user=request.user).select_related('resource', 'approved_by').order_by('-created_at')
    
    # Apply filters
    if status_filter:
        bookings = bookings.filter(status=status_filter)
    
    if resource_filter:
        bookings = bookings.filter(resource_id=resource_filter)
    
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            bookings = bookings.filter(start_time__date__gte=from_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            bookings = bookings.filter(start_time__date__lte=to_date)
        except ValueError:
            pass
    
    # Pagination
    paginator = Paginator(bookings, 20)  # Show 20 bookings per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get resources for filter dropdown (only ones user has access to) - with caching
    cache_key = f"user_resources_{request.user.id}_{getattr(request.user, 'userprofile', None) and request.user.userprofile.id}"
    resources = cache.get(cache_key)
    
    if resources is None:
        try:
            user_profile = request.user.userprofile
            if user_profile.role == 'sysadmin':
                resources = list(Resource.objects.filter(is_active=True).order_by('name'))
            else:
                # Database-level filtering based on user access rules
                resources_queryset = Resource.objects.filter(
                    is_active=True,
                    required_training_level__lte=user_profile.training_level
                ).order_by('name')
                
                # Additional filtering for induction requirements
                if not user_profile.is_inducted:
                    resources_queryset = resources_queryset.filter(requires_induction=False)
                
                resources = list(resources_queryset)
        except:
            resources = list(Resource.objects.filter(is_active=True).order_by('name'))
        
        # Cache for 5 minutes
        cache.set(cache_key, resources, 300)
    
    context = {
        'page_obj': page_obj,
        'resources': resources,
        'status_filter': status_filter,
        'resource_filter': resource_filter,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': Booking.STATUS_CHOICES,
    }
    
    return render(request, 'booking/my_bookings.html', context)


@login_required
def edit_booking_view(request, pk):
    """Edit an existing booking."""
    booking = get_object_or_404(Booking, pk=pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        can_edit = (booking.user == request.user or 
                   user_profile.role in ['technician', 'sysadmin'])
    except UserProfile.DoesNotExist:
        can_edit = booking.user == request.user
    
    if not can_edit:
        messages.error(request, 'You do not have permission to edit this booking.')
        return redirect('booking:booking_detail', pk=pk)
    
    # Check if booking can be edited
    if booking.status not in ['pending', 'approved']:
        messages.error(request, 'Only pending or approved bookings can be edited.')
        return redirect('booking:booking_detail', pk=pk)
    
    # Don't allow editing past bookings
    if booking.start_time < timezone.now():
        messages.error(request, 'Cannot edit bookings that have already started.')
        return redirect('booking:booking_detail', pk=pk)
    
    if request.method == 'POST':
        form = BookingForm(request.POST, instance=booking, user=request.user)
        if form.is_valid():
            try:
                updated_booking = form.save(commit=False)
                
                # If the booking was approved and user made changes, set it back to pending
                if (booking.status == 'approved' and 
                    booking.user == request.user and 
                    hasattr(request.user, 'userprofile') and
                    user_profile.role not in ['technician', 'sysadmin']):
                    
                    # Check if any important fields changed
                    important_changes = (
                        updated_booking.resource != booking.resource or
                        updated_booking.start_time != booking.start_time or
                        updated_booking.end_time != booking.end_time
                    )
                    
                    if important_changes:
                        updated_booking.status = 'pending'
                        updated_booking.approved_by = None
                        updated_booking.approved_at = None
                        messages.info(request, 'Booking updated and set to pending approval due to time/resource changes.', extra_tags='persistent-alert')
                    else:
                        messages.success(request, 'Booking updated successfully.')
                else:
                    messages.success(request, 'Booking updated successfully.')
                
                updated_booking.save()
                return redirect('booking:booking_detail', pk=updated_booking.pk)
                
            except Exception as e:
                messages.error(request, f'Error updating booking: {str(e)}')
        else:
            # Add detailed error messages
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
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
    """Create a new booking based on an existing one."""
    original_booking = get_object_or_404(Booking, pk=pk)
    
    # Check if user has access to view the original booking
    try:
        user_profile = request.user.userprofile
        can_access = (
            original_booking.user == request.user or 
            user_profile.role in ['technician', 'sysadmin'] or
            (original_booking.shared_with_group and 
             hasattr(user_profile, 'group') and
             hasattr(original_booking.user, 'userprofile') and
             user_profile.group == original_booking.user.userprofile.group)
        )
    except UserProfile.DoesNotExist:
        can_access = original_booking.user == request.user
    
    if not can_access:
        messages.error(request, 'You do not have permission to duplicate this booking.')
        return redirect('booking:dashboard')
    
    if request.method == 'POST':
        form = BookingForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                new_booking = form.save(commit=False)
                new_booking.user = request.user
                new_booking.status = 'pending'
                new_booking.save()
                
                messages.success(request, f'Booking "{new_booking.title}" created successfully.')
                return redirect('booking:booking_detail', pk=new_booking.pk)
            except Exception as e:
                messages.error(request, f'Error creating booking: {str(e)}')
        else:
            # Add detailed error messages
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        # Pre-populate form with original booking data, but adjust times
        initial_data = {
            'resource': original_booking.resource,
            'title': f"Copy of {original_booking.title}",
            'description': original_booking.description,
            'shared_with_group': original_booking.shared_with_group,
            'notes': original_booking.notes,
        }
        
        # Set start time to tomorrow at the same time
        tomorrow = timezone.now() + timedelta(days=1)
        duration = original_booking.end_time - original_booking.start_time
        
        start_time = tomorrow.replace(
            hour=original_booking.start_time.hour,
            minute=original_booking.start_time.minute,
            second=0,
            microsecond=0
        )
        end_time = start_time + duration
        
        initial_data['start_time'] = start_time
        initial_data['end_time'] = end_time
        
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


@login_required
def template_edit_view(request, pk):
    """Edit a booking template."""
    template = get_object_or_404(BookingTemplate, pk=pk)
    
    # Check if user can edit this template
    if template.user != request.user:
        messages.error(request, 'You can only edit your own templates.')
        return redirect('booking:template_list')
    
    if request.method == 'POST':
        form = BookingTemplateForm(request.POST, instance=template, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f'Template "{template.name}" updated successfully.')
            return redirect('booking:template_list')
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
        return redirect('booking:template_list')
    
    if request.method == 'POST':
        template_name = template.name
        template.delete()
        messages.success(request, f'Template "{template_name}" deleted successfully.')
        return redirect('booking:template_list')
    
    return render(request, 'booking/template_confirm_delete.html', {
        'template': template,
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
    
    # Base queryset
    bookings = Booking.objects.select_related('resource', 'user', 'approved_by').order_by('-created_at')
    
    # Apply filters
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
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            bookings = bookings.filter(start_time__date__gte=from_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            bookings = bookings.filter(start_time__date__lte=to_date)
        except ValueError:
            pass
    
    # Pagination
    paginator = Paginator(bookings, 25)  # Show 25 bookings per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get resources for filter dropdown
    resources = Resource.objects.filter(is_active=True).order_by('name')
    
    context = {
        'page_obj': page_obj,
        'resources': resources,
        'status_filter': status_filter,
        'resource_filter': resource_filter,
        'user_filter': user_filter,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': Booking.STATUS_CHOICES,
    }
    
    return render(request, 'booking/booking_management.html', context)


@login_required
def delete_booking_view(request, pk):
    """Delete a booking permanently (only for cancelled/completed bookings)."""
    booking = get_object_or_404(Booking, pk=pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        can_delete = (booking.user == request.user or 
                     user_profile.role in ['technician', 'sysadmin'])
    except UserProfile.DoesNotExist:
        can_delete = booking.user == request.user
    
    if not can_delete:
        messages.error(request, 'You do not have permission to delete this booking.')
        return redirect('booking:booking_detail', pk=pk)
    
    # Only allow deletion of cancelled or completed bookings
    if booking.status not in ['cancelled', 'completed']:
        messages.error(request, 'Only cancelled or completed bookings can be deleted.')
        return redirect('booking:booking_detail', pk=pk)
    
    if request.method == 'POST':
        confirm = request.POST.get('confirm_delete')
        if confirm == 'yes':
            booking_title = booking.title
            booking.delete()
            messages.success(request, f'Booking "{booking_title}" has been permanently deleted.')
            
            # Redirect based on user role
            if hasattr(request.user, 'userprofile') and request.user.userprofile.role in ['technician', 'sysadmin']:
                return redirect('booking:booking_management')
            else:
                return redirect('booking:my_bookings')
        else:
            return redirect('booking:booking_detail', pk=pk)
    
    return render(request, 'booking/delete_booking.html', {
        'booking': booking,
    })


@login_required
def create_recurring_booking_view(request, booking_pk):
    """Create recurring bookings based on an existing booking."""
    from ...models import RecurringBookingManager
    from ...forms import RecurringBookingForm
    from ...recurring import RecurringBookingGenerator
    
    base_booking = get_object_or_404(Booking, pk=booking_pk, user=request.user)
    
    # Check if user can create recurring bookings
    try:
        user_profile = request.user.userprofile
        if not user_profile.can_create_recurring:
            messages.error(request, 'You do not have permission to create recurring bookings.')
            return redirect('booking:booking_detail', pk=booking_pk)
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to create recurring bookings.')
        return redirect('booking:booking_detail', pk=booking_pk)
    
    if request.method == 'POST':
        form = RecurringBookingForm(request.POST)
        if form.is_valid():
            try:
                pattern = form.create_pattern()
                generator = RecurringBookingGenerator(base_booking, pattern)
                
                skip_conflicts = form.cleaned_data.get('skip_conflicts', True)
                result = generator.create_recurring_bookings(skip_conflicts=skip_conflicts)
                
                # Update the base booking to mark it as recurring
                base_booking.is_recurring = True
                base_booking.recurring_pattern = pattern.to_dict()
                base_booking.save()
                
                success_msg = f"Created {result['total_created']} recurring bookings."
                if result['skipped_dates']:
                    success_msg += f" Skipped {len(result['skipped_dates'])} dates due to conflicts."
                
                messages.success(request, success_msg)
                return redirect('booking:booking_detail', pk=booking_pk)
                
            except Exception as e:
                messages.error(request, f'Error creating recurring bookings: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = RecurringBookingForm()
    
    return render(request, 'booking/create_recurring.html', {
        'form': form,
        'base_booking': base_booking,
    })


@login_required
def cancel_recurring_series_view(request, booking_pk):
    """Cancel an entire recurring series."""
    from ...models import RecurringBookingManager
    
    booking = get_object_or_404(Booking, pk=booking_pk)
    
    # Check permissions
    try:
        user_profile = request.user.userprofile
        if (booking.user != request.user and 
            user_profile.role not in ['technician', 'sysadmin']):
            messages.error(request, 'You do not have permission to cancel this booking series.')
            return redirect('booking:booking_detail', pk=booking_pk)
    except UserProfile.DoesNotExist:
        if booking.user != request.user:
            messages.error(request, 'You do not have permission to cancel this booking series.')
            return redirect('booking:booking_detail', pk=booking_pk)
    
    if not booking.is_recurring:
        messages.error(request, 'This is not a recurring booking.')
        return redirect('booking:booking_detail', pk=booking_pk)
    
    if request.method == 'POST':
        cancel_future_only = request.POST.get('cancel_future_only') == 'on'
        
        try:
            cancelled_count = RecurringBookingManager.cancel_recurring_series(
                booking, cancel_future_only=cancel_future_only
            )
            
            if cancel_future_only:
                messages.success(request, f'Cancelled {cancelled_count} future bookings in the series.')
            else:
                messages.success(request, f'Cancelled {cancelled_count} bookings in the entire series.')
                
            return redirect('booking:dashboard')
            
        except Exception as e:
            messages.error(request, f'Error cancelling recurring series: {str(e)}')
    
    # Get series info for confirmation
    series = RecurringBookingManager.get_recurring_series(booking)
    future_count = sum(1 for b in series if b.start_time > timezone.now() and b.can_be_cancelled)
    total_count = sum(1 for b in series if b.can_be_cancelled)
    
    return render(request, 'booking/cancel_recurring.html', {
        'booking': booking,
        'series': series,
        'future_count': future_count,
        'total_count': total_count,
    })