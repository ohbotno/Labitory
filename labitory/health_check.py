# labitory/health_check.py
"""
Health check endpoints for production monitoring.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import logging
from django.http import JsonResponse
from django.db import connection
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


def health_check(request):
    """
    Basic health check endpoint that returns system status.
    Returns HTTP 200 if all systems are healthy, HTTP 503 if any system is down.
    """
    
    status = {
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'version': getattr(settings, 'APP_VERSION', 'unknown'),
        'environment': getattr(settings, 'ENVIRONMENT', 'unknown'),
        'checks': {}
    }
    
    all_healthy = True
    
    # Database connectivity check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        status['checks']['database'] = {'status': 'healthy', 'message': 'Database connection OK'}
    except Exception as e:
        status['checks']['database'] = {'status': 'unhealthy', 'message': f'Database error: {str(e)}'}
        all_healthy = False
        logger.error(f"Health check database error: {e}")
    
    # Cache connectivity check (if Redis is configured)
    try:
        cache_key = 'health_check_test'
        cache_value = f'test_{timezone.now().timestamp()}'
        cache.set(cache_key, cache_value, timeout=60)
        retrieved_value = cache.get(cache_key)
        
        if retrieved_value == cache_value:
            status['checks']['cache'] = {'status': 'healthy', 'message': 'Cache connection OK'}
        else:
            status['checks']['cache'] = {'status': 'unhealthy', 'message': 'Cache read/write failed'}
            all_healthy = False
    except Exception as e:
        status['checks']['cache'] = {'status': 'unhealthy', 'message': f'Cache error: {str(e)}'}
        all_healthy = False
        logger.error(f"Health check cache error: {e}")
    
    # Disk space check (basic)
    import shutil
    try:
        total, used, free = shutil.disk_usage(settings.BASE_DIR)
        free_percentage = (free / total) * 100
        
        if free_percentage > 10:  # More than 10% free space
            status['checks']['disk'] = {
                'status': 'healthy', 
                'message': f'Disk space OK ({free_percentage:.1f}% free)'
            }
        else:
            status['checks']['disk'] = {
                'status': 'warning', 
                'message': f'Low disk space ({free_percentage:.1f}% free)'
            }
            # Don't mark as unhealthy for disk space warnings
    except Exception as e:
        status['checks']['disk'] = {'status': 'unhealthy', 'message': f'Disk check error: {str(e)}'}
        logger.error(f"Health check disk error: {e}")
    
    # Memory check (basic)
    try:
        import psutil
        memory = psutil.virtual_memory()
        memory_percentage = memory.percent
        
        if memory_percentage < 90:  # Less than 90% memory usage
            status['checks']['memory'] = {
                'status': 'healthy', 
                'message': f'Memory usage OK ({memory_percentage:.1f}%)'
            }
        else:
            status['checks']['memory'] = {
                'status': 'warning', 
                'message': f'High memory usage ({memory_percentage:.1f}%)'
            }
    except ImportError:
        status['checks']['memory'] = {
            'status': 'info', 
            'message': 'psutil not installed, memory check skipped'
        }
    except Exception as e:
        status['checks']['memory'] = {'status': 'unhealthy', 'message': f'Memory check error: {str(e)}'}
        logger.error(f"Health check memory error: {e}")
    
    # Update overall status
    if not all_healthy:
        status['status'] = 'unhealthy'
    
    # Return appropriate HTTP status code
    http_status = 200 if all_healthy else 503
    
    return JsonResponse(status, status=http_status)


def readiness_check(request):
    """
    Readiness check endpoint for Kubernetes/container orchestration.
    Returns HTTP 200 when the application is ready to receive traffic.
    """
    
    status = {
        'status': 'ready',
        'timestamp': timezone.now().isoformat(),
        'checks': {}
    }
    
    all_ready = True
    
    # Check if database is ready and migrations are complete
    try:
        from django.db import connections
        from django.db.migrations.executor import MigrationExecutor
        
        connection = connections['default']
        executor = MigrationExecutor(connection)
        
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            status['checks']['migrations'] = {
                'status': 'not_ready', 
                'message': 'Pending database migrations'
            }
            all_ready = False
        else:
            status['checks']['migrations'] = {
                'status': 'ready', 
                'message': 'All migrations applied'
            }
    except Exception as e:
        status['checks']['migrations'] = {
            'status': 'not_ready', 
            'message': f'Migration check error: {str(e)}'
        }
        all_ready = False
        logger.error(f"Readiness check migration error: {e}")
    
    # Check if cache is available
    try:
        cache.get('readiness_test')
        status['checks']['cache'] = {'status': 'ready', 'message': 'Cache available'}
    except Exception as e:
        status['checks']['cache'] = {
            'status': 'not_ready', 
            'message': f'Cache not available: {str(e)}'
        }
        all_ready = False
    
    # Update overall status
    if not all_ready:
        status['status'] = 'not_ready'
    
    # Return appropriate HTTP status code
    http_status = 200 if all_ready else 503
    
    return JsonResponse(status, status=http_status)


def liveness_check(request):
    """
    Liveness check endpoint for Kubernetes/container orchestration.
    Returns HTTP 200 if the application is alive and should not be restarted.
    """
    
    status = {
        'status': 'alive',
        'timestamp': timezone.now().isoformat(),
        'uptime': timezone.now().isoformat(),  # Basic uptime indicator
    }
    
    # Simple liveness check - if we can respond, we're alive
    return JsonResponse(status, status=200)