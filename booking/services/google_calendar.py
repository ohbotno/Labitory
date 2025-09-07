# booking/services/google_calendar.py
"""
Google Calendar integration service for Labitory.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json

from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_LIBRARIES_AVAILABLE = True
except ImportError:
    GOOGLE_LIBRARIES_AVAILABLE = False

from ..models import GoogleCalendarIntegration, GoogleCalendarSyncLog, CalendarSyncPreferences, Booking

logger = logging.getLogger(__name__)


class GoogleCalendarService:
    """Service for Google Calendar OAuth integration and synchronization."""
    
    # Google Calendar API scopes
    SCOPES = [
        'https://www.googleapis.com/auth/calendar',
        'https://www.googleapis.com/auth/userinfo.email'
    ]
    
    def __init__(self):
        """Initialize the Google Calendar service."""
        if not GOOGLE_LIBRARIES_AVAILABLE:
            raise ImproperlyConfigured(
                "Google Calendar libraries not installed. "
                "Install with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )
        
        self.client_id = getattr(settings, 'GOOGLE_OAUTH2_CLIENT_ID', None)
        self.client_secret = getattr(settings, 'GOOGLE_OAUTH2_CLIENT_SECRET', None)
        
        if not self.client_id or not self.client_secret:
            raise ImproperlyConfigured(
                "Google OAuth2 credentials not configured. "
                "Set GOOGLE_OAUTH2_CLIENT_ID and GOOGLE_OAUTH2_CLIENT_SECRET in settings."
            )
    
    def get_oauth_flow(self, request):
        """Create OAuth flow for Google Calendar authorization."""
        try:
            # Build redirect URI
            redirect_uri = request.build_absolute_uri(reverse('booking:google_calendar_callback'))
            
            # Create flow
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [redirect_uri]
                    }
                },
                scopes=self.SCOPES
            )
            flow.redirect_uri = redirect_uri
            return flow
            
        except Exception as e:
            logger.error(f"Error creating OAuth flow: {e}")
            raise
    
    def get_authorization_url(self, request) -> str:
        """Get Google OAuth authorization URL."""
        flow = self.get_oauth_flow(request)
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'  # Force consent to get refresh token
        )
        
        # Store state in session for security
        request.session['google_oauth_state'] = flow.state
        
        return auth_url
    
    def handle_oauth_callback(self, request, authorization_code: str) -> GoogleCalendarIntegration:
        """Handle OAuth callback and create/update integration."""
        try:
            # Verify state for security
            stored_state = request.session.get('google_oauth_state')
            received_state = request.GET.get('state')
            
            if not stored_state or stored_state != received_state:
                raise ValueError("Invalid OAuth state parameter")
            
            # Exchange authorization code for tokens
            flow = self.get_oauth_flow(request)
            flow.fetch_token(code=authorization_code)
            
            credentials = flow.credentials
            
            # Get user info from Google
            service = build('oauth2', 'v2', credentials=credentials)
            user_info = service.userinfo().get().execute()
            
            # Calculate token expiry
            token_expires_at = timezone.now() + timedelta(seconds=credentials.expiry.timestamp() - timezone.now().timestamp())
            
            # Create or update integration
            integration, created = GoogleCalendarIntegration.objects.get_or_create(
                user=request.user,
                defaults={
                    'access_token': credentials.token,
                    'refresh_token': credentials.refresh_token,
                    'token_expires_at': token_expires_at,
                    'google_calendar_id': 'primary',  # Default to primary calendar
                }
            )
            
            if not created:
                # Update existing integration
                integration.access_token = credentials.token
                integration.refresh_token = credentials.refresh_token or integration.refresh_token
                integration.token_expires_at = token_expires_at
                integration.is_active = True
                integration.sync_error_count = 0
                integration.last_error = ''
                integration.save()
            
            # Create sync preferences if they don't exist
            CalendarSyncPreferences.objects.get_or_create(user=request.user)
            
            # Log successful connection
            GoogleCalendarSyncLog.objects.create(
                user=request.user,
                action='token_refresh' if not created else 'created',
                status='success',
                google_event_id='',
                response_data={'user_email': user_info.get('email')}
            )
            
            logger.info(f"Google Calendar integration {'updated' if not created else 'created'} for user {request.user.username}")
            
            return integration
            
        except Exception as e:
            logger.error(f"Error handling OAuth callback for user {request.user.username}: {e}")
            
            # Log the error
            GoogleCalendarSyncLog.objects.create(
                user=request.user,
                action='token_refresh',
                status='error',
                error_message=str(e)
            )
            
            raise
        finally:
            # Clean up session
            request.session.pop('google_oauth_state', None)
    
    def refresh_access_token(self, integration: GoogleCalendarIntegration) -> bool:
        """Refresh expired access token."""
        try:
            credentials = Credentials(
                token=integration.access_token,
                refresh_token=integration.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            
            # Refresh the token
            request = Request()
            credentials.refresh(request)
            
            # Update integration
            integration.access_token = credentials.token
            integration.token_expires_at = timezone.now() + timedelta(seconds=3600)  # 1 hour
            integration.sync_error_count = 0
            integration.last_error = ''
            integration.save()
            
            # Log successful refresh
            GoogleCalendarSyncLog.objects.create(
                user=integration.user,
                action='token_refresh',
                status='success'
            )
            
            logger.info(f"Access token refreshed for user {integration.user.username}")
            return True
            
        except Exception as e:
            logger.error(f"Error refreshing token for user {integration.user.username}: {e}")
            
            # Log the error
            GoogleCalendarSyncLog.objects.create(
                user=integration.user,
                action='token_refresh',
                status='error',
                error_message=str(e)
            )
            
            # Increment error count
            integration.sync_error_count += 1
            integration.last_error = str(e)
            integration.save()
            
            return False
    
    def get_calendar_service(self, integration: GoogleCalendarIntegration):
        """Get authenticated Google Calendar service."""
        # Check if token needs refresh
        if integration.needs_refresh():
            if not self.refresh_access_token(integration):
                raise ValueError("Unable to refresh access token")
        
        credentials = Credentials(
            token=integration.access_token,
            refresh_token=integration.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret
        )
        
        return build('calendar', 'v3', credentials=credentials)
    
    def create_calendar_event(self, integration: GoogleCalendarIntegration, booking: Booking) -> Optional[str]:
        """Create a Google Calendar event for a booking."""
        try:
            service = self.get_calendar_service(integration)
            preferences = getattr(integration.user, 'calendar_sync_preferences', None)
            
            # Build event data
            event_data = self._build_event_data(booking, preferences)
            
            # Create the event
            start_time = timezone.now()
            event = service.events().insert(
                calendarId=integration.google_calendar_id,
                body=event_data
            ).execute()
            duration_ms = int((timezone.now() - start_time).total_seconds() * 1000)
            
            # Log successful creation
            GoogleCalendarSyncLog.objects.create(
                user=integration.user,
                booking=booking,
                google_event_id=event['id'],
                action='created',
                status='success',
                request_data=event_data,
                response_data={'event_id': event['id'], 'html_link': event.get('htmlLink')},
                duration_ms=duration_ms
            )
            
            logger.info(f"Created Google Calendar event {event['id']} for booking {booking.id}")
            return event['id']
            
        except HttpError as e:
            error_msg = f"Google API error: {e.resp.status} {e.content.decode()}"
            logger.error(f"Error creating calendar event for booking {booking.id}: {error_msg}")
            
            GoogleCalendarSyncLog.objects.create(
                user=integration.user,
                booking=booking,
                action='created',
                status='error',
                error_message=error_msg,
                request_data=event_data if 'event_data' in locals() else None
            )
            
            # Increment error count
            integration.sync_error_count += 1
            integration.last_error = error_msg
            integration.save()
            
            return None
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Unexpected error creating calendar event for booking {booking.id}: {error_msg}")
            
            GoogleCalendarSyncLog.objects.create(
                user=integration.user,
                booking=booking,
                action='created',
                status='error',
                error_message=error_msg
            )
            
            integration.sync_error_count += 1
            integration.last_error = error_msg
            integration.save()
            
            return None
    
    def update_calendar_event(self, integration: GoogleCalendarIntegration, booking: Booking, google_event_id: str) -> bool:
        """Update an existing Google Calendar event."""
        try:
            service = self.get_calendar_service(integration)
            preferences = getattr(integration.user, 'calendar_sync_preferences', None)
            
            # Build updated event data
            event_data = self._build_event_data(booking, preferences)
            
            # Update the event
            start_time = timezone.now()
            event = service.events().update(
                calendarId=integration.google_calendar_id,
                eventId=google_event_id,
                body=event_data
            ).execute()
            duration_ms = int((timezone.now() - start_time).total_seconds() * 1000)
            
            # Log successful update
            GoogleCalendarSyncLog.objects.create(
                user=integration.user,
                booking=booking,
                google_event_id=google_event_id,
                action='updated',
                status='success',
                request_data=event_data,
                response_data={'event_id': event['id'], 'html_link': event.get('htmlLink')},
                duration_ms=duration_ms
            )
            
            logger.info(f"Updated Google Calendar event {google_event_id} for booking {booking.id}")
            return True
            
        except HttpError as e:
            error_msg = f"Google API error: {e.resp.status} {e.content.decode()}"
            logger.error(f"Error updating calendar event {google_event_id}: {error_msg}")
            
            GoogleCalendarSyncLog.objects.create(
                user=integration.user,
                booking=booking,
                google_event_id=google_event_id,
                action='updated',
                status='error',
                error_message=error_msg
            )
            
            return False
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Unexpected error updating calendar event {google_event_id}: {error_msg}")
            
            GoogleCalendarSyncLog.objects.create(
                user=integration.user,
                booking=booking,
                google_event_id=google_event_id,
                action='updated',
                status='error',
                error_message=error_msg
            )
            
            return False
    
    def delete_calendar_event(self, integration: GoogleCalendarIntegration, google_event_id: str, booking: Booking = None) -> bool:
        """Delete a Google Calendar event."""
        try:
            service = self.get_calendar_service(integration)
            
            # Delete the event
            start_time = timezone.now()
            service.events().delete(
                calendarId=integration.google_calendar_id,
                eventId=google_event_id
            ).execute()
            duration_ms = int((timezone.now() - start_time).total_seconds() * 1000)
            
            # Log successful deletion
            GoogleCalendarSyncLog.objects.create(
                user=integration.user,
                booking=booking,
                google_event_id=google_event_id,
                action='deleted',
                status='success',
                duration_ms=duration_ms
            )
            
            logger.info(f"Deleted Google Calendar event {google_event_id}")
            return True
            
        except HttpError as e:
            error_msg = f"Google API error: {e.resp.status} {e.content.decode()}"
            logger.error(f"Error deleting calendar event {google_event_id}: {error_msg}")
            
            GoogleCalendarSyncLog.objects.create(
                user=integration.user,
                booking=booking,
                google_event_id=google_event_id,
                action='deleted',
                status='error',
                error_message=error_msg
            )
            
            return False
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Unexpected error deleting calendar event {google_event_id}: {error_msg}")
            
            GoogleCalendarSyncLog.objects.create(
                user=integration.user,
                booking=booking,
                google_event_id=google_event_id,
                action='deleted',
                status='error',
                error_message=error_msg
            )
            
            return False
    
    def _build_event_data(self, booking: Booking, preferences: CalendarSyncPreferences = None) -> dict:
        """Build Google Calendar event data from booking."""
        # Build title
        title_parts = []
        if preferences and preferences.event_prefix:
            title_parts.append(preferences.event_prefix.strip())
        
        title_parts.append(booking.title)
        
        if preferences and preferences.include_resource_in_title:
            title_parts.append(f"({booking.resource.name})")
        
        title = " ".join(title_parts)
        
        # Build description
        description_parts = []
        if preferences and preferences.include_description and booking.description:
            description_parts.append(booking.description)
        
        description_parts.extend([
            f"\nResource: {booking.resource.name}",
            f"Booked by: {booking.user.get_full_name() or booking.user.username}",
            f"Status: {booking.get_status_display()}",
            f"\nManaged by Labitory System"
        ])
        
        description = "\n".join(description_parts)
        
        # Build location
        location = ""
        if preferences and preferences.set_event_location:
            location = getattr(booking.resource, 'location', '') or booking.resource.name
        
        # Convert datetime to RFC3339 format
        start_time = booking.start_time.isoformat()
        end_time = booking.end_time.isoformat()
        
        return {
            'summary': title,
            'description': description,
            'location': location,
            'start': {
                'dateTime': start_time,
                'timeZone': str(booking.start_time.tzinfo) or 'UTC',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': str(booking.end_time.tzinfo) or 'UTC',
            },
            'reminders': {
                'useDefault': True,
            },
            'source': {
                'title': 'Labitory',
                'url': f"{settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else 'localhost'}/booking/{booking.id}/"
            }
        }
    
    def disconnect_integration(self, user: User) -> bool:
        """Disconnect Google Calendar integration for a user."""
        try:
            integration = GoogleCalendarIntegration.objects.get(user=user)
            
            # Revoke Google access token
            try:
                credentials = Credentials(
                    token=integration.access_token,
                    refresh_token=integration.refresh_token,
                    token_uri='https://oauth2.googleapis.com/token',
                    client_id=integration.client_id,
                    client_secret=integration.client_secret,
                )
                
                # Revoke the credentials
                credentials.revoke(Request())
                logger.info(f"Successfully revoked Google access token for user {user.id}")
                
            except Exception as revoke_error:
                logger.warning(f"Failed to revoke Google access token for user {user.id}: {revoke_error}")
                # Continue with deletion even if revocation fails
            
            # Delete the integration
            integration.delete()
            
            # Log disconnection
            GoogleCalendarSyncLog.objects.create(
                user=user,
                action='deleted',
                status='success',
                google_event_id='',
                response_data={'message': 'Integration disconnected by user'}
            )
            
            logger.info(f"Google Calendar integration disconnected for user {user.username}")
            return True
            
        except GoogleCalendarIntegration.DoesNotExist:
            logger.warning(f"No Google Calendar integration found for user {user.username}")
            return False
        except Exception as e:
            logger.error(f"Error disconnecting Google Calendar for user {user.username}: {e}")
            return False


# Global service instance
google_calendar_service = GoogleCalendarService() if GOOGLE_LIBRARIES_AVAILABLE else None