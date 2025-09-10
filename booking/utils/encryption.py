# booking/utils/encryption.py
"""
Field-level encryption utilities for sensitive data.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class FieldEncryption:
    """
    Utility class for field-level encryption using Fernet (AES 128).
    """
    
    def __init__(self):
        self._fernet = None
        self._init_encryption()
    
    def _init_encryption(self):
        """
        Initialize the Fernet encryption instance.
        """
        encryption_key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
        
        if not encryption_key:
            raise ImproperlyConfigured(
                "FIELD_ENCRYPTION_KEY must be set in settings for field encryption"
            )
        
        # If key is a password, derive the actual key
        if len(encryption_key) != 44:  # Fernet keys are 44 characters when base64 encoded
            encryption_key = self._derive_key(encryption_key)
        
        self._fernet = Fernet(encryption_key)
    
    def _derive_key(self, password):
        """
        Derive a Fernet key from a password using PBKDF2.
        """
        # Use a fixed salt for key derivation (in production, use env variable)
        salt = getattr(settings, 'FIELD_ENCRYPTION_SALT', b'labitory_salt_2025')
        if isinstance(salt, str):
            salt = salt.encode('utf-8')
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode('utf-8')))
        return key
    
    def encrypt(self, plaintext):
        """
        Encrypt a plaintext string.
        
        Args:
            plaintext (str): The text to encrypt
            
        Returns:
            str: Base64-encoded encrypted text
        """
        if plaintext is None:
            return None
        
        if not isinstance(plaintext, str):
            plaintext = str(plaintext)
        
        encrypted_bytes = self._fernet.encrypt(plaintext.encode('utf-8'))
        return base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8')
    
    def decrypt(self, encrypted_text):
        """
        Decrypt an encrypted string.
        
        Args:
            encrypted_text (str): Base64-encoded encrypted text
            
        Returns:
            str: Decrypted plaintext
        """
        if encrypted_text is None:
            return None
        
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_text.encode('utf-8'))
            decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except Exception:
            # Return None if decryption fails (corrupted data, wrong key, etc.)
            return None


# Global encryption instance
_encryption_instance = None


def get_encryption_instance():
    """
    Get the global encryption instance.
    """
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = FieldEncryption()
    return _encryption_instance


def encrypt_field(value):
    """
    Encrypt a field value.
    """
    return get_encryption_instance().encrypt(value)


def decrypt_field(value):
    """
    Decrypt a field value.
    """
    return get_encryption_instance().decrypt(value)


def generate_encryption_key():
    """
    Generate a new Fernet encryption key.
    
    Returns:
        str: Base64-encoded encryption key
    """
    return Fernet.generate_key().decode('utf-8')


# Django model field for encrypted data
from django.db import models
from django.core.exceptions import ValidationError


class EncryptedField(models.TextField):
    """
    Django model field that automatically encrypts/decrypts data.
    """
    
    description = "Encrypted text field"
    
    def __init__(self, *args, **kwargs):
        # Remove custom kwargs before passing to parent
        self.encrypt_blank = kwargs.pop('encrypt_blank', False)
        super().__init__(*args, **kwargs)
    
    def to_python(self, value):
        """
        Convert database value to Python value (decrypt).
        """
        if value is None:
            return value
        
        if isinstance(value, str) and value:
            # Try to decrypt the value
            decrypted = decrypt_field(value)
            if decrypted is not None:
                return decrypted
            else:
                # If decryption fails, assume it's already plaintext
                # This handles the case where data was stored before encryption was enabled
                return value
        
        return value
    
    def get_prep_value(self, value):
        """
        Convert Python value to database value (encrypt).
        """
        if value is None:
            return value
        
        if not self.encrypt_blank and not value:
            return value
        
        if isinstance(value, str):
            return encrypt_field(value)
        
        return value
    
    def from_db_value(self, value, expression, connection):
        """
        Convert database value to Python value.
        """
        return self.to_python(value)


class EncryptedCharField(models.CharField):
    """
    Encrypted version of CharField.
    """
    
    description = "Encrypted character field"
    
    def __init__(self, *args, **kwargs):
        self.encrypt_blank = kwargs.pop('encrypt_blank', False)
        super().__init__(*args, **kwargs)
    
    def to_python(self, value):
        if value is None:
            return value
        
        if isinstance(value, str) and value:
            decrypted = decrypt_field(value)
            if decrypted is not None:
                return decrypted
            else:
                return value
        
        return value
    
    def get_prep_value(self, value):
        if value is None:
            return value
        
        if not self.encrypt_blank and not value:
            return value
        
        if isinstance(value, str):
            encrypted = encrypt_field(value)
            # Ensure encrypted value fits in max_length if specified
            if hasattr(self, 'max_length') and self.max_length:
                if len(encrypted) > self.max_length:
                    raise ValidationError(
                        f"Encrypted value too long for field (max_length={self.max_length})"
                    )
            return encrypted
        
        return value
    
    def from_db_value(self, value, expression, connection):
        return self.to_python(value)


class EncryptedEmailField(models.EmailField):
    """
    Encrypted version of EmailField.
    """
    
    description = "Encrypted email field"
    
    def __init__(self, *args, **kwargs):
        # Email fields are typically longer when encrypted
        if 'max_length' not in kwargs:
            kwargs['max_length'] = 254  # Standard email max length, but encrypted will be longer
        super().__init__(*args, **kwargs)
    
    def to_python(self, value):
        if value is None:
            return value
        
        if isinstance(value, str) and value:
            decrypted = decrypt_field(value)
            if decrypted is not None:
                return decrypted
            else:
                return value
        
        return value
    
    def get_prep_value(self, value):
        if value is None:
            return value
        
        if value:
            return encrypt_field(value)
        
        return value
    
    def from_db_value(self, value, expression, connection):
        return self.to_python(value)


# Utility functions for manual encryption/decryption in views
def encrypt_sensitive_data(data_dict, sensitive_fields):
    """
    Encrypt specific fields in a dictionary.
    
    Args:
        data_dict (dict): Dictionary containing data
        sensitive_fields (list): List of field names to encrypt
    
    Returns:
        dict: Dictionary with encrypted fields
    """
    encrypted_data = data_dict.copy()
    
    for field in sensitive_fields:
        if field in encrypted_data and encrypted_data[field]:
            encrypted_data[field] = encrypt_field(encrypted_data[field])
    
    return encrypted_data


def decrypt_sensitive_data(data_dict, sensitive_fields):
    """
    Decrypt specific fields in a dictionary.
    
    Args:
        data_dict (dict): Dictionary containing encrypted data
        sensitive_fields (list): List of field names to decrypt
    
    Returns:
        dict: Dictionary with decrypted fields
    """
    decrypted_data = data_dict.copy()
    
    for field in sensitive_fields:
        if field in decrypted_data and decrypted_data[field]:
            decrypted_data[field] = decrypt_field(decrypted_data[field])
    
    return decrypted_data


# Key rotation utilities
def rotate_encryption_key(old_key, new_key):
    """
    Rotate encryption keys by re-encrypting data with new key.
    
    This would typically be run as a management command.
    """
    # This is a simplified example - in production, you'd want to:
    # 1. Create a backup
    # 2. Process data in batches
    # 3. Handle failures gracefully
    # 4. Verify data integrity
    
    from django.apps import apps
    
    # Get all models with encrypted fields
    encrypted_models = []
    for model in apps.get_models():
        encrypted_fields = []
        for field in model._meta.fields:
            if isinstance(field, (EncryptedField, EncryptedCharField, EncryptedEmailField)):
                encrypted_fields.append(field.name)
        
        if encrypted_fields:
            encrypted_models.append((model, encrypted_fields))
    
    # Process each model
    for model, fields in encrypted_models:
        for obj in model.objects.all():
            for field_name in fields:
                old_value = getattr(obj, field_name)
                if old_value:
                    # Decrypt with old key and encrypt with new key
                    # Implementation would depend on how you handle key management
                    pass