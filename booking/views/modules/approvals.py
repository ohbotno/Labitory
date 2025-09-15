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
    ApprovalRule, UserTraining, ApprovalStatistics, Booking
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
    from booking.models import ApprovalStatistics, AccessRequest
    from django.db.models import Avg, Sum, Count
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
    
    # Base queryset for statistics
    stats_qs = ApprovalStatistics.objects.filter(
        period_start__gte=start_date,
        period_end__lte=end_date,
        period_type=period_type
    )
    
    # Filter by resource if specified
    if resource_filter:
        stats_qs = stats_qs.filter(resource_id=resource_filter)
    
    # Only show statistics for resources the user has responsibility for (unless admin)
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        stats_qs = stats_qs.filter(resource__responsible_persons__user=request.user)
    
    # Calculate summary statistics
    summary_data = stats_qs.aggregate(
        total_requests=Sum('access_requests_received'),
        total_approved=Sum('access_requests_approved'),
        total_rejected=Sum('access_requests_rejected'),
        total_pending=Sum('access_requests_pending'),
        avg_response_time=Avg('avg_response_time_hours'),
        total_overdue=Sum('overdue_items'),
        total_training_requests=Sum('training_requests_received'),
        total_training_completions=Sum('training_completions'),
        total_assessments=Sum('assessments_created'),
    )
    
    # Calculate approval rate
    total_processed = (summary_data['total_approved'] or 0) + (summary_data['total_rejected'] or 0)
    approval_rate = (summary_data['total_approved'] or 0) / total_processed * 100 if total_processed > 0 else 0
    
    # Calculate trends (comparing to previous period)
    previous_start = start_date - (end_date - start_date)
    previous_end = start_date - timedelta(days=1)
    
    previous_stats = ApprovalStatistics.objects.filter(
        period_start__gte=previous_start,
        period_end__lte=previous_end,
        period_type=period_type
    )
    
    if resource_filter:
        previous_stats = previous_stats.filter(resource_id=resource_filter)
    
    if not request.user.userprofile.role in ['technician', 'sysadmin']:
        previous_stats = previous_stats.filter(resource__responsible_persons__user=request.user)
    
    previous_data = previous_stats.aggregate(
        prev_total_requests=Sum('access_requests_received'),
        prev_total_approved=Sum('access_requests_approved'),
        prev_total_rejected=Sum('access_requests_rejected'),
        prev_avg_response_time=Avg('avg_response_time_hours'),
        prev_total_overdue=Sum('overdue_items'),
    )
    
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
    for stat in stats_qs.select_related('resource', 'approver'):
        total_requests = stat.access_requests_received
        approved = stat.access_requests_approved
        rejected = stat.access_requests_rejected
        processed = approved + rejected
        
        resource_stats.append({
            'resource_name': stat.resource.name,
            'approver_name': stat.approver.get_full_name() or stat.approver.username,
            'total_requests': total_requests,
            'approved': approved,
            'rejected': rejected,
            'approval_rate': (approved / processed * 100) if processed > 0 else 0,
            'avg_response_time': stat.avg_response_time_hours,
            'overdue': stat.overdue_items,
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
    timeline_stats = stats_qs.order_by('period_start').values('period_start', 'avg_response_time_hours')
    timeline_labels = [stat['period_start'].strftime('%m/%d') for stat in timeline_stats]
    timeline_data = [stat['avg_response_time_hours'] for stat in timeline_stats]
    
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
            if not all([name, approval_type]):
                messages.error(request, "Please fill in all required fields.")
                return redirect('booking:approval_rules')
            
            # Get related objects
            resource = None
            if resource_id:
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
                user_role=user_role if user_role else None,
                priority=priority,
                fallback_rule=fallback_rule,
                condition_type=condition_type if approval_type == 'conditional' else 'role_based',
                conditional_logic=conditional_logic,
                is_active=True,
                created_by=request.user
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