# booking/models/audit.py
"""
Audit logging models for comprehensive data change tracking.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
import json


class AuditLog(models.Model):
    """
    Comprehensive audit log for all data changes.
    """
    
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('READ', 'Read'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('PERMISSION_CHANGE', 'Permission Change'),
        ('API_ACCESS', 'API Access'),
        ('EXPORT', 'Data Export'),
        ('IMPORT', 'Data Import'),
    ]
    
    # Who performed the action
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    username = models.CharField(max_length=150, blank=True)  # Store username even if user is deleted
    
    # What was changed
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.CharField(max_length=255, null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    
    # Action details
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    table_name = models.CharField(max_length=255, blank=True)
    field_changes = models.JSONField(default=dict, blank=True)  # Field-level changes
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    
    # Context information
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    session_key = models.CharField(max_length=40, blank=True)
    
    # Additional metadata
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Request information
    request_method = models.CharField(max_length=10, blank=True)
    request_path = models.CharField(max_length=500, blank=True)
    request_id = models.CharField(max_length=50, blank=True, db_index=True)
    
    class Meta:
        db_table = 'booking_auditlog'
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['table_name', 'timestamp']),
            models.Index(fields=['ip_address', 'timestamp']),
        ]
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-timestamp']
    
    def __str__(self):
        user_info = self.username or "System"
        if self.content_object:
            return f"{user_info} {self.action} {self.content_object} at {self.timestamp}"
        return f"{user_info} {self.action} at {self.timestamp}"
    
    @classmethod
    def log_action(cls, user, action, content_object=None, field_changes=None, 
                   old_values=None, new_values=None, request=None, description="", **kwargs):
        """
        Convenient method to create audit log entries.
        """
        # Get user info
        username = user.username if user else "Anonymous"
        
        # Get object info
        content_type = None
        object_id = None
        table_name = ""
        
        if content_object:
            content_type = ContentType.objects.get_for_model(content_object)
            object_id = str(content_object.pk)
            table_name = content_object._meta.db_table
        
        # Get request info
        ip_address = None
        user_agent = ""
        request_method = ""
        request_path = ""
        session_key = ""
        
        if request:
            ip_address = get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            request_method = request.method
            request_path = request.path
            session_key = request.session.session_key if hasattr(request, 'session') else ""
        
        return cls.objects.create(
            user=user,
            username=username,
            content_type=content_type,
            object_id=object_id,
            content_object=content_object,
            action=action,
            table_name=table_name,
            field_changes=field_changes or {},
            old_values=old_values or {},
            new_values=new_values or {},
            ip_address=ip_address,
            user_agent=user_agent,
            session_key=session_key,
            description=description,
            metadata=kwargs.get('metadata', {}),
            request_method=request_method,
            request_path=request_path,
            request_id=kwargs.get('request_id', ''),
        )


class DataAccessLog(models.Model):
    """
    Log sensitive data access for compliance.
    """
    
    ACCESS_TYPES = [
        ('VIEW', 'View'),
        ('SEARCH', 'Search'),
        ('EXPORT', 'Export'),
        ('PRINT', 'Print'),
        ('API_READ', 'API Read'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    access_type = models.CharField(max_length=20, choices=ACCESS_TYPES)
    resource_type = models.CharField(max_length=100)  # e.g., 'user_profile', 'booking'
    resource_id = models.CharField(max_length=255)
    
    # Access details
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    # Query/filter information
    search_criteria = models.JSONField(default=dict, blank=True)
    fields_accessed = models.JSONField(default=list, blank=True)
    
    # Justification (for sensitive access)
    purpose = models.TextField(blank=True)
    
    class Meta:
        db_table = 'booking_dataaccesslog'
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['resource_type', 'timestamp']),
            models.Index(fields=['access_type', 'timestamp']),
        ]
        verbose_name = 'Data Access Log'
        verbose_name_plural = 'Data Access Logs'
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user.username} {self.access_type} {self.resource_type} at {self.timestamp}"


class LoginAttempt(models.Model):
    """
    Track all login attempts for security monitoring.
    """
    
    ATTEMPT_TYPES = [
        ('SUCCESS', 'Successful Login'),
        ('FAILED_PASSWORD', 'Failed - Wrong Password'),
        ('FAILED_USERNAME', 'Failed - Wrong Username'),
        ('FAILED_2FA', 'Failed - 2FA'),
        ('FAILED_LOCKED', 'Failed - Account Locked'),
        ('FAILED_DISABLED', 'Failed - Account Disabled'),
        ('LOGOUT', 'Logout'),
    ]
    
    username = models.CharField(max_length=150, db_index=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    attempt_type = models.CharField(max_length=20, choices=ATTEMPT_TYPES, db_index=True)
    
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(db_index=True)
    user_agent = models.TextField(blank=True)
    
    # Additional context
    failure_reason = models.TextField(blank=True)
    session_key = models.CharField(max_length=40, blank=True)
    
    # Location information (if available)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    
    class Meta:
        db_table = 'booking_loginattempt'
        indexes = [
            models.Index(fields=['username', 'timestamp']),
            models.Index(fields=['ip_address', 'timestamp']),
            models.Index(fields=['attempt_type', 'timestamp']),
        ]
        verbose_name = 'Login Attempt'
        verbose_name_plural = 'Login Attempts'
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.username} - {self.get_attempt_type_display()} from {self.ip_address} at {self.timestamp}"


class AdminAction(models.Model):
    """
    Track administrative actions for compliance.
    """
    
    ACTION_TYPES = [
        ('USER_CREATE', 'User Creation'),
        ('USER_UPDATE', 'User Update'),
        ('USER_DELETE', 'User Deletion'),
        ('USER_ACTIVATE', 'User Activation'),
        ('USER_DEACTIVATE', 'User Deactivation'),
        ('PERMISSION_GRANT', 'Permission Granted'),
        ('PERMISSION_REVOKE', 'Permission Revoked'),
        ('ROLE_CHANGE', 'Role Change'),
        ('SYSTEM_CONFIG', 'System Configuration'),
        ('DATA_EXPORT', 'Data Export'),
        ('DATA_IMPORT', 'Data Import'),
        ('BACKUP_CREATE', 'Backup Created'),
        ('BACKUP_RESTORE', 'Backup Restored'),
    ]
    
    admin_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_actions')
    action_type = models.CharField(max_length=30, choices=ACTION_TYPES, db_index=True)
    
    # Target of the action
    target_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='admin_actions_received')
    target_username = models.CharField(max_length=150, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    # Action details
    description = models.TextField()
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    
    # Justification
    reason = models.TextField(blank=True)
    
    class Meta:
        db_table = 'booking_adminaction'
        indexes = [
            models.Index(fields=['admin_user', 'timestamp']),
            models.Index(fields=['action_type', 'timestamp']),
            models.Index(fields=['target_user', 'timestamp']),
        ]
        verbose_name = 'Admin Action'
        verbose_name_plural = 'Admin Actions'
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.admin_user.username} - {self.get_action_type_display()} at {self.timestamp}"


def get_client_ip(request):
    """
    Get client IP address from request.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# Utility functions for audit logging
