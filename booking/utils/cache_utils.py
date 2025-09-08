# booking/utils/cache_utils.py
"""
Caching utilities for the Labitory system.

This module provides utilities for implementing efficient caching strategies
including query result caching, permission caching, and cache invalidation.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import hashlib
import logging
from functools import wraps
from typing import Optional, Any, Callable, List, Dict
from django.core.cache import cache
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


def generate_cache_key(*args, **kwargs) -> str:
    """
    Generate a consistent cache key from arguments.
    
    Args:
        *args: Positional arguments to include in key
        **kwargs: Keyword arguments to include in key
        
    Returns:
        str: MD5 hash of the arguments
    """
    key_data = f"{args}:{sorted(kwargs.items())}"
    return hashlib.md5(key_data.encode()).hexdigest()


def cache_result(timeout: int = 300, key_prefix: str = "query"):
    """
    Decorator to cache function results.
    
    Args:
        timeout: Cache timeout in seconds (default: 5 minutes)
        key_prefix: Prefix for cache keys
        
    Usage:
        @cache_result(timeout=600, key_prefix="booking")
        def get_bookings(user_id):
            return expensive_query()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{key_prefix}:{func.__name__}:{generate_cache_key(*args, **kwargs)}"
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, timeout)
            logger.debug(f"Cache miss for {cache_key}, result cached")
            
            return result
        return wrapper
    return decorator


class PermissionCache:
    """Cache for user permission checks."""
    
    CACHE_PREFIX = "permissions"
    CACHE_TIMEOUT = 300  # 5 minutes
    
    @classmethod
    def get_cache_key(cls, user_id: int, permission: str, obj_id: Optional[int] = None) -> str:
        """Generate cache key for permission check."""
        if obj_id:
            return f"{cls.CACHE_PREFIX}:user_{user_id}:perm_{permission}:obj_{obj_id}"
        return f"{cls.CACHE_PREFIX}:user_{user_id}:perm_{permission}"
    
    @classmethod
    def get_permission(cls, user_id: int, permission: str, obj_id: Optional[int] = None) -> Optional[bool]:
        """Get cached permission result."""
        cache_key = cls.get_cache_key(user_id, permission, obj_id)
        return cache.get(cache_key)
    
    @classmethod
    def set_permission(cls, user_id: int, permission: str, has_permission: bool, obj_id: Optional[int] = None) -> None:
        """Cache permission result."""
        cache_key = cls.get_cache_key(user_id, permission, obj_id)
        cache.set(cache_key, has_permission, cls.CACHE_TIMEOUT)
        logger.debug(f"Cached permission {permission} for user {user_id}: {has_permission}")
    
    @classmethod
    def invalidate_user_permissions(cls, user_id: int) -> None:
        """Invalidate all permissions for a user."""
        # Note: This is a simple implementation. In production, consider using cache tags
        pattern = f"{cls.CACHE_PREFIX}:user_{user_id}:*"
        logger.info(f"Invalidating permissions cache for user {user_id}")
        # Redis-specific cache deletion would be more efficient here


class ResourceAvailabilityCache:
    """Cache for resource availability calculations."""
    
    CACHE_PREFIX = "resource_availability"
    CACHE_TIMEOUT = 180  # 3 minutes (shorter due to dynamic nature)
    
    @classmethod
    def get_cache_key(cls, resource_id: int, date_str: str) -> str:
        """Generate cache key for resource availability."""
        return f"{cls.CACHE_PREFIX}:resource_{resource_id}:date_{date_str}"
    
    @classmethod
    def get_availability(cls, resource_id: int, date_str: str) -> Optional[Dict]:
        """Get cached availability data."""
        cache_key = cls.get_cache_key(resource_id, date_str)
        return cache.get(cache_key)
    
    @classmethod
    def set_availability(cls, resource_id: int, date_str: str, availability_data: Dict) -> None:
        """Cache availability data."""
        cache_key = cls.get_cache_key(resource_id, date_str)
        cache.set(cache_key, availability_data, cls.CACHE_TIMEOUT)
        logger.debug(f"Cached availability for resource {resource_id} on {date_str}")
    
    @classmethod
    def invalidate_resource_availability(cls, resource_id: int, date_str: Optional[str] = None) -> None:
        """Invalidate availability cache for a resource."""
        if date_str:
            cache_key = cls.get_cache_key(resource_id, date_str)
            cache.delete(cache_key)
            logger.info(f"Invalidated availability cache for resource {resource_id} on {date_str}")
        else:
            # Invalidate all dates for this resource
            logger.info(f"Invalidating all availability cache for resource {resource_id}")


