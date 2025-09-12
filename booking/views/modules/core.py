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
from booking.forms import UserProfileForm, AboutPageEditForm


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
            user=request.user
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
    
    return render(request, 'registration/profile.html', context)


@login_required
def calendar_view(request):
    """Calendar view showing bookings."""
    # Check if filtering by resource
    resource_id = request.GET.get('resource')
    
    # Base query for user's bookings
    base_query = Q(user=request.user) | Q(attendees=request.user)
    
    # Add resource filter if specified
    if resource_id:
        base_query = base_query & Q(resource_id=resource_id)
    
    # Get user's bookings
    user_bookings = Booking.objects.filter(
        base_query,
        status__in=['pending', 'approved', 'in_progress']
    ).distinct()
    
    # If user is a manager, show all bookings (with resource filter if applicable)
    try:
        user_profile = request.user.userprofile
        if user_profile.role in ['technician', 'sysadmin']:
            filter_kwargs = {'status__in': ['pending', 'approved', 'in_progress']}
            if resource_id:
                filter_kwargs['resource_id'] = resource_id
            all_bookings = Booking.objects.filter(**filter_kwargs)
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
    
    # Get resource info if filtering
    resource = None
    if resource_id:
        try:
            from booking.models import Resource
            resource = Resource.objects.get(id=resource_id)
        except Resource.DoesNotExist:
            pass
    
    # Get all active resources for the filter dropdown
    from booking.models import Resource
    resources = Resource.objects.filter(is_active=True).order_by('name')
    
    context = {
        'events_json': json.dumps(events),
        'resource': resource,
        'resource_id': resource_id,
        'resources': resources,
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
    from django.http import JsonResponse
    faculty_id = request.GET.get('faculty_id')
    colleges = []
    if faculty_id:
        colleges = list(College.objects.filter(faculty_id=faculty_id, is_active=True).order_by('name').values('id', 'name'))
    return JsonResponse({'colleges': colleges})


def ajax_load_departments(request):
    """Load departments based on selected college."""
    from django.http import JsonResponse
    college_id = request.GET.get('college_id')
    departments = []
    if college_id:
        departments = list(Department.objects.filter(college_id=college_id, is_active=True).order_by('name').values('id', 'name'))
    return JsonResponse({'departments': departments})


# Group Management Views
@login_required
def group_management_view(request):
    """Group management interface for managers."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to manage groups.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to manage groups.')
        return redirect('booking:dashboard')

    # Handle POST requests for group operations
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create_group':
            return handle_create_group(request)
        elif action == 'rename_group':
            return handle_rename_group(request)
        elif action == 'merge_groups':
            return handle_merge_groups(request)
        elif action == 'delete_group':
            return handle_delete_group(request)
        elif action == 'bulk_assign':
            return handle_bulk_assign_users(request)

    # Get groups with member counts
    groups_data = UserProfile.objects.exclude(group='').values('group').annotate(
        member_count=Count('id'),
        students=Count('id', filter=Q(role='student')),
        researchers=Count('id', filter=Q(role='researcher')),
        academics=Count('id', filter=Q(role='academic')),
        technicians=Count('id', filter=Q(role='technician')),
        recent_activity=Count('user__booking', filter=Q(user__booking__created_at__gte=timezone.now() - timedelta(days=30)))
    ).order_by('-member_count')

    # Get users without groups
    ungrouped_users = UserProfile.objects.filter(group='').select_related('user')
    
    # Get recent group activities (bookings by group members)
    recent_bookings = Booking.objects.filter(
        user__userprofile__group__isnull=False,
        created_at__gte=timezone.now() - timedelta(days=7)
    ).select_related('user__userprofile', 'resource').order_by('-created_at')[:20]

    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        groups_data = groups_data.filter(group__icontains=search_query)

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(groups_data, 20)
    page_number = request.GET.get('page')
    groups_page = paginator.get_page(page_number)

    context = {
        'groups_data': groups_page,
        'ungrouped_users': ungrouped_users,
        'recent_bookings': recent_bookings,
        'search_query': search_query,
        'total_groups': groups_data.count(),
        'total_ungrouped': ungrouped_users.count(),
    }

    return render(request, 'booking/group_management.html', context)


@login_required  
def group_detail_view(request, group_name):
    """Detailed view of a specific group."""
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            messages.error(request, 'You do not have permission to view group details.')
            return redirect('booking:dashboard')
    except UserProfile.DoesNotExist:
        messages.error(request, 'You do not have permission to view group details.')
        return redirect('booking:dashboard')

    # Get group members
    group_members = UserProfile.objects.filter(group=group_name).select_related(
        'user', 'faculty', 'college', 'department'
    ).order_by('user__last_name', 'user__first_name')

    if not group_members.exists():
        messages.error(request, f'Group "{group_name}" not found.')
        return redirect('booking:group_management')

    # Handle POST requests for member management
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'remove_member':
            user_id = request.POST.get('user_id')
            try:
                member = UserProfile.objects.get(id=user_id, group=group_name)
                member.group = ''
                member.save()
                messages.success(request, f'Removed {member.user.get_full_name()} from group {group_name}.')
            except UserProfile.DoesNotExist:
                messages.error(request, 'User not found in this group.')
        
        elif action == 'change_role':
            user_id = request.POST.get('user_id')
            new_role = request.POST.get('new_role')
            try:
                member = UserProfile.objects.get(id=user_id, group=group_name)
                member.role = new_role
                member.save()
                messages.success(request, f'Changed {member.user.get_full_name()}\'s role to {new_role}.')
            except UserProfile.DoesNotExist:
                messages.error(request, 'User not found in this group.')
        
        return redirect('booking:group_detail', group_name=group_name)

    # Get group statistics
    group_stats = {
        'total_members': group_members.count(),
        'roles': group_members.values('role').annotate(count=Count('id')),
        'recent_bookings': Booking.objects.filter(
            user__userprofile__group=group_name,
            created_at__gte=timezone.now() - timedelta(days=30)
        ).count(),
        'active_bookings': Booking.objects.filter(
            user__userprofile__group=group_name,
            status__in=['pending', 'approved'],
            start_time__gte=timezone.now()
        ).count(),
    }

    # Get group's recent bookings
    recent_bookings = Booking.objects.filter(
        user__userprofile__group=group_name
    ).select_related('user', 'resource').order_by('-created_at')[:10]

    # Available users to add to group
    available_users = UserProfile.objects.filter(group='').select_related('user')

    context = {
        'group_name': group_name,
        'group_members': group_members,
        'group_stats': group_stats,
        'recent_bookings': recent_bookings,
        'available_users': available_users,
        'role_choices': UserProfile.ROLE_CHOICES,
    }

    return render(request, 'booking/group_detail.html', context)


def handle_create_group(request):
    """Handle group creation."""
    group_name = request.POST.get('group_name', '').strip()
    description = request.POST.get('description', '').strip()
    
    if not group_name:
        messages.error(request, 'Group name is required.')
        return redirect('booking:group_management')
    
    # Check if group already exists
    if UserProfile.objects.filter(group=group_name).exists():
        messages.error(request, f'Group "{group_name}" already exists.')
        return redirect('booking:group_management')
    
    # For now, we'll just create the group when first user is assigned
    # In a more advanced implementation, we might have a separate Group model
    messages.success(request, f'Group "{group_name}" will be created when first user is assigned.')
    return redirect('booking:group_management')


def handle_rename_group(request):
    """Handle group renaming."""
    old_name = request.POST.get('old_group_name', '').strip()
    new_name = request.POST.get('new_group_name', '').strip()
    
    if not old_name or not new_name:
        messages.error(request, 'Both old and new group names are required.')
        return redirect('booking:group_management')
    
    if old_name == new_name:
        messages.error(request, 'New group name must be different from old name.')
        return redirect('booking:group_management')
    
    # Check if new name already exists
    if UserProfile.objects.filter(group=new_name).exists():
        messages.error(request, f'Group "{new_name}" already exists.')
        return redirect('booking:group_management')
    
    # Rename the group
    updated = UserProfile.objects.filter(group=old_name).update(group=new_name)
    
    if updated > 0:
        messages.success(request, f'Renamed group "{old_name}" to "{new_name}" for {updated} users.')
    else:
        messages.error(request, f'Group "{old_name}" not found.')
    
    return redirect('booking:group_management')


def handle_merge_groups(request):
    """Handle merging groups."""
    source_group = request.POST.get('source_group', '').strip()
    target_group = request.POST.get('target_group', '').strip()
    
    if not source_group or not target_group:
        messages.error(request, 'Both source and target group names are required.')
        return redirect('booking:group_management')
    
    if source_group == target_group:
        messages.error(request, 'Source and target groups must be different.')
        return redirect('booking:group_management')
    
    # Check if both groups exist
    source_count = UserProfile.objects.filter(group=source_group).count()
    target_count = UserProfile.objects.filter(group=target_group).count()
    
    if source_count == 0:
        messages.error(request, f'Source group "{source_group}" not found.')
        return redirect('booking:group_management')
    
    if target_count == 0:
        messages.error(request, f'Target group "{target_group}" not found.')
        return redirect('booking:group_management')
    
    # Merge the groups
    updated = UserProfile.objects.filter(group=source_group).update(group=target_group)
    
    messages.success(request, f'Merged {updated} users from "{source_group}" into "{target_group}".')
    return redirect('booking:group_management')


def handle_delete_group(request):
    """Handle group deletion (removes group assignment from users)."""
    group_name = request.POST.get('group_name', '').strip()
    
    if not group_name:
        messages.error(request, 'Group name is required.')
        return redirect('booking:group_management')
    
    # Remove group assignment from all users
    updated = UserProfile.objects.filter(group=group_name).update(group='')
    
    if updated > 0:
        messages.success(request, f'Removed group assignment from {updated} users in "{group_name}".')
    else:
        messages.error(request, f'Group "{group_name}" not found.')
    
    return redirect('booking:group_management')


def handle_bulk_assign_users(request):
    """Handle bulk assignment of users to a group."""
    group_name = request.POST.get('target_group', '').strip()
    user_ids = request.POST.getlist('user_ids')
    
    if not group_name:
        messages.error(request, 'Target group name is required.')
        return redirect('booking:group_management')
    
    if not user_ids:
        messages.error(request, 'No users selected.')
        return redirect('booking:group_management')
    
    # Update selected users
    updated = UserProfile.objects.filter(id__in=user_ids).update(group=group_name)
    
    messages.success(request, f'Assigned {updated} users to group "{group_name}".')
    return redirect('booking:group_management')


@login_required
def add_user_to_group(request, group_name):
    """Add a user to a specific group via AJAX."""
    from django.http import JsonResponse
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        user_profile = request.user.userprofile
        if user_profile.role not in ['technician', 'sysadmin']:
            return JsonResponse({'error': 'Permission denied'}, status=403)
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    user_id = request.POST.get('user_id')
    
    try:
        user_profile = UserProfile.objects.get(id=user_id)
        user_profile.group = group_name
        user_profile.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Added {user_profile.user.get_full_name()} to group {group_name}.'
        })
    except UserProfile.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)