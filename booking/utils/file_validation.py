"""
File validation utilities for secure file uploads.

This module provides comprehensive file validation including:
- MIME type validation with whitelist approach
- File size limits
- Security scanning for malicious content
- Custom Django validators for model fields
"""

import os
import tempfile
import mimetypes
from typing import List, Dict, Tuple, Optional, Union
from django.core.exceptions import ValidationError
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext_lazy as _

try:
    import magic
    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False

try:
    import clamd
    HAS_CLAMD = True
except ImportError:
    HAS_CLAMD = False

import logging
logger = logging.getLogger(__name__)


class FileValidationConfig:
    """Configuration for file validation."""
    
    # Default file size limits (in bytes)
    DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    DEFAULT_MAX_IMAGE_SIZE = 5 * 1024 * 1024   # 5MB
    
    # Allowed MIME types by category
    ALLOWED_IMAGE_TYPES = [
        'image/jpeg',
        'image/png', 
        'image/gif',
        'image/webp',
        'image/bmp',
        'image/svg+xml'
    ]
    
    ALLOWED_DOCUMENT_TYPES = [
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'text/plain',
        'text/csv',
        'application/rtf'
    ]
    
    ALLOWED_ARCHIVE_TYPES = [
        'application/zip',
        'application/x-zip-compressed',
        'application/x-rar-compressed',
        'application/x-tar',
        'application/gzip'
    ]
    
    # File extensions to MIME type mapping for fallback
    EXTENSION_MIME_MAP = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.bmp': 'image/bmp',
        '.svg': 'image/svg+xml',
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.ppt': 'application/vnd.ms-powerpoint',
        '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        '.txt': 'text/plain',
        '.csv': 'text/csv',
        '.rtf': 'application/rtf',
        '.zip': 'application/zip',
        '.rar': 'application/x-rar-compressed',
        '.tar': 'application/x-tar',
        '.gz': 'application/gzip'
    }
    
    # Dangerous file signatures to detect
    DANGEROUS_SIGNATURES = [
        b'MZ',  # PE executable
        b'\x7fELF',  # ELF executable
        b'\xca\xfe\xba\xbe',  # Mach-O binary
        b'PK\x03\x04\x14\x00\x06\x00',  # Password-protected ZIP
        b'%PDF-1.',  # PDF with potential JavaScript
    ]