class QueryCache:
    """General purpose query result caching."""
    
    CACHE_PREFIX = "query"
    DEFAULT_TIMEOUT = 300  # 5 minutes
    
    @classmethod
    def cache_queryset(cls, cache_key: str, queryset, timeout: Optional[int] = None) -> None:
        """
        Cache a queryset result.
        
        Args:
            cache_key: Unique cache key
            queryset: Django queryset to cache
            timeout: Cache timeout in seconds
        """
        timeout = timeout or cls.DEFAULT_TIMEOUT
        # Convert queryset to list to make it cacheable
        result = list(queryset.values())
        cache.set(f"{cls.CACHE_PREFIX}:{cache_key}", result, timeout)
        logger.debug(f"Cached queryset with {len(result)} items: {cache_key}")
    
    @classmethod
    def get_cached_queryset(cls, cache_key: str) -> Optional[List[Dict]]:
        """Get cached queryset result."""
        return cache.get(f"{cls.CACHE_PREFIX}:{cache_key}")


def invalidate_related_caches(model_name: str, obj_id: int, related_fields: List[str] = None) -> None:
    """
    Invalidate caches related to a specific model instance.
    
    Args:
        model_name: Name of the model (e.g., 'booking', 'resource')
        obj_id: ID of the model instance
        related_fields: List of related field names to invalidate
    """
    patterns_to_invalidate = [
        f"*{model_name}_{obj_id}*",
        f"*{model_name.lower()}_{obj_id}*",
    ]
    
    if related_fields:
        for field in related_fields:
            patterns_to_invalidate.append(f"*{field}_{obj_id}*")
    
    logger.info(f"Invalidating caches for {model_name} {obj_id}")
    # In a Redis implementation, we would use SCAN with patterns
    # For now, log the invalidation patterns


def cache_page_fragment(fragment_name: str, *args, **kwargs):
    """
    Decorator for caching page fragments.
    
    Usage:
        @cache_page_fragment('user_dashboard', timeout=600)
        def render_dashboard(request):
            return expensive_template_render()
    """
    timeout = kwargs.pop('timeout', 300)
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(request, *func_args, **func_kwargs):
            user_id = request.user.id if request.user.is_authenticated else 'anonymous'
            cache_key = f"fragment:{fragment_name}:user_{user_id}:{generate_cache_key(*args, *func_args, **func_kwargs)}"
            
            result = cache.get(cache_key)
            if result is not None:
                logger.debug(f"Fragment cache hit: {fragment_name}")
                return result
            
            result = func(request, *func_args, **func_kwargs)
            cache.set(cache_key, result, timeout)
            logger.debug(f"Fragment cached: {fragment_name}")
            
            return result
        return wrapper
    return decorator


class CacheWarmer:
    """Utility for warming up cache with frequently accessed data."""
    
    @staticmethod
    def warm_user_permissions(user_id: int) -> None:
        """Pre-cache common permissions for a user."""
        from django.contrib.auth.models import User
        from django.contrib.auth import get_user
        
        try:
            user = User.objects.get(id=user_id)
            common_permissions = [
                'booking.add_booking',
                'booking.view_booking',
                'booking.change_booking',
                'booking.delete_booking',
            ]
            
            for perm in common_permissions:
                has_perm = user.has_perm(perm)
                PermissionCache.set_permission(user_id, perm, has_perm)
            
            logger.info(f"Warmed permission cache for user {user_id}")
            
        except User.DoesNotExist:
            logger.warning(f"User {user_id} not found for cache warming")
    
    @staticmethod
    def warm_resource_availability(resource_id: int, days_ahead: int = 7) -> None:
        """Pre-cache availability for a resource."""
        from ..models import Resource
        
        try:
            resource = Resource.objects.get(id=resource_id)
            current_date = timezone.now().date()
            
            for day_offset in range(days_ahead):
                target_date = current_date + timedelta(days=day_offset)
                date_str = target_date.isoformat()
                
                # This would call your actual availability calculation
                # availability = calculate_resource_availability(resource, target_date)
                # ResourceAvailabilityCache.set_availability(resource_id, date_str, availability)
                
            logger.info(f"Warmed availability cache for resource {resource_id}")
            
        except Resource.DoesNotExist:
            logger.warning(f"Resource {resource_id} not found for cache warming")


# Utility functions for cache invalidation on model changes
def invalidate_booking_caches(booking_id: int, user_id: int, resource_id: int) -> None:
    """Invalidate caches when a booking is created/updated/deleted."""
    invalidate_related_caches('booking', booking_id)
    invalidate_related_caches('user', user_id, ['booking'])
    invalidate_related_caches('resource', resource_id, ['booking'])
    
    # Invalidate resource availability
    # This would be called with the booking's date
    logger.info(f"Invalidated caches for booking {booking_id}")


def invalidate_user_caches(user_id: int) -> None:
    """Invalidate caches when user data changes."""
    PermissionCache.invalidate_user_permissions(user_id)
    invalidate_related_caches('user', user_id)
    logger.info(f"Invalidated caches for user {user_id}")


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics (Redis-specific implementation needed)."""
    try:
        # This would be Redis-specific
        return {
            'status': 'available',
            'backend': settings.CACHES['default']['BACKEND'],
            'keys_count': 'N/A',  # Would need Redis DBSIZE command
            'memory_usage': 'N/A',  # Would need Redis INFO command
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e)
        }