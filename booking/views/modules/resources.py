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
from django.core.exceptions import ValidationError
from django.db.models import Q, Count
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from datetime import timedelta

from ...models import (
    Resource, ResourceAccess, AccessRequest, UserProfile, 
    WaitingListEntry, Booking, ResourceIssue
)
from ...forms import (
    AccessRequestForm, ResourceForm, ResourceResponsibleForm, 
    ResourceIssueReportForm, ResourceIssueUpdateForm, IssueFilterForm,
    ChecklistItemForm
)


def is_lab_admin(user):
    """Check if user is a lab admin."""
    return hasattr(user, 'userprofile') and user.userprofile.role in ['technician', 'sysadmin']


@login_required
def resources_list_view(request):
    """View to display all available resources with access control."""
    resources = Resource.objects.filter(is_active=True).order_by('resource_type', 'name')
    
    # Add access information for each resource
    for resource in resources:
        resource.user_has_access_result = resource.user_has_access(request.user)
        resource.can_view_calendar_result = resource.can_user_view_calendar(request.user)
        
        # Check if user has pending access request
        resource.has_pending_request = AccessRequest.objects.filter(
            resource=resource,
            user=request.user,
            status='pending'
        ).exists()
        
        # Check if user has pending training (only if resource requires training)
        from ...models.training import UserTraining
        resource.has_pending_training = False
        if resource.training_requirements.filter(is_mandatory=True).exists():
            # Check if user has pending training for any required courses
            resource.has_pending_training = UserTraining.objects.filter(
                user=request.user,
                training_course__resource_requirements__resource=resource,
                training_course__resource_requirements__is_mandatory=True,
                status__in=['enrolled', 'in_progress']
            ).exists()
    
    return render(request, 'booking/resources_list.html', {
        'resources': resources,
        'user': request.user,
    })


