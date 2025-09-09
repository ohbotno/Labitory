# booking/auth_backends.py
"""
Azure AD authentication backend for SSO integration.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import logging
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class AzureADBackend(BaseBackend):
    """
    Azure AD authentication backend for Single Sign-On (SSO).
    
    This backend handles authentication via Microsoft Azure AD OAuth2.
    It creates or updates user accounts based on Azure AD claims.
    """
    
    def authenticate(self, request, azure_token=None, **kwargs):
        """
        Authenticate user using Azure AD token.
        
        Args:
            request: HTTP request object
            azure_token: Azure AD access token with user claims
            
        Returns:
            User object if authentication successful, None otherwise
        """
        if not azure_token:
            return None
            
        try:
            # Extract user information from Azure AD token claims
            user_info = self._get_user_info_from_token(azure_token)
            if not user_info:
                return None
            
            # Get or create user based on Azure AD information
            user = self._get_or_create_user(user_info)
            if user:
                # Update user profile with Azure AD information
                self._update_user_profile(user, user_info)
                logger.info(f"Azure AD authentication successful for user: {user.username}")
                return user
                
        except Exception as e:
            logger.error(f"Azure AD authentication error: {e}")
            return None
    
    def get_user(self, user_id):
        """Get user by ID."""
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
    
    def _get_user_info_from_token(self, token):
        """
        Extract user information from Azure AD token claims.
        
        Args:
            token: Azure AD token with user claims
            
        Returns:
            dict: User information extracted from token
        """
        try:
            # Token should contain user claims
            claims = token.get('claims', {})
            
            return {
                'email': claims.get('preferred_username') or claims.get('email'),
                'first_name': claims.get('given_name', ''),
                'last_name': claims.get('family_name', ''),
                'full_name': claims.get('name', ''),
                'azure_id': claims.get('oid'),  # Azure Object ID
                'tenant_id': claims.get('tid'),  # Tenant ID
                'roles': claims.get('roles', []),
                'groups': claims.get('groups', []),
            }
        except Exception as e:
            logger.error(f"Error extracting user info from Azure AD token: {e}")
            return None
    
    def _get_or_create_user(self, user_info):
        """
        Get or create Django user based on Azure AD information.
        
        Args:
            user_info: User information from Azure AD
            
        Returns:
            User object or None
        """
        email = user_info.get('email')
        if not email:
            logger.error("No email found in Azure AD user info")
            return None
        
        try:
            # Try to find existing user by email
            user = User.objects.get(email=email)
            logger.info(f"Found existing user for Azure AD login: {user.username}")
            
        except User.DoesNotExist:
            # Create new user account
            username = self._generate_username(user_info)
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=user_info.get('first_name', ''),
                last_name=user_info.get('last_name', ''),
                is_active=True
            )
            # Set unusable password since they'll use SSO
            user.set_unusable_password()
            user.save()
            
            logger.info(f"Created new user for Azure AD login: {user.username}")
            
        except Exception as e:
            logger.error(f"Error creating user from Azure AD info: {e}")
            return None
        
        return user
    
    def _generate_username(self, user_info):
        """
        Generate unique username based on Azure AD information.
        
        Args:
            user_info: User information from Azure AD
            
        Returns:
            str: Unique username
        """
        email = user_info.get('email', '')
        # Use email prefix as base username
        base_username = email.split('@')[0] if email else 'azure_user'
        
        # Ensure username is unique
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}_{counter}"
            counter += 1
            
        return username
    
    def _update_user_profile(self, user, user_info):
        """
        Update user profile with Azure AD information.
        
        Args:
            user: Django User object
            user_info: User information from Azure AD
        """
        try:
            # Update basic user information
            user.first_name = user_info.get('first_name', user.first_name)
            user.last_name = user_info.get('last_name', user.last_name)
            user.save()
            
            # Update or create user profile
            from .models import UserProfile
            profile, created = UserProfile.objects.get_or_create(user=user)
            
            # Store Azure AD specific information
            if not hasattr(profile, 'azure_ad_data'):
                profile.azure_ad_data = {}
            
            profile.azure_ad_data = {
                'azure_id': user_info.get('azure_id'),
                'tenant_id': user_info.get('tenant_id'),
                'last_azure_login': timezone.now().isoformat(),
                'roles': user_info.get('roles', []),
                'groups': user_info.get('groups', []),
            }
            profile.save()
            
            # Handle group/role mapping if configured
            self._map_azure_roles_to_django_groups(user, user_info.get('roles', []))
            
        except Exception as e:
            logger.error(f"Error updating user profile for {user.username}: {e}")
    
    def _map_azure_roles_to_django_groups(self, user, azure_roles):
        """
        Map Azure AD roles to Django groups/permissions.
        
        Args:
            user: Django User object
            azure_roles: List of Azure AD roles
        """
        try:
            from django.contrib.auth.models import Group
            
            # Example role mappings - customize based on your Azure AD setup
            role_mappings = {
                'Lab-Manager': 'Lab Managers',
                'Lab-Admin': 'Lab Administrators',
                'Student': 'Students',
                'Faculty': 'Faculty',
                'Staff': 'Staff',
            }
            
            # Clear existing groups from previous Azure AD login
            user.groups.clear()
            
            # Add user to groups based on Azure AD roles
            for azure_role in azure_roles:
                django_group_name = role_mappings.get(azure_role)
                if django_group_name:
                    try:
                        group = Group.objects.get(name=django_group_name)
                        user.groups.add(group)
                        logger.info(f"Added user {user.username} to group {django_group_name}")
                    except Group.DoesNotExist:
                        logger.warning(f"Django group '{django_group_name}' not found for Azure role '{azure_role}'")
            
        except Exception as e:
            logger.error(f"Error mapping Azure AD roles to Django groups for {user.username}: {e}")