# booking/views/modules/issues.py
"""
Issue management views for the Aperture Booking system.

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

from ...models import Resource, Booking, ResourceIssue
from booking.forms import ResourceIssueReportForm, ResourceIssueUpdateForm, IssueFilterForm


@login_required
def report_resource_issue(request, resource_id):
    """Allow users to report issues with a resource."""
    resource = get_object_or_404(Resource, id=resource_id)
    booking_id = request.GET.get('booking')
    booking = None
    
    if booking_id:
        booking = get_object_or_404(Booking, id=booking_id, user=request.user)
    
    if request.method == 'POST':
        form = ResourceIssueReportForm(
            request.POST, 
            request.FILES,
            user=request.user,
            resource=resource,
            booking=booking
        )
        if form.is_valid():
            issue = form.save()
            messages.success(
                request, 
                f'Issue reported successfully. Reference #: {issue.id}'
            )
            return redirect('booking:resource_detail', resource_id=resource.id)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ResourceIssueReportForm(
            user=request.user,
            resource=resource,
            booking=booking
        )
    
    return render(request, 'booking/report_issue.html', {
        'form': form,
        'resource': resource,
        'booking': booking,
    })


@login_required
@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role in ['technician', 'sysadmin'])
def issues_dashboard(request):
    """Dashboard for managing resource issues."""
    filter_form = IssueFilterForm(request.GET)
    issues = ResourceIssue.objects.select_related('resource', 'reported_by', 'assigned_to').all()
    
    # Apply filters
    if filter_form.is_valid():
        if filter_form.cleaned_data.get('resource'):
            issues = issues.filter(resource=filter_form.cleaned_data['resource'])
        if filter_form.cleaned_data.get('status'):
            issues = issues.filter(status=filter_form.cleaned_data['status'])
        if filter_form.cleaned_data.get('severity'):
            issues = issues.filter(severity=filter_form.cleaned_data['severity'])
        if filter_form.cleaned_data.get('category'):
            issues = issues.filter(category=filter_form.cleaned_data['category'])
        if filter_form.cleaned_data.get('assigned_to'):
            issues = issues.filter(assigned_to=filter_form.cleaned_data['assigned_to'])
        if filter_form.cleaned_data.get('is_overdue'):
            # Filter for overdue issues (this would need a more complex query)
            pass
        if filter_form.cleaned_data.get('date_from'):
            issues = issues.filter(created_at__gte=filter_form.cleaned_data['date_from'])
        if filter_form.cleaned_data.get('date_to'):
            issues = issues.filter(created_at__lte=filter_form.cleaned_data['date_to'])
    
    # Statistics
    stats = {
        'total': issues.count(),
        'open': issues.filter(status='open').count(),
        'in_progress': issues.filter(status='in_progress').count(),
        'critical': issues.filter(severity='critical').count(),
        'overdue': sum(1 for issue in issues if issue.is_overdue),
    }
    
    # Pagination
    paginator = Paginator(issues, 25)
    page = request.GET.get('page')
    issues = paginator.get_page(page)
    
    return render(request, 'booking/issues_dashboard.html', {
        'issues': issues,
        'filter_form': filter_form,
        'stats': stats,
    })


@login_required
@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role in ['technician', 'sysadmin'])
def issue_detail(request, issue_id):
    """View and update a specific issue."""
    issue = get_object_or_404(ResourceIssue, id=issue_id)
    
    if request.method == 'POST':
        form = ResourceIssueUpdateForm(request.POST, instance=issue)
        if form.is_valid():
            form.save()
            messages.success(request, 'Issue updated successfully.')
            return redirect('booking:issue_detail', issue_id=issue.id)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ResourceIssueUpdateForm(instance=issue)
    
    return render(request, 'booking/issue_detail.html', {
        'issue': issue,
        'form': form,
    })


@login_required
def my_reported_issues(request):
    """View issues reported by the current user."""
    issues = ResourceIssue.objects.filter(
        reported_by=request.user
    ).select_related('resource', 'assigned_to').order_by('-created_at')
    
    # Pagination
    paginator = Paginator(issues, 20)
    page = request.GET.get('page')
    issues = paginator.get_page(page)
    
    return render(request, 'booking/my_issues.html', {
        'issues': issues,
    })