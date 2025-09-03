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
    ApprovalRule, UserTraining, TrainingRequest, ApprovalStatistics
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
# License feature removed - all features now available
def approval_statistics_view(request):
    """User-friendly approval statistics dashboard."""
    from booking.models import ApprovalStatistics, AccessRequest, TrainingRequest
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