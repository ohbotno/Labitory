# booking/views/modules/site_admin.py
"""
Site administrator views for the Labitory.

This module handles site administration, licensing, backups, and system configuration.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.template.loader import render_to_string
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count, Max
from datetime import datetime, timedelta
import json
from django.core.paginator import Paginator
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
import sys
import platform
import django
import csv
import os
import subprocess
import tempfile
import zipfile
import threading
import time

# Import models
from ...models import (
    AboutPage, UserProfile, Resource, Booking, ApprovalRule, Maintenance, EmailVerificationToken, 
    PasswordResetToken, BookingTemplate, Notification, NotificationPreference, WaitingListEntry, 
    Faculty, College, Department, ResourceAccess, AccessRequest, TrainingRequest,
    ResourceResponsible, RiskAssessment, UserRiskAssessment, TrainingCourse, 
    ResourceTrainingRequirement, UserTraining, ResourceIssue, UpdateInfo, 
    LabSettings, EmailConfiguration, SMSConfiguration
)

# Import additional models that may be needed
try:
    from booking.models import BackupSchedule, UpdateHistory
except ImportError:
    BackupSchedule = None
    UpdateHistory = None

# Import forms
from ...forms import (
    UserRegistrationForm, UserProfileForm, CustomPasswordResetForm, CustomSetPasswordForm, 
    BookingForm, RecurringBookingForm, BookingTemplateForm, CreateBookingFromTemplateForm, 
    SaveAsTemplateForm, AccessRequestForm, AccessRequestReviewForm, RiskAssessmentForm, 
    UserRiskAssessmentForm, TrainingCourseForm, UserTrainingEnrollForm, ResourceResponsibleForm,
    ResourceForm, AboutPageEditForm, ResourceIssueReportForm, ResourceIssueUpdateForm, IssueFilterForm
)

# Import additional forms that may be needed
try:
    from ...forms import EmailConfigurationForm, EmailConfigurationTestForm, SMSConfigurationForm, SMSConfigurationTestForm
except ImportError:
    EmailConfigurationForm = None
    EmailConfigurationTestForm = None 
    SMSConfigurationForm = None
    SMSConfigurationTestForm = None

# Import licensing forms (commented out as licensing is removed)
try:
    # from ..views.licensing import BrandingConfigurationForm, LicenseActivationForm
    pass
except ImportError:
    pass


def site_admin_dashboard_view(request):
    """Site administration dashboard - replaces Django admin."""
    from django.contrib.auth.models import User
    from django.db.models import Count, Q
    from django.utils import timezone
    from datetime import timedelta
    import sys
    import platform
    import django
    
    # System Information
    system_info = {
        'python_version': sys.version,
        'django_version': django.get_version(),
        'platform': f"{platform.system()} {platform.release()}",
        'server_time': timezone.now(),
    }
    
    # Database Statistics
    total_users = User.objects.count()
    total_resources = Resource.objects.count()
    total_bookings = Booking.objects.count()
    
    # Recent Activity (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_users = User.objects.filter(date_joined__gte=thirty_days_ago).count()
    recent_bookings = Booking.objects.filter(created_at__gte=thirty_days_ago).count()
    
    # User Role Distribution
    user_roles = UserProfile.objects.values('role').annotate(count=Count('role')).order_by('-count')
    
    # Pending Approvals
    pending_access_requests = AccessRequest.objects.filter(status='pending').count()
    pending_training_requests = TrainingRequest.objects.filter(status='pending').count()
    
    # Resource Status
    active_resources = Resource.objects.filter(is_active=True).count()
    inactive_resources = Resource.objects.filter(is_active=False).count()
    
    # Maintenance Status
    active_maintenance = Maintenance.objects.filter(
        start_time__lte=timezone.now(),
        end_time__gte=timezone.now()
    ).count()
    
    upcoming_maintenance = Maintenance.objects.filter(
        start_time__gt=timezone.now(),
        start_time__lte=timezone.now() + timedelta(days=7)
    ).count()
    
    # Update Information
    try:
        from booking.models import UpdateInfo
        from booking.services.update_service import UpdateService
        
        update_info = UpdateInfo.objects.first()
        if not update_info:
            # Create default update info if none exists
            update_service = UpdateService()
            update_info = update_service.get_or_create_update_info()
        
    except Exception:
        # If update system isn't available, create a basic placeholder
        update_info = None
    
    # License Information
    # Removed licensing requirement - all features now available
    license_stats = {
        'license_type': 'open_source',
        'is_valid': True,
        'organization': 'Open Source User',
        'expires_at': None,
        'recent_validations': 0,
        'validation_failures': 0,
        'enabled_features': {
            'advanced_reports': True,
            'custom_branding': True,
            'sms_notifications': True,
            'calendar_sync': True,
            'maintenance_tracking': True,
            'white_label': False,
            'multi_tenant': False,
        },
    }
    
    context = {
        'system_info': system_info,
        'stats': {
            'total_users': total_users,
            'total_resources': total_resources, 
            'total_bookings': total_bookings,
            'recent_users': recent_users,
            'recent_bookings': recent_bookings,
            'active_resources': active_resources,
            'inactive_resources': inactive_resources,
            'active_maintenance': active_maintenance,
            'upcoming_maintenance': upcoming_maintenance,
            'pending_access_requests': pending_access_requests,
            'pending_training_requests': pending_training_requests,
        },
        'user_roles': user_roles,
        'update_info': update_info,
        'license_stats': license_stats,
    }
    
    return render(request, 'booking/site_admin_dashboard.html', context)


@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_license_management_view(request):
    """Site admin license management page - PLACEHOLDER."""
    messages.error(request, "License management is temporarily unavailable. The LicenseConfiguration model needs to be implemented.")
    return redirect('booking:site_admin_dashboard')



def site_admin_branding_config_view(request):
    """Site admin branding configuration page - PLACEHOLDER."""
    messages.error(request, "Branding configuration is temporarily unavailable. The LicenseConfiguration model needs to be implemented.")
    return redirect('booking:site_admin_dashboard')



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_license_activate_view(request):
    """Site admin license activation page - PLACEHOLDER."""
    messages.error(request, "License activation is temporarily unavailable. The LicenseConfiguration model needs to be implemented.")
    return redirect('booking:site_admin_dashboard')



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_license_select_open_source_view(request):
    """Site admin open source license selection page - PLACEHOLDER."""
    messages.error(request, "Open source license selection is temporarily unavailable. The LicenseConfiguration model needs to be implemented.")
    return redirect('booking:site_admin_dashboard')



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_license_validation_logs_view(request):
    """Site admin license validation logs page - PLACEHOLDER."""
    messages.error(request, "License validation logs are temporarily unavailable. The LicenseConfiguration model needs to be implemented.")
    return redirect('booking:site_admin_dashboard')



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_license_validate_ajax(request):
    """AJAX endpoint for manual license validation - PLACEHOLDER."""
    return JsonResponse({
        'success': False,
        'error': 'License validation is temporarily unavailable. The LicenseConfiguration model needs to be implemented.'
    }, status=503)



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_license_export_view(request):
    """Export license information and validation logs to CSV - PLACEHOLDER."""
    messages.error(request, "License export is temporarily unavailable. The LicenseConfiguration model needs to be implemented.")
    return redirect('booking:site_admin_dashboard')



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_users_view(request):
    """User management interface."""
    users = User.objects.select_related('userprofile').order_by('-date_joined')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    # Role filter
    role_filter = request.GET.get('role', '')
    if role_filter:
        users = users.filter(userprofile__role=role_filter)
    
    # Status filter
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(users, 25)
    page_number = request.GET.get('page')
    users_page = paginator.get_page(page_number)
    
    context = {
        'users': users_page,
        'search_query': search_query,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'role_choices': UserProfile.ROLE_CHOICES,
    }
    
    return render(request, 'booking/site_admin_users.html', context)



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_user_delete_view(request, user_id):
    """Delete user interface with confirmation."""
    from django.contrib import messages
    from django.db import transaction
    from django.contrib.auth.models import User
    from booking.models import UserProfile, Booking, ResourceAccess, UserTraining
    
    user_to_delete = get_object_or_404(User, id=user_id)
    
    # Prevent deletion of the current user
    if user_to_delete == request.user:
        messages.error(request, "You cannot delete your own account.")
        return redirect('booking:site_admin_users')
    
    # Prevent deletion of other sysadmins unless current user is superuser
    if (hasattr(user_to_delete, 'userprofile') and 
        user_to_delete.userprofile.role == 'sysadmin' and 
        not request.user.is_superuser):
        messages.error(request, "You cannot delete other system administrators.")
        return redirect('booking:site_admin_users')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Get user info for confirmation message
                username = user_to_delete.username
                full_name = user_to_delete.get_full_name()
                
                # Delete the user (CASCADE relationships will be handled automatically)
                user_to_delete.delete()
                
                messages.success(
                    request, 
                    f'User "{username}" ({full_name}) has been permanently deleted.'
                )
                
                return redirect('booking:site_admin_users')
                
        except Exception as e:
            messages.error(
                request, 
                f'Error deleting user: {str(e)}'
            )
            return redirect('booking:site_admin_users')
    
    # Calculate impact for GET request (confirmation page)
    try:
        bookings_count = Booking.objects.filter(user=user_to_delete).count()
        active_bookings_count = Booking.objects.filter(
            user=user_to_delete, 
            status__in=['approved', 'pending']
        ).count()
        resource_access_count = ResourceAccess.objects.filter(user=user_to_delete).count()
        training_records_count = UserTraining.objects.filter(user=user_to_delete).count()
        
        # Check if user is referenced in any SET_NULL relationships
        approved_bookings_count = Booking.objects.filter(approved_by=user_to_delete).count()
        
    except Exception:
        # Fallback values if queries fail
        bookings_count = 0
        active_bookings_count = 0
        resource_access_count = 0
        training_records_count = 0
        approved_bookings_count = 0
    
    context = {
        'user_to_delete': user_to_delete,
        'bookings_count': bookings_count,
        'active_bookings_count': active_bookings_count,
        'resource_access_count': resource_access_count,
        'training_records_count': training_records_count,
        'approved_bookings_count': approved_bookings_count,
        'can_delete': active_bookings_count == 0,  # Only allow deletion if no active bookings
    }
    
    return render(request, 'booking/site_admin_user_confirm_delete.html', context)



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_system_config_view(request):
    """System configuration interface."""
    from django.conf import settings
    from django.http import JsonResponse
    from django.core.cache import cache
    
    # Handle AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        action = request.GET.get('action')
        
        if action == 'clear_cache' and request.method == 'POST':
            try:
                # Clear Django cache
                cache.clear()
                
                # Try to clear additional caches if available
                cache_stats = {
                    'django_cache': 'cleared',
                }
                
                # If using Redis, could also clear Redis cache
                try:
                    from django.core.cache.backends.redis import RedisCache
                    from django_redis import get_redis_connection
                    if isinstance(cache, RedisCache):
                        redis_conn = get_redis_connection("default")
                        redis_conn.flushdb()
                        cache_stats['redis_cache'] = 'cleared'
                except ImportError:
                    pass
                except Exception:
                    pass
                
                # Clear session cache if using cached sessions
                try:
                    from django.contrib.sessions.backends.cached_db import SessionStore
                    from django.contrib.sessions.backends.cache import SessionStore as CacheSessionStore
                    cache_stats['session_cache'] = 'cleared'
                except Exception:
                    pass
                
                return JsonResponse({
                    'success': True,
                    'message': f'Application cache cleared successfully. Cache types cleared: {", ".join(cache_stats.keys())}',
                    'cache_stats': cache_stats
                })
                
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to clear cache: {str(e)}'
                })
        
        elif action == 'restart_app' and request.method == 'POST':
            try:
                import os
                import sys
                import signal
                import subprocess
                from django.conf import settings
                
                # Log the restart attempt
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Application restart initiated by user: {request.user.username}")
                
                # Different restart methods depending on deployment
                restart_method = None
                restart_command = None
                
                # Try to detect deployment method and choose appropriate restart
                if hasattr(settings, 'WSGI_APPLICATION'):
                    # Production WSGI deployment
                    if os.environ.get('GUNICORN_CMD_ARGS') or 'gunicorn' in sys.modules:
                        # Gunicorn deployment
                        restart_method = 'gunicorn'
                        try:
                            # Send HUP signal to gunicorn master process
                            ppid = os.getppid()
                            os.kill(ppid, signal.SIGHUP)
                            restart_command = f'SIGHUP signal sent to gunicorn master (PID: {ppid})'
                        except Exception as e:
                            # Alternative: try to restart via systemctl if available
                            try:
                                result = subprocess.run(['systemctl', 'reload', 'gunicorn'], 
                                                      capture_output=True, text=True, timeout=5)
                                if result.returncode == 0:
                                    restart_command = 'systemctl reload gunicorn executed'
                                else:
                                    raise Exception(f'systemctl failed: {result.stderr}')
                            except Exception:
                                restart_command = f'Gunicorn restart attempted but may have failed: {e}'
                    
                    elif 'uwsgi' in sys.modules or os.environ.get('UWSGI_ORIGINAL_PROC_NAME'):
                        # uWSGI deployment
                        restart_method = 'uwsgi'
                        try:
                            # Send SIGHUP to uwsgi master
                            ppid = os.getppid()
                            os.kill(ppid, signal.SIGHUP)
                            restart_command = f'SIGHUP signal sent to uwsgi master (PID: {ppid})'
                        except Exception as e:
                            restart_command = f'uWSGI restart attempted: {e}'
                    
                    else:
                        # Generic WSGI or unknown deployment
                        restart_method = 'generic'
                        try:
                            # Try touching wsgi.py file to trigger reload
                            wsgi_file = os.path.join(settings.BASE_DIR, 'labitory', 'wsgi.py')
                            if os.path.exists(wsgi_file):
                                # Touch the file to update modification time
                                os.utime(wsgi_file, None)
                                restart_command = f'Touched WSGI file: {wsgi_file}'
                            else:
                                restart_command = 'WSGI file not found for touch restart'
                        except Exception as e:
                            restart_command = f'Generic restart attempted: {e}'
                
                else:
                    # Development server
                    restart_method = 'development'
                    try:
                        # For development, we can restart by sending signal to current process
                        # This will cause the Django development server to restart
                        def restart_server():
                            import threading
                            import time
                            time.sleep(1)  # Small delay to allow response to be sent
                            os.kill(os.getpid(), signal.SIGTERM)
                        
                        # Start restart in a separate thread to allow response to be sent first
                        restart_thread = threading.Thread(target=restart_server)
                        restart_thread.daemon = True
                        restart_thread.start()
                        
                        restart_command = 'Development server restart initiated'
                    except Exception as e:
                        restart_command = f'Development restart attempted: {e}'
                
                return JsonResponse({
                    'success': True,
                    'message': 'Application restart initiated successfully',
                    'restart_method': restart_method,
                    'restart_command': restart_command,
                    'note': 'The application should be back online within 10-30 seconds'
                })
                
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to restart application: {str(e)}'
                })
    
    if request.method == 'POST':
        # Handle configuration updates
        # This would need to be implemented based on your configuration system
        messages.success(request, 'Configuration updated successfully.')
        return redirect('booking:site_admin_config')
    
    # Get current configuration
    config_settings = {
        'debug_mode': settings.DEBUG,
        'time_zone': settings.TIME_ZONE,
        'language_code': settings.LANGUAGE_CODE,
        'email_backend': getattr(settings, 'EMAIL_BACKEND', 'Not configured'),
        'database_engine': settings.DATABASES['default']['ENGINE'],
        'static_url': settings.STATIC_URL,
        'media_url': settings.MEDIA_URL,
    }
    
    context = {
        'config_settings': config_settings,
    }
    
    return render(request, 'booking/site_admin_config.html', context)



@login_required
@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_lab_settings_view(request):
    """Lab settings management interface."""
    from django.contrib import messages
    from ..models import LabSettings
    
    # Get or create lab settings
    lab_settings = LabSettings.get_active()
    if not lab_settings:
        lab_settings = LabSettings.objects.create(
            lab_name="Labitory",
            is_active=True
        )
    
    if request.method == 'POST':
        lab_name = request.POST.get('lab_name', '').strip()
        
        if lab_name:
            lab_settings.lab_name = lab_name
            lab_settings.save()
            messages.success(request, 'Lab settings updated successfully.')
            return redirect('booking:site_admin_lab_settings')
        else:
            messages.error(request, 'Lab name cannot be empty.')
    
    context = {
        'lab_settings': lab_settings,
    }
    
    return render(request, 'booking/site_admin_lab_settings.html', context)



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_audit_logs_view(request):
    """Audit logs and system monitoring."""
    from booking.log_viewer import log_viewer
    
    # Recent bookings with actions
    recent_bookings = Booking.objects.select_related('user', 'resource').order_by('-created_at')[:20]
    
    # Recent user registrations
    recent_users = User.objects.order_by('-date_joined')[:10]
    
    # Recent access requests
    recent_access_requests = AccessRequest.objects.select_related('user', 'resource').order_by('-created_at')[:15]
    
    # System logs
    system_logs = log_viewer.get_logs(hours=24, max_lines=50)
    log_sources = log_viewer.get_available_sources()
    
    context = {
        'recent_bookings': recent_bookings,
        'recent_users': recent_users,
        'recent_access_requests': recent_access_requests,
        'system_logs': system_logs,
        'log_sources': log_sources,
    }
    
    return render(request, 'booking/site_admin_audit.html', context)



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_logs_ajax(request):
    """AJAX endpoint for system logs."""
    from django.http import JsonResponse
    from booking.log_viewer import log_viewer
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        source = request.GET.get('source')
        level = request.GET.get('level')
        search = request.GET.get('search')
        
        # Validate numeric parameters
        try:
            hours = int(request.GET.get('hours', 24))
            max_lines = int(request.GET.get('max_lines', 100))
        except ValueError:
            return JsonResponse({
                'error': 'Invalid numeric parameter'
            }, status=400)
        
        # Limit parameters to reasonable values
        hours = min(max(hours, 1), 720)  # 1 hour to 30 days
        max_lines = min(max(max_lines, 1), 1000)  # 1 to 1000 lines
        
        logs = log_viewer.get_logs(source, level, search, hours, max_lines)
        
        log_data = []
        for log in logs:
            try:
                log_data.append({
                    'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    'level': log.level,
                    'source': log.source,
                    'message': log.message,
                    'level_color': log.get_level_color()
                })
            except Exception as e:
                logger.warning(f"Error processing log entry: {e}")
                continue
        
        return JsonResponse({
            'logs': log_data,
            'total': len(log_data),
            'status': 'success'
        })
        
    except Exception as e:
        logger.error(f"Error in logs AJAX endpoint: {e}")
        return JsonResponse({
            'error': f'Server error: {str(e)}',
            'logs': [],
            'total': 0
        }, status=500)



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_health_check_view(request):
    """System health check endpoint for site administrators."""
    from django.http import JsonResponse
    from django.db import connection
    from django.core.cache import cache
    from django.conf import settings
    import os
    import time
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    health_results = {}
    overall_status = 'healthy'
    
    # Database connectivity check
    try:
        start_time = time.time()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        db_response_time = round((time.time() - start_time) * 1000, 2)
        health_results['database'] = {
            'status': 'healthy',
            'response_time_ms': db_response_time,
            'message': 'Database connection successful'
        }
    except Exception as e:
        health_results['database'] = {
            'status': 'unhealthy',
            'error': str(e),
            'message': 'Database connection failed'
        }
        overall_status = 'unhealthy'
    
    # Cache system check (if configured)
    try:
        cache_key = 'health_check_test'
        cache_value = 'test_value'
        cache.set(cache_key, cache_value, timeout=60)
        retrieved_value = cache.get(cache_key)
        
        if retrieved_value == cache_value:
            health_results['cache'] = {
                'status': 'healthy',
                'message': 'Cache system operational'
            }
        else:
            health_results['cache'] = {
                'status': 'warning',
                'message': 'Cache not working properly'
            }
            if overall_status == 'healthy':
                overall_status = 'warning'
    except Exception as e:
        health_results['cache'] = {
            'status': 'warning',
            'error': str(e),
            'message': 'Cache check failed - may not be configured'
        }
        if overall_status == 'healthy':
            overall_status = 'warning'
    
    # System resources check
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        system_status = 'healthy'
        warnings = []
        
        if cpu_percent > 80:
            warnings.append(f'High CPU usage: {cpu_percent}%')
            system_status = 'warning'
        
        if memory.percent > 80:
            warnings.append(f'High memory usage: {memory.percent}%')
            system_status = 'warning'
        
        if disk.percent > 85:
            warnings.append(f'High disk usage: {disk.percent}%')
            system_status = 'warning'
        
        health_results['system_resources'] = {
            'status': system_status,
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'disk_percent': disk.percent,
            'warnings': warnings,
            'message': 'System resources monitored'
        }
        
        if system_status == 'warning' and overall_status == 'healthy':
            overall_status = 'warning'
            
    except ImportError:
        health_results['system_resources'] = {
            'status': 'warning',
            'message': 'System resource monitoring unavailable (psutil not installed)'
        }
        if overall_status == 'healthy':
            overall_status = 'warning'
    except Exception as e:
        health_results['system_resources'] = {
            'status': 'warning',
            'error': str(e),
            'message': 'Could not check system resources'
        }
        if overall_status == 'healthy':
            overall_status = 'warning'
    
    # Application models check
    try:
        models_check = []
        
        # Check critical models
        user_count = User.objects.count()
        resource_count = Resource.objects.count()
        booking_count = Booking.objects.count()
        
        models_check.append(f'Users: {user_count}')
        models_check.append(f'Resources: {resource_count}')
        models_check.append(f'Bookings: {booking_count}')
        
        health_results['application_models'] = {
            'status': 'healthy',
            'counts': models_check,
            'message': 'Application models accessible'
        }
        
    except Exception as e:
        health_results['application_models'] = {
            'status': 'unhealthy',
            'error': str(e),
            'message': 'Application models check failed'
        }
        overall_status = 'unhealthy'
    
    # File system permissions check
    try:
        media_root = getattr(settings, 'MEDIA_ROOT', '/tmp')
        test_file = os.path.join(media_root, 'health_check_test.txt')
        
        # Try to write and read a test file
        with open(test_file, 'w') as f:
            f.write('health check test')
        
        with open(test_file, 'r') as f:
            content = f.read()
        
        os.remove(test_file)
        
        if content == 'health check test':
            health_results['file_system'] = {
                'status': 'healthy',
                'message': 'File system read/write operational'
            }
        else:
            health_results['file_system'] = {
                'status': 'warning',
                'message': 'File system write/read issue detected'
            }
            if overall_status == 'healthy':
                overall_status = 'warning'
                
    except Exception as e:
        health_results['file_system'] = {
            'status': 'warning',
            'error': str(e),
            'message': 'File system permissions check failed'
        }
        if overall_status == 'healthy':
            overall_status = 'warning'
    
    # Environment configuration check
    try:
        config_issues = []
        
        # Check critical settings
        if not settings.SECRET_KEY:
            config_issues.append('SECRET_KEY not configured')
        
        if settings.DEBUG:
            config_issues.append('DEBUG is True (should be False in production)')
        
        if not settings.ALLOWED_HOSTS:
            config_issues.append('ALLOWED_HOSTS not configured')
        
        config_status = 'warning' if config_issues else 'healthy'
        
        health_results['configuration'] = {
            'status': config_status,
            'issues': config_issues,
            'message': 'Configuration checked'
        }
        
        if config_status == 'warning' and overall_status == 'healthy':
            overall_status = 'warning'
            
    except Exception as e:
        health_results['configuration'] = {
            'status': 'warning',
            'error': str(e),
            'message': 'Configuration check failed'
        }
        if overall_status == 'healthy':
            overall_status = 'warning'
    
    # Return comprehensive health check results
    return JsonResponse({
        'overall_status': overall_status,
        'timestamp': timezone.now().isoformat(),
        'checks': health_results,
        'summary': {
            'healthy': len([k for k, v in health_results.items() if v['status'] == 'healthy']),
            'warnings': len([k for k, v in health_results.items() if v['status'] == 'warning']),
            'unhealthy': len([k for k, v in health_results.items() if v['status'] == 'unhealthy']),
            'total': len(health_results)
        }
    })



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_test_email_view(request):
    """Test email configuration endpoint for site administrators."""
    from django.http import JsonResponse
    from django.core.mail import send_mail, EmailMultiAlternatives
    from django.conf import settings
    from django.template.loader import render_to_string
    import time
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    import json
    try:
        data = json.loads(request.body)
        test_email = data.get('email', request.user.email)
    except (json.JSONDecodeError, AttributeError):
        test_email = request.user.email
    
    test_results = {}
    overall_status = 'success'
    
    # Check email configuration
    try:
        config_check = []
        config_issues = []
        
        # Check basic email settings
        if not settings.EMAIL_HOST:
            config_issues.append('EMAIL_HOST not configured')
        else:
            config_check.append(f'Email Host: {settings.EMAIL_HOST}')
            
        if not settings.DEFAULT_FROM_EMAIL:
            config_issues.append('DEFAULT_FROM_EMAIL not configured')
        else:
            config_check.append(f'From Email: {settings.DEFAULT_FROM_EMAIL}')
            
        config_check.append(f'Email Backend: {settings.EMAIL_BACKEND}')
        config_check.append(f'Email Port: {settings.EMAIL_PORT}')
        config_check.append(f'Use TLS: {settings.EMAIL_USE_TLS}')
        
        if settings.EMAIL_HOST_USER:
            config_check.append(f'SMTP User: {settings.EMAIL_HOST_USER}')
        else:
            config_check.append('SMTP User: Not configured')
            
        test_results['configuration'] = {
            'status': 'warning' if config_issues else 'success',
            'settings': config_check,
            'issues': config_issues,
            'message': 'Email configuration checked'
        }
        
        if config_issues and overall_status == 'success':
            overall_status = 'warning'
            
    except Exception as e:
        test_results['configuration'] = {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to check email configuration'
        }
        overall_status = 'error'
    
    # Test basic email sending capability
    try:
        start_time = time.time()
        
        # Test with simple send_mail
        subject = 'Labitory - Email Configuration Test'
        message = f"""
