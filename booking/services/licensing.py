# booking/services/licensing.py
"""
License validation and feature gating service for white-label deployments.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

import hashlib
import uuid
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.models import User
from typing import Dict, List, Optional, Tuple
import logging
import requests
import socket

logger = logging.getLogger(__name__)


class LicenseManager:
    """
    Manages license validation and feature gating for white-label deployments.
    Implements honor system for open source and validation for commercial licenses.
    """
    
    CACHE_TIMEOUT = 3600  # 1 hour
    VALIDATION_GRACE_PERIOD = timedelta(days=7)  # Grace period for network issues
    
    def __init__(self):
        self._current_license = None
        self._license_cache_key = 'current_license'
        self._features_cache_key = 'license_features'
    
    def get_current_license(self) -> Optional['LicenseConfiguration']:
        """Get the currently active license configuration."""
        if self._current_license is None:
            # Try cache first
            cached_license = cache.get(self._license_cache_key)
            if cached_license:
                self._current_license = cached_license
            else:
                # Load from database
                from booking.models import LicenseConfiguration
                try:
                    self._current_license = LicenseConfiguration.objects.filter(
                        is_active=True
                    ).first()
                    
                    if self._current_license:
                        cache.set(self._license_cache_key, self._current_license, self.CACHE_TIMEOUT)
                except Exception as e:
                    logger.error(f"Error loading license configuration: {e}")
                    self._current_license = None
        
        return self._current_license
    
    def is_feature_enabled(self, feature_name: str) -> bool:
        """Check if a specific feature is enabled in the current license."""
        features = self.get_enabled_features()
        return features.get(feature_name, False)
    
    def get_enabled_features(self) -> Dict[str, bool]:
        """Get all enabled features for the current license."""
        # Try cache first
        cached_features = cache.get(self._features_cache_key)
        if cached_features:
            return cached_features
        
        license_config = self.get_current_license()
        if license_config:
            features = license_config.get_enabled_features()
        else:
            # Default open source features if no license configured
            features = self._get_default_open_source_features()
        
        cache.set(self._features_cache_key, features, self.CACHE_TIMEOUT)
        return features
    
    def _get_default_open_source_features(self) -> Dict[str, bool]:
        """Default feature set for open source deployments."""
        return {
            'basic_booking': True,
            'user_management': True,
            'resource_management': True,
            'email_notifications': True,
            'custom_branding': False,
            'white_label': False,
            'advanced_reports': False,
            'api_access': True,
            'premium_support': False,
        }
    
    def validate_license(self, force_remote: bool = False) -> Tuple[bool, str]:
        """
        Validate the current license.
        
        Args:
            force_remote: Force remote validation even if cache is valid
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        license_config = self.get_current_license()
        if not license_config:
            return False, "No license configuration found"
        
        # For open source licenses, use honor system
        if license_config.license_type == 'open_source':
            return self._validate_open_source_license(license_config)
        
        # For commercial licenses, perform validation
        return self._validate_commercial_license(license_config, force_remote)
    
    def _validate_open_source_license(self, license_config) -> Tuple[bool, str]:
        """Validate open source license (honor system)."""
        from booking.models import LicenseValidationLog
        
        try:
            # Basic validation - just check if it's active
            if not license_config.is_active:
                return False, "License is not active"
            
            # Log successful validation
            LicenseValidationLog.objects.create(
                license=license_config,
                validation_type='periodic',
                result='success',
                domain_checked=self._get_current_domain(),
            )
            
            # Update last validation time
            license_config.last_validation = timezone.now()
            license_config.validation_failures = 0
            license_config.save(update_fields=['last_validation', 'validation_failures'])
            
            return True, "Open source license validated (honor system)"
            
        except Exception as e:
            logger.error(f"Error validating open source license: {e}")
            return False, f"Validation error: {e}"
    
    def _validate_commercial_license(self, license_config, force_remote: bool = False) -> Tuple[bool, str]:
        """Validate commercial license with optional remote validation."""
        from booking.models import LicenseValidationLog
        
        validation_start = timezone.now()
        
        try:
            # Check basic validity
            if not license_config.is_valid():
                reason = "License is inactive"
                if license_config.expires_at and license_config.expires_at < timezone.now():
                    reason = "License has expired"
                
                LicenseValidationLog.objects.create(
                    license=license_config,
                    validation_type='periodic',
                    result='expired',
                    domain_checked=self._get_current_domain(),
                    error_message=reason,
                )
                return False, reason
            
            # Check domain restrictions
            if license_config.allowed_domains:
                current_domain = self._get_current_domain()
                if current_domain not in license_config.allowed_domains:
                    LicenseValidationLog.objects.create(
                        license=license_config,
                        validation_type='periodic',
                        result='domain_mismatch',
                        domain_checked=current_domain,
                        error_message=f"Domain {current_domain} not in allowed list",
                    )
                    return False, f"Domain {current_domain} is not authorized for this license"
            
            # Check usage limits
            usage_issues = license_config.check_usage_limits()
            if usage_issues:
                LicenseValidationLog.objects.create(
                    license=license_config,
                    validation_type='periodic',
                    result='usage_exceeded',
                    domain_checked=self._get_current_domain(),
                    error_message="; ".join(usage_issues),
                )
                return False, f"Usage limits exceeded: {'; '.join(usage_issues)}"
            
            # Remote validation (optional for commercial licenses)
            if force_remote and hasattr(settings, 'LICENSE_VALIDATION_URL'):
                remote_valid, remote_error = self._validate_remote(license_config)
                if not remote_valid:
                    return False, remote_error
            
            # Log successful validation
            response_time = (timezone.now() - validation_start).total_seconds()
            LicenseValidationLog.objects.create(
                license=license_config,
                validation_type='periodic',
                result='success',
                domain_checked=self._get_current_domain(),
                response_time=response_time,
            )
            
            # Update license validation tracking
            license_config.last_validation = timezone.now()
            license_config.validation_failures = 0
            license_config.save(update_fields=['last_validation', 'validation_failures'])
            
            return True, "License validated successfully"
            
        except Exception as e:
            logger.error(f"Error validating commercial license: {e}")
            
            # Log validation error
            LicenseValidationLog.objects.create(
                license=license_config,
                validation_type='periodic',
                result='network_error',
                domain_checked=self._get_current_domain(),
                error_message=str(e),
            )
            
            # Increment failure count
            license_config.validation_failures += 1
            license_config.save(update_fields=['validation_failures'])
            
            # Allow grace period for network issues
            if (license_config.last_validation and 
                timezone.now() - license_config.last_validation < self.VALIDATION_GRACE_PERIOD):
                logger.warning(f"License validation failed but within grace period: {e}")
                return True, f"Validation failed but within grace period: {e}"
            
            return False, f"License validation failed: {e}"
    
    def _validate_remote(self, license_config) -> Tuple[bool, str]:
        """Perform remote license validation against licensing server."""
        try:
            validation_url = getattr(settings, 'LICENSE_VALIDATION_URL', None)
            if not validation_url:
                return True, "Remote validation not configured"
            
            payload = {
                'license_key': license_config.license_key,
                'domain': self._get_current_domain(),
                'product': 'labitory',
                'version': getattr(settings, 'VERSION', '1.0.0'),
            }
            
            response = requests.post(
                validation_url,
                json=payload,
                timeout=10,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('valid', False):
                    return True, "Remote validation successful"
                else:
                    return False, result.get('error', 'Remote validation failed')
            else:
                return False, f"Remote validation server error: {response.status_code}"
                
        except requests.RequestException as e:
            logger.error(f"Remote license validation failed: {e}")
            return False, f"Remote validation network error: {e}"
    
    def _get_current_domain(self) -> str:
        """Get the current domain for validation."""
        try:
            # Try to get from Django settings first
            allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
            if allowed_hosts and allowed_hosts[0] != '*':
                return allowed_hosts[0]
            
            # Fall back to hostname
            return socket.gethostname()
        except Exception:
            return 'localhost'
    
    def generate_license_key(self, organization_name: str, license_type: str) -> str:
        """Generate a unique license key for an organization."""
        # Create a unique identifier based on organization and timestamp
        unique_string = f"{organization_name}-{license_type}-{timezone.now().isoformat()}-{uuid.uuid4()}"
        
        # Create hash
        hash_object = hashlib.sha256(unique_string.encode())
        hash_hex = hash_object.hexdigest()
        
        # Format as license key (groups of 4 characters)
        formatted_key = '-'.join([hash_hex[i:i+4].upper() for i in range(0, 32, 4)])
        
        return formatted_key
    
    def check_license_requirements(self, required_features: List[str]) -> Tuple[bool, List[str]]:
        """
        Check if current license supports required features.
        
        Args:
            required_features: List of feature names to check
            
        Returns:
            Tuple of (all_satisfied, missing_features)
        """
        enabled_features = self.get_enabled_features()
        missing_features = []
        
        for feature in required_features:
            if not enabled_features.get(feature, False):
                missing_features.append(feature)
        
        return len(missing_features) == 0, missing_features
    
    def get_license_info(self) -> Dict:
        """Get current license information for display."""
        license_config = self.get_current_license()
        if not license_config:
            return {
                'type': 'open_source',
                'status': 'No license configured',
                'organization': 'Open Source User',
                'features': self._get_default_open_source_features(),
                'expires_at': None,
                'is_valid': True,
            }
        
        is_valid, error_msg = self.validate_license()
        
        return {
            'type': license_config.license_type,
            'status': 'Valid' if is_valid else error_msg,
            'organization': license_config.organization_name,
            'features': license_config.get_enabled_features(),
            'expires_at': license_config.expires_at,
            'support_expires_at': license_config.support_expires_at,
            'is_valid': is_valid,
            'last_validation': license_config.last_validation,
        }
    
    def clear_cache(self):
        """Clear license-related cache."""
        cache.delete(self._license_cache_key)
        cache.delete(self._features_cache_key)
        self._current_license = None


# Global license manager instance
license_manager = LicenseManager()


def require_license_feature(feature_name: str):
    """
    Decorator to require a specific license feature for a view or function.
    
    Usage:
        @require_license_feature('advanced_reports')
        def advanced_report_view(request):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if not license_manager.is_feature_enabled(feature_name):
                from django.http import HttpResponseForbidden
                from django.shortcuts import render
                
                # If this is a view function, render a nice error page
                if hasattr(args[0], 'method'):  # request object
                    return render(args[0], 'licensing/feature_not_available.html', {
                        'feature_name': feature_name,
                        'license_info': license_manager.get_license_info(),
                    })
                else:
                    raise PermissionError(f"Feature '{feature_name}' not available in current license")
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def get_branding_config():
    """Get current branding configuration."""
    license_config = license_manager.get_current_license()
    if license_config and hasattr(license_config, 'branding'):
        return license_config.branding
    
    # Return default branding for when no license is configured
    # This shows powered_by = True to encourage users to select a license option
    from booking.models import BrandingConfiguration
    defaults = BrandingConfiguration()
    defaults.app_title = 'Labitory'
    defaults.company_name = 'Open Source User'
    defaults.show_powered_by = True  # Show powered by when no license is explicitly selected
    return defaults