"""
Query optimization utilities for the Labitory.

This module provides optimized querysets and utility functions to prevent N+1 queries
and improve database performance throughout the application.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors
"""

from django.db.models import Prefetch, Q, Count, Avg, Sum, F, Value, CharField
from django.db.models.functions import Coalesce
from functools import wraps
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger('booking.query_optimization')


class OptimizedQuerySets:
    """Centralized optimized querysets to prevent N+1 queries."""
    
    @staticmethod
    def get_booking_queryset(include_attendees=True, include_history=False, include_checkin_events=False):
        """
        Get optimized booking queryset with related objects.
        
        Args:
            include_attendees: Include attendee information
            include_history: Include booking history records
            include_checkin_events: Include check-in/out events
        """
        from ..models import Booking, BookingAttendee, BookingHistory, CheckInOutEvent
        
        queryset = Booking.objects.select_related(
            'resource',
            'resource__college',
            'resource__college__faculty',
            'user',
            'user__userprofile',
            'user__userprofile__department',
            'user__userprofile__college',
            'user__userprofile__faculty',
            'approved_by',
            'approved_by__userprofile',
            'template_used',
            'billing_record',
            'billing_record__billing_rate',
            'billing_record__billing_period',
        )
        
        if include_attendees:
            queryset = queryset.prefetch_related(
                Prefetch(
                    'bookingattendee_set',
                    queryset=BookingAttendee.objects.select_related(
                        'user',
                        'user__userprofile'
                    )
                )
            )
        
        if include_history:
            queryset = queryset.prefetch_related(
                Prefetch(
                    'history',
                    queryset=BookingHistory.objects.select_related('user').order_by('-timestamp')
                )
            )
        
        if include_checkin_events:
            queryset = queryset.prefetch_related(
                Prefetch(
                    'checkin_events',
                    queryset=CheckInOutEvent.objects.select_related('user').order_by('-timestamp')
                )
            )
        
        # Prefetch prerequisite bookings with optimization
        queryset = queryset.prefetch_related(
            Prefetch(
                'prerequisite_bookings',
                queryset=Booking.objects.select_related('resource', 'user')
            ),
            'dependent_bookings'
        )
        
        return queryset
    
    @staticmethod
    def get_resource_queryset(include_access=False, include_issues=False, include_training=False):
        """
        Get optimized resource queryset with related objects.
        
        Args:
            include_access: Include access permissions
            include_issues: Include resource issues
            include_training: Include training requirements
        """
        from ..models import Resource, ResourceAccess, ResourceIssue, ResourceTrainingRequirement
        
        queryset = Resource.objects.select_related(
            'closed_by',
            'closed_by__userprofile',
        )
        
        if include_access:
            queryset = queryset.prefetch_related(
                Prefetch(
                    'access_permissions',
                    queryset=ResourceAccess.objects.select_related(
                        'user',
                        'user__userprofile',
                        'granted_by'
                    ).filter(is_active=True)
                ),
                Prefetch(
                    'responsible_persons',
                    queryset=Resource.responsible_persons.through.objects.select_related(
                        'user',
                        'user__userprofile',
                        'assigned_by'
                    ).filter(is_active=True)
                )
            )
        
        if include_issues:
            queryset = queryset.prefetch_related(
                Prefetch(
                    'issues',
                    queryset=ResourceIssue.objects.select_related(
                        'reported_by',
                        'assigned_to',
                        'related_booking'
                    ).filter(status__in=['open', 'in_progress']).order_by('-severity', '-created_at')
                )
            )
        
        if include_training:
            queryset = queryset.prefetch_related(
                Prefetch(
                    'training_requirements',
                    queryset=ResourceTrainingRequirement.objects.select_related(
                        'training_course'
                    ).filter(is_mandatory=True).order_by('order')
                )
            )
        
        # Add aggregated counts for common queries
        queryset = queryset.annotate(
            active_bookings_count=Count(
                'bookings',
                filter=Q(bookings__status__in=['approved', 'pending'])
            ),
            open_issues_count=Count(
                'issues',
                filter=Q(issues__status__in=['open', 'in_progress'])
            )
        )
        
        return queryset
    
    @staticmethod
    def get_notification_queryset(user=None, unread_only=False):
        """
        Get optimized notification queryset.
        
        Args:
            user: Filter notifications for specific user
            unread_only: Only include unread notifications
        """
        from ..models import Notification
        
        queryset = Notification.objects.select_related(
            'user',
            'user__userprofile',
            'booking',
            'booking__resource',
            'resource',
            'maintenance',
            'maintenance__resource',
            'access_request',
            'access_request__resource',
            'access_request__user',
            'training_request',
            'training_request__resource',
            'training_request__user',
        )
        
        if user:
            queryset = queryset.filter(user=user)
        
        if unread_only:
            queryset = queryset.filter(status__in=['pending', 'sent']).exclude(status='read')
        
        return queryset.order_by('-created_at')
    
    @staticmethod
    def get_user_profile_queryset():
        """Get optimized user profile queryset."""
        from ..models import UserProfile
        
        return UserProfile.objects.select_related(
            'user',
            'faculty',
            'college',
            'college__faculty',
            'department',
            'department__college',
            'department__college__faculty',
        ).prefetch_related(
            'user__groups',
            'user__user_permissions',
        )
    
    @staticmethod
    def get_access_request_queryset():
        """Get optimized access request queryset."""
        from ..models import AccessRequest
        
        return AccessRequest.objects.select_related(
            'resource',
            'user',
            'user__userprofile',
            'user__userprofile__department',
            'reviewed_by',
            'reviewed_by__userprofile',
            'safety_induction_confirmed_by',
            'lab_training_confirmed_by',
            'risk_assessment_confirmed_by',
        )
    
    @staticmethod
    def get_billing_record_queryset(billing_period=None):
        """
        Get optimized billing record queryset.
        
        Args:
            billing_period: Filter by specific billing period
        """
        from ..models import BillingRecord
        
        queryset = BillingRecord.objects.select_related(
            'booking',
            'booking__resource',
            'booking__user',
            'billing_period',
            'billing_rate',
            'resource',
            'user',
            'user__userprofile',
            'department',
            'department__college',
            'department__college__faculty',
            'confirmed_by',
            'adjusted_by',
        )
        
        if billing_period:
            queryset = queryset.filter(billing_period=billing_period)
        
        # Add aggregated totals
        queryset = queryset.annotate(
            net_charge=F('total_charge') - Coalesce(F('discount_amount'), Value(0))
        )
        
        return queryset
    
    @staticmethod
    def get_maintenance_queryset(include_documents=False):
        """
        Get optimized maintenance queryset.
        
        Args:
            include_documents: Include maintenance documents
        """
        from ..models import Maintenance, MaintenanceDocument
        
        queryset = Maintenance.objects.select_related(
            'resource',
            'vendor',
            'created_by',
            'created_by__userprofile',
            'assigned_to',
            'assigned_to__userprofile',
            'approved_by',
            'approved_by__userprofile',
        ).prefetch_related(
            'affects_other_resources',
            'prerequisite_maintenances',
            'dependent_maintenances',
        )
        
        if include_documents:
            queryset = queryset.prefetch_related(
                Prefetch(
                    'documents',
                    queryset=MaintenanceDocument.objects.select_related('uploaded_by')
                )
            )
        
        return queryset


