# booking/signals/cache_signals.py
"""
Django signals for automatic cache invalidation.

This module connects Django model signals to cache invalidation logic,
ensuring that cached data is properly invalidated when models change.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import logging
from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils import timezone

from ..models import Booking, Resource, Notification, AccessRequest
from ..utils.cache_utils import (
    invalidate_booking_caches, 
    invalidate_user_caches,
    ResourceAvailabilityCache,
    PermissionCache
)

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Booking)
def invalidate_booking_cache_on_save(sender, instance, created, **kwargs):
    """Invalidate relevant caches when a booking is saved."""
    try:
        invalidate_booking_caches(
            booking_id=instance.id,
            user_id=instance.user_id,
            resource_id=instance.resource_id
        )
        
        # Invalidate resource availability for the booking date
        date_str = instance.start_time.date().isoformat()
        ResourceAvailabilityCache.invalidate_resource_availability(
            resource_id=instance.resource_id,
            date_str=date_str
        )
        
        logger.debug(f"Invalidated caches for booking {instance.id} ({'created' if created else 'updated'})")
        
    except Exception as e:
        logger.error(f"Error invalidating booking cache: {e}")


@receiver(post_delete, sender=Booking)
def invalidate_booking_cache_on_delete(sender, instance, **kwargs):
    """Invalidate relevant caches when a booking is deleted."""
    try:
        invalidate_booking_caches(
            booking_id=instance.id,
            user_id=instance.user_id,
            resource_id=instance.resource_id
        )
        
        # Invalidate resource availability
        date_str = instance.start_time.date().isoformat()
        ResourceAvailabilityCache.invalidate_resource_availability(
            resource_id=instance.resource_id,
            date_str=date_str
        )
        
        logger.debug(f"Invalidated caches for deleted booking {instance.id}")
        
    except Exception as e:
        logger.error(f"Error invalidating booking cache on delete: {e}")


@receiver(post_save, sender=Resource)
def invalidate_resource_cache_on_save(sender, instance, created, **kwargs):
    """Invalidate resource-related caches when a resource is saved."""
    try:
        # Invalidate all availability cache for this resource
        ResourceAvailabilityCache.invalidate_resource_availability(
            resource_id=instance.id
        )
        
        logger.debug(f"Invalidated resource cache for resource {instance.id} ({'created' if created else 'updated'})")
        
    except Exception as e:
        logger.error(f"Error invalidating resource cache: {e}")


@receiver(post_save, sender=User)
def invalidate_user_cache_on_save(sender, instance, created, **kwargs):
    """Invalidate user-related caches when user data changes."""
    try:
        invalidate_user_caches(user_id=instance.id)
        
        logger.debug(f"Invalidated user cache for user {instance.id} ({'created' if created else 'updated'})")
        
    except Exception as e:
        logger.error(f"Error invalidating user cache: {e}")


@receiver(m2m_changed, sender=User.groups.through)
def invalidate_user_permissions_on_group_change(sender, instance, action, pk_set, **kwargs):
    """Invalidate user permissions when group membership changes."""
    try:
        if action in ('post_add', 'post_remove', 'post_clear'):
            PermissionCache.invalidate_user_permissions(user_id=instance.id)
            logger.debug(f"Invalidated permissions cache for user {instance.id} due to group change")
            
    except Exception as e:
        logger.error(f"Error invalidating user permissions cache: {e}")


@receiver(post_save, sender=AccessRequest)
def invalidate_access_cache_on_save(sender, instance, created, **kwargs):
    """Invalidate caches when access requests change."""
    try:
        # User's permissions might change based on access requests
        PermissionCache.invalidate_user_permissions(user_id=instance.user_id)
        
        # Resource availability might be affected
        if hasattr(instance, 'resource') and instance.resource:
            ResourceAvailabilityCache.invalidate_resource_availability(
                resource_id=instance.resource_id
            )
        
        logger.debug(f"Invalidated access request cache for request {instance.id}")
        
    except Exception as e:
        logger.error(f"Error invalidating access request cache: {e}")


# Batch cache invalidation for performance
class CacheInvalidationBatch:
    """Context manager for batching cache invalidations."""
    
    def __init__(self):
        self.invalidation_queue = set()
    
    def add_user_invalidation(self, user_id: int):
        """Add user cache invalidation to batch."""
        self.invalidation_queue.add(('user', user_id))
    
    def add_resource_invalidation(self, resource_id: int, date_str: str = None):
        """Add resource cache invalidation to batch."""
        self.invalidation_queue.add(('resource', resource_id, date_str))
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Process all queued invalidations."""
        for item in self.invalidation_queue:
            try:
                if item[0] == 'user':
                    invalidate_user_caches(item[1])
                elif item[0] == 'resource':
                    ResourceAvailabilityCache.invalidate_resource_availability(
                        item[1], item[2] if len(item) > 2 else None
                    )
            except Exception as e:
                logger.error(f"Error in batch cache invalidation: {e}")
        
        logger.debug(f"Processed {len(self.invalidation_queue)} cache invalidations")


# Management command helper for cache operations
def warm_common_caches():
    """Warm up commonly accessed caches."""
    from ..utils.cache_utils import CacheWarmer
    
    try:
        # Warm up active users' permissions
        active_users = User.objects.filter(
            is_active=True,
            last_login__gte=timezone.now() - timezone.timedelta(days=30)
        )[:50]  # Limit to recent active users
        
        for user in active_users:
            CacheWarmer.warm_user_permissions(user.id)
        
        # Warm up availability for active resources
        active_resources = Resource.objects.filter(
            is_active=True
        )[:20]  # Limit to avoid overwhelming cache
        
        for resource in active_resources:
            CacheWarmer.warm_resource_availability(resource.id, days_ahead=7)
        
        logger.info(f"Warmed caches for {len(active_users)} users and {len(active_resources)} resources")
        
    except Exception as e:
        logger.error(f"Error warming caches: {e}")


def clear_expired_caches():
    """Clear expired cache entries (Redis-specific implementation needed)."""
    try:
        # This would be implemented with Redis SCAN and TTL commands
        logger.info("Cache cleanup would run here (Redis-specific implementation needed)")
        
    except Exception as e:
        logger.error(f"Error clearing expired caches: {e}")