# booking/views/modules/resources.py
"""
Resource-related views for the Aperture Booking system.

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
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count

from ...models import (
    Resource, ResourceAccess, AccessRequest, UserProfile, 
    WaitingListEntry, Booking
)
from ...forms import AccessRequestForm, ResourceForm


def is_lab_admin(user):
    """Check if user is a lab admin."""
    return hasattr(user, 'userprofile') and user.userprofile.role in ['technician', 'sysadmin']


@login_required
def resources_list_view(request):
    """List available resources."""
    resources = Resource.objects.filter(is_active=True)
    
    # Filter by resource type if specified
    resource_type = request.GET.get('type')
    if resource_type:
        resources = resources.filter(resource_type=resource_type)
    
    # Search functionality
    search_query = request.GET.get('search')
    if search_query:
        resources = resources.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(location__icontains=search_query)
        )
    
    # Filter by availability for current user
    show_available_only = request.GET.get('available_only') == 'true'
    if show_available_only:
        try:
            user_profile = request.user.userprofile
            available_resources = []
            for resource in resources:
                if resource.is_available_for_user(user_profile):
                    available_resources.append(resource.pk)
            resources = resources.filter(pk__in=available_resources)
        except UserProfile.DoesNotExist:
            resources = resources.none()
    
    # Pagination
    paginator = Paginator(resources, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get unique resource types for filter dropdown
    resource_types = Resource.objects.values_list('resource_type', flat=True).distinct()
    
    context = {
        'page_obj': page_obj,
        'resource_types': resource_types,
        'current_type': resource_type,
        'search_query': search_query,
        'show_available_only': show_available_only,
    }
    
    return render(request, 'booking/resources_list.html', context)


@login_required
def resource_detail_view(request, resource_id):
    """View resource details and handle access requests."""
    resource = get_object_or_404(Resource, id=resource_id, is_active=True)
    
    # Check if user has access to this resource
    user_has_access = False
    access_request_pending = False
    
    try:
        user_profile = request.user.userprofile
        user_has_access = resource.is_available_for_user(user_profile)
        
        # Check for pending access requests
        access_request_pending = AccessRequest.objects.filter(
            user=request.user,
            resource=resource,
            status='pending'
        ).exists()
    except UserProfile.DoesNotExist:
        pass
    
    # Get recent bookings for this resource (for managers)
    recent_bookings = []
    try:
        if hasattr(request.user, 'userprofile') and request.user.userprofile.role in ['technician', 'sysadmin']:
            recent_bookings = Booking.objects.filter(
                resource=resource
            ).order_by('-start_time')[:10]
    except (UserProfile.DoesNotExist, AttributeError):
        pass
    
    # Check if user is on waiting list
    on_waiting_list = WaitingListEntry.objects.filter(
        user=request.user,
        resource=resource
    ).exists()
    
    context = {
        'resource': resource,
        'user_has_access': user_has_access,
        'access_request_pending': access_request_pending,
        'recent_bookings': recent_bookings,
        'on_waiting_list': on_waiting_list,
    }
    
    return render(request, 'booking/resource_detail.html', context)


@login_required
def request_resource_access_view(request, resource_id):
    """Request access to a resource."""
    resource = get_object_or_404(Resource, id=resource_id, is_active=True)
    
    # Check if user already has access
    try:
        user_profile = request.user.userprofile
        if resource.is_available_for_user(user_profile):
            messages.info(request, 'You already have access to this resource.')
            return redirect('booking:resource_detail', resource_id=resource.id)
    except UserProfile.DoesNotExist:
        messages.error(request, 'Please complete your profile first.')
        return redirect('booking:profile')
    
    # Check if there's already a pending request
    existing_request = AccessRequest.objects.filter(
        user=request.user,
        resource=resource,
        status='pending'
    ).first()
    
    if existing_request:
        messages.info(request, 'You already have a pending access request for this resource.')
        return redirect('booking:resource_detail', resource_id=resource.id)
    
    if request.method == 'POST':
        form = AccessRequestForm(request.POST, request.FILES)
        if form.is_valid():
            access_request = form.save(commit=False)
            access_request.user = request.user
            access_request.resource = resource
            access_request.save()
            
            messages.success(request, f'Access request for "{resource.name}" submitted successfully.')
            return redirect('booking:resource_detail', resource_id=resource.id)
    else:
        form = AccessRequestForm()
    
    context = {
        'form': form,
        'resource': resource,
    }
    
    return render(request, 'booking/request_access.html', context)


@login_required
@user_passes_test(is_lab_admin)
def access_requests_view(request):
    """View and manage access requests (admin only)."""
    access_requests = AccessRequest.objects.select_related(
        'user', 'resource', 'reviewed_by'
    ).order_by('-created_at')
    
    # Filter by status if specified
    status_filter = request.GET.get('status')
    if status_filter and status_filter != 'all':
        access_requests = access_requests.filter(status=status_filter)
    
    # Filter by resource if specified
    resource_filter = request.GET.get('resource')
    if resource_filter:
        access_requests = access_requests.filter(resource_id=resource_filter)
    
    # Pagination
    paginator = Paginator(access_requests, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get resources for filter dropdown
    resources = Resource.objects.filter(is_active=True).order_by('name')
    
    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'resource_filter': resource_filter,
        'resources': resources,
        'request_statuses': ['pending', 'approved', 'denied'],
    }
    
    return render(request, 'booking/access_requests.html', context)


@login_required
@user_passes_test(is_lab_admin)
def access_request_detail_view(request, request_id):
    """View and review a specific access request."""
    access_request = get_object_or_404(AccessRequest, id=request_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        review_notes = request.POST.get('review_notes', '')
        
        if action in ['approve', 'deny']:
            access_request.status = 'approved' if action == 'approve' else 'denied'
            access_request.reviewed_by = request.user
            access_request.reviewed_at = timezone.now()
            access_request.review_notes = review_notes
            access_request.save()
            
            if action == 'approve':
                # Create or update resource access
                ResourceAccess.objects.get_or_create(
                    user=access_request.user,
                    resource=access_request.resource,
                    defaults={
                        'granted_by': request.user,
                        'granted_at': timezone.now(),
                        'is_active': True,
                    }
                )
                messages.success(request, f'Access request approved for {access_request.user.get_full_name()}.')
            else:
                messages.success(request, f'Access request denied for {access_request.user.get_full_name()}.')
            
            return redirect('booking:access_requests')
    
    return render(request, 'booking/access_request_detail.html', {
        'access_request': access_request,
    })


@login_required
def resource_checkin_status_view(request, resource_id):
    """View check-in status for a specific resource."""
    resource = get_object_or_404(Resource, id=resource_id, is_active=True)
    
    # Get current bookings for this resource
    current_time = timezone.now()
    current_bookings = Booking.objects.filter(
        resource=resource,
        start_time__lte=current_time,
        end_time__gte=current_time,
        status__in=['approved', 'in_progress']
    ).select_related('user')
    
    # Get upcoming bookings (next 24 hours)
    upcoming_bookings = Booking.objects.filter(
        resource=resource,
        start_time__gt=current_time,
        start_time__lte=current_time + timedelta(hours=24),
        status='approved'
    ).select_related('user').order_by('start_time')
    
    context = {
        'resource': resource,
        'current_bookings': current_bookings,
        'upcoming_bookings': upcoming_bookings,
    }
    
    return render(request, 'booking/resource_checkin_status.html', context)