class QueryOptimizationMiddleware:
    """Middleware to detect and log N+1 queries in development."""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Only enable in development
        from django.conf import settings
        if settings.DEBUG:
            from django.db import connection
            from django.db import reset_queries
            
            reset_queries()
            response = self.get_response(request)
            
            # Log if too many queries
            num_queries = len(connection.queries)
            if num_queries > 10:
                logger.warning(
                    f"High query count detected: {num_queries} queries for {request.path}"
                )
                
                # In development, log duplicate queries
                query_counts = {}
                for query in connection.queries:
                    sql = query['sql']
                    # Normalize SQL for comparison
                    normalized = ' '.join(sql.split())[:100]
                    query_counts[normalized] = query_counts.get(normalized, 0) + 1
                
                duplicates = {k: v for k, v in query_counts.items() if v > 1}
                if duplicates:
                    logger.warning(f"Duplicate queries detected: {duplicates}")
        else:
            response = self.get_response(request)
        
        return response


class PaginationMixin:
    """Mixin to add efficient pagination to viewsets."""
    
    # Default page size
    page_size = 20
    
    def get_paginated_queryset(self, queryset, request):
        """
        Get paginated queryset with optimization.
        
        Includes total count optimization for large datasets.
        """
        from django.core.paginator import Paginator
        from django.db.models import Count
        
        page_number = request.GET.get('page', 1)
        page_size = request.GET.get('page_size', self.page_size)
        
        try:
            page_size = min(int(page_size), 100)  # Max 100 items per page
        except (ValueError, TypeError):
            page_size = self.page_size
        
        # Use count optimization for large querysets
        if queryset.model._meta.db_table in ['booking_booking', 'booking_notification']:
            # For frequently queried large tables, use approximate count
            paginator = Paginator(queryset, page_size)
            paginator._count = queryset.aggregate(count=Count('id'))['count']
        else:
            paginator = Paginator(queryset, page_size)
        
        try:
            page = paginator.page(page_number)
        except:
            page = paginator.page(1)
        
        return {
            'results': page.object_list,
            'pagination': {
                'count': paginator.count,
                'page': page.number,
                'pages': paginator.num_pages,
                'has_next': page.has_next(),
                'has_previous': page.has_previous(),
            }
        }