class FileValidator:
    """Main file validation class."""
    
    def __init__(self, 
                 allowed_types: List[str] = None,
                 max_size: int = None,
                 enable_virus_scan: bool = True,
                 enable_content_scan: bool = True):
        """
        Initialize file validator.
        
        Args:
            allowed_types: List of allowed MIME types
            max_size: Maximum file size in bytes
            enable_virus_scan: Whether to perform virus scanning
            enable_content_scan: Whether to scan file content for threats
        """
        self.allowed_types = allowed_types or FileValidationConfig.ALLOWED_IMAGE_TYPES
        self.max_size = max_size or FileValidationConfig.DEFAULT_MAX_FILE_SIZE
        self.enable_virus_scan = enable_virus_scan
        self.enable_content_scan = enable_content_scan
        
    def validate(self, file: UploadedFile) -> Dict[str, Union[bool, str, List[str]]]:
        """
        Comprehensive file validation.
        
        Args:
            file: Uploaded file to validate
            
        Returns:
            Dict with validation results
        """
        results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'file_info': {}
        }
        
        try:
            # Basic file info
            results['file_info'] = {
                'name': file.name,
                'size': file.size,
                'content_type': file.content_type
            }
            
            # Size validation
            size_result = self._validate_size(file)
            if not size_result['valid']:
                results['valid'] = False
                results['errors'].extend(size_result['errors'])
            
            # MIME type validation
            mime_result = self._validate_mime_type(file)
            if not mime_result['valid']:
                results['valid'] = False
                results['errors'].extend(mime_result['errors'])
            else:
                results['file_info']['detected_mime'] = mime_result['detected_mime']
            
            # Content security validation
            if self.enable_content_scan:
                content_result = self._validate_content_security(file)
                if not content_result['valid']:
                    results['valid'] = False
                    results['errors'].extend(content_result['errors'])
                results['warnings'].extend(content_result.get('warnings', []))
            
            # Virus scanning
            if self.enable_virus_scan:
                virus_result = self._scan_for_viruses(file)
                if not virus_result['valid']:
                    results['valid'] = False
                    results['errors'].extend(virus_result['errors'])
            
        except Exception as e:
            logger.error(f"File validation error: {e}")
            results['valid'] = False
            results['errors'].append(f"Validation failed: {str(e)}")
        
        return results
    
    def _validate_size(self, file: UploadedFile) -> Dict[str, Union[bool, List[str]]]:
        """Validate file size."""
        if file.size > self.max_size:
            return {
                'valid': False,
                'errors': [f"File size ({self._format_size(file.size)}) exceeds maximum allowed size ({self._format_size(self.max_size)})"]
            }
        
        if file.size == 0:
            return {
                'valid': False,
                'errors': ["File is empty"]
            }
        
        return {'valid': True, 'errors': []}
    
    def _validate_mime_type(self, file: UploadedFile) -> Dict[str, Union[bool, str, List[str]]]:
        """Validate MIME type using multiple methods."""
        detected_mime = None
        
        # Method 1: Use python-magic if available
        if HAS_MAGIC:
            try:
                # Reset file pointer
                file.seek(0)
                file_header = file.read(2048)
                file.seek(0)
                
                detected_mime = magic.from_buffer(file_header, mime=True)
            except Exception as e:
                logger.warning(f"python-magic MIME detection failed: {e}")
        
        # Method 2: Fallback to file extension
        if not detected_mime:
            file_ext = os.path.splitext(file.name)[1].lower()
            detected_mime = FileValidationConfig.EXTENSION_MIME_MAP.get(file_ext)
        
        # Method 3: Use uploaded content type as last resort
        if not detected_mime:
            detected_mime = file.content_type
        
        # Validate against allowed types
        if detected_mime not in self.allowed_types:
            return {
                'valid': False,
                'detected_mime': detected_mime,
                'errors': [f"File type '{detected_mime}' is not allowed. Allowed types: {', '.join(self.allowed_types)}"]
            }
        
        # Check for MIME type spoofing
        if file.content_type != detected_mime:
            logger.warning(f"MIME type mismatch: uploaded={file.content_type}, detected={detected_mime}")
        
        return {
            'valid': True,
            'detected_mime': detected_mime,
            'errors': []
        }
    
    def _validate_content_security(self, file: UploadedFile) -> Dict[str, Union[bool, List[str]]]:
        """Scan file content for security threats."""
        errors = []
        warnings = []
        
        try:
            # Reset file pointer
            file.seek(0)
            content = file.read(8192)  # Read first 8KB for signature detection
            file.seek(0)
            
            # Check for dangerous file signatures
            for signature in FileValidationConfig.DANGEROUS_SIGNATURES:
                if content.startswith(signature):
                    errors.append(f"File contains potentially dangerous signature")
                    break
            
            # Check for embedded executables (basic heuristic)
            if b'MZ' in content or b'\x7fELF' in content:
                errors.append("File may contain executable code")
            
            # Check for suspicious scripts in supposedly safe files
            dangerous_patterns = [
                b'<script',
                b'javascript:',
                b'vbscript:',
                b'onload=',
                b'onerror=',
                b'eval(',
                b'document.cookie'
            ]
            
            content_lower = content.lower()
            for pattern in dangerous_patterns:
                if pattern in content_lower:
                    warnings.append(f"File contains potentially suspicious content")
                    break
                    
        except Exception as e:
            logger.error(f"Content security scan failed: {e}")
            warnings.append("Could not complete content security scan")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }
    
    def _scan_for_viruses(self, file: UploadedFile) -> Dict[str, Union[bool, List[str]]]:
        """Scan file for viruses using ClamAV."""
        if not HAS_CLAMD:
            logger.warning("ClamAV not available, skipping virus scan")
            return {'valid': True, 'errors': []}
        
        try:
            # Connect to ClamAV daemon
            cd = clamd.ClamdUnixSocket()
            
            # Test connection
            if not cd.ping():
                logger.warning("ClamAV daemon not responding")
                return {'valid': True, 'errors': []}
            
            # Create temporary file for scanning
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                file.seek(0)
                temp_file.write(file.read())
                temp_file_path = temp_file.name
                file.seek(0)
            
            try:
                # Scan the file
                scan_result = cd.scan(temp_file_path)
                
                if scan_result is None:
                    return {'valid': True, 'errors': []}
                
                # Check results
                for file_path, result in scan_result.items():
                    if result[0] == 'FOUND':
                        return {
                            'valid': False,
                            'errors': [f"Virus detected: {result[1]}"]
                        }
                        
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass
            
            return {'valid': True, 'errors': []}
            
        except Exception as e:
            logger.error(f"Virus scan failed: {e}")
            # Don't fail validation if virus scanning fails
            return {'valid': True, 'errors': []}
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format file size in human readable format."""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"


# Django validator functions for model fields
def validate_image_file(file: UploadedFile):
    """Django validator for image files."""
    validator = FileValidator(
        allowed_types=FileValidationConfig.ALLOWED_IMAGE_TYPES,
        max_size=getattr(settings, 'MAX_IMAGE_SIZE', FileValidationConfig.DEFAULT_MAX_IMAGE_SIZE)
    )
    
    result = validator.validate(file)
    if not result['valid']:
        raise ValidationError('; '.join(result['errors']))


def validate_document_file(file: UploadedFile):
    """Django validator for document files."""
    validator = FileValidator(
        allowed_types=FileValidationConfig.ALLOWED_DOCUMENT_TYPES,
        max_size=getattr(settings, 'MAX_DOCUMENT_SIZE', FileValidationConfig.DEFAULT_MAX_FILE_SIZE)
    )
    
    result = validator.validate(file)
    if not result['valid']:
        raise ValidationError('; '.join(result['errors']))


def validate_any_file(file: UploadedFile):
    """Django validator for any safe file type."""
    all_allowed = (
        FileValidationConfig.ALLOWED_IMAGE_TYPES +
        FileValidationConfig.ALLOWED_DOCUMENT_TYPES +
        FileValidationConfig.ALLOWED_ARCHIVE_TYPES
    )
    
    validator = FileValidator(
        allowed_types=all_allowed,
        max_size=getattr(settings, 'MAX_FILE_SIZE', FileValidationConfig.DEFAULT_MAX_FILE_SIZE)
    )
    
    result = validator.validate(file)
    if not result['valid']:
        raise ValidationError('; '.join(result['errors']))


def create_custom_validator(allowed_types: List[str], max_size: int = None):
    """Create a custom file validator function."""
    def validator(file: UploadedFile):
        file_validator = FileValidator(
            allowed_types=allowed_types,
            max_size=max_size or FileValidationConfig.DEFAULT_MAX_FILE_SIZE
        )
        
        result = file_validator.validate(file)
        if not result['valid']:
            raise ValidationError('; '.join(result['errors']))
    
    return validator


# Utility functions
def get_file_info(file: UploadedFile) -> Dict[str, str]:
    """Get detailed file information."""
    validator = FileValidator()
    result = validator.validate(file)
    return result.get('file_info', {})


def is_safe_filename(filename: str) -> bool:
    """Check if filename is safe (no path traversal, etc.)."""
    if not filename:
        return False
    
    # Check for path traversal attempts
    if '..' in filename or '/' in filename or '\\' in filename:
        return False
    
    # Check for dangerous characters
    dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '\0']
    if any(char in filename for char in dangerous_chars):
        return False
    
    # Check length
    if len(filename) > 255:
        return False
    
    return True


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage."""
    if not filename:
        return 'unnamed_file'
    
    # Get file extension
    name, ext = os.path.splitext(filename)
    
    # Remove dangerous characters
    safe_chars = []
    for char in name:
        if char.isalnum() or char in '-_. ':
            safe_chars.append(char)
        else:
            safe_chars.append('_')
    
    safe_name = ''.join(safe_chars).strip()
    
    # Ensure not empty
    if not safe_name:
        safe_name = 'file'
    
    # Limit length
    if len(safe_name) > 200:
        safe_name = safe_name[:200]
    
    return safe_name + ext.lower()