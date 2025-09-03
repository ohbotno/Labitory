# booking/views/modules/calendar.py
"""
Calendar and synchronization views for the Aperture Booking system.

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
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q

from ...models import Resource


logger = logging.getLogger(__name__)


@login_required
def export_my_calendar_view(request):
    """Export user's bookings as ICS file for download."""
    from booking.calendar_sync import ICSCalendarGenerator, create_ics_response
    
    # Get parameters
    include_past = request.GET.get('include_past', 'false').lower() == 'true'
    days_ahead = int(request.GET.get('days_ahead', '90'))
    
    # Generate ICS
    generator = ICSCalendarGenerator(request)
    ics_content = generator.generate_user_calendar(
        user=request.user,
        include_past=include_past,
        days_ahead=days_ahead
    )
    
    # Create filename
    user_name = request.user.get_full_name() or request.user.username
    filename = f"my-bookings-{user_name.replace(' ', '-').lower()}.ics"
    
    return create_ics_response(ics_content, filename)


@login_required
def my_calendar_feed_view(request, token):
    """Provide ICS calendar feed for subscription (with token authentication)."""
    from booking.calendar_sync import ICSCalendarGenerator, CalendarTokenGenerator, create_ics_feed_response
    
    # Verify token
    if not CalendarTokenGenerator.verify_user_token(request.user, token):
        return HttpResponse("Invalid token", status=403)
    
    # Get parameters
    include_past = request.GET.get('include_past', 'false').lower() == 'true'
    days_ahead = int(request.GET.get('days_ahead', '90'))
    
    # Generate ICS
    generator = ICSCalendarGenerator(request)
    ics_content = generator.generate_user_calendar(
        user=request.user,
        include_past=include_past,
        days_ahead=days_ahead
    )
    
    return create_ics_feed_response(ics_content)


def public_calendar_feed_view(request, token):
    """Provide public ICS calendar feed for subscription (token-based, no login required)."""
    from booking.calendar_sync import ICSCalendarGenerator, CalendarTokenGenerator, create_ics_feed_response
    from django.contrib.auth.models import User
    
    # Find user by token - optimized to avoid N+1 query
    user = None
    # Get all active users in a single query with minimal fields
    users = User.objects.filter(is_active=True).only('id', 'username', 'date_joined')
    for u in users:
        if CalendarTokenGenerator.verify_user_token(u, token):
            user = u
            break
    
    if not user:
        return HttpResponse("Invalid token", status=403)
    
    # Get parameters
    include_past = request.GET.get('include_past', 'false').lower() == 'true'
    days_ahead = int(request.GET.get('days_ahead', '90'))
    
    # Generate ICS
    generator = ICSCalendarGenerator(request)
    ics_content = generator.generate_user_calendar(
        user=user,
        include_past=include_past,
        days_ahead=days_ahead
    )
    
    return create_ics_feed_response(ics_content)


@login_required
def export_resource_calendar_view(request, resource_id):
    """Export resource bookings as ICS file for download."""
    from booking.calendar_sync import ICSCalendarGenerator, create_ics_response
    
    resource = get_object_or_404(Resource, id=resource_id)
    
    # Check permissions - only allow if user has access to the resource or is admin
    if not (request.user.userprofile.role in ['technician', 'sysadmin'] or 
            resource.resourceaccess_set.filter(user=request.user, is_active=True).exists()):
        messages.error(request, "You don't have permission to export this resource's calendar.")
        return redirect('booking:resource_detail', resource_id=resource_id)
    
    # Get parameters
    days_ahead = int(request.GET.get('days_ahead', '90'))
    
    # Generate ICS
    generator = ICSCalendarGenerator(request)
    ics_content = generator.generate_resource_calendar(
        resource=resource,
        days_ahead=days_ahead
    )
    
    # Create filename
    filename = f"{resource.name.replace(' ', '-').lower()}-calendar.ics"
    
    return create_ics_response(ics_content, filename)


@login_required
def calendar_sync_settings_view(request):
    """Display calendar synchronization settings and subscription URLs."""
    from booking.calendar_sync import CalendarTokenGenerator
    
    # Generate user's calendar token
    user_token = CalendarTokenGenerator.generate_user_token(request.user)
    
    # Build subscription URLs
    feed_url = request.build_absolute_uri(
        reverse('booking:public_calendar_feed', kwargs={'token': user_token})
    )
    
    export_url = request.build_absolute_uri(
        reverse('booking:export_my_calendar')
    )
    
    # Get user's resources for resource calendar export
    user_resources = Resource.objects.filter(
        Q(responsible_persons__user=request.user) |
        Q(resourceaccess__user=request.user, resourceaccess__is_active=True)
    ).distinct().order_by('name')
    
    context = {
        'user_token': user_token,
        'feed_url': feed_url,
        'export_url': export_url,
        'user_resources': user_resources,
    }
    
    return render(request, 'booking/calendar_sync_settings.html', context)