def optimize_json_queries(queryset, json_field_name, filters: Dict[str, Any]):
    """
    Optimize queries on JSONField with proper indexing hints.
    
    Args:
        queryset: Base queryset
        json_field_name: Name of the JSONField
        filters: Dictionary of JSON path filters
    
    Returns:
        Optimized queryset
    """
    from django.db.models import Q
    from django.contrib.postgres.fields import JSONField
    
    # Build optimized JSON queries
    q_objects = Q()
    
    for json_path, value in filters.items():
        # Use proper JSON path syntax for database
        if '.' in json_path:
            # Nested path
            path_parts = json_path.split('.')
            lookup = f"{json_field_name}__" + "__".join(path_parts)
        else:
            # Direct key
            lookup = f"{json_field_name}__{json_path}"
        
        if value is None:
            q_objects &= Q(**{f"{lookup}__isnull": True})
        elif isinstance(value, (list, tuple)):
            q_objects &= Q(**{f"{lookup}__in": value})
        else:
            q_objects &= Q(**{lookup: value})
    
    return queryset.filter(q_objects)


def cached_property_with_prefetch(prefetch_related=None):
    """
    Decorator for cached properties that need prefetch_related.
    
    Ensures related objects are prefetched before accessing property.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self):
            if prefetch_related:
                # Check if prefetch was done
                if not hasattr(self, '_prefetch_done'):
                    logger.warning(
                        f"Accessing {func.__name__} without prefetch_related({prefetch_related}). "
                        f"Consider using OptimizedQuerySets."
                    )
            
            if not hasattr(self, f'_cached_{func.__name__}'):
                setattr(self, f'_cached_{func.__name__}', func(self))
            return getattr(self, f'_cached_{func.__name__}')
        
        return property(wrapper)
    
    return decorator


class DatabaseConnectionPool:
    """Database connection pooling configuration."""
    
    @staticmethod
    def configure_pooling(database_config: dict) -> dict:
        """
        Configure database connection pooling.
        
        Args:
            database_config: Django database configuration dictionary
        
        Returns:
            Updated configuration with pooling settings
        """
        engine = database_config.get('ENGINE', '')
        
        if 'postgresql' in engine:
            # PostgreSQL connection pooling
            database_config.update({
                'CONN_MAX_AGE': 600,  # Keep connections alive for 10 minutes
                'OPTIONS': {
                    **database_config.get('OPTIONS', {}),
                    'connect_timeout': 10,
                    'options': '-c statement_timeout=30000',  # 30 second statement timeout
                    # For pgbouncer compatibility
                    'sslmode': 'prefer',
                    'server_side_binding': True,
                }
            })
        elif 'mysql' in engine:
            # MySQL connection pooling
            database_config.update({
                'CONN_MAX_AGE': 600,
                'OPTIONS': {
                    **database_config.get('OPTIONS', {}),
                    'connect_timeout': 10,
                    'read_timeout': 30,
                    'write_timeout': 30,
                    'max_connections': 100,
                    'wait_timeout': 28800,  # 8 hours
                    'interactive_timeout': 28800,
                }
            })
        
        return database_config
    
    @staticmethod
    def get_pool_status():
        """Get current connection pool status for monitoring."""
        from django.db import connection
        
        with connection.cursor() as cursor:
            if 'postgresql' in connection.vendor:
                cursor.execute("""
                    SELECT count(*) as total,
                           sum(case when state = 'active' then 1 else 0 end) as active,
                           sum(case when state = 'idle' then 1 else 0 end) as idle
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                """)
                return cursor.fetchone()
            elif 'mysql' in connection.vendor:
                cursor.execute("SHOW STATUS LIKE 'Threads%'")
                return dict(cursor.fetchall())
        
        return None


# Export optimized managers for models
class OptimizedBookingManager:
    """Optimized manager for Booking model."""
    
    @staticmethod
    def get_queryset():
        return OptimizedQuerySets.get_booking_queryset()
    
    @staticmethod
    def for_calendar_view(resource_id, start_date, end_date):
        """Get bookings optimized for calendar view."""
        from ..models import Booking
        
        return Booking.objects.select_related(
            'resource',
            'user',
            'user__userprofile'
        ).filter(
            resource_id=resource_id,
            start_time__lte=end_date,
            end_time__gte=start_date,
            status__in=['approved', 'pending']
        ).order_by('start_time')
    
    @staticmethod
    def for_user_dashboard(user):
        """Get bookings optimized for user dashboard."""
        from ..models import Booking
        from django.utils import timezone
        
        return Booking.objects.select_related(
            'resource',
            'approved_by'
        ).filter(
            user=user,
            end_time__gte=timezone.now()
        ).order_by('start_time')[:10]  # Limit to next 10 bookings


# Utility function to analyze query performance
def analyze_query_performance(queryset):
    """
    Analyze and log query performance for a queryset.
    
    Useful for development and debugging.
    """
    from django.db import connection
    from django.db import reset_queries
    import time
    
    reset_queries()
    start_time = time.time()
    
    # Force evaluation
    list(queryset)
    
    end_time = time.time()
    
    queries = connection.queries
    total_time = sum(float(q['time']) for q in queries)
    
    logger.info(f"""
    Query Performance Analysis:
    - Total queries: {len(queries)}
    - Total DB time: {total_time:.3f}s
    - Total execution time: {end_time - start_time:.3f}s
    - Queries: {[q['sql'][:100] for q in queries]}
    """)
    
    return {
        'query_count': len(queries),
        'db_time': total_time,
        'total_time': end_time - start_time,
        'queries': queries
    }