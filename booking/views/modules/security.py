# booking/views/modules/security.py
"""
Security-related views for site administration.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_protect
from django.conf import settings
import json
from datetime import datetime, timedelta
import csv

from ...models import (
    APIToken, SecurityEvent, AuditLog, DataAccessLog, 
    LoginAttempt, AdminAction, UserProfile
)
from ...forms.security import (
    APITokenCreateForm, APITokenSearchForm, SecurityEventFilterForm,
    GDPRRequestForm, DataExportForm
)
from ...api.authentication import generate_jwt_tokens, revoke_token, revoke_all_user_tokens
from ...utils.security_utils import get_client_ip


def is_site_admin(user):
    """Check if user is a site administrator."""
    if not user.is_authenticated:
        return False
    try:
        return user.userprofile.role in ['sysadmin', 'technician']
    except (UserProfile.DoesNotExist, AttributeError):
        return user.is_superuser


@login_required
@user_passes_test(is_site_admin, login_url='/accounts/login/')
def security_dashboard_view(request):
    """
    Main security dashboard showing overview of security metrics.
    """
    # Calculate metrics for the last 30 days
    thirty_days_ago = timezone.now() - timedelta(days=30)
    
    # Security metrics
    total_api_tokens = APIToken.objects.filter(is_revoked=False).count()
    active_sessions = LoginAttempt.objects.filter(
        attempt_type='SUCCESS',
        timestamp__gte=thirty_days_ago
    ).values('user').distinct().count()
    
    security_events_count = SecurityEvent.objects.filter(
        timestamp__gte=thirty_days_ago
    ).count()
    
    failed_login_attempts = LoginAttempt.objects.filter(
        attempt_type__in=['FAILED_PASSWORD', 'FAILED_USERNAME', 'FAILED_2FA'],
        timestamp__gte=thirty_days_ago
    ).count()
    
    # Recent security events
    recent_security_events = SecurityEvent.objects.select_related('user').order_by('-timestamp')[:10]
    
    # Login attempt trends (last 7 days)
    seven_days_ago = timezone.now() - timedelta(days=7)
    login_trends = []
    for i in range(7):
        day = timezone.now() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        successful_logins = LoginAttempt.objects.filter(
            attempt_type='SUCCESS',
            timestamp__gte=day_start,
            timestamp__lt=day_end
        ).count()
        
        failed_logins = LoginAttempt.objects.filter(
            attempt_type__in=['FAILED_PASSWORD', 'FAILED_USERNAME'],
            timestamp__gte=day_start,
            timestamp__lt=day_end
        ).count()
        
        login_trends.append({
            'date': day_start.strftime('%Y-%m-%d'),
            'successful': successful_logins,
            'failed': failed_logins
        })
    
    # Top security event types
    event_types = SecurityEvent.objects.filter(
        timestamp__gte=thirty_days_ago
    ).values('event_type').annotate(count=Count('id')).order_by('-count')[:5]
    
    context = {
        'total_api_tokens': total_api_tokens,
        'active_sessions': active_sessions,
        'security_events_count': security_events_count,
        'failed_login_attempts': failed_login_attempts,
        'recent_security_events': recent_security_events,
        'login_trends': json.dumps(login_trends[::-1]),  # Reverse for chronological order
        'event_types': list(event_types),
    }
    
    return render(request, 'booking/site_admin_security_dashboard.html', context)


@login_required
@user_passes_test(is_site_admin, login_url='/accounts/login/')
def api_tokens_management_view(request):
    """
    API token management interface.
    """
    search_form = APITokenSearchForm(request.GET or None)
    
    # Get all tokens with user information
    tokens = APIToken.objects.select_related('user').all().order_by('-created_at')
    
    # Apply search filters
    if search_form.is_valid():
        if search_form.cleaned_data['username']:
            tokens = tokens.filter(
                user__username__icontains=search_form.cleaned_data['username']
            )
        
        if search_form.cleaned_data['token_type']:
            tokens = tokens.filter(token_type=search_form.cleaned_data['token_type'])
        
        if search_form.cleaned_data['status']:
            if search_form.cleaned_data['status'] == 'active':
                tokens = tokens.filter(is_revoked=False, expires_at__gt=timezone.now())
            elif search_form.cleaned_data['status'] == 'expired':
                tokens = tokens.filter(expires_at__lte=timezone.now())
            elif search_form.cleaned_data['status'] == 'revoked':
                tokens = tokens.filter(is_revoked=True)
    
    # Pagination
    paginator = Paginator(tokens, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Token statistics
    stats = {
        'total': APIToken.objects.count(),
        'active': APIToken.objects.filter(is_revoked=False, expires_at__gt=timezone.now()).count(),
        'expired': APIToken.objects.filter(expires_at__lte=timezone.now()).count(),
        'revoked': APIToken.objects.filter(is_revoked=True).count(),
    }
    
    context = {
        'page_obj': page_obj,
        'search_form': search_form,
        'stats': stats,
    }
    
    return render(request, 'booking/site_admin_api_tokens.html', context)


@login_required
@user_passes_test(is_site_admin, login_url='/accounts/login/')
@require_POST
@csrf_protect
def api_token_revoke_view(request):
    """
    Revoke an API token via AJAX.
    """
    token_jti = request.POST.get('token_jti')
    
    if not token_jti:
        return JsonResponse({'success': False, 'error': 'Token JTI required'})
    
    try:
        token = APIToken.objects.get(jti=token_jti)
        token.revoke()
        
        # Log admin action
        AdminAction.objects.create(
            admin_user=request.user,
            action_type='TOKEN_REVOKED',
            target_user=token.user,
            description=f'API token revoked by admin: {token_jti}',
            ip_address=get_client_ip(request),
            old_values={'revoked': False},
            new_values={'revoked': True},
        )
        
        return JsonResponse({'success': True, 'message': 'Token revoked successfully'})
    
    except APIToken.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Token not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_site_admin, login_url='/accounts/login/')
@require_POST
@csrf_protect
def api_token_revoke_all_user_view(request):
    """
    Revoke all tokens for a specific user.
    """
    user_id = request.POST.get('user_id')
    
    if not user_id:
        return JsonResponse({'success': False, 'error': 'User ID required'})
    
    try:
        user = User.objects.get(id=user_id)
        revoke_all_user_tokens(user)
        
        # Log admin action
        AdminAction.objects.create(
            admin_user=request.user,
            action_type='TOKEN_REVOKED',
            target_user=user,
            description=f'All API tokens revoked for user: {user.username}',
            ip_address=get_client_ip(request),
        )
        
        return JsonResponse({'success': True, 'message': f'All tokens revoked for {user.username}'})
    
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_site_admin, login_url='/accounts/login/')
def security_events_view(request):
    """
    Security events monitoring interface.
    """
    filter_form = SecurityEventFilterForm(request.GET or None)
    
    # Get security events
    events = SecurityEvent.objects.select_related('user').all().order_by('-timestamp')
    
    # Apply filters
    if filter_form.is_valid():
        if filter_form.cleaned_data['event_type']:
            events = events.filter(event_type=filter_form.cleaned_data['event_type'])
        
        if filter_form.cleaned_data['username']:
            events = events.filter(
                user__username__icontains=filter_form.cleaned_data['username']
            )
        
        if filter_form.cleaned_data['ip_address']:
            events = events.filter(ip_address=filter_form.cleaned_data['ip_address'])
        
        if filter_form.cleaned_data['date_from']:
            events = events.filter(timestamp__gte=filter_form.cleaned_data['date_from'])
        
        if filter_form.cleaned_data['date_to']:
            events = events.filter(timestamp__lte=filter_form.cleaned_data['date_to'])
    
    # Pagination
    paginator = Paginator(events, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'filter_form': filter_form,
    }
    
    return render(request, 'booking/site_admin_security_events.html', context)


@login_required
@user_passes_test(is_site_admin, login_url='/accounts/login/')
def gdpr_management_view(request):
    """
    GDPR data management interface.
    """
    # Get data access logs for monitoring
    recent_access = DataAccessLog.objects.select_related('user').order_by('-timestamp')[:20]
    
    # Get export requests (we'll create a model for these)
    # For now, show recent admin actions related to data export
    export_actions = AdminAction.objects.filter(
        action_type='DATA_EXPORT'
    ).select_related('admin_user', 'target_user').order_by('-timestamp')[:10]
    
    context = {
        'recent_access': recent_access,
        'export_actions': export_actions,
    }
    
    return render(request, 'booking/site_admin_gdpr.html', context)


@login_required
@user_passes_test(is_site_admin, login_url='/accounts/login/')
def export_user_data_view(request, user_id):
    """
    Export all data for a specific user (GDPR compliance).
    """
    user = get_object_or_404(User, id=user_id)
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="user_data_{user.username}_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    
    # Write user basic information
    writer.writerow(['User Information'])
    writer.writerow(['Field', 'Value'])
    writer.writerow(['Username', user.username])
    writer.writerow(['Email', user.email])
    writer.writerow(['First Name', user.first_name])
    writer.writerow(['Last Name', user.last_name])
    writer.writerow(['Date Joined', user.date_joined])
    writer.writerow(['Last Login', user.last_login])
    writer.writerow(['Is Active', user.is_active])
    writer.writerow([])
    
    # Write user profile information if exists
    try:
        profile = user.userprofile
        writer.writerow(['Profile Information'])
        writer.writerow(['Field', 'Value'])
        writer.writerow(['Phone Number', profile.phone_number])
        writer.writerow(['Role', profile.role])
        writer.writerow(['Group', profile.group.name if profile.group else ''])
        writer.writerow(['Theme Preference', profile.theme_preference])
        writer.writerow([])
    except UserProfile.DoesNotExist:
        pass
    
    # Write bookings
    from ...models import Booking
    bookings = Booking.objects.filter(user=user)
    if bookings.exists():
        writer.writerow(['Bookings'])
        writer.writerow(['Resource', 'Start Time', 'End Time', 'Purpose', 'Status'])
        for booking in bookings:
            writer.writerow([
                booking.resource.name,
                booking.start_time,
                booking.end_time,
                booking.purpose,
                booking.get_status_display()
            ])
        writer.writerow([])
    
    # Write API tokens
    tokens = APIToken.objects.filter(user=user)
    if tokens.exists():
        writer.writerow(['API Tokens'])
        writer.writerow(['Token Type', 'Created', 'Expires', 'Is Revoked'])
        for token in tokens:
            writer.writerow([
                token.token_type,
                token.created_at,
                token.expires_at,
                token.is_revoked
            ])
        writer.writerow([])
    
    # Write security events
    security_events = SecurityEvent.objects.filter(user=user)
    if security_events.exists():
        writer.writerow(['Security Events'])
        writer.writerow(['Event Type', 'Timestamp', 'IP Address', 'Description'])
        for event in security_events:
            writer.writerow([
                event.get_event_type_display(),
                event.timestamp,
                event.ip_address,
                event.description
            ])
    
    # Log the export action
    AdminAction.objects.create(
        admin_user=request.user,
        action_type='DATA_EXPORT',
        target_user=user,
        description=f'Full user data exported for {user.username}',
        ip_address=get_client_ip(request),
    )
    
    return response


@login_required
@user_passes_test(is_site_admin, login_url='/accounts/login/')
def enhanced_audit_logs_view(request):
    """
    Enhanced audit logs view with new audit models.
    """
    # Get audit logs with related objects
    audit_logs = AuditLog.objects.select_related('user', 'content_type').order_by('-timestamp')
    
    # Apply filters (similar to existing audit view but enhanced)
    filter_type = request.GET.get('filter_type', 'all')
    username_filter = request.GET.get('username', '')
    action_filter = request.GET.get('action', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    if filter_type != 'all':
        audit_logs = audit_logs.filter(content_type__model=filter_type)
    
    if username_filter:
        audit_logs = audit_logs.filter(username__icontains=username_filter)
    
    if action_filter:
        audit_logs = audit_logs.filter(action=action_filter)
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
            audit_logs = audit_logs.filter(timestamp__date__gte=date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
            audit_logs = audit_logs.filter(timestamp__date__lte=date_to_obj)
        except ValueError:
            pass
    
    # Pagination
    paginator = Paginator(audit_logs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get action choices for filter dropdown
    action_choices = AuditLog.ACTION_CHOICES
    
    context = {
        'page_obj': page_obj,
        'filter_type': filter_type,
        'username_filter': username_filter,
        'action_filter': action_filter,
        'date_from': date_from,
        'date_to': date_to,
        'action_choices': action_choices,
    }
    
    return render(request, 'booking/site_admin_audit_enhanced.html', context)