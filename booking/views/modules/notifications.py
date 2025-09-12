# booking/views/modules/notifications.py
"""
Notification-related views for the Labitory.

This module handles user notifications, notification preferences, and waiting list functionality.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from datetime import datetime, timedelta

from ...models import (
    Notification, NotificationPreference, WaitingListEntry, Resource,
    WaitingListNotification
)
from ...serializers import WaitingListEntrySerializer
from booking.notifications import notification_service
from booking.waiting_list import waiting_list_service


@login_required
def notifications_list(request):
    """Display user's notifications."""
    
    # Get user's notifications, ordered by most recent first
    # Only show in-app notifications to avoid duplicates from multiple delivery methods
    notifications = Notification.objects.filter(
        user=request.user, 
        delivery_method='in_app'
    ).order_by('-created_at')[:50]
    
    # Count unread notifications (not marked as read)
    # Only count in-app notifications to avoid duplicates
    unread_count = Notification.objects.filter(
        user=request.user, 
        delivery_method='in_app',
        read_at__isnull=True
    ).count()
    
    # Mark notifications as read when viewing the list
    # Only mark in-app notifications as read
    if request.method == 'GET':
        Notification.objects.filter(
            user=request.user,
            delivery_method='in_app',
            read_at__isnull=True
        ).update(read_at=timezone.now(), status='read')
    
    return render(request, 'booking/notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })


@login_required
def notification_preferences(request):
    """Display and update user's notification preferences."""
    if request.method == 'POST':
        # Update preferences
        for key, value in request.POST.items():
            if key.startswith('pref_'):
                # Parse preference key: pref_{notification_type}_{delivery_method}
                parts = key.replace('pref_', '').split('_')
                if len(parts) >= 2:
                    notification_type = '_'.join(parts[:-1])
                    delivery_method = parts[-1]
                    
                    preference, created = NotificationPreference.objects.get_or_create(
                        user=request.user,
                        notification_type=notification_type,
                        delivery_method=delivery_method,
                        defaults={'is_enabled': value == 'on'}
                    )
                    
                    if not created:
                        preference.is_enabled = value == 'on'
                        preference.save()
        
        messages.success(request, 'Notification preferences updated successfully.')
        return redirect('booking:notification_preferences')
    
    # Get current preferences
    preferences = {}
    user_prefs = NotificationPreference.objects.filter(user=request.user)
    
    for pref in user_prefs:
        key = f"{pref.notification_type}_{pref.delivery_method}"
        preferences[key] = pref.is_enabled
    
    # Available notification types and delivery methods
    notification_types = NotificationPreference.NOTIFICATION_TYPES
    delivery_methods = NotificationPreference.DELIVERY_METHODS
    
    return render(request, 'booking/notification_preferences.html', {
        'preferences': preferences,
        'notification_types': notification_types,
        'delivery_methods': delivery_methods,
    })


@login_required
def notification_preferences_view(request):
    """Notification preferences management view."""
    
    # Get all notification types
    notification_types = NotificationPreference.NOTIFICATION_TYPES
    delivery_methods = NotificationPreference.DELIVERY_METHODS
    frequency_choices = [
        ('immediate', 'Immediate'),
        ('daily_digest', 'Daily Digest'),
        ('weekly_digest', 'Weekly Digest'),
    ]
    
    if request.method == 'POST':
        # Process preference updates
        updated_count = 0
        
        for notification_type, _ in notification_types:
            for delivery_method, _ in delivery_methods:
                # Get form field names
                enabled_field = f"{notification_type}_{delivery_method}_enabled"
                frequency_field = f"{notification_type}_{delivery_method}_frequency"
                
                is_enabled = request.POST.get(enabled_field) == 'on'
                frequency = request.POST.get(frequency_field, 'immediate')
                
                # Update or create preference
                preference, created = NotificationPreference.objects.update_or_create(
                    user=request.user,
                    notification_type=notification_type,
                    delivery_method=delivery_method,
                    defaults={
                        'is_enabled': is_enabled,
                        'frequency': frequency
                    }
                )
                
                if created or preference.is_enabled != is_enabled:
                    updated_count += 1
        
        messages.success(request, f'Updated {updated_count} notification preferences.')
        return redirect('booking:notification_preferences')
    
    # Get current preferences
    current_preferences = {}
    user_prefs = NotificationPreference.objects.filter(user=request.user)
    
    for pref in user_prefs:
        key = f"{pref.notification_type}_{pref.delivery_method}"
        current_preferences[key] = {
            'enabled': pref.is_enabled,
            'frequency': getattr(pref, 'frequency', 'immediate')
        }
    
    return render(request, 'booking/notification_preferences_detailed.html', {
        'current_preferences': current_preferences,
        'notification_types': notification_types,
        'delivery_methods': delivery_methods,
        'frequency_choices': frequency_choices,
    })


@login_required
def waiting_list_view(request):
    """Display user's waiting list entries."""
    entries = waiting_list_service.get_user_waiting_list_entries(request.user)
    
    # Get pending notifications
    notifications = WaitingListNotification.objects.filter(
        waiting_list_entry__user=request.user,
        user_response='pending'
    ).select_related('waiting_list_entry__resource').order_by('-sent_at')
    
    return render(request, 'booking/waiting_list.html', {
        'waiting_list_entries': entries,
        'pending_notifications': notifications,
    })


@login_required
def join_waiting_list(request, resource_id):
    """Join waiting list for a resource."""
    resource = get_object_or_404(Resource, id=resource_id)
    
    # Check if user can access this resource
    try:
        user_profile = request.user.userprofile
        if not resource.is_available_for_user(user_profile):
            messages.error(request, f'You do not meet the requirements to book {resource.name}.', extra_tags='persistent-alert')
            return redirect('booking:calendar')
    except:
        messages.error(request, 'User profile not found.')
        return redirect('booking:calendar')
    
    if request.method == 'POST':
        try:
            # Get form data
            preferred_start = timezone.datetime.fromisoformat(request.POST['preferred_start_time'])
            preferred_end = timezone.datetime.fromisoformat(request.POST['preferred_end_time'])
            
            # Optional parameters
            options = {
                'min_duration_minutes': int(request.POST.get('min_duration_minutes', 60)),
                'max_duration_minutes': int(request.POST.get('max_duration_minutes', 240)),
                'flexible_start_time': request.POST.get('flexible_start_time') == 'on',
                'flexible_duration': request.POST.get('flexible_duration') == 'on',
                'auto_book': request.POST.get('auto_book') == 'on',
                'priority': request.POST.get('priority', 'normal'),
                'notes': request.POST.get('notes', ''),
            }
            
            # Add to waiting list
            entry = waiting_list_service.add_to_waiting_list(
                user=request.user,
                resource=resource,
                preferred_start=preferred_start,
                preferred_end=preferred_end,
                **options
            )
            
            messages.success(request, f'Successfully added to waiting list for {resource.name}!')
            return redirect('booking:waiting_list')
            
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Failed to join waiting list: {str(e)}')
    
    # Pre-fill with requested time if available
    requested_start = request.GET.get('start_time')
    requested_end = request.GET.get('end_time')
    
    return render(request, 'booking/join_waiting_list.html', {
        'resource': resource,
        'requested_start': requested_start,
        'requested_end': requested_end,
    })


@login_required
def leave_waiting_list(request, entry_id):
    """Leave waiting list."""
    success, message = waiting_list_service.cancel_waiting_list_entry(entry_id, request.user)
    
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)
    
    return redirect('booking:waiting_list')


