# booking/middleware/licensing.py
"""
License validation middleware for white-label deployments.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
"""

from django.shortcuts import render, redirect
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from django.contrib import messages
from django.core.cache import cache
from booking.services.licensing import license_manager
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


class LicenseValidationMiddleware:
    """
    Middleware to validate license and enforce feature restrictions.
    """
    
    # URLs that should be accessible even with invalid license
    EXEMPT_URLS = [
        '/admin/login/',
        '/admin/logout/',
        '/license/',
        '/license/activate/',
        '/license/status/',
        '/static/',
        '/media/',
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.validation_interval = 3600 * 24  # Validate once per day (in seconds)
        self.cache_key = 'license_middleware_last_validation'
    
    def __call__(self, request):
        # Skip validation for exempt URLs
        if any(request.path.startswith(url) for url in self.EXEMPT_URLS):
            response = self.get_response(request)
            return response
        
        # Skip validation for superusers in admin
        if (request.path.startswith('/admin/') and 
            request.user.is_authenticated and 
            request.user.is_superuser):
            response = self.get_response(request)
            return response
        
        # Perform license validation
        license_valid = self._validate_license(request)
        
        if not license_valid:
            return self._handle_invalid_license(request)
        
        # Add license info to request for templates
        request.license_info = license_manager.get_license_info()
        request.enabled_features = license_manager.get_enabled_features()
        
        response = self.get_response(request)
        return response
    
    def _validate_license(self, request) -> bool:
        """Validate license with caching to avoid excessive checks."""
        # Check cache for last validation time
        last_validation_timestamp = cache.get(self.cache_key)
        now = timezone.now().timestamp()
        
        # Only validate once per interval to avoid performance impact
        if last_validation_timestamp and (now - last_validation_timestamp < self.validation_interval):
            # Still within validation interval, skip validation
            return True
        
        try:
            is_valid, error_msg = license_manager.validate_license()
            
            # Update cache with current timestamp
            cache.set(self.cache_key, now, self.validation_interval)
            
            if not is_valid:
                logger.warning(f"License validation failed: {error_msg}")
                
                # Store error in session for display
                if hasattr(request, 'session'):
                    request.session['license_error'] = error_msg
            
            return is_valid
            
        except Exception as e:
            logger.error(f"License validation error in middleware: {e}")
            # In case of validation errors, allow access for open source
            return True
    
    def _handle_invalid_license(self, request):
        """Handle invalid license by redirecting to license activation page."""
        # For AJAX requests, return JSON error
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if is_ajax or request.content_type == 'application/json':
            from django.http import JsonResponse
            return JsonResponse({
                'error': 'License validation failed',
                'redirect': reverse('booking:license_status')
            }, status=403)
        
        # For regular requests, redirect to license page
        license_error = getattr(request, 'session', {}).get('license_error', 'License validation failed')
        messages.error(request, f"License issue: {license_error}")
        return redirect('booking:license_status')


class BrandingMiddleware:
    """
    Middleware to inject branding configuration into all requests.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Add branding info to request
        from booking.services.licensing import get_branding_config
        request.branding = get_branding_config()
        
        response = self.get_response(request)
        
        # Inject custom CSS if available
        if (hasattr(request, 'branding') and 
            request.branding.custom_css and 
            response.get('Content-Type', '').startswith('text/html')):
            
            css_injection = f"""
            <style type="text/css">
            /* Custom branding CSS */
            {request.branding.custom_css}
            </style>
            """
            
            # Simple CSS injection before </head>
            if b'</head>' in response.content:
                response.content = response.content.replace(
                    b'</head>',
                    css_injection.encode('utf-8') + b'</head>'
                )
        
        return response