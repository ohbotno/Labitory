# booking/push_service.py
"""
Web Push notification service using pywebpush.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

import json
import logging
from typing import Dict, Any, Optional, List
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)

# Import pywebpush conditionally
try:
    from pywebpush import webpush, WebPushException
    PUSH_AVAILABLE = True
except ImportError:
    PUSH_AVAILABLE = False
    logger.warning("pywebpush not installed. Push notifications will be disabled.")



class PushNotificationService:
    """Service for sending web push notifications."""
    
    def __init__(self):
        self.vapid_private_key = getattr(settings, 'VAPID_PRIVATE_KEY', None)
        self.vapid_public_key = getattr(settings, 'VAPID_PUBLIC_KEY', None)
        self.vapid_subject = getattr(settings, 'VAPID_SUBJECT', 'mailto:admin@example.com')
    
    def is_available(self) -> bool:
        """Check if push notification service is available and configured."""
        return (PUSH_AVAILABLE and 
                self.vapid_private_key and 
                self.vapid_public_key)
    
    def send_push_notification(
        self, 
        subscription, 
        title: str, 
        message: str,
        data: Optional[Dict[str, Any]] = None,
        icon: Optional[str] = None,
        badge: Optional[str] = None,
        actions: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Send push notification to a specific subscription.
        
        Args:
            subscription: PushSubscription instance
            title: Notification title
            message: Notification body
            data: Additional data to include
            icon: URL to notification icon
            badge: URL to notification badge
            actions: List of notification actions
            
        Returns:
            bool: True if notification was sent successfully
        """
        if not self.is_available():
            logger.warning("Push notification service not available")
            return False
        
        # Build notification payload
        payload = {
            "title": title,
            "body": message,
            "icon": icon or "/static/images/logo.png",
            "badge": badge or "/static/images/logo.png",
            "data": data or {},
            "requireInteraction": True,  # Keep notification visible until user interacts
            "timestamp": int(__import__('time').time() * 1000)
        }
        
        # Add notification actions if provided
        if actions:
            payload["actions"] = actions
        
        try:
            # Send push notification
            webpush(
                subscription_info=subscription.to_dict(),
                data=json.dumps(payload),
                vapid_private_key=self.vapid_private_key,
                vapid_claims={
                    "sub": self.vapid_subject
                },
                content_encoding="aes128gcm"
            )
            
            # Update subscription last used time
            subscription.last_used = __import__('django.utils.timezone').timezone.now()
            subscription.save(update_fields=['last_used'])
            
            logger.info(f"Push notification sent to {subscription.user.username}")
            return True
            
        except WebPushException as e:
            logger.error(f"Push notification failed for {subscription.user.username}: {e}")
            
            # Handle expired/invalid subscriptions
            if e.response and e.response.status_code in [410, 404]:
                subscription.is_active = False
                subscription.save(update_fields=['is_active'])
                logger.info(f"Deactivated invalid push subscription for {subscription.user.username}")
            
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending push notification: {e}")
            return False
    
    def send_to_user(
        self, 
        user, 
        title: str, 
        message: str,
        **kwargs
    ) -> int:
        """
        Send push notification to all active subscriptions for a user.
        
        Args:
            user: Django User instance
            title: Notification title
            message: Notification body
            **kwargs: Additional arguments for send_push_notification
            
        Returns:
            int: Number of notifications sent successfully
        """
        if not self.is_available():
            return 0
        
        from .models import PushSubscription
        subscriptions = PushSubscription.objects.filter(
            user=user,
            is_active=True
        )
        
        sent_count = 0
        for subscription in subscriptions:
            if self.send_push_notification(subscription, title, message, **kwargs):
                sent_count += 1
        
        return sent_count
    
    def create_subscription(
        self, 
        user, 
        endpoint: str, 
        p256dh_key: str, 
        auth_key: str,
        user_agent: str = ""
    ):
        """
        Create or update push subscription for a user.
        
        Args:
            user: Django User instance
            endpoint: Push service endpoint URL
            p256dh_key: Public key for encryption
            auth_key: Authentication secret
            user_agent: Browser/device information
            
        Returns:
            PushSubscription: Created or updated subscription
        """
        from .models import PushSubscription
        subscription, created = PushSubscription.objects.update_or_create(
            user=user,
            endpoint=endpoint,
            defaults={
                'p256dh_key': p256dh_key,
                'auth_key': auth_key,
                'user_agent': user_agent,
                'is_active': True
            }
        )
        
        action = "Created" if created else "Updated"
        logger.info(f"{action} push subscription for {user.username}")
        
        return subscription
    
    def remove_subscription(self, user, endpoint: str) -> bool:
        """
        Remove push subscription for a user.
        
        Args:
            user: Django User instance
            endpoint: Push service endpoint URL
            
        Returns:
            bool: True if subscription was removed
        """
        try:
            from .models import PushSubscription
            subscription = PushSubscription.objects.get(user=user, endpoint=endpoint)
            subscription.delete()
            logger.info(f"Removed push subscription for {user.username}")
            return True
        except PushSubscription.DoesNotExist:
            logger.warning(f"Push subscription not found for {user.username}")
            return False
    
    def get_vapid_public_key(self) -> Optional[str]:
        """Get VAPID public key for client-side subscription."""
        return self.vapid_public_key
    
    def format_notification_for_push(self, notification) -> Dict[str, Any]:
        """
        Format notification for push delivery.
        
        Args:
            notification: Notification instance
            
        Returns:
            dict: Formatted notification data
        """
        # Build notification data
        data = {
            'notification_id': notification.id,
            'notification_type': notification.notification_type,
            'priority': notification.priority,
            'url': self._get_notification_url(notification)
        }
        
        # Add related object data
        if notification.booking:
            data.update({
                'booking_id': notification.booking.id,
                'resource_name': notification.booking.resource.name,
                'start_time': notification.booking.start_time.isoformat()
            })
        
        if notification.resource:
            data.update({
                'resource_id': notification.resource.id,
                'resource_name': notification.resource.name
            })
        
        # Create actions based on notification type
        actions = self._get_notification_actions(notification)
        
        return {
            'data': data,
            'actions': actions
        }
    
    def _get_notification_url(self, notification) -> str:
        """Get URL to navigate to when notification is clicked."""
        base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        
        if notification.booking:
            return f"{base_url}/booking/{notification.booking.id}/"
        elif notification.resource:
            return f"{base_url}/resources/{notification.resource.id}/"
        elif notification.access_request:
            return f"{base_url}/resources/{notification.access_request.resource.id}/"
        else:
            return f"{base_url}/notifications/"
    
    def _get_notification_actions(self, notification) -> List[Dict[str, Any]]:
        """Get notification actions based on type."""
        actions = []
        
        if notification.notification_type == 'booking_confirmed':
            actions.append({
                'action': 'view',
                'title': 'View Booking',
                'icon': '/static/images/calendar-icon.png'
            })
        elif notification.notification_type in ['access_request_submitted', 'training_request_submitted']:
            actions.append({
                'action': 'view',
                'title': 'View Request',
                'icon': '/static/images/request-icon.png'
            })
        elif notification.notification_type == 'approval_request':
            actions.extend([
                {
                    'action': 'approve',
                    'title': 'Approve',
                    'icon': '/static/images/check-icon.png'
                },
                {
                    'action': 'review',
                    'title': 'Review',
                    'icon': '/static/images/eye-icon.png'
                }
            ])
        
        # Always add a dismiss action
        actions.append({
            'action': 'dismiss',
            'title': 'Dismiss',
            'icon': '/static/images/close-icon.png'
        })
        
        return actions
    
    def cleanup_inactive_subscriptions(self, days_old: int = 30) -> int:
        """
        Remove inactive push subscriptions.
        
        Args:
            days_old: Remove subscriptions older than this many days
            
        Returns:
            int: Number of subscriptions removed
        """
        from django.utils import timezone
        from datetime import timedelta
        from .models import PushSubscription
        
        cutoff_date = timezone.now() - timedelta(days=days_old)
        
        # Remove inactive subscriptions
        inactive_count = PushSubscription.objects.filter(
            models.Q(is_active=False) | models.Q(last_used__lt=cutoff_date)
        ).count()
        
        PushSubscription.objects.filter(
            models.Q(is_active=False) | models.Q(last_used__lt=cutoff_date)
        ).delete()
        
        logger.info(f"Cleaned up {inactive_count} inactive push subscriptions")
        return inactive_count


# Global push service instance
push_service = PushNotificationService()