@login_required
def google_calendar_auth_view(request):
    """Initiate Google Calendar OAuth flow."""
    try:
        from ..services.google_calendar import google_calendar_service
        
        if not google_calendar_service:
            messages.error(request, 'Google Calendar integration is not available. Please contact administrator.')
            return redirect('booking:calendar_sync_settings')
        
        # Get authorization URL
        auth_url = google_calendar_service.get_authorization_url(request)
        return redirect(auth_url)
        
    except Exception as e:
        logger.error(f"Error initiating Google Calendar auth for user {request.user.username}: {e}")
        messages.error(request, f'Error connecting to Google Calendar: {e}')
        return redirect('booking:calendar_sync_settings')


@login_required
def google_calendar_callback_view(request):
    """Handle Google Calendar OAuth callback."""
    try:
        from ..services.google_calendar import google_calendar_service
        from ..models import GoogleCalendarIntegration
        
        if not google_calendar_service:
            messages.error(request, 'Google Calendar integration is not available.')
            return redirect('booking:calendar_sync_settings')
        
        # Check for authorization code
        authorization_code = request.GET.get('code')
        if not authorization_code:
            error = request.GET.get('error', 'No authorization code received')
            messages.error(request, f'Google Calendar authorization failed: {error}')
            return redirect('booking:calendar_sync_settings')
        
        # Handle the callback
        integration = google_calendar_service.handle_oauth_callback(request, authorization_code)
        
        messages.success(
            request, 
            'Google Calendar has been connected successfully! Your bookings will now sync automatically.'
        )
        
        return redirect('booking:calendar_sync_settings')
        
    except Exception as e:
        logger.error(f"Error handling Google Calendar callback for user {request.user.username}: {e}")
        messages.error(request, f'Error connecting Google Calendar: {e}')
        return redirect('booking:calendar_sync_settings')


@login_required
def google_calendar_settings_view(request):
    """Manage Google Calendar integration settings."""
    from ..models import GoogleCalendarIntegration, CalendarSyncPreferences
    from ..forms import CalendarSyncPreferencesForm
    
    try:
        integration = GoogleCalendarIntegration.objects.get(user=request.user)
    except GoogleCalendarIntegration.DoesNotExist:
        integration = None
    
    try:
        preferences = CalendarSyncPreferences.objects.get(user=request.user)
    except CalendarSyncPreferences.DoesNotExist:
        preferences = CalendarSyncPreferences.objects.create(user=request.user)
    
    if request.method == 'POST':
        form = CalendarSyncPreferencesForm(request.POST, instance=preferences)
        if form.is_valid():
            form.save()
            messages.success(request, 'Calendar sync preferences updated successfully.')
            return redirect('booking:google_calendar_settings')
    else:
        form = CalendarSyncPreferencesForm(instance=preferences)
    
    context = {
        'integration': integration,
        'preferences': preferences,
        'form': form,
    }
    
    return render(request, 'booking/google_calendar_settings.html', context)


@login_required
def google_calendar_sync_view(request):
    """Manually trigger Google Calendar sync."""
    from ..services.google_calendar import google_calendar_service
    from ..models import GoogleCalendarIntegration
    
    try:
        integration = GoogleCalendarIntegration.objects.get(user=request.user)
        
        if not integration.can_sync():
            messages.error(request, 'Google Calendar sync is not available. Please check your connection.')
            return redirect('booking:calendar_sync_settings')
        
        # Get user's future bookings
        from ..models import Booking
        bookings = Booking.objects.filter(
            user=request.user,
            start_time__gte=timezone.now(),
            status__in=['confirmed', 'pending']
        ).order_by('start_time')
        
        sync_count = 0
        error_count = 0
        
        for booking in bookings:
            # Check if booking already has a Google event
            existing_log = booking.googlecalendarsynclog_set.filter(
                user=request.user,
                action='created',
                status='success'
            ).first()
            
            if existing_log:
                # Update existing event
                success = google_calendar_service.update_calendar_event(
                    integration, booking, existing_log.google_event_id
                )
            else:
                # Create new event
                event_id = google_calendar_service.create_calendar_event(integration, booking)
                success = event_id is not None
            
            if success:
                sync_count += 1
            else:
                error_count += 1
        
        # Update last sync time
        integration.last_sync = timezone.now()
        integration.save()
        
        if error_count == 0:
            messages.success(request, f'Successfully synced {sync_count} bookings to Google Calendar.')
        else:
            messages.warning(
                request, 
                f'Synced {sync_count} bookings successfully, but {error_count} failed. Check sync logs for details.'
            )
        
    except GoogleCalendarIntegration.DoesNotExist:
        messages.error(request, 'Google Calendar is not connected. Please connect first.')
    except Exception as e:
        logger.error(f"Error syncing Google Calendar for user {request.user.username}: {e}")
        messages.error(request, f'Error syncing with Google Calendar: {e}')
    
    return redirect('booking:calendar_sync_settings')


@login_required
def google_calendar_disconnect_view(request):
    """Disconnect Google Calendar integration."""
    from ..services.google_calendar import google_calendar_service
    
    if request.method == 'POST':
        try:
            success = google_calendar_service.disconnect_integration(request.user)
            
            if success:
                messages.success(request, 'Google Calendar has been disconnected successfully.')
            else:
                messages.warning(request, 'Google Calendar was not connected.')
                
        except Exception as e:
            logger.error(f"Error disconnecting Google Calendar for user {request.user.username}: {e}")
            messages.error(request, f'Error disconnecting Google Calendar: {e}')
    
    return redirect('booking:calendar_sync_settings')