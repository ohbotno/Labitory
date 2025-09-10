"""
Model field validator configuration.

This module configures validators for all file and image fields in the models.
It should be imported after Django models are loaded to populate the validators.
"""

from django.conf import settings
from .file_validation import (
    validate_image_file,
    validate_document_file,
    create_custom_validator
)


def configure_model_validators():
    """
    Configure validators for all file/image fields in models.
    
    This function should be called after Django models are loaded,
    typically in the AppConfig.ready() method.
    """
    # Import models locally to avoid circular imports
    from booking.models.core import AboutPage
    from booking.models.resources import Resource, IssueReport
    from booking.models.maintenance import MaintenanceDocument
    from booking.models.training import RiskAssessment
    
    # Configure image field validators
    image_fields = [
        (AboutPage._meta.get_field('image'), 'image'),
        (Resource._meta.get_field('image'), 'image'),
        (IssueReport._meta.get_field('image'), 'image'),
    ]
    
    for field, field_type in image_fields:
        if hasattr(field, 'validators'):
            field.validators = [validate_image_file]
    
    # Configure document field validators
    document_fields = [
        (RiskAssessment._meta.get_field('assessment_file'), 'document'),
        (MaintenanceDocument._meta.get_field('file'), 'document'),
    ]
    
    for field, field_type in document_fields:
        if hasattr(field, 'validators'):
            field.validators = [validate_document_file]


def get_field_validator_config():
    """
    Get configuration for field validators.
    
    Returns:
        Dict mapping field types to their validator configurations
    """
    return {
        'image': {
            'validator': validate_image_file,
            'max_size': getattr(settings, 'MAX_IMAGE_SIZE', 5 * 1024 * 1024),
            'allowed_types': getattr(settings, 'ALLOWED_IMAGE_TYPES', [
                'image/jpeg', 'image/png', 'image/gif', 'image/webp'
            ]),
        },
        'document': {
            'validator': validate_document_file,
            'max_size': getattr(settings, 'MAX_DOCUMENT_SIZE', 20 * 1024 * 1024),
            'allowed_types': getattr(settings, 'ALLOWED_DOCUMENT_TYPES', [
                'application/pdf',
                'application/msword',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/vnd.ms-excel',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            ]),
        },
    }


def create_field_specific_validator(field_name, field_type, **kwargs):
    """
    Create a validator for a specific field with custom configuration.
    
    Args:
        field_name: Name of the field
        field_type: Type of field ('image', 'document', 'file')
        **kwargs: Additional validator configuration
        
    Returns:
        Validator function
    """
    config = get_field_validator_config().get(field_type, {})
    
    # Override config with kwargs
    allowed_types = kwargs.get('allowed_types', config.get('allowed_types', []))
    max_size = kwargs.get('max_size', config.get('max_size', 10 * 1024 * 1024))
    
    return create_custom_validator(allowed_types, max_size)


def validate_model_file_fields():
    """
    Validate all model file fields have proper configuration.
    
    This can be used for debugging or health checks.
    
    Returns:
        Dict with validation results
    """
    from booking.models.core import AboutPage
    from booking.models.resources import Resource, IssueReport
    from booking.models.maintenance import MaintenanceDocument
    from booking.models.training import RiskAssessment
    
    results = {
        'valid': True,
        'fields_checked': 0,
        'fields_with_validators': 0,
        'missing_validators': [],
        'errors': []
    }
    
    # Check all file/image fields
    file_fields = [
        ('AboutPage.image', AboutPage._meta.get_field('image')),
        ('Resource.image', Resource._meta.get_field('image')),
        ('IssueReport.image', IssueReport._meta.get_field('image')),
        ('RiskAssessment.assessment_file', RiskAssessment._meta.get_field('assessment_file')),
        ('MaintenanceDocument.file', MaintenanceDocument._meta.get_field('file')),
    ]
    
    for field_name, field in file_fields:
        results['fields_checked'] += 1
        
        if hasattr(field, 'validators') and field.validators:
            results['fields_with_validators'] += 1
        else:
            results['missing_validators'].append(field_name)
            results['valid'] = False
    
    return results