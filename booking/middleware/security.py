# booking/middleware/security.py
"""
Security middleware for additional HTTP security headers and protections.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import re
import bleach
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone
from django.http import HttpResponse
from django.core.cache import cache


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Middleware to add comprehensive security headers.
    """
    
    def process_response(self, request, response):
        """
        Add security headers to all responses.
        """
        # Content Security Policy
        csp_directives = {
            "default-src": "'self'",
            "script-src": "'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net",
            "style-src": "'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net",
            "font-src": "'self' https://fonts.gstatic.com",
            "img-src": "'self' data: https:",
            "connect-src": "'self'",
            "frame-ancestors": "'none'",
            "base-uri": "'self'",
            "form-action": "'self'",
            "object-src": "'none'",
            "media-src": "'self'",
        }
        
        # Build CSP header
        csp_header = "; ".join([f"{directive} {sources}" for directive, sources in csp_directives.items()])
        response['Content-Security-Policy'] = csp_header
        
        # Additional security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = (
            'camera=(), microphone=(), geolocation=(), '
            'payment=(), usb=(), magnetometer=(), gyroscope=()'
        )
        
        # HSTS (only in production with HTTPS)
        if not settings.DEBUG and request.is_secure():
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        
        # Server header obfuscation
        response['Server'] = 'Labitory'
        
        return response


class ContentSanitizationMiddleware(MiddlewareMixin):
    """
    Middleware to sanitize user input and prevent XSS attacks.
    """
    
    # Fields that should not be sanitized (e.g., password fields)
    EXEMPT_FIELDS = ['password', 'password1', 'password2', 'current_password']
    
    # Paths that should be exempt from sanitization
    EXEMPT_PATHS = ['/admin/', '/api/']
    
    def process_request(self, request):
        """
        Sanitize POST data before processing.
        """
        # Skip sanitization for exempt paths
        if any(request.path.startswith(path) for path in self.EXEMPT_PATHS):
            return None
        
        if request.method == 'POST' and hasattr(request, 'POST'):
            # Create a mutable copy of POST data
            sanitized_data = request.POST.copy()
            
            for key, value in request.POST.items():
                if key not in self.EXEMPT_FIELDS:
                    if isinstance(value, str):
                        # Sanitize HTML content
                        sanitized_value = bleach.clean(
                            value,
                            tags=['p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li'],
                            attributes={},
                            strip=True
                        )
                        sanitized_data[key] = sanitized_value
            
            # Replace POST data with sanitized version
            request.POST = sanitized_data
        
        return None


class RateLimitMiddleware(MiddlewareMixin):
    """
    Basic rate limiting middleware (in addition to django-ratelimit).
    """
    
    def process_request(self, request):
        """
        Check rate limits before processing request.
        """
        # Get client IP
        ip = self.get_client_ip(request)
        
        # Basic rate limiting for sensitive endpoints
        sensitive_paths = ['/accounts/login/', '/accounts/password_reset/', '/api/auth/']
        
        for path in sensitive_paths:
            if request.path.startswith(path):
                cache_key = f"rate_limit:{ip}:{path}"
                current_requests = cache.get(cache_key, 0)
                
                # Allow 10 requests per minute for sensitive endpoints
                limit = 10
                window = 60  # 1 minute
                
                if current_requests >= limit:
                    return HttpResponse(
                        "Rate limit exceeded. Please try again later.",
                        status=429,
                        content_type="text/plain"
                    )
                
                # Increment counter
                cache.set(cache_key, current_requests + 1, window)
        
        return None
    
    def get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SecurityEventMiddleware(MiddlewareMixin):
    """
    Middleware to detect and log security-related events.
    """
    
    # Suspicious patterns
    SQL_INJECTION_PATTERNS = [
        r"(\bunion\b.*\bselect\b)",
        r"(\bselect\b.*\bfrom\b.*\bwhere\b)",
        r"(\bdrop\b.*\btable\b)",
        r"(\binsert\b.*\binto\b)",
        r"(\bupdate\b.*\bset\b)",
        r"(\bdelete\b.*\bfrom\b)",
    ]
    
    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
        r"<iframe[^>]*>",
    ]
    
    def process_request(self, request):
        """
        Analyze request for suspicious patterns.
        """
        suspicious_activity = []
        
        # Check query parameters and POST data
        all_params = {}
        all_params.update(request.GET.dict())
        if hasattr(request, 'POST'):
            all_params.update(request.POST.dict())
        
        for key, value in all_params.items():
            if isinstance(value, str):
                # Check for SQL injection patterns
                for pattern in self.SQL_INJECTION_PATTERNS:
                    if re.search(pattern, value.lower()):
                        suspicious_activity.append(f"Potential SQL injection in {key}")
                
                # Check for XSS patterns
                for pattern in self.XSS_PATTERNS:
                    if re.search(pattern, value, re.IGNORECASE):
                        suspicious_activity.append(f"Potential XSS in {key}")
        
        # Log suspicious activity
        if suspicious_activity:
            self.log_security_event(request, suspicious_activity)
        
        return None
    
    def log_security_event(self, request, suspicious_activity):
        """
        Log security events.
        """
        from ..models import SecurityEvent
        
        user = request.user if request.user.is_authenticated else None
        ip = self.get_client_ip(request)
        
        SecurityEvent.objects.create(
            user=user,
            event_type='suspicious_activity',
            description=f"Suspicious patterns detected: {', '.join(suspicious_activity)}",
            ip_address=ip,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            metadata={
                'patterns': suspicious_activity,
                'path': request.path,
                'method': request.method,
            }
        )
    
    def get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SessionSecurityMiddleware(MiddlewareMixin):
    """
    Enhanced session security middleware.
    """
    
    def process_request(self, request):
        """
        Enhance session security.
        """
        if request.user.is_authenticated:
            # Check for session hijacking
            if self.detect_session_hijacking(request):
                # Flush session and force re-authentication
                request.session.flush()
                self.log_security_event(request, 'session_hijacking_detected')
                return None
            
            # Update session metadata
            request.session['last_activity'] = timezone.now().isoformat()
            request.session['ip_address'] = self.get_client_ip(request)
            request.session['user_agent'] = request.META.get('HTTP_USER_AGENT', '')
        
        return None
    
    def detect_session_hijacking(self, request):
        """
        Detect potential session hijacking.
        """
        # Check if IP address has changed
        stored_ip = request.session.get('ip_address')
        current_ip = self.get_client_ip(request)
        
        if stored_ip and stored_ip != current_ip:
            # Log but don't immediately flag - IP can change legitimately
            pass
        
        # Check if User-Agent has changed significantly
        stored_ua = request.session.get('user_agent')
        current_ua = request.META.get('HTTP_USER_AGENT', '')
        
        if stored_ua and stored_ua != current_ua:
            # Significant change in user agent might indicate hijacking
            return True
        
        return False
    
    def log_security_event(self, request, event_type):
        """
        Log security events.
        """
        from ..models import SecurityEvent
        
        SecurityEvent.objects.create(
            user=request.user if request.user.is_authenticated else None,
            event_type=event_type,
            description=f"Security event detected: {event_type}",
            ip_address=self.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            metadata={
                'path': request.path,
                'method': request.method,
            }
        )
    
    def get_client_ip(self, request):
        """Get client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip