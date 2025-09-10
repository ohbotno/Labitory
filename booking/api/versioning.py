# booking/api/versioning.py
"""
API versioning support for Labitory.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from rest_framework.versioning import URLPathVersioning, AcceptHeaderVersioning
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.utils import timezone


class LabitoryAPIVersioning(URLPathVersioning):
    """
    Custom API versioning that supports both URL and header-based versioning.
    """
    default_version = 'v1'
    allowed_versions = ['v1', 'v2']
    version_param = 'version'
    
    def determine_version(self, request, *args, **kwargs):
        """
        Determine API version from URL path or headers.
        """
        # First try URL path versioning
        version = super().determine_version(request, *args, **kwargs)
        
        # If no version in URL, check Accept header
        if not version:
            accept_header = request.META.get('HTTP_ACCEPT', '')
            if 'application/vnd.labitory.v2+json' in accept_header:
                version = 'v2'
            elif 'application/vnd.labitory.v1+json' in accept_header:
                version = 'v1'
        
        # If still no version, check X-API-Version header
        if not version:
            version = request.META.get('HTTP_X_API_VERSION')
        
        # Default to v1 if nothing specified
        if not version:
            version = self.default_version
            
        return version
    
    def reverse(self, viewname, args=None, kwargs=None, request=None, format=None, **extra):
        """
        Include version in URL reversal.
        """
        if request and hasattr(request, 'version'):
            kwargs = kwargs or {}
            kwargs['version'] = request.version
        return super().reverse(viewname, args, kwargs, request, format, **extra)


class LabitoryAcceptHeaderVersioning(AcceptHeaderVersioning):
    """
    Accept header versioning for Labitory API.
    """
    default_version = 'v1'
    allowed_versions = ['v1', 'v2']
    
    def determine_version(self, request, *args, **kwargs):
        """
        Determine version from Accept header.
        """
        media_type = request.content_type
        
        if 'application/vnd.labitory.v2+json' in media_type:
            return 'v2'
        elif 'application/vnd.labitory.v1+json' in media_type:
            return 'v1'
        
        # Check Accept header
        accept = request.META.get('HTTP_ACCEPT', '')
        if 'application/vnd.labitory.v2+json' in accept:
            return 'v2'
        elif 'application/vnd.labitory.v1+json' in accept:
            return 'v1'
            
        return self.default_version


def get_api_version(request):
    """
    Utility function to get API version from request.
    """
    return getattr(request, 'version', 'v1')


def version_response(data, request):
    """
    Add version information to API responses.
    """
    version = get_api_version(request)
    
    # Add version info to response
    if isinstance(data, dict):
        data['_meta'] = {
            'version': version,
            'api_endpoint': request.build_absolute_uri(),
            'timestamp': timezone.now().isoformat(),
        }
    
    return data


def check_version_compatibility(request, min_version='v1', max_version=None):
    """
    Check if the request version is compatible with endpoint requirements.
    
    Args:
        request: Django request object
        min_version: Minimum required API version
        max_version: Maximum supported API version (optional)
    
    Returns:
        tuple: (is_compatible: bool, error_response: Response or None)
    """
    version = get_api_version(request)
    
    # Convert version strings to comparable integers
    def version_to_int(v):
        return int(v.replace('v', ''))
    
    current_version = version_to_int(version)
    min_version_int = version_to_int(min_version)
    
    if current_version < min_version_int:
        return False, Response({
            'error': f'API version {version} is not supported for this endpoint',
            'min_version': min_version,
            'current_version': version,
            'upgrade_required': True
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if max_version:
        max_version_int = version_to_int(max_version)
        if current_version > max_version_int:
            return False, Response({
                'error': f'API version {version} is not supported for this endpoint',
                'max_version': max_version,
                'current_version': version,
                'deprecated': True
            }, status=status.HTTP_400_BAD_REQUEST)
    
    return True, None


def api_deprecated_warning(request, deprecated_version, removal_version=None):
    """
    Generate deprecation warning for API responses.
    """
    version = get_api_version(request)
    
    if version == deprecated_version:
        warning = f"API version {version} is deprecated"
        if removal_version:
            warning += f" and will be removed in {removal_version}"
        
        return {
            'deprecated': True,
            'message': warning,
            'current_version': version,
            'latest_version': 'v2'  # Update this as needed
        }
    
    return None


class VersionCompatibilityMixin:
    """
    Mixin to add version compatibility checking to ViewSets.
    """
    min_version = 'v1'
    max_version = None
    
    def dispatch(self, request, *args, **kwargs):
        """
        Check version compatibility before processing request.
        """
        is_compatible, error_response = check_version_compatibility(
            request, self.min_version, self.max_version
        )
        
        if not is_compatible:
            return error_response
        
        return super().dispatch(request, *args, **kwargs)
    
    def finalize_response(self, request, response, *args, **kwargs):
        """
        Add version headers to response.
        """
        response = super().finalize_response(request, response, *args, **kwargs)
        
        # Add version headers
        response['X-API-Version'] = get_api_version(request)
        response['X-API-Supported-Versions'] = ','.join(['v1', 'v2'])
        
        # Add deprecation warning if applicable
        deprecation = api_deprecated_warning(request, 'v1', 'v3')
        if deprecation:
            response['X-API-Deprecation-Warning'] = deprecation['message']
        
        return response


# Version-specific serializer selection
def get_serializer_class_for_version(base_serializer_class, version):
    """
    Get the appropriate serializer class for the API version.
    """
    if version == 'v2':
        # Try to import v2 serializer
        module_name = base_serializer_class.__module__.replace('.serializers', '.serializers_v2')
        try:
            module = __import__(module_name, fromlist=[base_serializer_class.__name__])
            return getattr(module, base_serializer_class.__name__)
        except (ImportError, AttributeError):
            pass
    
    # Default to base serializer
    return base_serializer_class