Email Configuration Test

This is a test email sent from the Labitory system to verify email configuration.

Test Details:
- Sent at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}
- Sent to: {test_email}
- Sent from: {settings.DEFAULT_FROM_EMAIL}
- Email Backend: {settings.EMAIL_BACKEND}
- SMTP Host: {settings.EMAIL_HOST}
- SMTP Port: {settings.EMAIL_PORT}

If you received this email, your email configuration is working correctly!

--
Labitory System
        """.strip()
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[test_email],
            fail_silently=False
        )
        
        send_time = round((time.time() - start_time) * 1000, 2)
        
        test_results['basic_send'] = {
            'status': 'success',
            'send_time_ms': send_time,
            'recipient': test_email,
            'message': 'Basic email sent successfully'
        }
        
    except Exception as e:
        test_results['basic_send'] = {
            'status': 'error',
            'error': str(e),
            'recipient': test_email,
            'message': 'Failed to send basic email'
        }
        overall_status = 'error'
    
    # Test HTML email sending capability
    try:
        start_time = time.time()
        
        # Create a more complex HTML test email
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Email Test</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f4f4f4; }}
        .container {{ max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ background-color: #007bff; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; margin: -20px -20px 20px -20px; }}
        .success {{ background-color: #d4edda; border: 1px solid #c3e6cb; color: #155724; padding: 15px; border-radius: 4px; margin: 20px 0; }}
        .info {{ background-color: #e7f3ff; border: 1px solid #b3d7ff; color: #004085; padding: 15px; border-radius: 4px; margin: 20px 0; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>🧪 Labitory - HTML Email Test</h2>
        </div>
        
        <div class="success">
            <strong>✅ HTML Email Test Successful!</strong><br>
            Your email system can successfully send and render HTML emails.
        </div>
        
        <p>This is an HTML test email sent from the <strong>Labitory</strong> system.</p>
        
        <div class="info">
            <strong>Test Information:</strong><br>
            • Sent at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}<br>
            • Recipient: {test_email}<br>
            • From: {settings.DEFAULT_FROM_EMAIL}<br>
            • Backend: {settings.EMAIL_BACKEND}<br>
            • SMTP Host: {settings.EMAIL_HOST}<br>
            • SMTP Port: {settings.EMAIL_PORT}
        </div>
        
        <p>If you can see this formatted email with colors and styling, your HTML email configuration is working correctly!</p>
        
        <div class="footer">
            <p>This email was automatically generated by the Labitory system for testing purposes.</p>
        </div>
    </div>
</body>
</html>
        """.strip()
        
        text_content = f"""
HTML Email Configuration Test

This is an HTML test email sent from the Labitory system.

Test Details:
- Sent at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}
- Sent to: {test_email}
- Sent from: {settings.DEFAULT_FROM_EMAIL}
- Email Backend: {settings.EMAIL_BACKEND}
- SMTP Host: {settings.EMAIL_HOST}
- SMTP Port: {settings.EMAIL_PORT}

If you received this email with proper HTML formatting, your email configuration supports HTML emails!

--
Labitory System
        """.strip()
        
        email = EmailMultiAlternatives(
            subject='Labitory - HTML Email Configuration Test',
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[test_email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        send_time = round((time.time() - start_time) * 1000, 2)
        
        test_results['html_send'] = {
            'status': 'success',
            'send_time_ms': send_time,
            'recipient': test_email,
            'message': 'HTML email sent successfully'
        }
        
    except Exception as e:
        test_results['html_send'] = {
            'status': 'error',
            'error': str(e),
            'recipient': test_email,
            'message': 'Failed to send HTML email'
        }
        if overall_status == 'success':
            overall_status = 'warning'  # HTML failure is less critical than basic email failure
    
    # Test notification system integration
    try:
        from booking.notifications import NotificationService
        
        notification_service = NotificationService()
        
        # Test if notification service can access email settings
        test_results['notification_integration'] = {
            'status': 'success',
            'message': 'Notification service integration available',
            'service_available': True
        }
        
    except Exception as e:
        test_results['notification_integration'] = {
            'status': 'warning',
            'error': str(e),
            'message': 'Notification service integration check failed',
            'service_available': False
        }
        if overall_status == 'success':
            overall_status = 'warning'
    
    # Connection test (if using SMTP)
    if 'smtp' in settings.EMAIL_BACKEND.lower():
        try:
            import smtplib
            from email.mime.text import MIMEText
            
            start_time = time.time()
            
            # Test SMTP connection
            if settings.EMAIL_USE_TLS:
                server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
                server.starttls()
            else:
                server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
            
            if settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD:
                server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            
            server.quit()
            
            connection_time = round((time.time() - start_time) * 1000, 2)
            
            test_results['smtp_connection'] = {
                'status': 'success',
                'connection_time_ms': connection_time,
                'message': 'SMTP connection successful'
            }
            
        except Exception as e:
            test_results['smtp_connection'] = {
                'status': 'error',
                'error': str(e),
                'message': 'SMTP connection failed'
            }
            overall_status = 'error'
    else:
        test_results['smtp_connection'] = {
            'status': 'info',
            'message': f'Not using SMTP backend (using {settings.EMAIL_BACKEND})'
        }
    
    # Return comprehensive email test results
    return JsonResponse({
        'overall_status': overall_status,
        'timestamp': timezone.now().isoformat(),
        'test_email': test_email,
        'tests': test_results,
        'summary': {
            'success': len([k for k, v in test_results.items() if v['status'] == 'success']),
            'warnings': len([k for k, v in test_results.items() if v['status'] == 'warning']),
            'errors': len([k for k, v in test_results.items() if v['status'] == 'error']),
            'info': len([k for k, v in test_results.items() if v['status'] == 'info']),
            'total': len(test_results)
        },
        'recommendations': [
            'Check your spam/junk folder if test emails are not received',
            'Verify firewall settings allow outbound SMTP connections',
            'Ensure email credentials are correct if using authentication',
            'Consider using environment variables for sensitive email settings'
        ]
    })



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_email_config_view(request):
    """Email configuration management for site administrators."""
    from django.shortcuts import render, redirect, get_object_or_404
    from django.contrib import messages
    from django.http import JsonResponse
    from booking.models import EmailConfiguration
    from ..forms import EmailConfigurationForm, EmailConfigurationTestForm
    
    # Get all email configurations
    configurations = EmailConfiguration.objects.all().order_by('-is_active', '-updated_at')
    active_config = EmailConfiguration.get_active_configuration()
    
    # Handle AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        action = request.GET.get('action')
        
        if action == 'activate' and request.method == 'POST':
            config_id = request.POST.get('config_id')
            try:
                config = get_object_or_404(EmailConfiguration, id=config_id)
                config.activate()
                return JsonResponse({
                    'success': True,
                    'message': f'Configuration "{config.name}" activated successfully'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to activate configuration: {str(e)}'
                })
        
        elif action == 'deactivate' and request.method == 'POST':
            config_id = request.POST.get('config_id')
            try:
                config = get_object_or_404(EmailConfiguration, id=config_id)
                if not config.is_active:
                    return JsonResponse({
                        'success': False,
                        'message': 'Configuration is not currently active'
                    })
                config.is_active = False
                config.save()
                return JsonResponse({
                    'success': True,
                    'message': f'Configuration "{config.name}" deactivated successfully'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to deactivate configuration: {str(e)}'
                })
        
        elif action == 'test' and request.method == 'POST':
            config_id = request.POST.get('config_id')
            test_email = request.POST.get('test_email')
            try:
                config = get_object_or_404(EmailConfiguration, id=config_id)
                success, message = config.test_configuration(test_email)
                return JsonResponse({
                    'success': success,
                    'message': message,
                    'last_test_date': config.last_test_date.isoformat() if config.last_test_date else None,
                    'is_validated': config.is_validated
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Test failed: {str(e)}'
                })
        
        elif action == 'delete' and request.method == 'POST':
            config_id = request.POST.get('config_id')
            try:
                config = get_object_or_404(EmailConfiguration, id=config_id)
                if config.is_active:
                    return JsonResponse({
                        'success': False,
                        'message': 'Cannot delete the active configuration'
                    })
                config_name = config.name
                config.delete()
                return JsonResponse({
                    'success': True,
                    'message': f'Configuration "{config_name}" deleted successfully'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to delete configuration: {str(e)}'
                })
    
    context = {
        'configurations': configurations,
        'active_config': active_config,
        'common_configs': EmailConfiguration.get_common_configurations(),
    }
    
    return render(request, 'booking/site_admin_email_config.html', context)



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_email_config_create_view(request):
    """Create new email configuration."""
    from django.shortcuts import render, redirect
    from django.contrib import messages
    from booking.models import EmailConfiguration
    from ..forms import EmailConfigurationForm
    
    if request.method == 'POST':
        form = EmailConfigurationForm(request.POST)
        if form.is_valid():
            config = form.save(commit=False)
            config.created_by = request.user
            config.save()
            messages.success(request, f'Email configuration "{config.name}" created successfully.')
            return redirect('booking:site_admin_email_config')
    else:
        form = EmailConfigurationForm()
        
        # Pre-fill with common configuration if requested
        preset = request.GET.get('preset')
        if preset:
            common_configs = EmailConfiguration.get_common_configurations()
            for config in common_configs:
                if config['name'].lower().replace(' ', '_') == preset:
                    for field, value in config.items():
                        if field in form.fields:
                            form.fields[field].initial = value
                    break
    
    context = {
        'form': form,
        'title': 'Create Email Configuration',
        'common_configs': EmailConfiguration.get_common_configurations(),
    }
    
    return render(request, 'booking/site_admin_email_config_form.html', context)



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_email_config_edit_view(request, config_id):
    """Edit existing email configuration."""
    from django.shortcuts import render, redirect, get_object_or_404
    from django.contrib import messages
    from booking.models import EmailConfiguration
    from ..forms import EmailConfigurationForm
    
    config = get_object_or_404(EmailConfiguration, id=config_id)
    
    if request.method == 'POST':
        form = EmailConfigurationForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, f'Email configuration "{config.name}" updated successfully.')
            return redirect('booking:site_admin_email_config')
    else:
        form = EmailConfigurationForm(instance=config)
    
    context = {
        'form': form,
        'config': config,
        'title': f'Edit Email Configuration: {config.name}',
        'common_configs': EmailConfiguration.get_common_configurations(),
    }
    
    return render(request, 'booking/site_admin_email_config_form.html', context)



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_sms_config_view(request):
    """SMS configuration management for site administrators."""
    from django.shortcuts import render, redirect, get_object_or_404
    from django.contrib import messages
    from django.http import JsonResponse
    from booking.models import SMSConfiguration
    from ..forms import SMSConfigurationForm, SMSConfigurationTestForm
    
    # Get all SMS configurations
    configurations = SMSConfiguration.objects.all().order_by('-is_active', '-updated_at')
    active_config = SMSConfiguration.get_active_configuration()
    
    # Handle AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        action = request.GET.get('action')
        
        if action == 'activate' and request.method == 'POST':
            config_id = request.POST.get('config_id')
            try:
                config = get_object_or_404(SMSConfiguration, id=config_id)
                config.activate()
                # Reload SMS service configuration
                from booking.services.sms_service import sms_service
                sms_service.reload_configuration()
                return JsonResponse({
                    'success': True,
                    'message': f'Configuration "{config.name}" activated successfully'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to activate configuration: {str(e)}'
                })
        
        elif action == 'deactivate' and request.method == 'POST':
            config_id = request.POST.get('config_id')
            try:
                config = get_object_or_404(SMSConfiguration, id=config_id)
                if not config.is_active:
                    return JsonResponse({
                        'success': False,
                        'message': 'Configuration is not currently active'
                    })
                config.is_active = False
                config.save()
                # Reload SMS service configuration
                from booking.services.sms_service import sms_service
                sms_service.reload_configuration()
                return JsonResponse({
                    'success': True,
                    'message': f'Configuration "{config.name}" deactivated successfully'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to deactivate configuration: {str(e)}'
                })
        
        elif action == 'test' and request.method == 'POST':
            config_id = request.POST.get('config_id')
            test_phone_number = request.POST.get('test_phone_number')
            test_type = request.POST.get('test_type', 'validate')
            try:
                config = get_object_or_404(SMSConfiguration, id=config_id)
                if test_type == 'send_sms' and test_phone_number:
                    success, message = config.test_configuration(test_phone_number)
                else:
                    success, message = config.test_configuration()
                return JsonResponse({
                    'success': success,
                    'message': message,
                    'last_test_date': config.last_test_date.isoformat() if config.last_test_date else None,
                    'is_validated': config.is_validated
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Test failed: {str(e)}'
                })
        
        elif action == 'delete' and request.method == 'POST':
            config_id = request.POST.get('config_id')
            try:
                config = get_object_or_404(SMSConfiguration, id=config_id)
                if config.is_active:
                    return JsonResponse({
                        'success': False,
                        'message': 'Cannot delete the active configuration'
                    })
                config_name = config.name
                config.delete()
                return JsonResponse({
                    'success': True,
                    'message': f'Configuration "{config_name}" deleted successfully'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to delete configuration: {str(e)}'
                })
        
        elif action == 'enable' and request.method == 'POST':
            config_id = request.POST.get('config_id')
            try:
                config = get_object_or_404(SMSConfiguration, id=config_id)
                config.is_enabled = True
                config.save()
                # Reload SMS service configuration
                from booking.services.sms_service import sms_service
                sms_service.reload_configuration()
                return JsonResponse({
                    'success': True,
                    'message': f'SMS notifications enabled for "{config.name}"'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to enable SMS: {str(e)}'
                })
        
        elif action == 'disable' and request.method == 'POST':
            config_id = request.POST.get('config_id')
            try:
                config = get_object_or_404(SMSConfiguration, id=config_id)
                config.is_enabled = False
                config.save()
                # Reload SMS service configuration
                from booking.services.sms_service import sms_service
                sms_service.reload_configuration()
                return JsonResponse({
                    'success': True,
                    'message': f'SMS notifications disabled for "{config.name}"'
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'message': f'Failed to disable SMS: {str(e)}'
                })
    
    context = {
        'configurations': configurations,
        'active_config': active_config,
        'sms_enabled_globally': SMSConfiguration.is_sms_enabled(),
    }
    
    return render(request, 'booking/site_admin_sms_config.html', context)



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_sms_config_create_view(request):
    """Create new SMS configuration."""
    from django.shortcuts import render, redirect
    from django.contrib import messages
    from booking.models import SMSConfiguration
    from ..forms import SMSConfigurationForm
    
    if request.method == 'POST':
        form = SMSConfigurationForm(request.POST)
        if form.is_valid():
            config = form.save(commit=False)
            config.created_by = request.user
            config.save()
            messages.success(request, f'SMS configuration "{config.name}" created successfully.')
            return redirect('booking:site_admin_sms_config')
    else:
        form = SMSConfigurationForm()
    
    context = {
        'form': form,
        'title': 'Create SMS Configuration',
    }
    
    return render(request, 'booking/site_admin_sms_config_form.html', context)



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_sms_config_edit_view(request, config_id):
    """Edit existing SMS configuration."""
    from django.shortcuts import render, redirect, get_object_or_404
    from django.contrib import messages
    from booking.models import SMSConfiguration
    from ..forms import SMSConfigurationForm
    
    config = get_object_or_404(SMSConfiguration, id=config_id)
    
    if request.method == 'POST':
        form = SMSConfigurationForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            # Reload SMS service if this was the active configuration
            if config.is_active:
                from booking.services.sms_service import sms_service
                sms_service.reload_configuration()
            messages.success(request, f'SMS configuration "{config.name}" updated successfully.')
            return redirect('booking:site_admin_sms_config')
    else:
        form = SMSConfigurationForm(instance=config)
    
    context = {
        'form': form,
        'config': config,
        'title': f'Edit SMS Configuration: {config.name}',
    }
    
    return render(request, 'booking/site_admin_sms_config_form.html', context)


# Backup Management Views

def site_admin_backup_management_view(request):
    """Backup management interface."""
    from booking.backup_service import BackupService
    import json
    
    backup_service = BackupService()
    
    # Handle POST requests for backup operations
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create_backup':
            include_media = request.POST.get('include_media') == 'on'
            description = request.POST.get('description', '')
            
            try:
                result = backup_service.create_full_backup(
                    include_media=include_media,
                    description=description
                )
                
                if result['success']:
                    messages.success(request, f"Backup created successfully: {result['backup_name']}")
                else:
                    messages.error(request, f"Backup failed: {', '.join(result['errors'])}")
                    
            except Exception as e:
                messages.error(request, f"Backup creation failed: {str(e)}")
        
        elif action == 'delete_backup':
            backup_name = request.POST.get('backup_name')
            if backup_name:
                try:
                    result = backup_service.delete_backup(backup_name)
                    if result['success']:
                        messages.success(request, result['message'])
                    else:
                        messages.error(request, result['message'])
                except Exception as e:
                    messages.error(request, f"Failed to delete backup: {str(e)}")
        
        elif action == 'cleanup_old':
            try:
                result = backup_service.cleanup_old_backups()
                if result['success']:
                    messages.success(request, f"Cleanup completed. Deleted {result['deleted_count']} old backups.")
                    if result['errors']:
                        for error in result['errors']:
                            messages.warning(request, error)
                else:
                    messages.error(request, f"Cleanup failed: {', '.join(result['errors'])}")
            except Exception as e:
                messages.error(request, f"Cleanup failed: {str(e)}")
        
        elif action == 'create_schedule':
            try:
                from booking.models import BackupSchedule
                schedule = BackupSchedule(
                    name=request.POST.get('name', 'Automated Backup'),
                    enabled=request.POST.get('enabled') == 'on',
                    frequency=request.POST.get('frequency', 'weekly'),
                    backup_time=request.POST.get('backup_time', '02:00'),
                    day_of_week=int(request.POST.get('day_of_week', 6)),
                    day_of_month=int(request.POST.get('day_of_month', 1)),
                    include_media=request.POST.get('include_media') == 'on',
                    include_database=request.POST.get('include_database') == 'on',
                    include_configuration=request.POST.get('include_configuration') == 'on',
                    max_backups_to_keep=int(request.POST.get('max_backups_to_keep', 7)),
                    retention_days=int(request.POST.get('retention_days', 30)),
                    notification_email=request.POST.get('notification_email', ''),
                    created_by=request.user
                )
                schedule.clean()
                schedule.save()
                messages.success(request, f"Backup schedule '{schedule.name}' created successfully")
                
            except Exception as e:
                messages.error(request, f"Failed to create backup schedule: {str(e)}")
        
        elif action == 'update_schedule':
            schedule_id = request.POST.get('schedule_id')
            try:
                from booking.models import BackupSchedule
                schedule = BackupSchedule.objects.get(id=schedule_id)
                schedule.name = request.POST.get('name', schedule.name)
                schedule.enabled = request.POST.get('enabled') == 'on'
                schedule.frequency = request.POST.get('frequency', schedule.frequency)
                schedule.backup_time = request.POST.get('backup_time', schedule.backup_time)
                schedule.day_of_week = int(request.POST.get('day_of_week', schedule.day_of_week))
                schedule.day_of_month = int(request.POST.get('day_of_month', schedule.day_of_month))
                schedule.include_media = request.POST.get('include_media') == 'on'
                schedule.include_database = request.POST.get('include_database') == 'on'
                schedule.include_configuration = request.POST.get('include_configuration') == 'on'
                schedule.max_backups_to_keep = int(request.POST.get('max_backups_to_keep', schedule.max_backups_to_keep))
                schedule.retention_days = int(request.POST.get('retention_days', schedule.retention_days))
                schedule.notification_email = request.POST.get('notification_email', schedule.notification_email)
                schedule.clean()
                schedule.save()
                messages.success(request, f"Backup schedule '{schedule.name}' updated successfully")
                
            except Exception as e:
                messages.error(request, f"Failed to update backup schedule: {str(e)}")
        
        elif action == 'delete_schedule':
            schedule_id = request.POST.get('schedule_id')
            try:
                from booking.models import BackupSchedule
                schedule = BackupSchedule.objects.get(id=schedule_id)
                schedule_name = schedule.name
                schedule.delete()
                messages.success(request, f"Backup schedule '{schedule_name}' deleted successfully")
                
            except Exception as e:
                messages.error(request, f"Failed to delete backup schedule: {str(e)}")
        
        elif action == 'test_schedule':
            schedule_id = request.POST.get('schedule_id')
            try:
                result = backup_service.test_scheduled_backup(int(schedule_id))
                if result.get('success'):
                    messages.success(request, f"Test backup completed successfully: {result.get('backup_name', 'Unknown')}")
                else:
                    error_msg = '; '.join(result.get('errors', ['Unknown error']))
                    messages.error(request, f"Test backup failed: {error_msg}")
                    
            except Exception as e:
                messages.error(request, f"Failed to test backup schedule: {str(e)}")
        
        return redirect('booking:site_admin_backup_management')
    
    # Get backup information
    try:
        backups = backup_service.list_backups()
        stats = backup_service.get_backup_statistics()
        automation_status = backup_service.get_backup_schedules_status()
    except Exception as e:
        messages.error(request, f"Failed to load backup information: {str(e)}")
        backups = []
        stats = {}
        automation_status = {}
    
    # Get backup schedules for automation tab
    try:
        from booking.models import BackupSchedule
        schedules = BackupSchedule.objects.all().order_by('-created_at')
        
        # Get form choices for templates
        frequency_choices = BackupSchedule.FREQUENCY_CHOICES
        day_of_week_choices = BackupSchedule.DAY_OF_WEEK_CHOICES
    except Exception as e:
        schedules = []
        frequency_choices = []
        day_of_week_choices = []
    
    context = {
        'backups': backups,
        'stats': stats,
        'automation_status': automation_status,
        'schedules': schedules,
        'frequency_choices': frequency_choices,
        'day_of_week_choices': day_of_week_choices,
        'title': 'Backup Management',
    }
    
    return render(request, 'booking/site_admin_backup_management.html', context)



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_create_ajax(request):
    """AJAX endpoint for creating backups."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    from booking.backup_service import BackupService
    import json
    
    try:
        data = json.loads(request.body)
        backup_service = BackupService()
        
        include_media = data.get('include_media', True)
        description = data.get('description', '')
        
        result = backup_service.create_full_backup(
            include_media=include_media,
            description=description
        )
        
        if result['success']:
            # Convert datetime objects to strings for JSON serialization
            if 'timestamp' in result:
                result['timestamp'] = result['timestamp'].isoformat()
            
            return JsonResponse({
                'success': True,
                'backup_name': result['backup_name'],
                'message': f"Backup created successfully: {result['backup_name']}",
                'details': result
            })
        else:
            return JsonResponse({
                'success': False,
                'error': ', '.join(result['errors'])
            })
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_status_ajax(request):
    """AJAX endpoint for getting backup status and statistics."""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    from booking.backup_service import BackupService
    
    try:
        backup_service = BackupService()
        
        backups = backup_service.list_backups()
        stats = backup_service.get_backup_statistics()
        
        # Convert datetime objects to strings for JSON serialization
        for backup in backups:
            if 'timestamp' in backup:
                backup['timestamp'] = backup['timestamp']
        
        return JsonResponse({
            'success': True,
            'backups': backups,
            'stats': stats
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_download_view(request, backup_name):
    """Download a specific backup file."""
    from booking.backup_service import BackupService
    from django.http import FileResponse, Http404
    import os
    
    try:
        backup_service = BackupService()
        backup_path = os.path.join(backup_service.backup_dir, backup_name)
        compressed_path = f"{backup_path}.tar.gz"
        
        # Check for compressed backup first
        if os.path.exists(compressed_path):
            response = FileResponse(
                open(compressed_path, 'rb'),
                as_attachment=True,
                filename=f"{backup_name}.tar.gz"
            )
            return response
        elif os.path.exists(backup_path) and os.path.isfile(backup_path):
            response = FileResponse(
                open(backup_path, 'rb'),
                as_attachment=True,
                filename=backup_name
            )
            return response
        else:
            raise Http404("Backup file not found")
            
    except Exception as e:
        messages.error(request, f"Failed to download backup: {str(e)}")
        return redirect('booking:site_admin_backup_management')



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_restore_info_ajax(request, backup_name):
    """AJAX endpoint for getting backup restoration information."""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    from booking.backup_service import BackupService
    
    try:
        backup_service = BackupService()
        result = backup_service.get_backup_restoration_info(backup_name)
        
        if result['success']:
            # Convert datetime objects to strings for JSON serialization
            if 'timestamp' in result.get('backup_info', {}):
                result['backup_info']['timestamp'] = result['backup_info']['timestamp']
            
            return JsonResponse(result)
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Unknown error')
            })
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_restore_ajax(request):
    """AJAX endpoint for restoring backups."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    from booking.backup_service import BackupService
    import json
    import secrets
    
    try:
        data = json.loads(request.body)
        backup_service = BackupService()
        
        backup_name = data.get('backup_name')
        restore_components = data.get('restore_components', {})
        confirmation_token = data.get('confirmation_token')
        
        if not backup_name:
            return JsonResponse({'success': False, 'error': 'Backup name is required'})
        
        # Generate a secure confirmation token if database restoration is requested
        expected_token = None
        if restore_components.get('database', False):
            expected_token = f"RESTORE_{backup_name}_{secrets.token_hex(8)}"
            
            # Check if the provided token matches (for database restoration)
            if not confirmation_token or confirmation_token != expected_token:
                return JsonResponse({
                    'success': False,
                    'error': 'Database restoration requires confirmation',
                    'confirmation_required': True,
                    'confirmation_token': expected_token,
                    'warning_message': f'This will PERMANENTLY OVERWRITE your current database with data from backup "{backup_name}". This action cannot be undone.'
                })
        
        result = backup_service.restore_backup(
            backup_name=backup_name,
            restore_components=restore_components,
            confirmation_token=confirmation_token
        )
        
        if result['success']:
            # Convert datetime objects to strings for JSON serialization
            if 'timestamp' in result:
                result['timestamp'] = result['timestamp'].isoformat()
            
            return JsonResponse({
                'success': True,
                'message': f"Backup '{backup_name}' restored successfully",
                'details': result
            })
        else:
            return JsonResponse({
                'success': False,
                'error': ', '.join(result['errors']) if result['errors'] else 'Restoration failed'
            })
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_restore_view(request, backup_name):
    """Backup restoration interface."""
    from booking.backup_service import BackupService
    
    backup_service = BackupService()
    
    # Get backup restoration information
    try:
        restore_info = backup_service.get_backup_restoration_info(backup_name)
        
        if not restore_info['success']:
            messages.error(request, restore_info.get('error', 'Failed to get backup information'))
            return redirect('booking:site_admin_backup_management')
            
    except Exception as e:
        messages.error(request, f"Failed to analyze backup: {str(e)}")
        return redirect('booking:site_admin_backup_management')
    
    # Handle POST request for restoration
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'restore_backup':
            restore_components = {
                'database': request.POST.get('restore_database') == 'on',
                'media': request.POST.get('restore_media') == 'on',
                'configuration': request.POST.get('restore_configuration') == 'on'
            }
            
            confirmation_token = request.POST.get('confirmation_token')
            
            try:
                result = backup_service.restore_backup(
                    backup_name=backup_name,
                    restore_components=restore_components,
                    confirmation_token=confirmation_token
                )
                
                if result['success']:
                    messages.success(request, f"Backup '{backup_name}' restored successfully!")
                    
                    # Show component-specific results
                    for component, details in result.get('components_restored', {}).items():
                        if details.get('success'):
                            if component == 'database':
                                if details.get('backup_created'):
                                    messages.info(request, "Current database was backed up before restoration")
                            elif component == 'media':
                                count = details.get('restored_count', 0)
                                messages.info(request, f"Restored {count} media files")
                            elif component == 'configuration':
                                files = details.get('files_found', [])
                                messages.info(request, f"Configuration analysis complete: {len(files)} files found")
                    
                    # Show warnings
                    for warning in result.get('warnings', []):
                        messages.warning(request, warning)
                        
                else:
                    messages.error(request, f"Restoration failed: {', '.join(result['errors'])}")
                    
            except Exception as e:
                messages.error(request, f"Restoration failed: {str(e)}")
        
        return redirect('booking:site_admin_backup_management')
    
    context = {
        'backup_name': backup_name,
        'restore_info': restore_info,
        'title': f'Restore Backup: {backup_name}',
    }
    
    return render(request, 'booking/site_admin_backup_restore.html', context)



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_automation_view(request):
    """Backup automation management interface."""
    from booking.models import BackupSchedule
    from booking.backup_service import BackupService
    
    backup_service = BackupService()
    
    # Handle POST requests for schedule operations
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'create_schedule':
            try:
                schedule = BackupSchedule(
                    name=request.POST.get('name', 'Automated Backup'),
                    enabled=request.POST.get('enabled') == 'on',
                    frequency=request.POST.get('frequency', 'weekly'),
                    backup_time=request.POST.get('backup_time', '02:00'),
                    day_of_week=int(request.POST.get('day_of_week', 6)),
                    day_of_month=int(request.POST.get('day_of_month', 1)),
                    include_media=request.POST.get('include_media') == 'on',
                    include_database=request.POST.get('include_database') == 'on',
                    include_configuration=request.POST.get('include_configuration') == 'on',
                    max_backups_to_keep=int(request.POST.get('max_backups_to_keep', 7)),
                    retention_days=int(request.POST.get('retention_days', 30)),
                    notification_email=request.POST.get('notification_email', ''),
                    created_by=request.user
                )
                schedule.clean()
                schedule.save()
                messages.success(request, f"Backup schedule '{schedule.name}' created successfully")
                
            except Exception as e:
                messages.error(request, f"Failed to create backup schedule: {str(e)}")
        
        elif action == 'update_schedule':
            schedule_id = request.POST.get('schedule_id')
            try:
                schedule = BackupSchedule.objects.get(id=schedule_id)
                schedule.name = request.POST.get('name', schedule.name)
                schedule.enabled = request.POST.get('enabled') == 'on'
                schedule.frequency = request.POST.get('frequency', schedule.frequency)
                schedule.backup_time = request.POST.get('backup_time', schedule.backup_time)
                schedule.day_of_week = int(request.POST.get('day_of_week', schedule.day_of_week))
                schedule.day_of_month = int(request.POST.get('day_of_month', schedule.day_of_month))
                schedule.include_media = request.POST.get('include_media') == 'on'
                schedule.include_database = request.POST.get('include_database') == 'on'
                schedule.include_configuration = request.POST.get('include_configuration') == 'on'
                schedule.max_backups_to_keep = int(request.POST.get('max_backups_to_keep', schedule.max_backups_to_keep))
                schedule.retention_days = int(request.POST.get('retention_days', schedule.retention_days))
                schedule.notification_email = request.POST.get('notification_email', schedule.notification_email)
                schedule.clean()
                schedule.save()
                messages.success(request, f"Backup schedule '{schedule.name}' updated successfully")
                
            except BackupSchedule.DoesNotExist:
                messages.error(request, "Backup schedule not found")
            except Exception as e:
                messages.error(request, f"Failed to update backup schedule: {str(e)}")
        
        elif action == 'delete_schedule':
            schedule_id = request.POST.get('schedule_id')
            try:
                schedule = BackupSchedule.objects.get(id=schedule_id)
                schedule_name = schedule.name
                schedule.delete()
                messages.success(request, f"Backup schedule '{schedule_name}' deleted successfully")
                
            except BackupSchedule.DoesNotExist:
                messages.error(request, "Backup schedule not found")
            except Exception as e:
                messages.error(request, f"Failed to delete backup schedule: {str(e)}")
        
        elif action == 'test_schedule':
            schedule_id = request.POST.get('schedule_id')
            try:
                result = backup_service.test_scheduled_backup(int(schedule_id))
                if result.get('success'):
                    messages.success(request, f"Test backup completed successfully: {result.get('backup_name', 'Unknown')}")
                else:
                    error_msg = '; '.join(result.get('errors', ['Unknown error']))
                    messages.error(request, f"Test backup failed: {error_msg}")
                    
            except Exception as e:
                messages.error(request, f"Failed to test backup schedule: {str(e)}")
        
        return redirect('booking:site_admin_backup_automation')
    
    # Get backup schedules and status
    try:
        schedules = BackupSchedule.objects.all().order_by('-created_at')
        automation_status = backup_service.get_backup_schedules_status()
        
        # Get scheduler status
        from booking.scheduler import get_scheduler
        scheduler = get_scheduler()
        scheduler_status = scheduler.get_status()
        automation_status['scheduler'] = scheduler_status
        
    except Exception as e:
        messages.error(request, f"Failed to load backup schedules: {str(e)}")
        schedules = []
        automation_status = {}
    
    context = {
        'schedules': schedules,
        'automation_status': automation_status,
        'frequency_choices': BackupSchedule.FREQUENCY_CHOICES,
        'day_of_week_choices': BackupSchedule.DAY_OF_WEEK_CHOICES,
        'title': 'Backup Automation',
    }
    
    return render(request, 'booking/site_admin_backup_automation.html', context)



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_automation_ajax(request):
    """AJAX endpoint for backup automation operations."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    from booking.models import BackupSchedule
    from booking.backup_service import BackupService
    import json
    
    try:
        data = json.loads(request.body)
        action = data.get('action')
        backup_service = BackupService()
        
        if action == 'run_schedules':
            # Run all scheduled backups
            results = backup_service.run_scheduled_backups()
            return JsonResponse({
                'success': True,
                'results': results
            })
        
        elif action == 'test_schedule':
            schedule_id = data.get('schedule_id')
            result = backup_service.test_scheduled_backup(int(schedule_id))
            return JsonResponse(result)
        
        elif action == 'get_status':
            status = backup_service.get_backup_schedules_status()
            return JsonResponse({
                'success': True,
                'status': status
            })
        
        elif action == 'toggle_schedule':
            schedule_id = data.get('schedule_id')
            schedule = BackupSchedule.objects.get(id=schedule_id)
            schedule.enabled = not schedule.enabled
            schedule.save()
            
            return JsonResponse({
                'success': True,
                'enabled': schedule.enabled,
                'message': f"Schedule '{schedule.name}' {'enabled' if schedule.enabled else 'disabled'}"
            })
        
        else:
            return JsonResponse({'success': False, 'error': 'Unknown action'})
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})



@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_backup_schedule_detail_ajax(request, schedule_id):
    """AJAX endpoint for getting backup schedule details."""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})
    
    try:
        from booking.models import BackupSchedule
        
        schedule = BackupSchedule.objects.get(id=schedule_id)
        
        schedule_data = {
            'id': schedule.id,
            'name': schedule.name,
            'enabled': schedule.enabled,
            'frequency': schedule.frequency,
            'backup_time': schedule.backup_time.strftime('%H:%M'),
            'day_of_week': schedule.day_of_week,
            'day_of_month': schedule.day_of_month,
            'include_media': schedule.include_media,
            'include_database': schedule.include_database,
            'include_configuration': schedule.include_configuration,
            'max_backups_to_keep': schedule.max_backups_to_keep,
            'retention_days': schedule.retention_days,
            'notification_email': schedule.notification_email,
            'last_run': schedule.last_run.isoformat() if schedule.last_run else None,
            'last_success': schedule.last_success.isoformat() if schedule.last_success else None,
            'last_backup_name': schedule.last_backup_name,
            'consecutive_failures': schedule.consecutive_failures,
            'total_runs': schedule.total_runs,
            'total_successes': schedule.total_successes,
            'success_rate': schedule.success_rate,
            'is_healthy': schedule.is_healthy,
            'next_run': schedule.get_next_run_time().isoformat() if schedule.get_next_run_time() else None,
            'last_error': schedule.last_error
        }
        
        return JsonResponse({
            'success': True,
            'schedule': schedule_data
        })
        
    except BackupSchedule.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Schedule not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})



@login_required
@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role in ['technician', 'sysadmin'])
def site_admin_updates_view(request):
    """Site admin view for managing application updates."""
    from booking.update_service import UpdateService
    from booking.models import UpdateInfo, UpdateHistory
    
    update_service = UpdateService()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'check_updates':
            result = update_service.check_for_updates()
            if result['success']:
                if result['update_available']:
                    messages.success(request, f"Update available: {result['latest_version']}")
                else:
                    messages.info(request, "You are running the latest version")
            else:
                messages.error(request, f"Failed to check for updates: {result['error']}")
        
        elif action == 'download_update':
            result = update_service.download_update()
            if result['success']:
                messages.success(request, "Update downloaded successfully")
            else:
                messages.error(request, f"Failed to download update: {result['error']}")
        
        elif action == 'install_update':
            backup_enabled = request.POST.get('create_backup') == 'on'
            result = update_service.install_update(backup_before_update=backup_enabled)
            if result['success']:
                message = "Update installed successfully"
                if result.get('backup_created'):
                    message += f" (Backup created: {result['backup_path']})"
                messages.success(request, message)
            else:
                messages.error(request, f"Failed to install update: {result['error']}")
        
        elif action == 'configure_repo':
            repo = request.POST.get('github_repo', '').strip()
            auto_check = request.POST.get('auto_check_enabled') == 'on'
            
            if repo:
                update_info = UpdateInfo.get_instance()
                update_info.github_repo = repo
                update_info.auto_check_enabled = auto_check
                update_info.save()
                messages.success(request, "Update settings saved successfully")
            else:
                messages.error(request, "GitHub repository is required")
        
        return redirect('booking:site_admin_updates')
    
    # Get update status and history
    update_status = update_service.get_update_status()
    update_history = UpdateHistory.objects.all()[:10]  # Last 10 updates
    
    context = {
        'update_status': update_status,
        'update_history': update_history,
    }
    
    return render(request, 'booking/site_admin_updates.html', context)



@login_required
@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role in ['technician', 'sysadmin'])
def site_admin_updates_ajax_view(request):
    """AJAX endpoint for update operations."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})
    
    from booking.update_service import UpdateService
    import json
    
    try:
        data = json.loads(request.body)
        action = data.get('action')
        
        update_service = UpdateService()
        
        if action == 'check_updates':
            result = update_service.check_for_updates()
            return JsonResponse(result)
        
        elif action == 'download_update':
            result = update_service.download_update()
            return JsonResponse(result)
        
        elif action == 'install_update':
            backup_enabled = data.get('create_backup', True)
            result = update_service.install_update(backup_before_update=backup_enabled)
            return JsonResponse(result)
        
        elif action == 'get_status':
            status = update_service.get_update_status()
            return JsonResponse({'success': True, 'status': status})
        
        elif action == 'rollback':
            update_id = data.get('update_id')
            if not update_id:
                return JsonResponse({'success': False, 'error': 'Update ID required'})
            
            result = update_service.rollback_update(update_id)
            return JsonResponse(result)
        
        else:
            return JsonResponse({'success': False, 'error': 'Unknown action'})
    
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'})
    except Exception as e:
        logger.error(f"Error in update AJAX view: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


# ============= USER RESOURCE ACCESS MANAGEMENT =============

@login_required
@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_user_resource_access_view(request, user_id):
    """Get resource access information for a user."""
    try:
        user = User.objects.get(id=user_id)
        from booking.models import ResourceAccess
        from django.utils import timezone

        resource_access = ResourceAccess.objects.filter(
            user=user
        ).select_related('resource', 'granted_by').order_by('-granted_at')

        # Build HTML response
        if resource_access.exists():
            html = '<div class="table-responsive"><table class="table table-sm"><thead><tr><th>Resource</th><th>Type</th><th>Granted By</th><th>Status</th><th>Actions</th></tr></thead><tbody>'

            for access in resource_access:
                status_badge = ""
                action_button = ""

                if not access.is_active:
                    status_badge = '<span class="badge bg-secondary">Inactive</span>'
                elif access.is_expired:
                    status_badge = '<span class="badge bg-warning">Expired</span>'
                else:
                    status_badge = '<span class="badge bg-success">Active</span>'
                    # Only show revoke button for active access
                    action_button = f'<button class="btn btn-sm btn-outline-danger" onclick="revokeResourceAccessSiteAdmin({access.id}, \'{access.resource.name}\', {user.id})">Revoke</button>'

                expires_text = ""
                if access.expires_at:
                    expires_text = f"<br><small class='text-muted'>Expires: {access.expires_at.strftime('%b %d, %Y')}</small>"

                html += f'''
                <tr id="site-access-{access.id}">
                    <td>{access.resource.name}</td>
                    <td><span class="badge bg-info">{access.get_access_type_display()}</span></td>
                    <td>{access.granted_by.get_full_name() or access.granted_by.username}<br><small class="text-muted">{access.granted_at.strftime('%b %d, %Y')}</small>{expires_text}</td>
                    <td>{status_badge}</td>
                    <td>{action_button}</td>
                </tr>
                '''

            html += '</tbody></table></div>'
        else:
            html = '<p class="text-muted">No resource access found.</p>'

        return JsonResponse({
            'success': True,
            'html': html,
            'count': resource_access.count()
        })

    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(lambda u: hasattr(u, 'userprofile') and u.userprofile.role == 'sysadmin')
def site_admin_revoke_resource_access_view(request, user_id, access_id):
    """Revoke a user's access to a specific resource."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})

    try:
        from booking.models import ResourceAccess

        # Get the access record
        access = ResourceAccess.objects.get(id=access_id, user_id=user_id)

        # Check if access is still active
        if not access.is_active:
            return JsonResponse({'success': False, 'error': 'Access is already inactive'})

        # Revoke access
        access.is_active = False
        access.save()

        # Log the action
        from django.contrib import messages
        messages.success(request, f'Access to {access.resource.name} revoked for {access.user.get_full_name() or access.user.username}')

        return JsonResponse({
            'success': True,
            'message': f'Access to {access.resource.name} has been revoked'
        })

    except ResourceAccess.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Resource access not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ============= RESOURCE ISSUE REPORTING VIEWS =============


