# booking/views/modules/approvals.py
"""
Approval views for the Aperture Booking system (access requests, risk assessments, approval rules).

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
from django.contrib.auth.models import User
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count, Max, Avg, Sum
from django.core.paginator import Paginator
from datetime import datetime, timedelta
import json

from ...models import (
    Resource, AccessRequest, RiskAssessment, UserRiskAssessment,
    ApprovalRule, UserTraining, ApprovalStatistics, Booking,
    BookingApproval, ApprovalTier, QuotaAllocation, UserQuota, QuotaUsageLog,
    ApprovalDelegate, ApprovalEscalation, SingleApprovalRequest, ApprovalNotificationTemplate
)
from ...forms import (
    AccessRequestReviewForm, RiskAssessmentForm, UserRiskAssessmentForm
)
# Removed licensing requirement - all features now available


def is_lab_admin(user):
    """Check if user is in Lab Admin group."""
    return user.groups.filter(name='Lab Admin').exists() or user.is_staff or user.userprofile.role in ['technician', 'sysadmin']


@login_required
def approval_dashboard_view(request):
    """Dashboard for approval workflow management."""
    # Summary statistics
    pending_access_requests = AccessRequest.objects.filter(status='pending').count()
    incomplete_assessments = UserRiskAssessment.objects.filter(status='submitted').count()
    pending_training = UserTraining.objects.filter(status='completed').count()
    overdue_items = 0  # Placeholder for overdue calculations
    
    # Recent access requests
    recent_access_requests = AccessRequest.objects.filter(
        status='pending'
    ).select_related('user', 'resource').order_by('-created_at')[:5]
    
    # Quick stats
    approved_today = AccessRequest.objects.filter(
        status='approved',
        reviewed_at__date=timezone.now().date()
    ).count()
    total_this_week = AccessRequest.objects.filter(
        created_at__week=timezone.now().isocalendar().week
    ).count()
    
    context = {
        'pending_access_requests': pending_access_requests,
        'incomplete_assessments': incomplete_assessments,
        'pending_training': pending_training,
        'overdue_items': overdue_items,
        'recent_access_requests': recent_access_requests,
        'approved_today': approved_today,
        'total_this_week': total_this_week,
    }
    
    return render(request, 'booking/approval_dashboard.html', context)


@login_required
def approve_access_request_view(request, request_id):
    """Approve an access request."""
    access_request = get_object_or_404(AccessRequest, id=request_id)
    
    # Check permissions
    if not access_request.can_be_approved_by(request.user):
        messages.error(request, "You don't have permission to approve this request.")
        return redirect('booking:access_request_detail', request_id=request_id)
    
    if request.method == 'POST':
        form = AccessRequestReviewForm(request.POST)
        if form.is_valid():
            review_notes = form.cleaned_data.get('review_notes', '')
            granted_duration = form.cleaned_data.get('granted_duration_days')
            
            # Approve the request
            access_request.approve(request.user, review_notes, granted_duration)
            
            messages.success(request, f"Access request for {access_request.resource.name} has been approved.")
            return redirect('booking:access_request_detail', request_id=request_id)
    else:
        form = AccessRequestReviewForm(initial={'decision': 'approve'})
    
    context = {
        'access_request': access_request,
        'form': form,
        'action': 'approve',
    }
    
    return render(request, 'booking/access_request_review.html', context)


@login_required
def reject_access_request_view(request, request_id):
    """Reject an access request."""
    access_request = get_object_or_404(AccessRequest, id=request_id)
    
    # Check permissions
    if not access_request.can_be_approved_by(request.user):
        messages.error(request, "You don't have permission to reject this request.")
        return redirect('booking:access_request_detail', request_id=request_id)
    
    if request.method == 'POST':
        form = AccessRequestReviewForm(request.POST)
        if form.is_valid():
            review_notes = form.cleaned_data.get('review_notes', '')
            
            # Reject the request
            access_request.reject(request.user, review_notes)
            
            messages.success(request, f"Access request for {access_request.resource.name} has been rejected.")
            return redirect('booking:access_request_detail', request_id=request_id)
    else:
        form = AccessRequestReviewForm(initial={'decision': 'reject'})
    
    context = {
        'access_request': access_request,
        'form': form,
        'action': 'reject',
    }
    
    return render(request, 'booking/access_request_review.html', context)


@login_required
def risk_assessments_view(request):
    """List view for risk assessments."""
    from django.core.paginator import Paginator
    
    # Get all risk assessments
    risk_assessments = RiskAssessment.objects.select_related('resource', 'created_by')
    
    # Apply filters
    assessment_type_filter = request.GET.get('assessment_type')
    if assessment_type_filter:
        risk_assessments = risk_assessments.filter(assessment_type=assessment_type_filter)
    
    risk_level_filter = request.GET.get('risk_level')
    if risk_level_filter:
        risk_assessments = risk_assessments.filter(risk_level=risk_level_filter)
    
    resource_filter = request.GET.get('resource')
    if resource_filter:
        risk_assessments = risk_assessments.filter(resource_id=resource_filter)
    
    status_filter = request.GET.get('status')
    if status_filter == 'active':
        risk_assessments = risk_assessments.filter(is_active=True, valid_until__gte=timezone.now().date())
    elif status_filter == 'expired':
        risk_assessments = risk_assessments.filter(valid_until__lt=timezone.now().date())
    
    # Filter by user (for viewing a specific user's risk assessments)
    user_filter = request.GET.get('user')
    if user_filter:
        risk_assessments = risk_assessments.filter(created_by_id=user_filter)
    
    # Order by creation date
    risk_assessments = risk_assessments.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(risk_assessments, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get user's assessment status
    user_assessments = {}
    if request.user.is_authenticated:
        user_assessment_qs = UserRiskAssessment.objects.filter(
            user=request.user,
            risk_assessment__in=risk_assessments
        ).select_related('risk_assessment')
        
        user_assessments = {
            ua.risk_assessment.id: ua for ua in user_assessment_qs
        }
    
    # Filter options
    assessment_types = RiskAssessment.ASSESSMENT_TYPES
    resources = Resource.objects.filter(is_active=True).order_by('name')
    
    context = {
        'risk_assessments': page_obj,
        'assessment_types': assessment_types,
        'resources': resources,
        'user_assessments': user_assessments,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
    }
    
    return render(request, 'booking/risk_assessments.html', context)


@login_required
def risk_assessment_detail_view(request, assessment_id):
    """Detail view for a risk assessment."""
    assessment = get_object_or_404(RiskAssessment, id=assessment_id)
    
    # Get user's assessment if exists
    user_assessment = None
    if request.user.is_authenticated:
        try:
            user_assessment = UserRiskAssessment.objects.get(
                user=request.user,
                risk_assessment=assessment
            )
        except UserRiskAssessment.DoesNotExist:
            pass
    
    context = {
        'assessment': assessment,
        'user_assessment': user_assessment,
    }
    
    return render(request, 'booking/risk_assessment_detail.html', context)


@login_required
def start_risk_assessment_view(request, assessment_id):
    """Start a risk assessment."""
    assessment = get_object_or_404(RiskAssessment, id=assessment_id)
    
    # Check if user already has an assessment
    user_assessment, created = UserRiskAssessment.objects.get_or_create(
        user=request.user,
        risk_assessment=assessment,
        defaults={'status': 'not_started'}
    )
    
    if request.method == 'POST':
        form = UserRiskAssessmentForm(request.POST, request.FILES, instance=user_assessment, risk_assessment=assessment)
        if form.is_valid():
            user_assessment = form.save(commit=False)
            
            # Handle file upload
            if form.cleaned_data.get('risk_assessment_file'):
                user_assessment.assessment_file = form.cleaned_data['risk_assessment_file']
            
            user_assessment.status = 'submitted'
            user_assessment.submitted_at = timezone.now()
            user_assessment.save()
            
            messages.success(request, "Risk assessment submitted for review.")
            return redirect('booking:resource_detail', resource_id=assessment.resource.id)
        else:
            # Add error message for failed validation
            messages.error(request, "Please correct the errors below before submitting.")
    else:
        # Mark as started
        if user_assessment.status == 'not_started':
            user_assessment.status = 'in_progress'
            user_assessment.started_at = timezone.now()
            user_assessment.save()
        
        form = UserRiskAssessmentForm(instance=user_assessment, risk_assessment=assessment)
    
    context = {
        'assessment': assessment,
        'user_assessment': user_assessment,
        'form': form,
    }
    
    return render(request, 'booking/start_risk_assessment.html', context)


@login_required
def submit_risk_assessment_view(request, assessment_id):
    """Submit a completed risk assessment."""
    assessment = get_object_or_404(RiskAssessment, id=assessment_id)
    user_assessment = get_object_or_404(
        UserRiskAssessment,
        user=request.user,
        risk_assessment=assessment
    )
    
    if user_assessment.status != 'in_progress':
        messages.error(request, "This assessment cannot be submitted.")
        return redirect('booking:risk_assessment_detail', assessment_id=assessment_id)
    
    user_assessment.status = 'submitted'
    user_assessment.submitted_at = timezone.now()
    user_assessment.save()
    
    messages.success(request, "Risk assessment submitted for review.")
    return redirect('booking:risk_assessment_detail', assessment_id=assessment_id)


@login_required
def create_risk_assessment_view(request):
    """Create a new risk assessment."""
    if not request.user.userprofile.role in ['technician', 'academic', 'sysadmin']:
        messages.error(request, "You don't have permission to create risk assessments.")
        return redirect('booking:risk_assessments')
    
    if request.method == 'POST':
        form = RiskAssessmentForm(request.POST)
        if form.is_valid():
            assessment = form.save(commit=False)
            assessment.created_by = request.user
            assessment.save()
            
            messages.success(request, f"Risk assessment '{assessment.title}' created successfully.")
            return redirect('booking:risk_assessment_detail', assessment_id=assessment.id)
    else:
        form = RiskAssessmentForm()
    
    context = {
        'form': form,
    }

    return render(request, 'booking/create_risk_assessment.html', context)


@login_required
@user_passes_test(is_lab_admin)
def download_risk_assessment_view(request, request_id, assessment_id):
    """Download a risk assessment file for lab admin review."""
    from django.http import HttpResponse, Http404
    from django.utils.encoding import smart_str
    import os
    import mimetypes

    # Get the access request to ensure it exists and validate permissions
    access_request = get_object_or_404(AccessRequest, id=request_id)

    # Get the user risk assessment
    user_assessment = get_object_or_404(
        UserRiskAssessment,
        id=assessment_id,
        user=access_request.user  # Ensure assessment belongs to the access request user
    )

    # Check if file exists
    if not user_assessment.assessment_file:
        raise Http404("No assessment file found")

    if not user_assessment.assessment_file.storage.exists(user_assessment.assessment_file.name):
        raise Http404("Assessment file not found")

    # Get the file
    file_path = user_assessment.assessment_file.path
    file_name = os.path.basename(file_path)

    # Determine content type
    content_type, _ = mimetypes.guess_type(file_path)
    if content_type is None:
        content_type = 'application/octet-stream'

    # Create response with file content
    with open(file_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type=content_type)

    # Set headers for download
    response['Content-Disposition'] = f'attachment; filename="{smart_str(file_name)}"'
    response['Content-Length'] = os.path.getsize(file_path)

    return response


@login_required
@user_passes_test(is_lab_admin)
# License feature removed - all features now available
def approval_statistics_view(request):
    """User-friendly approval statistics dashboard."""
    from booking.models import AccessRequest, UserTraining, UserRiskAssessment, Resource
    from django.db.models import Avg, Sum, Count, Q, Case, When, F, DurationField
    from django.db import models
    from datetime import datetime, timedelta
    import json

    # Get filter parameters
    period_type = request.GET.get('period', 'monthly')
    resource_filter = request.GET.get('resource')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    # Set default date range (last 30 days)
    today = timezone.now().date()
    if not start_date:
        start_date = today - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()

    if not end_date:
        end_date = today
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

    # Base queryset for access requests in the date range
    access_requests = AccessRequest.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    )

    # Filter by resource if specified
    if resource_filter:
        access_requests = access_requests.filter(resource_id=resource_filter)

    # Only show statistics for resources the user has responsibility for (unless admin)
    user_resources = None
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        # Get resources the user is responsible for
        user_resources = Resource.objects.filter(
            Q(responsible_persons__user=request.user) |
            Q(lab_admins__user=request.user)
        ).values_list('id', flat=True)
        access_requests = access_requests.filter(resource_id__in=user_resources)

    # Calculate summary statistics from real data
    summary_data = access_requests.aggregate(
        total_requests=Count('id'),
        total_approved=Count('id', filter=Q(status='approved')),
        total_rejected=Count('id', filter=Q(status='rejected')),
        total_pending=Count('id', filter=Q(status='pending')),
    )

    # Calculate average response time for approved/rejected requests
    processed_requests = access_requests.filter(
        status__in=['approved', 'rejected'],
        reviewed_at__isnull=False
    ).annotate(
        response_time_hours=Case(
            When(reviewed_at__isnull=False,
                 then=(F('reviewed_at') - F('created_at')) / timedelta(hours=1)),
            default=0,
            output_field=models.FloatField()
        )
    )

    avg_response_time = processed_requests.aggregate(
        avg_time=Avg('response_time_hours')
    )['avg_time'] or 0

    # Add response time to summary
    summary_data['avg_response_time'] = avg_response_time

    # Calculate training statistics
    training_requests = UserTraining.objects.filter(
        enrolled_at__date__gte=start_date,
        enrolled_at__date__lte=end_date
    )

    if resource_filter:
        training_requests = training_requests.filter(
            training_course__resourcetrainingrequirement__resource_id=resource_filter
        )

    training_stats = training_requests.aggregate(
        total_training_requests=Count('id'),
        total_training_completions=Count('id', filter=Q(status='completed')),
    )

    # Calculate risk assessment statistics
    risk_assessments = UserRiskAssessment.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    )

    if resource_filter:
        risk_assessments = risk_assessments.filter(
            risk_assessment__resource_id=resource_filter
        )

    assessment_stats = risk_assessments.aggregate(
        total_assessments=Count('id'),
    )

    # Combine all statistics
    summary_data.update(training_stats)
    summary_data.update(assessment_stats)

    # Calculate overdue items (requests older than 7 days without response)
    overdue_cutoff = timezone.now() - timedelta(days=7)
    summary_data['total_overdue'] = access_requests.filter(
        status='pending',
        created_at__lt=overdue_cutoff
    ).count()
    
    # Calculate approval rate
    total_processed = (summary_data['total_approved'] or 0) + (summary_data['total_rejected'] or 0)
    approval_rate = (summary_data['total_approved'] or 0) / total_processed * 100 if total_processed > 0 else 0
    
    # Calculate trends (comparing to previous period)
    previous_start = start_date - (end_date - start_date)
    previous_end = start_date - timedelta(days=1)

    # Get previous period data from AccessRequest model
    previous_access_requests = AccessRequest.objects.filter(
        created_at__date__gte=previous_start,
        created_at__date__lte=previous_end
    )

    if resource_filter:
        previous_access_requests = previous_access_requests.filter(resource_id=resource_filter)

    if not request.user.userprofile.role in ['technician', 'sysadmin'] and user_resources:
        previous_access_requests = previous_access_requests.filter(resource_id__in=user_resources)

    previous_data = previous_access_requests.aggregate(
        prev_total_requests=Count('id'),
        prev_total_approved=Count('id', filter=Q(status='approved')),
        prev_total_rejected=Count('id', filter=Q(status='rejected')),
    )

    # Calculate previous period response time
    prev_processed = previous_access_requests.filter(
        status__in=['approved', 'rejected'],
        reviewed_at__isnull=False
    ).annotate(
        response_time_hours=Case(
            When(reviewed_at__isnull=False,
                 then=(F('reviewed_at') - F('created_at')) / timedelta(hours=1)),
            default=0,
            output_field=models.FloatField()
        )
    )

    prev_avg_response_time = prev_processed.aggregate(
        avg_time=Avg('response_time_hours')
    )['avg_time'] or 0

    # Calculate previous overdue items
    prev_overdue_cutoff = timezone.now() - timedelta(days=7)
    prev_total_overdue = previous_access_requests.filter(
        status='pending',
        created_at__lt=prev_overdue_cutoff
    ).count()

    previous_data.update({
        'prev_avg_response_time': prev_avg_response_time,
        'prev_total_overdue': prev_total_overdue,
    })
    
    # Calculate trend indicators
    prev_processed = (previous_data['prev_total_approved'] or 0) + (previous_data['prev_total_rejected'] or 0)
    prev_approval_rate = (previous_data['prev_total_approved'] or 0) / prev_processed * 100 if prev_processed > 0 else 0
    
    summary = {
        'total_requests': summary_data['total_requests'] or 0,
        'approval_rate': approval_rate,
        'avg_response_time': summary_data['avg_response_time'] or 0,
        'overdue_items': summary_data['total_overdue'] or 0,
        
        # Trends
        'approval_change': approval_rate - prev_approval_rate,
        'approval_trend': 'up' if approval_rate > prev_approval_rate else 'down' if approval_rate < prev_approval_rate else 'stable',
        'response_change': (summary_data['avg_response_time'] or 0) - (previous_data['prev_avg_response_time'] or 0),
        'response_trend': 'down' if (summary_data['avg_response_time'] or 0) < (previous_data['prev_avg_response_time'] or 0) else 'up' if (summary_data['avg_response_time'] or 0) > (previous_data['prev_avg_response_time'] or 0) else 'stable',
        'overdue_change': (summary_data['total_overdue'] or 0) - (previous_data['prev_total_overdue'] or 0),
        'overdue_trend': 'up' if (summary_data['total_overdue'] or 0) > (previous_data['prev_total_overdue'] or 0) else 'down' if (summary_data['total_overdue'] or 0) < (previous_data['prev_total_overdue'] or 0) else 'stable',
        'volume_change': (summary_data['total_requests'] or 0) - (previous_data['prev_total_requests'] or 0),
        'volume_trend': 'up' if (summary_data['total_requests'] or 0) > (previous_data['prev_total_requests'] or 0) else 'down' if (summary_data['total_requests'] or 0) < (previous_data['prev_total_requests'] or 0) else 'stable',
    }
    
    # Resource-level statistics
    resource_stats = []

    # Get all resources that have access requests in the period
    resources_with_requests = access_requests.values('resource_id', 'resource__name').distinct()

    for resource_info in resources_with_requests:
        resource_id = resource_info['resource_id']
        resource_name = resource_info['resource__name']

        # Get requests for this specific resource
        resource_requests = access_requests.filter(resource_id=resource_id)

        # Calculate statistics for this resource
        resource_summary = resource_requests.aggregate(
            total_requests=Count('id'),
            approved=Count('id', filter=Q(status='approved')),
            rejected=Count('id', filter=Q(status='rejected')),
            pending=Count('id', filter=Q(status='pending')),
        )

        # Calculate response time for this resource
        resource_processed = resource_requests.filter(
            status__in=['approved', 'rejected'],
            reviewed_at__isnull=False
        ).annotate(
            response_time_hours=Case(
                When(reviewed_at__isnull=False,
                     then=(F('reviewed_at') - F('created_at')) / timedelta(hours=1)),
                default=0,
                output_field=models.FloatField()
            )
        )

        resource_avg_response_time = resource_processed.aggregate(
            avg_time=Avg('response_time_hours')
        )['avg_time'] or 0

        # Calculate overdue for this resource
        resource_overdue = resource_requests.filter(
            status='pending',
            created_at__lt=overdue_cutoff
        ).count()

        # Get the most recent approver for this resource
        latest_approver = resource_requests.filter(
            reviewed_by__isnull=False
        ).order_by('-reviewed_at').first()

        approver_name = 'N/A'
        if latest_approver and latest_approver.reviewed_by:
            approver_name = latest_approver.reviewed_by.get_full_name() or latest_approver.reviewed_by.username

        processed = resource_summary['approved'] + resource_summary['rejected']

        resource_stats.append({
            'resource_name': resource_name,
            'approver_name': approver_name,
            'total_requests': resource_summary['total_requests'],
            'approved': resource_summary['approved'],
            'rejected': resource_summary['rejected'],
            'approval_rate': (resource_summary['approved'] / processed * 100) if processed > 0 else 0,
            'avg_response_time': resource_avg_response_time,
            'overdue': resource_overdue,
        })
    
    # Sort by total requests descending
    resource_stats.sort(key=lambda x: x['total_requests'], reverse=True)
    
    # Top performers (by approval rate and response time)
    top_performers = sorted(resource_stats, key=lambda x: (x['approval_rate'], -x['avg_response_time']), reverse=True)[:5]
    
    # Chart data for distribution
    distribution_labels = ['Approved', 'Rejected', 'Pending']
    distribution_data = [
        summary_data['total_approved'] or 0,
        summary_data['total_rejected'] or 0,
        summary_data['total_pending'] or 0
    ]
    
    # Timeline data for response time trend
    # Generate weekly buckets for the timeline
    timeline_stats = []
    timeline_labels = []
    timeline_data = []

    # Create weekly buckets for the date range
    current_date = start_date
    while current_date <= end_date:
        week_end = min(current_date + timedelta(days=6), end_date)

        # Get access requests for this week
        week_requests = access_requests.filter(
            created_at__date__gte=current_date,
            created_at__date__lte=week_end
        )

        # Calculate average response time for this week
        week_processed = week_requests.filter(
            status__in=['approved', 'rejected'],
            reviewed_at__isnull=False
        ).annotate(
            response_time_hours=Case(
                When(reviewed_at__isnull=False,
                     then=(F('reviewed_at') - F('created_at')) / timedelta(hours=1)),
                default=0,
                output_field=models.FloatField()
            )
        )

        week_avg_response = week_processed.aggregate(
            avg_time=Avg('response_time_hours')
        )['avg_time'] or 0

        timeline_labels.append(current_date.strftime('%m/%d'))
        timeline_data.append(week_avg_response)

        current_date = week_end + timedelta(days=1)
    
    # Recent activity (mock data - in real implementation, this would come from audit logs)
    recent_activity = [
        {
            'description': 'New access request approved for Lab Equipment A',
            'timestamp': timezone.now() - timedelta(hours=2),
            'icon': 'check',
            'color': 'success'
        },
        {
            'description': 'Training session completed for Safety Protocol',
            'timestamp': timezone.now() - timedelta(hours=5),
            'icon': 'graduation-cap',
            'color': 'info'
        },
        {
            'description': 'Risk assessment reviewed for Chemical Lab',
            'timestamp': timezone.now() - timedelta(hours=8),
            'icon': 'shield-alt',
            'color': 'warning'
        },
    ]
    
    # Get all resources for filter dropdown
    resources = Resource.objects.all().order_by('name')
    
    # Handle CSV export
    if request.GET.get('export') == 'csv':
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="approval_statistics_{start_date}_to_{end_date}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Resource', 'Approver', 'Total Requests', 'Approved', 'Rejected', 
            'Approval Rate (%)', 'Avg Response Time (hours)', 'Overdue Items'
        ])
        
        for stat in resource_stats:
            writer.writerow([
                stat['resource_name'],
                stat['approver_name'],
                stat['total_requests'],
                stat['approved'],
                stat['rejected'],
                f"{stat['approval_rate']:.1f}",
                f"{stat['avg_response_time']:.1f}",
                stat['overdue']
            ])
        
        return response
    
    context = {
        'summary': summary,
        'resource_stats': resource_stats[:10],  # Limit to top 10 for display
        'top_performers': top_performers,
        'recent_activity': recent_activity,
        'resources': resources,
        
        # Chart data (convert to JSON for template)
        'distribution_labels': json.dumps(distribution_labels),
        'distribution_data': json.dumps(distribution_data),
        'timeline_labels': json.dumps(timeline_labels),
        'timeline_data': json.dumps(timeline_data),
    }
    
    return render(request, 'booking/approval_statistics.html', context)


@login_required
def approval_rules_view(request):
    """User-friendly approval rules management interface."""
    from booking.models import ApprovalRule
    import json
    
    # Only allow technicians and sysadmins to manage rules
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        messages.error(request, "You don't have permission to manage approval rules.")
        return redirect('booking:dashboard')
    
    # Get all rules with filters
    rules_qs = ApprovalRule.objects.all().select_related('resource', 'fallback_rule')
    
    # Apply filters
    type_filter = request.GET.get('type')
    resource_filter = request.GET.get('resource')
    search_filter = request.GET.get('search')
    
    if type_filter:
        rules_qs = rules_qs.filter(approval_type=type_filter)
    
    if resource_filter:
        rules_qs = rules_qs.filter(resource_id=resource_filter)
    
    if search_filter:
        rules_qs = rules_qs.filter(
            Q(name__icontains=search_filter) |
            Q(description__icontains=search_filter)
        )
    
    # Order by priority, then by created date
    rules_qs = rules_qs.order_by('priority', '-created_at')
    
    # Pagination
    paginator = Paginator(rules_qs, 10)
    page_number = request.GET.get('page')
    rules = paginator.get_page(page_number)
    
    # Calculate statistics
    stats = {
        'auto_rules': ApprovalRule.objects.filter(approval_type='auto').count(),
        'manual_rules': ApprovalRule.objects.filter(approval_type__in=['single', 'tiered']).count(),
        'conditional_rules': ApprovalRule.objects.filter(approval_type='conditional').count(),
        'active_rules': ApprovalRule.objects.filter(is_active=True).count(),
    }
    
    # Get resources for filters and creation
    resources = Resource.objects.all().order_by('name')
    
    # Get all rules for fallback options
    all_rules = ApprovalRule.objects.all().order_by('name')

    # Get lab admins and technicians who can be approvers
    from django.contrib.auth.models import Group
    from django.db.models import Q

    # Get users who can be approvers (technicians, sysadmins, and Lab Admin group members)
    lab_admins = User.objects.filter(
        Q(userprofile__role__in=['technician', 'sysadmin']) |
        Q(groups__name='Lab Admin'),
        is_active=True
    ).select_related('userprofile').distinct().order_by('first_name', 'last_name', 'username')

    # Handle POST request for creating rule
    if request.method == 'POST':
        try:
            # Get form data
            name = request.POST.get('name')
            approval_type = request.POST.get('approval_type')
            description = request.POST.get('description', '')
            resource_id = request.POST.get('resource')
            user_role = request.POST.get('user_role')
            priority = int(request.POST.get('priority', 100))
            fallback_rule_id = request.POST.get('fallback_rule')
            condition_type = request.POST.get('condition_type')
            conditional_logic_json = request.POST.get('conditional_logic')
            
            # Validate required fields
            if not name or not name.strip():
                messages.error(request, "Please provide a name for the approval rule.")
                return redirect('booking:approval_rules')

            if not approval_type or not approval_type.strip():
                messages.error(request, "Please select an approval type.")
                return redirect('booking:approval_rules')

            # Get related objects
            resource = None
            if resource_id and resource_id.strip():
                resource = get_object_or_404(Resource, id=resource_id)
            
            fallback_rule = None
            if fallback_rule_id:
                fallback_rule = get_object_or_404(ApprovalRule, id=fallback_rule_id)
            
            # Parse conditional logic
            conditional_logic = {}
            if approval_type == 'conditional' and conditional_logic_json:
                try:
                    conditional_logic = json.loads(conditional_logic_json)
                except json.JSONDecodeError:
                    conditional_logic = {}
            
            # Create approval rule
            rule = ApprovalRule.objects.create(
                name=name,
                approval_type=approval_type,
                description=description,
                resource=resource,
                user_roles=[user_role] if user_role else [],
                priority=priority,
                fallback_rule=fallback_rule,
                condition_type=condition_type if approval_type == 'conditional' else 'role_based',
                conditional_logic=conditional_logic,
                is_active=True
            )
            
            messages.success(request, f"Approval rule '{name}' created successfully.")
            return redirect('booking:approval_rules')
            
        except Exception as e:
            messages.error(request, f"Error creating approval rule: {str(e)}")
            return redirect('booking:approval_rules')
    
    context = {
        'rules': rules,
        'stats': stats,
        'resources': resources,
        'all_rules': all_rules,
        'lab_admins': lab_admins,
    }
    
    return render(request, 'booking/approval_rules.html', context)


@login_required
def approval_rule_toggle_view(request, rule_id):
    """Toggle approval rule active/inactive status."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})

    # Only allow technicians and sysadmins
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})

    try:
        import json

        rule = get_object_or_404(ApprovalRule, id=rule_id)

        data = json.loads(request.body)
        new_status = data.get('active', False)

        rule.is_active = new_status
        rule.save()

        return JsonResponse({
            'success': True,
            'message': f"Rule {'enabled' if new_status else 'disabled'} successfully"
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def approval_rule_edit_view(request, rule_id):
    """Get approval rule data for editing."""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'GET required'})

    # Only allow technicians and sysadmins
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})

    try:
        rule = get_object_or_404(ApprovalRule, id=rule_id)

        # Serialize rule data
        rule_data = {
            'id': rule.id,
            'name': rule.name,
            'approval_type': rule.approval_type,
            'description': rule.description,
            'resource_id': rule.resource.id if rule.resource else None,
            'user_role': rule.user_roles[0] if rule.user_roles else None,
            'priority': rule.priority,
            'is_active': rule.is_active,
            'condition_type': rule.condition_type,
            'conditional_logic': rule.conditional_logic,
            'fallback_rule_id': rule.fallback_rule.id if rule.fallback_rule else None,
        }

        return JsonResponse({
            'success': True,
            'rule': rule_data
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def approval_rule_update_view(request, rule_id):
    """Update approval rule."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})

    # Only allow technicians and sysadmins
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        return JsonResponse({'success': False, 'error': 'Permission denied'})

    try:
        rule = get_object_or_404(ApprovalRule, id=rule_id)

        # Get form data
        name = request.POST.get('name')
        approval_type = request.POST.get('approval_type')
        description = request.POST.get('description', '')
        resource_id = request.POST.get('resource')
        user_role = request.POST.get('user_role')
        priority = int(request.POST.get('priority', 100))
        is_active = request.POST.get('is_active') == 'true'
        condition_type = request.POST.get('condition_type')
        conditional_logic_json = request.POST.get('conditional_logic')

        # Validate required fields
        if not name or not name.strip():
            return JsonResponse({'success': False, 'error': 'Please provide a name for the approval rule.'})

        if not approval_type or not approval_type.strip():
            return JsonResponse({'success': False, 'error': 'Please select an approval type.'})

        # Get related objects
        resource = None
        if resource_id and resource_id.strip():
            try:
                from ...models import Resource
                resource = Resource.objects.get(id=resource_id)
            except Resource.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Selected resource not found.'})

        # Parse conditional logic
        conditional_logic = {}
        if approval_type == 'conditional' and conditional_logic_json:
            try:
                import json
                conditional_logic = json.loads(conditional_logic_json)
            except json.JSONDecodeError:
                conditional_logic = {}

        # Update the rule
        rule.name = name
        rule.approval_type = approval_type
        rule.description = description
        rule.resource = resource
        rule.user_roles = [user_role] if user_role else []
        rule.priority = priority
        rule.is_active = is_active
        rule.condition_type = condition_type if approval_type == 'conditional' else 'role_based'
        rule.conditional_logic = conditional_logic
        rule.save()

        return JsonResponse({
            'success': True,
            'message': f"Approval rule '{name}' updated successfully."
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def access_requests_view(request):
    """List view for access requests."""
    from django.core.paginator import Paginator
    
    # Start with all access requests
    access_requests = AccessRequest.objects.select_related('user', 'resource', 'reviewed_by')
    
    # Apply filters
    status_filter = request.GET.get('status')
    if status_filter:
        access_requests = access_requests.filter(status=status_filter)
    
    resource_type_filter = request.GET.get('resource_type')
    if resource_type_filter:
        access_requests = access_requests.filter(resource__resource_type=resource_type_filter)
    
    access_type_filter = request.GET.get('access_type')
    if access_type_filter:
        access_requests = access_requests.filter(access_type=access_type_filter)
    
    # Order by priority and creation date
    access_requests = access_requests.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(access_requests, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Filter options for the template
    resource_types = Resource.RESOURCE_TYPE_CHOICES
    
    context = {
        'access_requests': page_obj,
        'resource_types': resource_types,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
    }
    
    return render(request, 'booking/access_requests.html', context)



def _update_access_requests_after_risk_assessment_approval(assessment, reviewed_by):
    """
    Update related access requests when a risk assessment is approved.

    This function finds all pending access requests for the user and checks if
    approving this risk assessment completes their risk assessment requirements.
    If so, it confirms the risk assessment prerequisite for the access request.
    """
    user = assessment.user

    # Find all pending access requests for this user that require risk assessments
    pending_requests = AccessRequest.objects.filter(
        user=user,
        status='pending',
        risk_assessment_confirmed=False,
        resource__requires_risk_assessment=True
    )

    for access_request in pending_requests:
        # Check if this access request now has all required risk assessments approved
        resource = access_request.resource

        # Get all mandatory risk assessments for this resource
        required_assessments = RiskAssessment.objects.filter(
            resource=resource,
            is_mandatory=True,
            is_active=True
        )

        # Check if user has approved assessments for all required ones
        all_assessments_approved = True
        for req_assessment in required_assessments:
            has_approved = UserRiskAssessment.objects.filter(
                user=user,
                risk_assessment=req_assessment,
                status='approved'
            ).exists()

            if not has_approved:
                all_assessments_approved = False
                break

        # If all required assessments are approved, confirm the risk assessment prerequisite
        if all_assessments_approved:
            access_request.confirm_risk_assessment(
                confirmed_by=reviewed_by,
                notes=f'Auto-confirmed: All required risk assessments approved including {assessment.risk_assessment.title}'
            )
            print(f"DEBUG: Auto-confirmed risk assessment prerequisite for access request {access_request.id}")


@login_required
@user_passes_test(is_lab_admin)
def lab_admin_access_requests_view(request):
    """Manage access requests."""
    print("DEBUG: lab_admin_access_requests_view function called!")
    from booking.models import AccessRequest
    
    # Handle status updates
    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')
        
        if request_id and action:
            access_request = get_object_or_404(AccessRequest, id=request_id)
            
            if action == 'approve':
                try:
                    # Double-check prerequisites before approval
                    if not access_request.prerequisites_met():
                        missing = []
                        if not access_request.safety_induction_confirmed:
                            missing.append("Safety Induction")
                        if not access_request.lab_training_confirmed:
                            missing.append("Lab Training")
                        if not access_request.risk_assessment_confirmed:
                            missing.append("Risk Assessment")
                        
                        missing_str = ", ".join(missing)
                        messages.error(request, f'Cannot approve: Missing prerequisites - {missing_str}', extra_tags='persistent-alert')
                    else:
                        access_request.approve(request.user, "Approved via Lab Admin dashboard")
                        messages.success(request, f'Access request approved for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                except ValueError as e:
                    messages.error(request, f'Error approving request: {str(e)}', extra_tags='persistent-alert')
                except Exception as e:
                    messages.error(request, f'Unexpected error: {str(e)}', extra_tags='persistent-alert')
                
            elif action == 'reject':
                try:
                    access_request.reject(request.user, "Rejected via Lab Admin dashboard")
                    messages.success(request, f'Access request rejected for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                except ValueError as e:
                    messages.error(request, f'Error rejecting request: {str(e)}')
                except Exception as e:
                    messages.error(request, f'Unexpected error: {str(e)}')
                    
            elif action == 'confirm_safety':
                notes = request.POST.get('safety_notes', '').strip()
                try:
                    access_request.confirm_safety_induction(request.user, notes)
                    messages.success(request, f'Safety induction confirmed for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                except Exception as e:
                    messages.error(request, f'Error confirming safety induction: {str(e)}')
                    
            elif action == 'confirm_training':
                notes = request.POST.get('training_notes', '').strip()
                try:
                    # Confirm lab training on the access request
                    access_request.confirm_lab_training(request.user, notes)

                    # Also mark any related UserTraining records as completed
                    from ...models.training import UserTraining
                    pending_training = UserTraining.objects.filter(
                        user=access_request.user,
                        training_course__resource_trainings__resource=access_request.resource,
                        status__in=['enrolled', 'in_progress', 'failed']
                    )

                    for user_training in pending_training:
                        user_training.mark_as_completed_by_admin(
                            instructor=request.user,
                            notes=f"Training confirmed by {request.user.get_full_name()} for resource access. {notes}".strip()
                        )

                    messages.success(request, f'Lab training confirmed for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                except Exception as e:
                    messages.error(request, f'Error confirming lab training: {str(e)}')
                    
            elif action == 'confirm_risk_assessment':
                notes = request.POST.get('risk_assessment_notes', '').strip()
                try:
                    access_request.confirm_risk_assessment(request.user, notes)
                    messages.success(request, f'Risk assessment confirmed for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                except Exception as e:
                    messages.error(request, f'Error confirming risk assessment: {str(e)}')
                    
            elif action == 'schedule_training':
                justification = request.POST.get('training_justification', '').strip()
                training_date = request.POST.get('training_date', '').strip()
                training_time = request.POST.get('training_time', '').strip()
                training_duration = request.POST.get('training_duration', '').strip()
                trainer_notes = request.POST.get('trainer_notes', '').strip()
                
                if not justification:
                    justification = f"Training requested for access to {access_request.resource.name}"
                
                # Parse training date and time
                training_datetime = None
                if training_date and training_time:
                    try:
                        from datetime import datetime
                        training_datetime = datetime.strptime(f"{training_date} {training_time}", "%Y-%m-%d %H:%M")
                        training_datetime = timezone.make_aware(training_datetime)
                    except ValueError:
                        messages.error(request, 'Invalid date or time format.')
                        return redirect('booking:lab_admin_access_requests')
                elif training_date:
                    try:
                        from datetime import datetime
                        training_datetime = datetime.strptime(training_date, "%Y-%m-%d")
                        training_datetime = timezone.make_aware(training_datetime)
                    except ValueError:
                        messages.error(request, 'Invalid date format.')
                        return redirect('booking:lab_admin_access_requests')
                
                # Add duration and trainer notes to justification if provided
                full_justification = justification
                if training_duration:
                    duration_text = f"{training_duration} hour{'s' if float(training_duration) != 1 else ''}"
                    full_justification += f"\n\nExpected Duration: {duration_text}"
                if trainer_notes:
                    full_justification += f"\n\nTrainer Notes: {trainer_notes}"
                
                try:
                    # Training requests now handled through UserTraining model automatically
                    # when AccessRequest creates required training records
                    
                    # Handle booking creation and notifications when training is scheduled
                    if training_datetime:
                        try:
                            # Calculate end time (default 2 hours if no duration specified)
                            duration_hours = 2  # Default duration
                            if training_duration:
                                try:
                                    duration_hours = float(training_duration)
                                except ValueError:
                                    duration_hours = 2
                            
                            training_end_time = training_datetime + timedelta(hours=duration_hours)
                            
                            # Check for booking conflicts
                            conflicts = Booking.objects.filter(
                                resource=access_request.resource,
                                status__in=['approved', 'pending'],
                                start_time__lt=training_end_time,
                                end_time__gt=training_datetime
                            )
                            
                            if conflicts.exists():
                                # Find next available slot
                                next_slot = None
                                for hour_offset in range(1, 168):  # Check next week
                                    test_start = training_datetime + timedelta(hours=hour_offset)
                                    test_end = test_start + timedelta(hours=duration_hours)
                                    
                                    test_conflicts = Booking.objects.filter(
                                        resource=access_request.resource,
                                        status__in=['approved', 'pending'],
                                        start_time__lt=test_end,
                                        end_time__gt=test_start
                                    )
                                    
                                    if not test_conflicts.exists():
                                        next_slot = test_start
                                        break
                                
                                conflict_msg = f'The requested time slot conflicts with existing bookings.'
                                if next_slot:
                                    conflict_msg += f' Next available slot: {next_slot.strftime("%B %d, %Y at %I:%M %p")}'
                                
                                messages.warning(request, conflict_msg, extra_tags='persistent-alert')
                                # Reset to pending status and clear training_date
                                training_request.status = 'pending'
                                training_request.training_date = None
                                training_request.save()
                            else:
                                # No conflicts, create the booking
                                booking = Booking.objects.create(
                                    resource=access_request.resource,
                                    user=access_request.user,
                                    title=f'Training Session: {access_request.resource.name}',
                                    description=f'Training session for {access_request.user.get_full_name()}.\n\n{training_request.justification}',
                                    start_time=training_datetime,
                                    end_time=training_end_time,
                                    status='approved',  # Training bookings are auto-approved
                                    notes=f'Training Request ID: {training_request.id}'
                                )
                                
                                # Send notifications
                                try:
                                    from booking.notifications import training_request_notifications
                                    training_request_notifications.training_request_scheduled(training_request, training_datetime)
                                except Exception as e:
                                    import logging
                                    logger = logging.getLogger(__name__)
                                    logger.error(f"Failed to send training scheduled notification: {e}")
                                
                                if created:
                                    messages.success(request, f'Training session scheduled for {access_request.user.get_full_name()} on {training_datetime.strftime("%B %d, %Y at %I:%M %p")}. Resource has been booked.', extra_tags='persistent-alert')
                                else:
                                    messages.success(request, f'Training session updated and scheduled for {access_request.user.get_full_name()} on {training_datetime.strftime("%B %d, %Y at %I:%M %p")}. Resource has been booked.', extra_tags='persistent-alert')
                                    
                        except Exception as e:
                            messages.error(request, f'Error scheduling training session: {str(e)}')
                            # Reset to pending status
                            training_request.status = 'pending'
                            training_request.training_date = None
                            training_request.save()
                    else:
                        # No specific time scheduled
                        if created:
                            messages.success(request, f'Training request created for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                        else:
                            messages.info(request, f'Training request already exists for {access_request.user.get_full_name()}', extra_tags='persistent-alert')
                        
                except Exception as e:
                    messages.error(request, f'Error creating training request: {str(e)}')

        # Handle risk assessment approval/rejection
        assessment_id = request.POST.get('assessment_id')
        action = request.POST.get('action')

        if assessment_id and action in ['approve_assessment', 'reject_assessment']:
            try:
                assessment = get_object_or_404(UserRiskAssessment, id=assessment_id)

                if action == 'approve_assessment':
                    assessment.status = 'approved'
                    assessment.reviewed_by = request.user
                    assessment.reviewed_at = timezone.now()
                    assessment.save()

                    # Check and update related access requests
                    _update_access_requests_after_risk_assessment_approval(assessment, request.user)

                    messages.success(request, f'Risk assessment approved for {assessment.user.get_full_name()}', extra_tags='persistent-alert')

                elif action == 'reject_assessment':
                    rejection_reason = request.POST.get('rejection_reason', '').strip()
                    assessment.status = 'rejected'
                    assessment.reviewed_by = request.user
                    assessment.reviewed_at = timezone.now()
                    assessment.rejection_reason = rejection_reason
                    assessment.save()

                    messages.success(request, f'Risk assessment rejected for {assessment.user.get_full_name()}', extra_tags='persistent-alert')

            except Exception as e:
                messages.error(request, f'Error processing risk assessment: {str(e)}')

        return redirect('booking:lab_admin_access_requests')
    
    # Get access requests
    access_requests = AccessRequest.objects.select_related(
        'user', 'resource', 'reviewed_by', 'safety_induction_confirmed_by', 'lab_training_confirmed_by', 'risk_assessment_confirmed_by'
    ).order_by('-created_at')
    
    # Apply filters
    status_filter = request.GET.get('status', 'pending')
    if status_filter and status_filter != 'all':
        access_requests = access_requests.filter(status=status_filter)
    
    # Pagination
    paginator = Paginator(access_requests, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Add prerequisite status and user submitted assessments to each request
    print(f"DEBUG: Lab admin viewing {len(page_obj)} access requests")
    for request_obj in page_obj:
        print(f"DEBUG: Request from {request_obj.user.username} ({request_obj.user.get_full_name()}) for {request_obj.resource.name}")
        request_obj.prerequisite_status = request_obj.get_prerequisite_status()

        # Get user's submitted risk assessments that have files uploaded
        request_obj.user_submitted_assessments = UserRiskAssessment.objects.filter(
            user=request_obj.user,
            assessment_file__isnull=False  # Only include assessments with files
        ).select_related('risk_assessment').order_by('-submitted_at')

        print(f"  - Found {request_obj.user_submitted_assessments.count()} risk assessments with files")
        for assessment in request_obj.user_submitted_assessments:
            print(f"    * Assessment ID: {assessment.id}, File: {assessment.assessment_file}, Status: {assessment.status}")

        # If no assessments with files, check if they have any assessments at all
        if request_obj.user_submitted_assessments.count() == 0:
            all_assessments = UserRiskAssessment.objects.filter(user=request_obj.user)
            print(f"  - User has {all_assessments.count()} total assessments (but no files)")
            for assessment in all_assessments:
                print(f"    * ID: {assessment.id}, File: {assessment.assessment_file or 'None'}, Status: {assessment.status}")
    
    # Add today's date for date picker minimum value
    from datetime import date
    
    context = {
        'access_requests': page_obj,
        'status_filter': status_filter,
        'today': date.today(),
    }
    
    return render(request, 'booking/lab_admin_access_requests.html', context)


@login_required
def start_risk_assessment_view(request, assessment_id):
    """Start a risk assessment."""
    assessment = get_object_or_404(RiskAssessment, id=assessment_id)
    
    # Check if user already has an assessment
    user_assessment, created = UserRiskAssessment.objects.get_or_create(
        user=request.user,
        risk_assessment=assessment,
        defaults={'status': 'not_started'}
    )
    
    if request.method == 'POST':
        form = UserRiskAssessmentForm(request.POST, request.FILES, instance=user_assessment, risk_assessment=assessment)
        if form.is_valid():
            user_assessment = form.save(commit=False)
            
            # Handle file upload
            if form.cleaned_data.get('risk_assessment_file'):
                user_assessment.assessment_file = form.cleaned_data['risk_assessment_file']
            
            user_assessment.status = 'submitted'
            user_assessment.submitted_at = timezone.now()
            user_assessment.save()
            
            messages.success(request, "Risk assessment submitted for review.")
            return redirect('booking:resource_detail', resource_id=assessment.resource.id)
        else:
            # Add error message for failed validation
            messages.error(request, "Please correct the errors below before submitting.")
    else:
        # Mark as started
        if user_assessment.status == 'not_started':
            user_assessment.status = 'in_progress'
            user_assessment.started_at = timezone.now()
            user_assessment.save()
        
        form = UserRiskAssessmentForm(instance=user_assessment, risk_assessment=assessment)
    
    context = {
        'assessment': assessment,
        'user_assessment': user_assessment,
        'form': form,
    }
    
    return render(request, 'booking/start_risk_assessment.html', context)


@login_required
def submit_risk_assessment_view(request, assessment_id):
    """Submit a completed risk assessment."""
    assessment = get_object_or_404(RiskAssessment, id=assessment_id)
    user_assessment = get_object_or_404(
        UserRiskAssessment,
        user=request.user,
        risk_assessment=assessment
    )
    
    if user_assessment.status != 'in_progress':
        messages.error(request, "This assessment cannot be submitted.")
        return redirect('booking:risk_assessment_detail', assessment_id=assessment_id)
    
    user_assessment.status = 'submitted'
    user_assessment.submitted_at = timezone.now()
    user_assessment.save()
    
    messages.success(request, "Risk assessment submitted for review.")
    return redirect('booking:risk_assessment_detail', assessment_id=assessment_id)


@login_required
def create_risk_assessment_view(request):
    """Create a new risk assessment."""
    if not request.user.userprofile.role in ['technician', 'academic', 'sysadmin']:
        messages.error(request, "You don't have permission to create risk assessments.")
        return redirect('booking:risk_assessments')
    
    if request.method == 'POST':
        form = RiskAssessmentForm(request.POST)
        if form.is_valid():
            assessment = form.save(commit=False)
            assessment.created_by = request.user
            assessment.save()
            
            messages.success(request, f"Risk assessment '{assessment.title}' created successfully.")
            return redirect('booking:risk_assessment_detail', assessment_id=assessment.id)
    else:
        form = RiskAssessmentForm()
    
    context = {
        'form': form,
    }

    return render(request, 'booking/create_risk_assessment.html', context)


@login_required
@user_passes_test(is_lab_admin)
def download_risk_assessment_view(request, request_id, assessment_id):
    """Download a risk assessment file for lab admin review."""
    from django.http import HttpResponse, Http404
    from django.utils.encoding import smart_str
    import os
    import mimetypes

    # Get the access request to ensure it exists and validate permissions
    access_request = get_object_or_404(AccessRequest, id=request_id)

    # Get the user risk assessment
    user_assessment = get_object_or_404(
        UserRiskAssessment,
        id=assessment_id,
        user=access_request.user  # Ensure assessment belongs to the access request user
    )

    # Check if file exists
    if not user_assessment.assessment_file:
        raise Http404("No assessment file found")

    if not user_assessment.assessment_file.storage.exists(user_assessment.assessment_file.name):
        raise Http404("Assessment file not found")

    # Get the file
    file_path = user_assessment.assessment_file.path
    file_name = os.path.basename(file_path)

    # Determine content type
    content_type, _ = mimetypes.guess_type(file_path)
    if content_type is None:
        content_type = 'application/octet-stream'

    # Create response with file content
    with open(file_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type=content_type)

    # Set headers for download
    response['Content-Disposition'] = f'attachment; filename="{smart_str(file_name)}"'
    response['Content-Length'] = os.path.getsize(file_path)

    return response

# =============================================================================
# TIERED APPROVAL BACKEND FUNCTIONS
# =============================================================================

def create_tiered_approval_workflow(booking, approval_rule):
    """Initialize tiered approval workflow for a booking."""
    if approval_rule.approval_type != 'tiered':
        return False

    # Create approval steps for all tiers
    approval_steps = approval_rule.create_tiered_approval_steps(booking)

    # Save all approval steps
    BookingApproval.objects.bulk_create(approval_steps)

    # Update booking status to pending
    booking.status = 'pending'
    booking.save()

    return True


def process_tier_approval(booking_approval_id, approver, action, comments='', conditions=''):
    """Process an individual tier approval/rejection."""
    try:
        approval = BookingApproval.objects.get(id=booking_approval_id)

        # Verify approver has permission
        if approval.approver != approver:
            return {'success': False, 'message': 'Not authorized to approve this request'}

        # Update approval
        approval.status = 'approved' if action == 'approve' else 'rejected'
        approval.approved_at = timezone.now()
        approval.comments = comments
        approval.conditions = conditions
        approval.save()

        booking = approval.booking
        approval_rule = approval.approval_rule

        if action == 'approve':
            # Check if this tier is now complete
            if approval_rule.is_tier_complete(booking, approval.tier_level):
                # Check if all tiers are complete
                if approval_rule.is_tiered_approval_complete(booking):
                    # All tiers approved - approve the booking
                    booking.status = 'approved'
                    booking.approved_by = approver
                    booking.approved_at = timezone.now()
                    booking.save()

                    return {
                        'success': True,
                        'message': 'All tiers approved - booking confirmed',
                        'booking_status': 'approved'
                    }
                else:
                    # Move to next tier
                    next_tier = approval_rule.get_next_approval_tier(booking)
                    if next_tier:
                        return {
                            'success': True,
                            'message': f'Tier {approval.tier_level} approved - moved to {next_tier.name}',
                            'booking_status': 'pending',
                            'next_tier': next_tier.tier_level
                        }
        else:
            # Rejection - reject the entire booking
            booking.status = 'rejected'
            booking.save()

            # Mark all other pending approvals as withdrawn
            BookingApproval.objects.filter(
                booking=booking,
                status='pending'
            ).update(status='withdrawn')

            return {
                'success': True,
                'message': f'Booking rejected at tier {approval.tier_level}',
                'booking_status': 'rejected'
            }

        return {
            'success': True,
            'message': f'Tier {approval.tier_level} processed successfully',
            'booking_status': booking.status
        }

    except BookingApproval.DoesNotExist:
        return {'success': False, 'message': 'Approval not found'}
    except Exception as e:
        return {'success': False, 'message': f'Error processing approval: {str(e)}'}



# =============================================================================
# QUOTA-BASED APPROVAL BACKEND FUNCTIONS
# =============================================================================

def process_quota_based_booking(booking, approval_rule):
    """Process a booking with quota-based approval."""
    if approval_rule.approval_type != 'quota':
        return {'success': False, 'message': 'Not a quota-based approval rule'}

    # Build booking request object
    booking_request = {
        'title': booking.title,
        'start_time': booking.start_time,
        'end_time': booking.end_time,
        'duration_hours': (booking.end_time - booking.start_time).total_seconds() / 3600,
        'resource': booking.resource
    }

    # Evaluate quota-based approval
    quota_result = approval_rule.evaluate_quota_based_approval(
        booking_request, booking.user.userprofile
    )

    if quota_result['approved']:
        # Auto-approve the booking
        booking.status = 'approved'
        booking.approved_by = booking.user  # Self-approved within quota
        booking.approved_at = timezone.now()
        booking.save()

        return {
            'success': True,
            'approved': True,
            'message': quota_result['reason'],
            'quota_info': quota_result.get('quota_info', {})
        }
    else:
        # Requires manual approval
        booking.status = 'pending'
        booking.save()

        return {
            'success': True,
            'approved': False,
            'message': quota_result['reason'],
            'quota_info': quota_result.get('quota_info', {})
        }


def confirm_booking_quota_usage(booking):
    """Confirm quota usage when a booking is completed."""
    # Find quota allocations that apply to this booking
    applicable_allocations = QuotaAllocation.objects.filter(
        is_active=True
    ).order_by('-priority')

    for allocation in applicable_allocations:
        if (allocation.applies_to_user(booking.user.userprofile) and 
            allocation.applies_to_resource(booking.resource)):

            # Get current period
            rule = ApprovalRule()
            current_period = rule._get_current_quota_period(allocation)

            try:
                user_quota = UserQuota.objects.get(
                    user=booking.user,
                    allocation=allocation,
                    period_start=current_period['start']
                )

                # Calculate actual usage
                duration_hours = (booking.end_time - booking.start_time).total_seconds() / 3600

                # Release any reservation and record actual usage
                user_quota.release_reservation(duration_hours)
                user_quota.allocate_usage(duration_hours, is_reservation=False)

                # Log the usage
                QuotaUsageLog.objects.create(
                    user_quota=user_quota,
                    booking=booking,
                    amount_used=duration_hours,
                    usage_type='booking',
                    description=f'Completed booking: {booking.title}'
                )

                break

            except UserQuota.DoesNotExist:
                continue


@login_required
def quota_allocations_view(request):
    """Manage quota allocations."""
    # Only allow technicians and sysadmins
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        messages.error(request, "You don't have permission to manage quota allocations.")
        return redirect('booking:dashboard')

    allocations = QuotaAllocation.objects.all().select_related('resource', 'created_by').order_by('-priority', 'name')

    # Apply filters
    type_filter = request.GET.get('type')
    period_filter = request.GET.get('period')
    active_filter = request.GET.get('active')

    if type_filter:
        allocations = allocations.filter(quota_type=type_filter)
    if period_filter:
        allocations = allocations.filter(period_type=period_filter)
    if active_filter == 'true':
        allocations = allocations.filter(is_active=True)
    elif active_filter == 'false':
        allocations = allocations.filter(is_active=False)

    # Handle allocation creation
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            description = request.POST.get('description', '')
            quota_type = request.POST.get('quota_type')
            quota_amount = float(request.POST.get('quota_amount'))
            period_type = request.POST.get('period_type')
            resource_id = request.POST.get('resource')
            user_roles = request.POST.getlist('user_roles')

            allocation = QuotaAllocation.objects.create(
                name=name,
                description=description,
                quota_type=quota_type,
                quota_amount=quota_amount,
                period_type=period_type,
                resource_id=resource_id if resource_id else None,
                user_roles=user_roles,
                created_by=request.user
            )

            messages.success(request, f'Quota allocation "{allocation.name}" created successfully.')
            return redirect('booking:quota_allocations')

        except Exception as e:
            messages.error(request, f'Error creating quota allocation: {str(e)}')

    # Get resources and users for the form
    resources = Resource.objects.filter(is_active=True).order_by('name')
    users = User.objects.filter(is_active=True).select_related('userprofile').order_by('first_name', 'last_name', 'username')

    # Get user quota status overview
    user_quota_status = []
    active_users = User.objects.filter(is_active=True)[:10]  # Limit to first 10 for overview
    for user in active_users:
        user_quotas = UserQuota.objects.filter(user=user).select_related('allocation')
        quota_data = []
        for quota in user_quotas:
            usage_percentage = (quota.used_amount / quota.allocation.quota_amount * 100) if quota.allocation.quota_amount > 0 else 0
            quota_data.append({
                'allocation': quota.allocation,
                'used_amount': quota.used_amount,
                'allocated_amount': quota.allocation.quota_amount,
                'usage_percentage': usage_percentage,
            })

        if quota_data:  # Only include users with quotas
            user_quota_status.append({
                'user': user,
                'quotas': quota_data,
            })

    context = {
        'quota_allocations': allocations,
        'resources': resources,
        'users': users,
        'user_quota_status': user_quota_status,
        'quota_types': QuotaAllocation.QUOTA_TYPES,
        'period_types': QuotaAllocation.PERIOD_TYPES,
    }

    return render(request, 'booking/quota_allocations.html', context)


@login_required
def user_quota_status_view(request, user_id=None):
    """View quota status for a user."""
    if user_id:
        # Admin viewing another user's quota
        if not request.user.userprofile.role in ['technician', 'sysadmin']:
            messages.error(request, "You don't have permission to view other users' quotas.")
            return redirect('booking:dashboard')
        target_user = get_object_or_404(User, id=user_id)
    else:
        # User viewing their own quota
        target_user = request.user

    # Get quota status
    quota_status = ApprovalRule.get_user_quota_status(target_user)

    context = {
        'target_user': target_user,
        'quota_status': quota_status,
    }

    return render(request, 'booking/user_quota_status.html', context)


@login_required
@user_passes_test(is_lab_admin)
def quota_allocation_edit_view(request, quota_id):
    """Edit a specific quota allocation."""
    quota = get_object_or_404(QuotaAllocation, id=quota_id)

    if request.method == 'GET':
        # Return quota data as JSON for AJAX form population
        data = {
            'success': True,
            'quota': {
                'id': quota.id,
                'name': quota.name,
                'description': quota.description,
                'quota_type': quota.quota_type,
                'quota_amount': float(quota.quota_amount),
                'period_type': quota.period_type,
                'resource': quota.resource.id if quota.resource else None,
                'user': quota.user.id if quota.user else None,
                'role': quota.role,
                'allow_overdraft': quota.allow_overdraft,
                'is_active': quota.is_active,
            }
        }
        return JsonResponse(data)

    elif request.method == 'POST':
        try:
            # Update quota allocation
            quota.name = request.POST.get('name')
            quota.description = request.POST.get('description', '')
            quota.quota_type = request.POST.get('quota_type')
            quota.quota_amount = request.POST.get('quota_amount')
            quota.period_type = request.POST.get('period_type')

            resource_id = request.POST.get('resource')
            quota.resource = Resource.objects.get(id=resource_id) if resource_id else None

            target_type = request.POST.get('target_type')
            if target_type == 'user':
                user_id = request.POST.get('user')
                quota.user = User.objects.get(id=user_id) if user_id else None
                quota.role = None
            elif target_type == 'role':
                quota.role = request.POST.get('role')
                quota.user = None
            else:  # global
                quota.user = None
                quota.role = None

            quota.allow_overdraft = 'allow_overdraft' in request.POST
            quota.is_active = 'is_active' in request.POST
            quota.save()

            return JsonResponse({'success': True, 'message': 'Quota allocation updated successfully'})

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@login_required
@user_passes_test(is_lab_admin)
def quota_allocation_delete_view(request, quota_id):
    """Delete a quota allocation."""
    if request.method == 'POST':
        try:
            quota = get_object_or_404(QuotaAllocation, id=quota_id)
            quota_name = quota.name
            quota.delete()
            return JsonResponse({'success': True, 'message': f'Quota allocation "{quota_name}" deleted successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@login_required
@user_passes_test(is_lab_admin)
def quota_usage_view(request, quota_id):
    """View detailed usage information for a quota allocation."""
    quota = get_object_or_404(QuotaAllocation, id=quota_id)

    # Get current period usage
    current_usage = None
    if quota.user:
        # Single user quota
        try:
            user_quota = UserQuota.objects.get(allocation=quota, user=quota.user)
            current_usage = {
                'used_amount': user_quota.used_amount,
                'allocated_amount': quota.quota_amount,
                'usage_percentage': (user_quota.used_amount / quota.quota_amount * 100) if quota.quota_amount > 0 else 0,
                'remaining_amount': quota.quota_amount - user_quota.used_amount,
                'overdraft_amount': max(0, user_quota.used_amount - quota.quota_amount),
                'period_start': user_quota.period_start,
                'period_end': user_quota.period_end,
            }
        except UserQuota.DoesNotExist:
            pass

    # Get recent usage logs
    usage_logs = QuotaUsageLog.objects.filter(
        allocation=quota
    ).select_related('user', 'booking').order_by('-created_at')[:50]

    # Get period summaries (last 6 periods)
    period_summaries = []
    if quota.user:
        user_quotas = UserQuota.objects.filter(
            allocation=quota,
            user=quota.user
        ).order_by('-period_start')[:6]

        for user_quota in user_quotas:
            usage_percentage = (user_quota.used_amount / quota.quota_amount * 100) if quota.quota_amount > 0 else 0
            period_summaries.append({
                'period_start': user_quota.period_start,
                'allocated_amount': quota.quota_amount,
                'used_amount': user_quota.used_amount,
                'usage_percentage': usage_percentage,
            })

    context = {
        'quota': quota,
        'current_usage': current_usage,
        'usage_logs': usage_logs,
        'period_summaries': period_summaries,
    }

    return render(request, 'booking/quota_usage_details.html', context)


# Enhanced Single-Level Approval Views

@login_required
@user_passes_test(is_lab_admin)
def approval_delegations_view(request):
    """Manage approval delegations."""
    delegations = ApprovalDelegate.objects.select_related(
        'delegator', 'delegate', 'approval_rule', 'resource', 'created_by'
    ).order_by('-created_at')

    # Apply filters
    status_filter = request.GET.get('status')
    delegator_filter = request.GET.get('delegator')
    delegate_filter = request.GET.get('delegate')

    if status_filter:
        delegations = delegations.filter(status=status_filter)
    if delegator_filter:
        delegations = delegations.filter(delegator_id=delegator_filter)
    if delegate_filter:
        delegations = delegations.filter(delegate_id=delegate_filter)

    # Handle delegation creation
    if request.method == 'POST':
        try:
            delegator_id = request.POST.get('delegator')
            delegate_id = request.POST.get('delegate')
            approval_rule_id = request.POST.get('approval_rule')
            resource_id = request.POST.get('resource')
            delegation_type = request.POST.get('delegation_type')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            reason = request.POST.get('reason')

            delegation = ApprovalDelegate.objects.create(
                delegator_id=delegator_id,
                delegate_id=delegate_id,
                approval_rule_id=approval_rule_id if approval_rule_id else None,
                resource_id=resource_id if resource_id else None,
                delegation_type=delegation_type,
                start_date=start_date,
                end_date=end_date if end_date else None,
                reason=reason,
                created_by=request.user
            )

            messages.success(request, f'Delegation created successfully: {delegation}')
            return redirect('booking:approval_delegations')

        except Exception as e:
            messages.error(request, f'Error creating delegation: {str(e)}')

    # Get data for the form
    users = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
    approval_rules = ApprovalRule.objects.filter(is_active=True).order_by('name')
    resources = Resource.objects.filter(is_active=True).order_by('name')

    context = {
        'delegations': delegations,
        'users': users,
        'approval_rules': approval_rules,
        'resources': resources,
        'delegation_types': ApprovalDelegate.DELEGATION_TYPES,
        'delegation_status': ApprovalDelegate.DELEGATION_STATUS,
    }

    return render(request, 'booking/approval_delegations.html', context)


@login_required
@user_passes_test(is_lab_admin)
def approval_escalations_view(request):
    """Manage approval escalation rules."""
    escalations = ApprovalEscalation.objects.select_related(
        'approval_rule', 'substitute_approver', 'created_by'
    ).order_by('approval_rule__name', 'priority')

    # Handle escalation creation
    if request.method == 'POST':
        try:
            approval_rule_id = request.POST.get('approval_rule')
            timeout_hours = int(request.POST.get('timeout_hours'))
            action = request.POST.get('action')
            substitute_approver_id = request.POST.get('substitute_approver')
            business_hours_only = 'business_hours_only' in request.POST
            priority = int(request.POST.get('priority', 1))

            escalation = ApprovalEscalation.objects.create(
                approval_rule_id=approval_rule_id,
                timeout_hours=timeout_hours,
                action=action,
                substitute_approver_id=substitute_approver_id if substitute_approver_id else None,
                business_hours_only=business_hours_only,
                priority=priority,
                created_by=request.user
            )

            messages.success(request, f'Escalation rule created: {escalation}')
            return redirect('booking:approval_escalations')

        except Exception as e:
            messages.error(request, f'Error creating escalation rule: {str(e)}')

    # Get data for the form
    approval_rules = ApprovalRule.objects.filter(is_active=True).order_by('name')
    users = User.objects.filter(is_active=True).order_by('first_name', 'last_name')

    context = {
        'escalations': escalations,
        'approval_rules': approval_rules,
        'users': users,
        'escalation_actions': ApprovalEscalation.ESCALATION_ACTIONS,
    }

    return render(request, 'booking/approval_escalations.html', context)


@login_required
def single_approval_requests_view(request):
    """View and manage single-level approval requests."""
    # Get approval requests for current user
    if request.user.userprofile.role in ['technician', 'sysadmin']:
        # Admin can see all requests
        approval_requests = SingleApprovalRequest.objects.select_related(
            'booking', 'approval_rule', 'requester', 'assigned_approver', 'current_approver'
        ).order_by('-requested_at')
    else:
        # Regular users see only their assigned or delegated requests
        approval_requests = SingleApprovalRequest.objects.filter(
            Q(current_approver=request.user) | Q(assigned_approver=request.user)
        ).select_related(
            'booking', 'approval_rule', 'requester', 'assigned_approver', 'current_approver'
        ).order_by('-requested_at')

    # Apply filters
    status_filter = request.GET.get('status')
    priority_filter = request.GET.get('priority')
    overdue_filter = request.GET.get('overdue')

    if status_filter:
        approval_requests = approval_requests.filter(status=status_filter)
    if priority_filter:
        approval_requests = approval_requests.filter(priority=priority_filter)
    if overdue_filter == 'true':
        approval_requests = [req for req in approval_requests if req.is_overdue()]

    # Handle approval actions
    if request.method == 'POST':
        action = request.POST.get('action')
        request_id = request.POST.get('request_id')
        comments = request.POST.get('comments', '')

        try:
            approval_request = get_object_or_404(SingleApprovalRequest, id=request_id)

            if action == 'approve':
                approval_request.status = 'approved'
                approval_request.approved_at = timezone.now()
                approval_request.approved_by = request.user
                approval_request.response_comments = comments
                approval_request.save()

                # Update booking status
                approval_request.booking.status = 'approved'
                approval_request.booking.save()

                messages.success(request, f'Approval granted for {approval_request.booking}')

            elif action == 'reject':
                approval_request.status = 'rejected'
                approval_request.approved_at = timezone.now()
                approval_request.approved_by = request.user
                approval_request.response_comments = comments
                approval_request.save()

                # Update booking status
                approval_request.booking.status = 'rejected'
                approval_request.booking.save()

                messages.success(request, f'Approval rejected for {approval_request.booking}')

            elif action == 'delegate':
                delegate_id = request.POST.get('delegate_user')
                if delegate_id:
                    delegate_user = User.objects.get(id=delegate_id)

                    # Check if there's a valid delegation
                    delegation = ApprovalDelegate.objects.filter(
                        delegator=request.user,
                        delegate=delegate_user,
                        status='active'
                    ).first()

                    if delegation and delegation.can_approve(
                        booking=approval_request.booking,
                        approval_rule=approval_request.approval_rule,
                        resource=approval_request.booking.resource
                    ):
                        approval_request.delegate_to(delegate_user, delegation)
                        messages.success(request, f'Approval delegated to {delegate_user.get_full_name()}')
                    else:
                        messages.error(request, 'Invalid delegation or delegate not authorized')

            return redirect('booking:single_approval_requests')

        except Exception as e:
            messages.error(request, f'Error processing approval: {str(e)}')

    context = {
        'approval_requests': approval_requests,
        'approval_status': SingleApprovalRequest.APPROVAL_STATUS,
        'priority_levels': SingleApprovalRequest.PRIORITY_LEVELS,
    }

    return render(request, 'booking/single_approval_requests.html', context)


@login_required
@user_passes_test(is_lab_admin)
def approval_notification_templates_view(request):
    """Manage approval notification templates."""
    templates = ApprovalNotificationTemplate.objects.select_related(
        'approval_rule', 'created_by'
    ).order_by('template_type', 'name')

    # Handle template creation
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            template_type = request.POST.get('template_type')
            approval_rule_id = request.POST.get('approval_rule')
            subject_template = request.POST.get('subject_template')
            body_template = request.POST.get('body_template')
            delivery_method = request.POST.get('delivery_method')

            template = ApprovalNotificationTemplate.objects.create(
                name=name,
                template_type=template_type,
                approval_rule_id=approval_rule_id if approval_rule_id else None,
                subject_template=subject_template,
                body_template=body_template,
                delivery_method=delivery_method,
                created_by=request.user
            )

            messages.success(request, f'Notification template created: {template}')
            return redirect('booking:approval_notification_templates')

        except Exception as e:
            messages.error(request, f'Error creating template: {str(e)}')

    # Get data for the form
    approval_rules = ApprovalRule.objects.filter(is_active=True).order_by('name')

    context = {
        'templates': templates,
        'approval_rules': approval_rules,
        'template_types': ApprovalNotificationTemplate.TEMPLATE_TYPES,
        'delivery_methods': ApprovalNotificationTemplate.DELIVERY_METHODS,
    }

    return render(request, 'booking/approval_notification_templates.html', context)


def process_single_level_approval(booking, approval_rule):
    """Process a single-level approval request."""
    try:
        # Determine the approver
        approvers = list(approval_rule.approvers.all())
        if not approvers:
            # No specific approvers, use default logic
            if approval_rule.user_roles:
                # Find users with required roles
                from django.contrib.auth.models import Group
                approver_groups = Group.objects.filter(name__in=approval_rule.user_roles)
                potential_approvers = User.objects.filter(groups__in=approver_groups, is_active=True).distinct()
                if potential_approvers.exists():
                    approvers = [potential_approvers.first()]

        if not approvers:
            # Fallback to lab admins
            from django.contrib.auth.models import Group
            lab_admin_group = Group.objects.filter(name='Lab Admin').first()
            if lab_admin_group:
                approvers = list(lab_admin_group.user_set.filter(is_active=True))

        if not approvers:
            raise ValueError("No valid approvers found for this approval rule")

        # Select primary approver (could be round-robin, least busy, etc.)
        primary_approver = approvers[0]

        # Calculate due date
        due_date = None
        if hasattr(approval_rule, 'tier_timeout_hours') and approval_rule.tier_timeout_hours:
            due_date = timezone.now() + timedelta(hours=approval_rule.tier_timeout_hours)

        # Create the approval request
        approval_request = SingleApprovalRequest.objects.create(
            booking=booking,
            approval_rule=approval_rule,
            requester=booking.user,
            assigned_approver=primary_approver,
            current_approver=primary_approver,
            due_date=due_date,
            priority='normal'  # Could be determined by booking urgency
        )

        # Update booking status
        booking.status = 'pending_approval'
        booking.save()

        return approval_request

    except Exception as e:
        raise Exception(f"Failed to process single-level approval: {str(e)}")


def check_approval_escalations():
    """Check for overdue approvals and trigger escalations."""
    overdue_requests = SingleApprovalRequest.objects.filter(
        status__in=['pending', 'delegated'],
        due_date__lt=timezone.now()
    ).select_related('approval_rule')

    for request in overdue_requests:
        escalations = ApprovalEscalation.objects.filter(
            approval_rule=request.approval_rule,
            is_active=True
        ).order_by('priority', 'timeout_hours')

        for escalation in escalations:
            # Check if enough time has passed for this escalation
            time_since_request = timezone.now() - request.requested_at
            hours_since_request = time_since_request.total_seconds() / 3600

            if hours_since_request >= escalation.timeout_hours:
                # Trigger escalation
                if escalation.action == 'notify':
                    # Send notification reminder
                    request.reminders_sent += 1
                    request.last_reminder_sent = timezone.now()
                    request.save()

                elif escalation.action == 'delegate' and escalation.substitute_approver:
                    # Auto-delegate to substitute
                    request.escalate_to(escalation.substitute_approver, f"Auto-escalated after {escalation.timeout_hours} hours")

                elif escalation.action == 'auto_approve':
                    # Auto-approve with conditions
                    request.status = 'approved'
                    request.approved_at = timezone.now()
                    request.response_comments = f"Auto-approved due to escalation after {escalation.timeout_hours} hours"
                    request.save()

                    request.booking.status = 'approved'
                    request.booking.save()

                elif escalation.action in ['escalate_manager', 'escalate_admin']:
                    # Escalate to higher authority
                    if escalation.substitute_approver:
                        request.escalate_to(escalation.substitute_approver, f"Escalated to {escalation.get_action_display()}")

                break  # Only apply the first matching escalation


@login_required
@user_passes_test(is_lab_admin)
def tiered_approval_action_view(request, approval_id):
    """Handle tiered approval actions (approve, reject, delegate)."""
    try:
        booking_approval = get_object_or_404(BookingApproval, id=approval_id)

        if request.method == 'POST':
            action = request.POST.get('action')
            comments = request.POST.get('comments', '')

            if action in ['approve', 'reject', 'delegate']:
                result = process_tier_approval(approval_id, request.user, action, comments)
                if result:
                    messages.success(request, f"Approval {action}d successfully.")
                else:
                    messages.error(request, f"Failed to {action} approval.")
            else:
                messages.error(request, "Invalid action.")

            return redirect('booking:booking_approval_details', booking_id=booking_approval.booking.id)

        context = {
            'approval': booking_approval,
            'booking': booking_approval.booking,
        }
        return render(request, 'booking/tiered_approval_action.html', context)

    except Exception as e:
        messages.error(request, f"Error processing approval action: {str(e)}")
        return redirect('booking:approval_dashboard')


@login_required
def my_pending_approvals_view(request):
    """Display pending approvals for the current user."""
    try:
        # Get tiered approvals where user is current approver
        tiered_approvals = BookingApproval.objects.filter(
            current_tier__tier_approvers=request.user,
            status='pending'
        ).select_related('booking', 'approval_rule').order_by('-requested_at')

        # Get single approval requests assigned to user
        single_approvals = SingleApprovalRequest.objects.filter(
            current_approver=request.user,
            status__in=['pending', 'delegated']
        ).select_related('booking', 'approval_rule').order_by('-requested_at')

        context = {
            'tiered_approvals': tiered_approvals,
            'single_approvals': single_approvals,
            'total_pending': tiered_approvals.count() + single_approvals.count(),
        }
        return render(request, 'booking/my_pending_approvals.html', context)

    except Exception as e:
        messages.error(request, f"Error loading pending approvals: {str(e)}")
        return render(request, 'booking/my_pending_approvals.html', {'error': str(e)})


@login_required
def booking_approval_details_view(request, booking_id):
    """Display detailed approval information for a booking."""
    try:
        booking = get_object_or_404(Booking, id=booking_id)

        # Check if user has permission to view this booking's approval details
        if not (request.user == booking.user or is_lab_admin(request.user)):
            messages.error(request, "You don't have permission to view this booking's approval details.")
            return redirect('booking:dashboard')

        # Get tiered approval details
        booking_approval = BookingApproval.objects.filter(booking=booking).first()
        approval_tiers = []
        if booking_approval:
            approval_tiers = ApprovalTier.objects.filter(
                booking_approval=booking_approval
            ).order_by('tier_level')

        # Get single approval requests
        single_approval = SingleApprovalRequest.objects.filter(booking=booking).first()

        context = {
            'booking': booking,
            'booking_approval': booking_approval,
            'approval_tiers': approval_tiers,
            'single_approval': single_approval,
            'can_edit': is_lab_admin(request.user),
        }
        return render(request, 'booking/booking_approval_details.html', context)

    except Exception as e:
        messages.error(request, f"Error loading approval details: {str(e)}")
        return redirect('booking:dashboard')