@login_required
def resource_detail_view(request, resource_id):
    """View to show resource details and calendar or access request form."""
    from django.utils import timezone
    from ...models import RiskAssessment, UserRiskAssessment

    resource = get_object_or_404(Resource, id=resource_id, is_active=True)

    # Handle POST requests (like re-request training)
    if request.method == 'POST':
        action = request.POST.get('action', '')

        # Handle re-request training action
        if action == 'rerequest_training':
            training_id = request.POST.get('training_id')

            # Debug: Check if training_id is valid
            if not training_id or training_id == '':
                messages.error(request, 'Invalid training ID provided.')
                return redirect('booking:resource_detail', resource_id=resource.id)

            try:
                from ...models.training import UserTraining
                user_training = get_object_or_404(UserTraining, id=training_id, user=request.user)

                if user_training.status not in ['failed', 'cancelled', 'expired']:
                    messages.error(request, 'Can only re-request failed, cancelled, or expired training.')
                else:
                    # Reset the UserTraining status to allow re-enrollment
                    user_training.reset_for_retry()
                    messages.success(request, f'Training re-requested for {user_training.training_course.title}. Your training status has been reset and you can now re-enroll.', extra_tags='persistent-alert')

            except Exception as e:
                messages.error(request, f'Error re-requesting training: {str(e)}')

            return redirect('booking:resource_detail', resource_id=resource.id)
    
    # Check user's access
    user_has_access = resource.user_has_access(request.user)
    can_view_calendar = resource.can_user_view_calendar(request.user)
    
    # Check if user has pending access request
    has_pending_request = AccessRequest.objects.filter(
        resource=resource,
        user=request.user,
        status='pending'
    ).exists()
    
    # Check for recent rejected requests
    recent_rejected_request = AccessRequest.objects.filter(
        resource=resource,
        user=request.user,
        status='rejected',
        reviewed_at__gte=timezone.now() - timedelta(days=30)  # Show rejections from last 30 days
    ).order_by('-reviewed_at').first()
    
    # Check if user has pending training (only if resource requires training)
    has_pending_training = False
    if resource.required_training_level > 0:
        # Check for pending UserTraining records for this resource's required courses
        from ...models.training import UserTraining
        from ...models import ResourceTrainingRequirement
        required_courses = ResourceTrainingRequirement.objects.filter(
            resource=resource,
            is_mandatory=True
        ).values_list('training_course_id', flat=True)

        if required_courses:
            has_pending_training = UserTraining.objects.filter(
                user=request.user,
                training_course_id__in=required_courses,
                status__in=['enrolled', 'scheduled']
            ).exists()
    
    # Get approval progress for the user
    approval_progress = resource.get_approval_progress(request.user)
    
    # Check required risk assessments for this resource
    required_risk_assessments = RiskAssessment.objects.filter(
        resource=resource,
        is_active=True,
        valid_until__gte=timezone.now().date()
    ).order_by('risk_level', 'title')
    
    # Check user's status for each required risk assessment
    user_risk_assessments = {}
    risk_assessment_status = {'completed': 0, 'pending': 0, 'not_started': 0}
    
    for ra in required_risk_assessments:
        try:
            user_ra = UserRiskAssessment.objects.get(
                user=request.user,
                risk_assessment=ra
            )
            user_risk_assessments[ra.id] = user_ra
            if user_ra.status == 'approved':
                risk_assessment_status['completed'] += 1
            elif user_ra.status in ['submitted', 'in_progress']:
                risk_assessment_status['pending'] += 1
            else:
                risk_assessment_status['not_started'] += 1
        except UserRiskAssessment.DoesNotExist:
            user_risk_assessments[ra.id] = None
            risk_assessment_status['not_started'] += 1
    
    # Determine if user needs to complete risk assessments
    # Only consider risk assessment if the resource requires it via boolean field
    needs_risk_assessments = (
        resource.requires_risk_assessment and
        (required_risk_assessments.exists() and 
         risk_assessment_status['completed'] < required_risk_assessments.count())
    )
    
    # Check if training is actually complete by examining approval progress
    training_completed = False
    if approval_progress and approval_progress.get('stages'):
        for stage in approval_progress['stages']:
            if stage.get('key') == 'training' and stage.get('status') == 'completed':
                training_completed = True
                break
    
    # Override has_pending_training if training is actually completed
    # This ensures we don't show "Training Pending" when training is done
    if training_completed:
        has_pending_training = False
    
    # If user can view calendar and resource is not closed, show calendar view
    if can_view_calendar and not resource.is_closed:
        return render(request, 'booking/resource_detail.html', {
            'resource': resource,
            'user_has_access': user_has_access,
            'can_view_calendar': can_view_calendar,
            'has_pending_training': has_pending_training,
            'approval_progress': approval_progress,
            'required_risk_assessments': required_risk_assessments,
            'user_risk_assessments': user_risk_assessments,
            'risk_assessment_status': risk_assessment_status,
            'needs_risk_assessments': needs_risk_assessments,
            'recent_rejected_request': recent_rejected_request,
            'show_calendar': True,
        })
    
    # Otherwise show access request form
    return render(request, 'booking/resource_detail.html', {
        'resource': resource,
        'user_has_access': user_has_access,
        'can_view_calendar': can_view_calendar,
        'has_pending_request': has_pending_request,
        'has_pending_training': has_pending_training,
        'approval_progress': approval_progress,
        'required_risk_assessments': required_risk_assessments,
        'user_risk_assessments': user_risk_assessments,
        'risk_assessment_status': risk_assessment_status,
        'needs_risk_assessments': needs_risk_assessments,
        'recent_rejected_request': recent_rejected_request,
        'show_calendar': False,
    })


