# booking/sms_service.py
"""
SMS notification service using Twilio.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

import logging
from typing import Optional
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

# Import Twilio conditionally
try:
    from twilio.rest import Client
    from twilio.base.exceptions import TwilioException
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    logger.warning("Twilio not installed. SMS notifications will be disabled.")


class SMSService:
    """Service for sending SMS notifications via Twilio."""
    
    def __init__(self):
        self.client = None
        self.from_number = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Twilio client if credentials are available."""
        if not TWILIO_AVAILABLE:
            logger.warning("Twilio SDK not available. SMS functionality disabled.")
            return
        
        # Try to get configuration from database first
        try:
            from ..models import SMSConfiguration
            sms_config = SMSConfiguration.get_active_configuration()
            
            if sms_config and sms_config.is_enabled:
                account_sid = sms_config.twilio_account_sid
                auth_token = sms_config.twilio_auth_token
                self.from_number = sms_config.twilio_phone_number
                self.sms_config = sms_config
                logger.info(f"Using SMS configuration: {sms_config.name}")
            else:
                # Fallback to environment variables for backward compatibility
                account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
                auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
                self.from_number = getattr(settings, 'TWILIO_PHONE_NUMBER', None)
                self.sms_config = None
                if account_sid:
                    logger.info("Using SMS configuration from environment variables")
                
        except Exception as e:
            logger.warning(f"Could not load SMS configuration from database: {e}")
            # Fallback to environment variables
            account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
            auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
            self.from_number = getattr(settings, 'TWILIO_PHONE_NUMBER', None)
            self.sms_config = None
        
        if account_sid and auth_token and self.from_number:
            try:
                self.client = Client(account_sid, auth_token)
                logger.info("Twilio SMS service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Twilio client: {e}")
                self.client = None
        else:
            logger.info("Twilio credentials not configured. SMS functionality disabled.")
    
    def is_available(self) -> bool:
        """Check if SMS service is available and configured."""
        if not TWILIO_AVAILABLE or self.client is None:
            return False
        
        # Check if we have a database configuration
        if hasattr(self, 'sms_config') and self.sms_config:
            return self.sms_config.is_enabled and self.sms_config.is_active
        
        # If using environment variables, check settings
        return getattr(settings, 'SMS_ENABLED', True)
    
    def reload_configuration(self):
        """Reload SMS configuration from database."""
        self.client = None
        self.from_number = None
        self._initialize_client()
    
    def send_sms(self, to_number: str, message: str) -> bool:
        """
        Send SMS message to a phone number.
        
        Args:
            to_number: Phone number in international format (e.g., +1234567890)
            message: SMS message content (max 1600 characters)
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        if not self.is_available():
            logger.warning(f"SMS service not available. Skipping SMS to {to_number}")
            return False
        
        if not to_number or not message:
            logger.error("SMS requires both phone number and message")
            return False
        
        # Ensure phone number starts with +
        if not to_number.startswith('+'):
            logger.error(f"Phone number must be in international format: {to_number}")
            return False
        
        # Truncate message if too long
        max_length = 1600  # Default
        if hasattr(self, 'sms_config') and self.sms_config:
            max_length = self.sms_config.message_character_limit
        
        if len(message) > max_length:
            message = message[:max_length-3] + "..."
            logger.warning(f"SMS message truncated to {max_length} characters for {to_number}")
        
        try:
            message_instance = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_number
            )
            
            logger.info(f"SMS sent successfully to {to_number}. SID: {message_instance.sid}")
            return True
            
        except TwilioException as e:
            logger.error(f"Twilio error sending SMS to {to_number}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending SMS to {to_number}: {e}")
            return False
    
    def validate_phone_number(self, phone_number: str) -> bool:
        """
        Validate phone number format using Twilio's lookup service.
        
        Args:
            phone_number: Phone number to validate
            
        Returns:
            bool: True if phone number is valid, False otherwise
        """
        if not self.is_available():
            # Basic validation without Twilio
            return phone_number.startswith('+') and len(phone_number) >= 10
        
        try:
            # Use Twilio's lookup service for validation
            phone_number_lookup = self.client.lookups.phone_numbers(phone_number).fetch()
            return phone_number_lookup.phone_number is not None
        except TwilioException:
            return False
        except Exception as e:
            logger.error(f"Error validating phone number {phone_number}: {e}")
            return False
    
    def format_notification_message(self, notification) -> str:
        """
        Format notification for SMS delivery.
        
        Args:
            notification: Notification instance
            
        Returns:
            str: Formatted SMS message
        """
        # Create a concise SMS message
        message_parts = []
        
        # Add site name prefix
        site_name = getattr(settings, 'SITE_NAME', 'Labitory')
        message_parts.append(f"[{site_name}]")
        
        # Add title
        message_parts.append(notification.title)
        
        # Add concise message content
        # Remove HTML tags and limit length for SMS
        clean_message = notification.message.replace('<br>', ' ').replace('\n', ' ')
        # Simple HTML tag removal
        import re
        clean_message = re.sub(r'<[^>]+>', '', clean_message)
        
        # Limit message length (SMS is typically 160 chars per segment)
        if len(clean_message) > 140:  # Leave room for title and site name
            clean_message = clean_message[:137] + "..."
        
        message_parts.append(clean_message)
        
        return ' - '.join(message_parts)
    
    def get_user_phone_number(self, user) -> Optional[str]:
        """
        Get user's phone number from their profile.
        
        Args:
            user: Django User instance
            
        Returns:
            str: Phone number in international format, or None if not available
        """
        try:
            # Check if user has a profile with phone number
            if hasattr(user, 'userprofile') and user.userprofile.phone:
                phone = user.userprofile.phone.strip()
                
                # Basic formatting - ensure it starts with +
                if phone and not phone.startswith('+'):
                    # Assume US number if no country code
                    if phone.startswith('1'):
                        phone = '+' + phone
                    else:
                        phone = '+1' + phone
                
                return phone
            
        except Exception as e:
            logger.error(f"Error getting phone number for user {user.username}: {e}")
        
        return None


# Global SMS service instance
sms_service = SMSService()