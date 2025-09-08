"""
Billing views for the Labitory.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Sum, Count, F, Avg
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from datetime import datetime, timedelta
import csv
import json
from decimal import Decimal

from booking.models import (
    BillingPeriod, BillingRate, BillingRecord, DepartmentBilling,
    Resource, Department, UserProfile
)
from booking.forms.billing import BillingRateForm


def is_lab_admin(user):
    """Check if user has lab admin permissions."""
    if not user.is_authenticated:
        return False
    try:
        return user.userprofile.role in ['technician', 'sysadmin'] or user.is_superuser
    except:
        return user.is_superuser


@login_required
@user_passes_test(is_lab_admin)
def billing_dashboard(request):
    """Main billing dashboard showing overview and current period summary."""
    current_period = BillingPeriod.get_current_period()
    
    context = {
        'current_period': current_period,
        'total_periods': BillingPeriod.objects.count(),
        'active_rates': BillingRate.objects.filter(is_active=True).count(),
        'billable_resources': Resource.objects.filter(is_billable=True).count(),
    }
    
    if current_period:
        # Current period statistics
        period_stats = {
            'total_charges': current_period.total_charges,
            'total_hours': current_period.total_hours,
            'total_sessions': current_period.billing_records.count(),
            'departments_charged': current_period.billing_records.values('department').distinct().count()
        }
        context['period_stats'] = period_stats
        
        # Top departments by charges
        top_departments = DepartmentBilling.objects.filter(
            billing_period=current_period
        ).order_by('-total_charges')[:10]
        context['top_departments'] = top_departments
        
        # Recent billing records
        recent_records = BillingRecord.objects.filter(
            billing_period=current_period
        ).select_related('resource', 'user', 'department').order_by('-created_at')[:20]
        context['recent_records'] = recent_records
        
        # Status breakdown
        status_breakdown = BillingRecord.objects.filter(
            billing_period=current_period
        ).values('status').annotate(
            count=Count('id'),
            total_charges=Sum('total_charge')
        )
        context['status_breakdown'] = list(status_breakdown)
    
    return render(request, 'booking/billing/dashboard.html', context)


@login_required
@user_passes_test(is_lab_admin)
def billing_periods(request):
    """Manage billing periods."""
    periods = BillingPeriod.objects.all().order_by('-start_date')
    paginator = Paginator(periods, 25)
    page = request.GET.get('page', 1)
    periods = paginator.get_page(page)
    
    return render(request, 'booking/billing/periods.html', {
        'periods': periods
    })


@login_required
@user_passes_test(is_lab_admin)
def billing_period_detail(request, period_id):
    """View details for a specific billing period."""
    period = get_object_or_404(BillingPeriod, id=period_id)
    
    # Department summaries for this period
    dept_summaries = DepartmentBilling.objects.filter(
        billing_period=period
    ).select_related('department').order_by('-total_charges')
    
    # Billing records for this period
    records = BillingRecord.objects.filter(
        billing_period=period
    ).select_related('resource', 'user', 'department').order_by('-session_start')
    
    # Filter by department if requested
    dept_filter = request.GET.get('department')
    if dept_filter:
        records = records.filter(department_id=dept_filter)
        dept_summaries = dept_summaries.filter(department_id=dept_filter)
    
    # Filter by status if requested
    status_filter = request.GET.get('status')
    if status_filter:
        records = records.filter(status=status_filter)
    
    # Paginate records
    paginator = Paginator(records, 50)
    page = request.GET.get('page', 1)
    records = paginator.get_page(page)
    
    # Get available departments for filtering
    departments = Department.objects.filter(
        billing_records__billing_period=period
    ).distinct().order_by('name')
    
    context = {
        'period': period,
        'dept_summaries': dept_summaries,
        'records': records,
        'departments': departments,
        'dept_filter': dept_filter,
        'status_filter': status_filter,
    }
    
    return render(request, 'booking/billing/period_detail.html', context)


@login_required
@user_passes_test(is_lab_admin)
def department_billing(request, department_id, period_id=None):
    """View billing for a specific department."""
    department = get_object_or_404(Department, id=department_id)
    
    if period_id:
        period = get_object_or_404(BillingPeriod, id=period_id)
        periods = [period]
    else:
        # Show recent periods
        periods = BillingPeriod.objects.order_by('-start_date')[:12]
    
    # Get billing summaries for this department
    summaries = DepartmentBilling.objects.filter(
        department=department,
        billing_period__in=periods
    ).select_related('billing_period').order_by('-billing_period__start_date')
    
    # Get recent billing records
    recent_records = BillingRecord.objects.filter(
        department=department
    ).select_related('resource', 'user', 'billing_period').order_by('-session_start')[:50]
    
    context = {
        'department': department,
        'summaries': summaries,
        'recent_records': recent_records,
        'selected_period': period if period_id else None,
    }
    
    return render(request, 'booking/billing/department_detail.html', context)


@login_required
@user_passes_test(is_lab_admin)
def billing_rates(request):
    """Manage billing rates."""
    rates = BillingRate.objects.all().select_related('resource', 'department').order_by('resource__name', '-priority')
    
    # Filter by resource if requested
    resource_filter = request.GET.get('resource')
    if resource_filter:
        rates = rates.filter(resource_id=resource_filter)
    
    # Filter by active status
    active_filter = request.GET.get('active')
    if active_filter == 'true':
        rates = rates.filter(is_active=True)
    elif active_filter == 'false':
        rates = rates.filter(is_active=False)
    
    paginator = Paginator(rates, 50)
    page = request.GET.get('page', 1)
    rates = paginator.get_page(page)
    
    # Get billable resources for filtering
    resources = Resource.objects.filter(is_billable=True).order_by('name')
    
    context = {
        'rates': rates,
        'resources': resources,
        'resource_filter': resource_filter,
        'active_filter': active_filter,
    }
    
    return render(request, 'booking/billing/rates.html', context)


@login_required
@user_passes_test(is_lab_admin)
def billing_records(request):
    """View and manage billing records."""
    records = BillingRecord.objects.all().select_related(
        'resource', 'user', 'department', 'billing_period'
    ).order_by('-session_start')
    
    # Apply filters
    period_filter = request.GET.get('period')
    if period_filter:
        records = records.filter(billing_period_id=period_filter)
    
    status_filter = request.GET.get('status')
    if status_filter:
        records = records.filter(status=status_filter)
    
    department_filter = request.GET.get('department')
    if department_filter:
        records = records.filter(department_id=department_filter)
    
    resource_filter = request.GET.get('resource')
    if resource_filter:
        records = records.filter(resource_id=resource_filter)
    
    # Date range filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        records = records.filter(session_start__date__gte=date_from)
    if date_to:
        records = records.filter(session_start__date__lte=date_to)
    
    # Paginate
    paginator = Paginator(records, 50)
    page = request.GET.get('page', 1)
    records = paginator.get_page(page)
    
    # Get filter options
    periods = BillingPeriod.objects.order_by('-start_date')
    departments = Department.objects.order_by('name')
    resources = Resource.objects.filter(is_billable=True).order_by('name')
    
    context = {
        'records': records,
        'periods': periods,
        'departments': departments,
        'resources': resources,
        'filters': {
            'period': period_filter,
            'status': status_filter,
            'department': department_filter,
            'resource': resource_filter,
            'date_from': date_from,
            'date_to': date_to,
        }
    }
    
    return render(request, 'booking/billing/records.html', context)


@login_required
@user_passes_test(is_lab_admin)
def export_billing_data(request):
    """Export billing data to CSV."""
    export_type = request.GET.get('type', 'records')
    period_id = request.GET.get('period')
    department_id = request.GET.get('department')
    
    response = HttpResponse(content_type='text/csv')
    
    if export_type == 'records':
        # Export billing records
        filename = 'billing_records'
        records = BillingRecord.objects.select_related(
            'resource', 'user', 'department', 'billing_period'
        ).order_by('-session_start')
        
        if period_id:
            records = records.filter(billing_period_id=period_id)
            period = BillingPeriod.objects.get(id=period_id)
            filename += f'_{period.name.replace(" ", "_")}'
        
        if department_id:
            records = records.filter(department_id=department_id)
            dept = Department.objects.get(id=department_id)
            filename += f'_{dept.name.replace(" ", "_")}'
        
        response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Date', 'Resource', 'User', 'Department', 'Start Time', 'End Time',
            'Duration (min)', 'Billable Hours', 'Rate Applied', 'Total Charge',
            'Status', 'Project Code', 'Cost Center'
        ])
        
        for record in records:
            writer.writerow([
                record.session_start.date(),
                record.resource.name,
                record.user.get_full_name() or record.user.username,
                record.department.name if record.department else '',
                record.session_start.strftime('%Y-%m-%d %H:%M'),
                record.session_end.strftime('%Y-%m-%d %H:%M'),
                record.duration_minutes,
                record.billable_hours,
                f'£{record.hourly_rate_applied}',
                f'£{record.total_charge}',
                record.get_status_display(),
                record.project_code or '',
                record.cost_center or '',
            ])
    
    elif export_type == 'departments':
        # Export department summaries
        filename = 'department_billing'
        summaries = DepartmentBilling.objects.select_related(
            'department', 'billing_period'
        ).order_by('-billing_period__start_date', 'department__name')
        
        if period_id:
            summaries = summaries.filter(billing_period_id=period_id)
            period = BillingPeriod.objects.get(id=period_id)
            filename += f'_{period.name.replace(" ", "_")}'
        
        response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'Billing Period', 'Department', 'Total Sessions', 'Total Hours',
            'Total Charges', 'Draft Charges', 'Confirmed Charges', 'Billed Charges'
        ])
        
        for summary in summaries:
            writer.writerow([
                summary.billing_period.name,
                summary.department.name,
                summary.total_sessions,
                summary.total_hours,
                f'£{summary.total_charges}',
                f'£{summary.draft_charges}',
                f'£{summary.confirmed_charges}',
                f'£{summary.billed_charges}',
            ])
    
    return response


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["POST"])
def create_monthly_period(request):
    """Create a new monthly billing period."""
    try:
        year = int(request.POST.get('year'))
        month = int(request.POST.get('month'))
        
        # Check if period already exists
        start_date = datetime(year, month, 1).date()
        if BillingPeriod.objects.filter(start_date=start_date, period_type='monthly').exists():
            messages.error(request, f'A monthly billing period for {month}/{year} already exists.')
            return redirect('booking:billing_periods')
        
        period = BillingPeriod.create_monthly_period(year, month, request.user)
        messages.success(request, f'Created billing period: {period.name}')
        
    except ValueError:
        messages.error(request, 'Invalid year or month provided.')
    except Exception as e:
        messages.error(request, f'Error creating billing period: {str(e)}')
    
    return redirect('booking:billing_periods')


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["POST"])
def close_billing_period(request, period_id):
    """Close a billing period."""
    period = get_object_or_404(BillingPeriod, id=period_id)
    
    if period.status == 'closed':
        messages.warning(request, f'Billing period {period.name} is already closed.')
    else:
        period.close_period(request.user)
        messages.success(request, f'Closed billing period: {period.name}')
    
    return redirect('billing_period_detail', period_id=period.id)


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["POST"])
def confirm_billing_records(request):
    """Bulk confirm billing records."""
    record_ids = request.POST.getlist('record_ids')
    
    if not record_ids:
        messages.warning(request, 'No records selected.')
        return redirect(request.META.get('HTTP_REFERER', 'billing_records'))
    
    records = BillingRecord.objects.filter(id__in=record_ids, status='draft')
    count = 0
    
    for record in records:
        record.confirm(request.user)
        count += 1
    
    messages.success(request, f'Confirmed {count} billing records.')
    return redirect(request.META.get('HTTP_REFERER', 'billing_records'))


@login_required
@user_passes_test(is_lab_admin)
def billing_analytics(request):
    """Billing analytics and reports."""
    # Get date range from request or default to last 3 months
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=90)
    
    if request.GET.get('start_date'):
        start_date = datetime.strptime(request.GET.get('start_date'), '%Y-%m-%d').date()
    if request.GET.get('end_date'):
        end_date = datetime.strptime(request.GET.get('end_date'), '%Y-%m-%d').date()
    
    # Overall statistics
    records = BillingRecord.objects.filter(
        session_start__date__gte=start_date,
        session_start__date__lte=end_date
    )
    
    stats = {
        'total_sessions': records.count(),
        'total_charges': records.aggregate(total=Sum('total_charge'))['total'] or Decimal('0'),
        'total_hours': records.aggregate(total=Sum('billable_hours'))['total'] or Decimal('0'),
        'avg_charge_per_session': records.aggregate(avg=Avg('total_charge'))['avg'] or Decimal('0'),
        'unique_users': records.values('user').distinct().count(),
        'unique_resources': records.values('resource').distinct().count(),
    }
    
    # Top resources by usage
    top_resources = records.values('resource__name').annotate(
        sessions=Count('id'),
        total_charges=Sum('total_charge'),
        total_hours=Sum('billable_hours')
    ).order_by('-total_charges')[:10]
    
    # Top departments by charges
    top_departments = records.values('department__name').annotate(
        sessions=Count('id'),
        total_charges=Sum('total_charge'),
        total_hours=Sum('billable_hours')
    ).order_by('-total_charges')[:10]
    
    # Usage by day of week
    usage_by_weekday = records.extra(
        select={'weekday': 'strftime("%%w", session_start)'}
    ).values('weekday').annotate(
        sessions=Count('id'),
        total_charges=Sum('total_charge')
    ).order_by('weekday')
    
    # Convert weekday numbers to names
    weekday_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    for item in usage_by_weekday:
        item['weekday_name'] = weekday_names[int(item['weekday'])]
    
    context = {
        'start_date': start_date,
        'end_date': end_date,
        'stats': stats,
        'top_resources': top_resources,
        'top_departments': top_departments,
        'usage_by_weekday': usage_by_weekday,
    }
    
    return render(request, 'booking/billing/analytics.html', context)


@login_required
@user_passes_test(is_lab_admin)
def user_billing_history(request, user_id):
    """View billing history for a specific user."""
    from django.contrib.auth.models import User
    
    user = get_object_or_404(User, id=user_id)
    
    records = BillingRecord.objects.filter(
        user=user
    ).select_related('resource', 'department', 'billing_period').order_by('-session_start')
    
    # Paginate
    paginator = Paginator(records, 50)
    page = request.GET.get('page', 1)
    records = paginator.get_page(page)
    
    # Calculate totals
    totals = BillingRecord.objects.filter(user=user).aggregate(
        total_charges=Sum('total_charge'),
        total_hours=Sum('billable_hours'),
        total_sessions=Count('id')
    )
    
    context = {
        'target_user': user,
        'records': records,
        'totals': totals,
    }
    
    return render(request, 'booking/billing/user_history.html', context)


@login_required
@user_passes_test(is_lab_admin)
def create_billing_rate(request):
    """Create a new billing rate."""
    if request.method == 'POST':
        form = BillingRateForm(request.POST)
        if form.is_valid():
            form._user = request.user  # Set user for the form to use in save()
            rate = form.save()
            messages.success(request, f'Billing rate created successfully for {rate.resource.name}.')
            return redirect('booking:billing_rates')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BillingRateForm()
    
    context = {
        'form': form,
        'title': 'Create Billing Rate',
        'submit_text': 'Create Rate'
    }
    
    return render(request, 'booking/billing/rate_form.html', context)


@login_required
@user_passes_test(is_lab_admin)
def edit_billing_rate(request, rate_id):
    """Edit an existing billing rate."""
    rate = get_object_or_404(BillingRate, id=rate_id)
    
    if request.method == 'POST':
        form = BillingRateForm(request.POST, instance=rate)
        if form.is_valid():
            rate = form.save()
            messages.success(request, f'Billing rate updated successfully for {rate.resource.name}.')
            return redirect('booking:billing_rates')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = BillingRateForm(instance=rate)
    
    context = {
        'form': form,
        'rate': rate,
        'title': f'Edit Billing Rate - {rate.resource.name}',
        'submit_text': 'Update Rate'
    }
    
    return render(request, 'booking/billing/rate_form.html', context)


@login_required
@user_passes_test(is_lab_admin)
@require_http_methods(["POST"])
def delete_billing_rate(request, rate_id):
    """Delete a billing rate."""
    rate = get_object_or_404(BillingRate, id=rate_id)
    resource_name = rate.resource.name
    rate.delete()
    messages.success(request, f'Billing rate for {resource_name} has been deleted.')
    return redirect('booking:billing_rates')