@login_required
def request_resource_access_view(request, resource_id):
    """Handle resource access requests."""
    
    resource = get_object_or_404(Resource, id=resource_id, is_active=True)
    
    # Check if user already has access or pending request
    if resource.user_has_access(request.user):
        messages.info(request, 'You already have access to this resource.', extra_tags='persistent-alert')
        return redirect('booking:resource_detail', resource_id=resource.id)
    
    if AccessRequest.objects.filter(resource=resource, user=request.user, status='pending').exists():
        messages.info(request, 'You already have a pending access request for this resource.', extra_tags='persistent-alert')
        return redirect('booking:resource_detail', resource_id=resource.id)
    
    # Check if user has pending training enrollment (only if resource requires training)
    if resource.required_training_level > 0:
        from ...models.training import UserTraining
        from ...models import ResourceTrainingRequirement
        required_courses = ResourceTrainingRequirement.objects.filter(
            resource=resource,
            is_mandatory=True
        ).values_list('training_course_id', flat=True)

        if required_courses and UserTraining.objects.filter(
            user=request.user,
            training_course_id__in=required_courses,
            status__in=['enrolled', 'scheduled']
        ).exists():
            messages.info(request, 'You already have pending training for this resource.', extra_tags='persistent-alert')
            return redirect('booking:resource_detail', resource_id=resource.id)
    
    if request.method == 'POST':
        # Existing access request handling
        access_type = request.POST.get('access_type', 'book')
        justification = request.POST.get('justification', '').strip()
        requested_duration_days = request.POST.get('requested_duration_days')
        has_training = request.POST.get('has_training', '')
        supervisor_name = request.POST.get('supervisor_name', '').strip()
        supervisor_email = request.POST.get('supervisor_email', '').strip()
        
        if not justification:
            messages.error(request, 'Please provide a justification for your access request.')
            return redirect('booking:request_resource_access', resource_id=resource.id)
        
        # Check supervisor requirements for students
        user_profile = request.user.userprofile
        if user_profile.role == 'student':
            if not supervisor_name:
                messages.error(request, 'Supervisor name is required for student access requests.')
                return redirect('booking:request_resource_access', resource_id=resource.id)
            if not supervisor_email:
                messages.error(request, 'Supervisor email is required for student access requests.')
                return redirect('booking:request_resource_access', resource_id=resource.id)
        
        # Training requirements handling is now done through AccessRequest creation
        # which will automatically create UserTraining records for required courses

        # Proceed with access request
        try:
            access_request = AccessRequest.objects.create_request(
                resource=resource,
                user=request.user,
                access_type=access_type,
                justification=justification,
                requested_duration_days=int(requested_duration_days) if requested_duration_days else None,
                supervisor_name=supervisor_name if user_profile.role == 'student' else '',
                supervisor_email=supervisor_email if user_profile.role == 'student' else ''
            )
        except ValidationError as e:
            messages.error(request, str(e), extra_tags='persistent-alert')
            return redirect('booking:resource_detail', resource_id=resource.id)
        
        messages.success(request, f'Access request for {resource.name} has been submitted successfully.', extra_tags='persistent-alert')
        
        # Send notifications
        try:
            from booking.notifications import access_request_notifications
            access_request_notifications.access_request_submitted(access_request)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send access request submission notification: {e}")
        
        return redirect('booking:resource_detail', resource_id=resource.id)
    
    # Determine if user is a student and needs supervisor info
    is_student = hasattr(request.user, 'userprofile') and request.user.userprofile.role == 'student'
    
    return render(request, 'booking/request_access.html', {
        'resource': resource,
        'is_student': is_student,
    })


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


@login_required
def manage_resource_view(request, resource_id):
    """Manage a specific resource."""
    resource = get_object_or_404(Resource, id=resource_id)
    
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        messages.error(request, "You don't have permission to manage resources.")
        return redirect('booking:resource_detail', resource_id=resource_id)
    
    context = {
        'resource': resource,
    }
    
    return render(request, 'booking/manage_resource.html', context)


@login_required
def assign_resource_responsible_view(request, resource_id):
    """Assign responsibility for a resource."""
    resource = get_object_or_404(Resource, id=resource_id)
    
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        messages.error(request, "You don't have permission to assign resource responsibility.")
        return redirect('booking:resource_detail', resource_id=resource_id)
    
    if request.method == 'POST':
        form = ResourceResponsibleForm(request.POST, resource=resource)
        if form.is_valid():
            responsible = form.save(commit=False)
            responsible.resource = resource
            responsible.assigned_by = request.user
            responsible.save()
            
            messages.success(request, f"Resource responsibility assigned to {responsible.user.get_full_name()}.")
            return redirect('booking:manage_resource', resource_id=resource_id)
    else:
        form = ResourceResponsibleForm(resource=resource)
    
    context = {
        'resource': resource,
        'form': form,
    }
    
    return render(request, 'booking/assign_resource_responsible.html', context)



@login_required
@require_http_methods(["GET", "POST"])
def ajax_create_checklist_item(request):
    """AJAX view for creating checklist items in a popup."""
    if not (request.user.is_staff or hasattr(request.user, 'userprofile') and 
            request.user.userprofile.role in ['technician', 'sysadmin']):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    if request.method == 'GET':
        form = ChecklistItemForm()
        html = render_to_string('booking/modals/checklist_item_form.html', {
            'form': form,
        }, request=request)
        return JsonResponse({'html': html})
    
    elif request.method == 'POST':
        form = ChecklistItemForm(request.POST)
        if form.is_valid():
            checklist_item = form.save(commit=False)
            checklist_item.created_by = request.user
            checklist_item.save()
            
            return JsonResponse({
                'success': True,
                'item': {
                    'id': checklist_item.id,
                    'title': checklist_item.title,
                    'description': checklist_item.description,
                    'category': checklist_item.get_category_display(),
                    'item_type': checklist_item.get_item_type_display(),
                    'is_required': checklist_item.is_required,
                }
            })
        else:
            html = render_to_string('booking/modals/checklist_item_form.html', {
                'form': form,
            }, request=request)
            return JsonResponse({'html': html, 'errors': form.errors})