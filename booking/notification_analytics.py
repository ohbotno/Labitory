# booking/notification_analytics.py
"""
Notification analytics and tracking for the Labitory system.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from typing import Dict, List, Optional
import logging

from .models import Notification, NotificationPreference, UserProfile

logger = logging.getLogger(__name__)


class NotificationAnalytics:
    """Analytics service for notification system."""
    
    def get_notification_stats(self, days: int = 30) -> Dict:
        """Get notification statistics for the specified period."""
        start_date = timezone.now() - timedelta(days=days)
        
        # Basic stats
        total_notifications = Notification.objects.filter(created_at__gte=start_date).count()
        sent_notifications = Notification.objects.filter(
            created_at__gte=start_date,
            status='sent'
        ).count()
        failed_notifications = Notification.objects.filter(
            created_at__gte=start_date,
            status='failed'
        ).count()
        read_notifications = Notification.objects.filter(
            created_at__gte=start_date,
            status='read'
        ).count()
        
        # Delivery success rate
        delivery_rate = (sent_notifications / total_notifications * 100) if total_notifications > 0 else 0
        read_rate = (read_notifications / sent_notifications * 100) if sent_notifications > 0 else 0
        
        # Notifications by type
        type_stats = Notification.objects.filter(
            created_at__gte=start_date
        ).values('notification_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Notifications by delivery method
        method_stats = Notification.objects.filter(
            created_at__gte=start_date
        ).values('delivery_method').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Daily notification volume
        daily_stats = []
        for i in range(days):
            day = start_date + timedelta(days=i)
            day_end = day + timedelta(days=1)
            
            daily_count = Notification.objects.filter(
                created_at__gte=day,
                created_at__lt=day_end
            ).count()
            
            daily_stats.append({
                'date': day.date(),
                'count': daily_count
            })
        
        return {
            'period_days': days,
            'total_notifications': total_notifications,
            'sent_notifications': sent_notifications,
            'failed_notifications': failed_notifications,
            'read_notifications': read_notifications,
            'delivery_rate': round(delivery_rate, 2),
            'read_rate': round(read_rate, 2),
            'type_breakdown': list(type_stats),
            'method_breakdown': list(method_stats),
            'daily_volume': daily_stats
        }
    
    def get_user_notification_stats(self, user, days: int = 30) -> Dict:
        """Get notification statistics for a specific user."""
        start_date = timezone.now() - timedelta(days=days)
        
        user_notifications = Notification.objects.filter(
            user=user,
            created_at__gte=start_date
        )
        
        total = user_notifications.count()
        sent = user_notifications.filter(status='sent').count()
        read = user_notifications.filter(status='read').count()
        failed = user_notifications.filter(status='failed').count()
        
        # Most common notification types for this user
        type_stats = user_notifications.values('notification_type').annotate(
            count=Count('id')
        ).order_by('-count')[:5]
        
        # Read rate
        read_rate = (read / sent * 100) if sent > 0 else 0
        
        return {
            'user': user.get_full_name() or user.username,
            'period_days': days,
            'total_notifications': total,
            'sent_notifications': sent,
            'read_notifications': read,
            'failed_notifications': failed,
            'read_rate': round(read_rate, 2),
            'top_notification_types': list(type_stats)
        }
    
    def get_notification_preferences_stats(self) -> Dict:
        """Get statistics about user notification preferences."""
        total_users = UserProfile.objects.count()
        
        # Users with custom preferences
        users_with_prefs = NotificationPreference.objects.values('user').distinct().count()
        
        # Most popular delivery methods
        method_stats = NotificationPreference.objects.filter(
            is_enabled=True
        ).values('delivery_method').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Most popular notification types
        type_stats = NotificationPreference.objects.filter(
            is_enabled=True
        ).values('notification_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Frequency preferences
        frequency_stats = NotificationPreference.objects.values('frequency').annotate(
            count=Count('id')
        ).order_by('-count')
        
        return {
            'total_users': total_users,
            'users_with_custom_preferences': users_with_prefs,
            'preference_adoption_rate': round((users_with_prefs / total_users * 100), 2) if total_users > 0 else 0,
            'popular_delivery_methods': list(method_stats),
            'popular_notification_types': list(type_stats),
            'frequency_preferences': list(frequency_stats)
        }
    
    def get_escalation_stats(self, days: int = 30) -> Dict:
        """Get escalation notification statistics."""
        start_date = timezone.now() - timedelta(days=days)
        
        escalation_notifications = Notification.objects.filter(
            notification_type='escalation_notification',
            created_at__gte=start_date
        )
        
        total_escalations = escalation_notifications.count()
        
        # Escalations by level
        level_stats = []
        for level in [1, 2, 3]:
            count = escalation_notifications.filter(
                metadata__escalation_level=level
            ).count()
            level_stats.append({
                'level': level,
                'count': count
            })
        
        # Escalations by request type
        type_stats = escalation_notifications.values(
            'metadata__request_type'
        ).annotate(
            count=Count('id')
        ).order_by('-count')
        
        return {
            'period_days': days,
            'total_escalations': total_escalations,
            'escalation_levels': level_stats,
            'request_types': list(type_stats)
        }
    
    def get_performance_metrics(self) -> Dict:
        """Get notification system performance metrics."""
        # Average notification processing time (if we had timestamps)
        # For now, basic metrics
        
        pending_count = Notification.objects.filter(status='pending').count()
        failed_count = Notification.objects.filter(status='failed').count()
        
        # Recent failure rate
        recent_notifications = Notification.objects.filter(
            created_at__gte=timezone.now() - timedelta(hours=24)
        )
        
        recent_total = recent_notifications.count()
        recent_failed = recent_notifications.filter(status='failed').count()
        recent_failure_rate = (recent_failed / recent_total * 100) if recent_total > 0 else 0
        
        return {
            'pending_notifications': pending_count,
            'failed_notifications': failed_count,
            'recent_failure_rate': round(recent_failure_rate, 2),
            'system_health': 'good' if recent_failure_rate < 5 else 'warning' if recent_failure_rate < 15 else 'critical'
        }
    
    def generate_analytics_report(self, days: int = 30) -> Dict:
        """Generate comprehensive analytics report."""
        return {
            'generated_at': timezone.now(),
            'notification_stats': self.get_notification_stats(days),
            'preference_stats': self.get_notification_preferences_stats(),
            'escalation_stats': self.get_escalation_stats(days),
            'performance_metrics': self.get_performance_metrics()
        }


# Global analytics instance
notification_analytics = NotificationAnalytics()