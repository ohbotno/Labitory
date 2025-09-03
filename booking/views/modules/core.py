# booking/views/modules/core.py
"""
Core views for the Aperture Booking system (dashboard, profile, calendar, etc.).

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
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from datetime import datetime, timedelta
import json

from ...models import (
    AboutPage, UserProfile, Booking, Resource, Notification, 
    WaitingListEntry, Faculty, College, Department
)
from ...forms import UserProfileForm, AboutPageEditForm


@login_required
def dashboard_view(request):
    """Main dashboard view."""
    try:
        user_profile = request.user.userprofile
        
        # Get user's upcoming bookings
        upcoming_bookings = Booking.objects.filter(
            user=request.user,
            start_time__gt=timezone.now(),
            status__in=['pending', 'approved']
        ).order_by('start_time')[:5]
        
        # Get recent notifications
        recent_notifications = Notification.objects.filter(
            recipient=request.user
        ).order_by('-created_at')[:5]
        
        # Get available resources count
        available_resources_count = 0
        for resource in Resource.objects.filter(is_active=True):
            if resource.is_available_for_user(user_profile):
                available_resources_count += 1
        
        # Get waiting list entries
        waiting_list_entries = WaitingListEntry.objects.filter(
            user=request.user
        ).select_related('resource')[:5]
        
        context = {
            'upcoming_bookings': upcoming_bookings,
            'recent_notifications': recent_notifications,
            'available_resources_count': available_resources_count,
            'waiting_list_entries': waiting_list_entries,
            'user_profile': user_profile,
        }
        
    except UserProfile.DoesNotExist:
        messages.warning(request, 'Please complete your profile to access all features.')
        context = {
            'profile_incomplete': True,
        }
    
    return render(request, 'booking/dashboard.html', context)


@login_required
def profile_view(request):
    """User profile view and edit."""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        # Create a basic profile if it doesn't exist
        profile = UserProfile.objects.create(user=request.user)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('booking:profile')
    else:
        form = UserProfileForm(instance=profile)
    
    # Get user's booking statistics
    total_bookings = Booking.objects.filter(user=request.user).count()
    pending_bookings = Booking.objects.filter(
        user=request.user, 
        status='pending'
    ).count()
    completed_bookings = Booking.objects.filter(
        user=request.user, 
        status='completed'
    ).count()
    
    context = {
        'form': form,
        'profile': profile,
        'total_bookings': total_bookings,
        'pending_bookings': pending_bookings,
        'completed_bookings': completed_bookings,
    }
    
    return render(request, 'booking/profile.html', context)


@login_required
def calendar_view(request):
    """Calendar view showing bookings."""
    # Get user's bookings
    user_bookings = Booking.objects.filter(
        Q(user=request.user) | Q(attendees=request.user),
        status__in=['pending', 'approved', 'in_progress']
    ).distinct()
    
    # If user is a manager, show all bookings
    try:
        user_profile = request.user.userprofile
        if user_profile.role in ['technician', 'sysadmin']:
            all_bookings = Booking.objects.filter(
                status__in=['pending', 'approved', 'in_progress']
            )
        else:
            all_bookings = user_bookings
    except UserProfile.DoesNotExist:
        all_bookings = user_bookings
    
    # Prepare events data for calendar
    events = []
    for booking in all_bookings:
        event = {
            'id': booking.id,
            'title': booking.title,
            'start': booking.start_time.isoformat(),
            'end': booking.end_time.isoformat(),
            'url': f'/booking/{booking.id}/',
            'className': f'booking-{booking.status}',
            'extendedProps': {
                'resource': booking.resource.name,
                'user': booking.user.get_full_name(),
                'status': booking.status,
            }
        }
        events.append(event)
    
    context = {
        'events_json': json.dumps(events),
    }
    
    return render(request, 'booking/calendar.html', context)


def about_page_view(request):
    """Display the about page."""
    try:
        about_page = AboutPage.objects.get()
    except AboutPage.DoesNotExist:
        about_page = None
    
    return render(request, 'booking/about.html', {'about_page': about_page})


@login_required
def about_page_edit_view(request):
    """Edit the about page (admin only)."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to edit the about page.')
            return redirect('booking:about')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to edit the about page.')
        return redirect('booking:about')
    
    try:
        about_page = AboutPage.objects.get()
    except AboutPage.DoesNotExist:
        about_page = AboutPage()
    
    if request.method == 'POST':
        form = AboutPageEditForm(request.POST, instance=about_page)
        if form.is_valid():
            form.save()
            messages.success(request, 'About page updated successfully.')
            return redirect('booking:about')
    else:
        form = AboutPageEditForm(instance=about_page)
    
    return render(request, 'booking/about_edit.html', {'form': form})


# AJAX views for dynamic form loading
def ajax_load_colleges(request):
    """Load colleges based on selected faculty."""
    faculty_id = request.GET.get('faculty')
    colleges = College.objects.filter(faculty_id=faculty_id).order_by('name')
    return render(request, 'booking/ajax/college_dropdown_list_options.html', {'colleges': colleges})


def ajax_load_departments(request):
    """Load departments based on selected college."""
    college_id = request.GET.get('college')
    departments = Department.objects.filter(college_id=college_id).order_by('name')
    return render(request, 'booking/ajax/department_dropdown_list_options.html', {'departments': departments})