@login_required
def respond_to_availability(request, notification_id):
    """Respond to availability notification."""
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'accept':
            success, message = waiting_list_service.accept_availability_offer(notification_id, request.user)
        elif action == 'decline':
            success, message = waiting_list_service.decline_availability_offer(notification_id, request.user)
        else:
            success, message = False, 'Invalid action.'
        
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
    
    return redirect('booking:waiting_list')


# API Views for notifications
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """API viewset for user notifications."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return notifications for the current user."""
        # Only return in-app notifications to avoid duplicates from multiple delivery methods
        return Notification.objects.filter(
            user=self.request.user, 
            delivery_method='in_app'
        ).order_by('-created_at')
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Mark a notification as read."""
        notification = self.get_object()
        notification.read_at = timezone.now()
        notification.status = 'read'
        notification.save()
        return Response({'status': 'success'})
    
    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        """Mark all notifications as read."""
        # Only mark in-app notifications as read
        marked_read = Notification.objects.filter(
            user=request.user,
            delivery_method='in_app',
            read_at__isnull=True
        ).update(read_at=timezone.now(), status='read')
        return Response({'status': 'success', 'marked_read': marked_read})


# API Views for Waiting List
class WaitingListEntryViewSet(viewsets.ModelViewSet):
    """API viewset for waiting list entries."""
    serializer_class = WaitingListEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get waiting list entries based on user permissions."""
        if hasattr(self.request.user, 'userprofile') and self.request.user.userprofile.role in ['technician', 'sysadmin']:
            return WaitingListEntry.objects.all().select_related('user', 'resource', 'resulting_booking')
        else:
            return WaitingListEntry.objects.filter(user=self.request.user).select_related('resource', 'resulting_booking')
    
    def perform_create(self, serializer):
        """Create waiting list entry for current user."""
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel waiting list entry."""
        entry = self.get_object()
        
        if entry.user != request.user and request.user.userprofile.role not in ['technician', 'sysadmin']:
            return Response({'error': 'Permission denied'}, status=403)
        
        if entry.status not in ['waiting', 'notified']:
            return Response({'error': 'Cannot cancel entry in current status'}, status=400)
        
        entry.cancel_waiting()
        return Response({'status': 'success', 'message': 'Waiting list entry cancelled'})
    
    @action(detail=False, methods=['get'])
    def my_entries(self, request):
        """Get current user's waiting list entries."""
        entries = self.get_queryset().filter(user=request.user)
        serializer = self.get_serializer(entries, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def respond_to_notification(self, request, pk=None):
        """Respond to an availability notification."""
        entry = self.get_object()
        action = request.data.get('action')
        
        if entry.user != request.user:
            return Response({'error': 'Permission denied'}, status=403)
        
        if action == 'accept':
            success, message = waiting_list_service.accept_availability_offer(pk, request.user)
        elif action == 'decline':
            success, message = waiting_list_service.decline_availability_offer(pk, request.user)
        else:
            return Response({'error': 'Invalid action'}, status=400)
        
        return Response({
            'success': success,
            'message': message
        })