def log_model_change(user, instance, action, old_values=None, new_values=None, request=None):
    """
    Log model instance changes.
    """
    field_changes = {}
    
    if old_values and new_values:
        for field, new_value in new_values.items():
            old_value = old_values.get(field)
            if old_value != new_value:
                field_changes[field] = {
                    'old': old_value,
                    'new': new_value
                }
    
    AuditLog.log_action(
        user=user,
        action=action,
        content_object=instance,
        field_changes=field_changes,
        old_values=old_values,
        new_values=new_values,
        request=request,
        description=f"{action} {instance._meta.verbose_name} {instance}"
    )


def log_data_access(user, resource_type, resource_id, access_type, request=None, **kwargs):
    """
    Log sensitive data access.
    """
    ip_address = None
    user_agent = ""
    
    if request:
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    DataAccessLog.objects.create(
        user=user,
        access_type=access_type,
        resource_type=resource_type,
        resource_id=str(resource_id),
        ip_address=ip_address,
        user_agent=user_agent,
        search_criteria=kwargs.get('search_criteria', {}),
        fields_accessed=kwargs.get('fields_accessed', []),
        purpose=kwargs.get('purpose', '')
    )


def log_login_attempt(username, attempt_type, request=None, user=None, failure_reason=""):
    """
    Log login attempts.
    """
    ip_address = None
    user_agent = ""
    session_key = ""
    
    if request:
        ip_address = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        session_key = request.session.session_key if hasattr(request, 'session') else ""
    
    LoginAttempt.objects.create(
        username=username,
        user=user,
        attempt_type=attempt_type,
        ip_address=ip_address,
        user_agent=user_agent,
        failure_reason=failure_reason,
        session_key=session_key
    )


def log_admin_action(admin_user, action_type, description, request=None, target_user=None, **kwargs):
    """
    Log administrative actions.
    """
    ip_address = None
    if request:
        ip_address = get_client_ip(request)
    
    AdminAction.objects.create(
        admin_user=admin_user,
        action_type=action_type,
        target_user=target_user,
        target_username=target_user.username if target_user else "",
        timestamp=timezone.now(),
        ip_address=ip_address,
        description=description,
        old_values=kwargs.get('old_values', {}),
        new_values=kwargs.get('new_values', {}),
        reason=kwargs.get('reason', '')
    )