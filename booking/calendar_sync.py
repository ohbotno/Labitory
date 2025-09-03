# booking/calendar_sync.py
"""
Calendar synchronization utilities for external calendar integration.

This module provides functionality to export bookings as ICS (iCalendar) format
for integration with external calendar applications like Outlook, Google Calendar, etc.
"""

from datetime import datetime, timedelta
from django.http import HttpResponse
from django.utils import timezone
from django.urls import reverse
from django.contrib.sites.models import Site
import uuid
import hashlib


class ICSCalendarGenerator:
    """Generate ICS calendar feeds for bookings."""
    
    def __init__(self, request=None):
        self.request = request
        self.domain = self._get_domain()
    
    def _get_domain(self):
        """Get the current site domain."""
        if self.request:
            return self.request.build_absolute_uri('/')[:-1]  # Remove trailing slash
        try:
            site = Site.objects.get_current()
            return f"https://{site.domain}"
        except:
            return "https://labitory.local"
    
    def generate_user_calendar(self, user, include_past=False, days_ahead=90):
        """Generate ICS calendar for a specific user's bookings."""
        from .models import Booking
        
        # Get user's bookings
        bookings_qs = Booking.objects.filter(
            user=user,
            status__in=['confirmed', 'pending']
        ).select_related('resource').order_by('start_time')
        
        # Filter by date range
        now = timezone.now()
        if not include_past:
            bookings_qs = bookings_qs.filter(start_time__gte=now)
        
        end_date = now + timedelta(days=days_ahead)
        bookings_qs = bookings_qs.filter(start_time__lte=end_date)
        
        return self._generate_ics(bookings_qs, f"My Labitory Bookings - {user.get_full_name()}")
    
    def generate_resource_calendar(self, resource, days_ahead=90, include_maintenance=True):
        """Generate ICS calendar for a specific resource's bookings and maintenance."""
        from .models import Booking, Maintenance
        
        # Get resource's bookings
        now = timezone.now()
        end_date = now + timedelta(days=days_ahead)
        
        bookings_qs = Booking.objects.filter(
            resource=resource,
            status__in=['confirmed', 'pending'],
            start_time__gte=now,
            start_time__lte=end_date
        ).select_related('user').order_by('start_time')
        
        # Get maintenance periods if requested
        maintenance_qs = None
        if include_maintenance:
            maintenance_qs = Maintenance.objects.filter(
                resource=resource,
                start_time__gte=now,
                start_time__lte=end_date
            ).select_related('created_by').order_by('start_time')
        
        return self._generate_ics_with_maintenance(
            bookings_qs, 
            maintenance_qs, 
            f"{resource.name} - Labitory"
        )
    
    def _generate_ics(self, bookings_qs, calendar_name):
        """Generate the actual ICS content."""
        return self._generate_ics_with_maintenance(bookings_qs, None, calendar_name)
    
    def _generate_ics_with_maintenance(self, bookings_qs, maintenance_qs, calendar_name):
        """Generate ICS content with both bookings and maintenance."""
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Labitory//Calendar Sync//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:{calendar_name}",
            f"X-WR-CALDESC:Labitory System Calendar",
            "X-WR-TIMEZONE:UTC",
            "X-PUBLISHED-TTL:PT1H",  # Refresh every hour
        ]
        
        # Add booking events
        if bookings_qs:
            for booking in bookings_qs:
                lines.extend(self._booking_to_vevent(booking))
        
        # Add maintenance events
        if maintenance_qs:
            for maintenance in maintenance_qs:
                lines.extend(self._maintenance_to_vevent(maintenance))
        
        lines.append("END:VCALENDAR")
        
        return "\r\n".join(lines)
    
    def _booking_to_vevent(self, booking):
        """Convert a booking to VEVENT format."""
        # Generate unique UID
        uid = f"booking-{booking.id}@{self.domain.replace('https://', '').replace('http://', '')}"
        
        # Format dates in UTC
        start_utc = booking.start_time.astimezone(timezone.utc)
        end_utc = booking.end_time.astimezone(timezone.utc)
        
        # Format for ICS (YYYYMMDDTHHMMSSZ)
        start_str = start_utc.strftime("%Y%m%dT%H%M%SZ")
        end_str = end_utc.strftime("%Y%m%dT%H%M%SZ")
        
        # Create description
        description_parts = [
            f"Resource: {booking.resource.name}",
            f"Location: {booking.resource.location}",
            f"Status: {booking.get_status_display()}",
        ]
        
        if booking.description:
            description_parts.append(f"Notes: {booking.description}")
        
        if booking.attendees.exists():
            attendees = ", ".join([a.user.get_full_name() for a in booking.attendees.all()])
            description_parts.append(f"Attendees: {attendees}")
        
        description = "\\n".join(description_parts)
        
        # Escape special characters for ICS
        summary = self._escape_ics_text(booking.title)
        description = self._escape_ics_text(description)
        location = self._escape_ics_text(booking.resource.location)
        
        # Generate timestamp
        dtstamp = timezone.now().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        
        # Build VEVENT
        vevent = [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{start_str}",
            f"DTEND:{end_str}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            f"LOCATION:{location}",
            f"STATUS:{'CONFIRMED' if booking.status == 'confirmed' else 'TENTATIVE'}",
            "TRANSP:OPAQUE",
            "SEQUENCE:0",
        ]
        
        # Add URL to booking detail if possible
        if self.request:
            try:
                booking_url = self.request.build_absolute_uri(
                    reverse('booking:booking_detail', kwargs={'pk': booking.id})
                )
                vevent.append(f"URL:{booking_url}")
            except:
                pass
        
        # Add categories based on resource type
        if booking.resource.resource_type:
            vevent.append(f"CATEGORIES:{booking.resource.get_resource_type_display()}")
        
        # Add alarm for 15 minutes before
        vevent.extend([
            "BEGIN:VALARM",
            "TRIGGER:-PT15M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:Reminder: {summary}",
            "END:VALARM",
        ])
        
        vevent.append("END:VEVENT")
        
        return vevent
    
    def _maintenance_to_vevent(self, maintenance):
        """Convert a maintenance period to VEVENT format."""
        # Generate unique UID
        uid = f"maintenance-{maintenance.id}@{self.domain.replace('https://', '').replace('http://', '')}"
        
        # Format dates in UTC
        start_utc = maintenance.start_time.astimezone(timezone.utc)
        end_utc = maintenance.end_time.astimezone(timezone.utc)
        
        # Format for ICS (YYYYMMDDTHHMMSSZ)
        start_str = start_utc.strftime("%Y%m%dT%H%M%SZ")
        end_str = end_utc.strftime("%Y%m%dT%H%M%SZ")
        
        # Create description
        description_parts = [
            f"Resource: {maintenance.resource.name}",
            f"Location: {maintenance.resource.location}",
            f"Type: {maintenance.get_maintenance_type_display()}",
            f"Created by: {maintenance.created_by.get_full_name()}",
        ]
        
        if maintenance.description:
            description_parts.append(f"Details: {maintenance.description}")
        
        if maintenance.blocks_booking:
            description_parts.append("⚠️ This maintenance period blocks new bookings")
        
        if maintenance.is_recurring:
            description_parts.append("🔄 Recurring maintenance")
        
        description = "\\n".join(description_parts)
        
        # Escape special characters for ICS
        summary = self._escape_ics_text(f"🔧 {maintenance.title}")
        description = self._escape_ics_text(description)
        location = self._escape_ics_text(maintenance.resource.location)
        
        # Generate timestamp
        dtstamp = timezone.now().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        
        # Build VEVENT
        vevent = [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{start_str}",
            f"DTEND:{end_str}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            f"LOCATION:{location}",
            "STATUS:CONFIRMED",
            "TRANSP:OPAQUE",
            "SEQUENCE:0",
        ]
        
        # Add URL to maintenance detail if possible
        if self.request:
            try:
                maintenance_url = self.request.build_absolute_uri(
                    f"/lab-admin/maintenance/{maintenance.id}/"
                )
                vevent.append(f"URL:{maintenance_url}")
            except:
                pass
        
        # Add categories for maintenance
        vevent.append(f"CATEGORIES:Maintenance,{maintenance.maintenance_type.title()}")
        
        # Add alarm for maintenance (30 minutes before for staff)
        vevent.extend([
            "BEGIN:VALARM",
            "TRIGGER:-PT30M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:Maintenance starting: {maintenance.title}",
            "END:VALARM",
        ])
        
        vevent.append("END:VEVENT")
        
        return vevent
    
    def _escape_ics_text(self, text):
        """Escape special characters for ICS format."""
        if not text:
            return ""
        
        # Replace problematic characters
        text = str(text)
        text = text.replace("\\", "\\\\")
        text = text.replace(",", "\\,")
        text = text.replace(";", "\\;")
        text = text.replace("\n", "\\n")
        text = text.replace("\r", "")
        
        return text
    
    def generate_booking_invitation(self, booking, method="REQUEST"):
        """Generate an ICS invitation for a single booking."""
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Labitory//Calendar Invitation//EN",
            "CALSCALE:GREGORIAN",
            f"METHOD:{method}",
            f"X-WR-CALNAME:Booking Invitation - {booking.title}",
        ]
        
        # Add the booking event
        lines.extend(self._booking_to_vevent(booking))
        lines.append("END:VCALENDAR")
        
        return "\r\n".join(lines)
    
    def generate_maintenance_invitation(self, maintenance, method="REQUEST"):
        """Generate an ICS invitation for a single maintenance period."""
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Labitory//Maintenance Invitation//EN"
            "CALSCALE:GREGORIAN",
            f"METHOD:{method}",
            f"X-WR-CALNAME:Maintenance Notification - {maintenance.title}",
        ]
        
        # Add the maintenance event
        lines.extend(self._maintenance_to_vevent(maintenance))
        lines.append("END:VCALENDAR")
        
        return "\r\n".join(lines)


class CalendarTokenGenerator:
    """Generate secure tokens for calendar subscriptions."""
    
    @staticmethod
    def generate_user_token(user):
        """Generate a secure token for a user's calendar feed."""
        # Create a hash based on user ID, username, and a secret
        secret_string = f"{user.id}-{user.username}-{user.date_joined}-labitory-calendar"
        return hashlib.sha256(secret_string.encode()).hexdigest()[:32]
    
    @staticmethod
    def verify_user_token(user, token):
        """Verify a calendar token for a user."""
        expected_token = CalendarTokenGenerator.generate_user_token(user)
        return token == expected_token
    
    @staticmethod
    def generate_resource_token(resource):
        """Generate a secure token for a resource's calendar feed."""
        secret_string = f"{resource.id}-{resource.name}-{resource.created_at}-labitory-resource"
        return hashlib.sha256(secret_string.encode()).hexdigest()[:32]
    
    @staticmethod
    def verify_resource_token(resource, token):
        """Verify a calendar token for a resource."""
        expected_token = CalendarTokenGenerator.generate_resource_token(resource)
        return token == expected_token


def create_ics_response(ics_content, filename="calendar.ics"):
    """Create an HTTP response with ICS content."""
    response = HttpResponse(ics_content, content_type='text/calendar; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'no-cache, must-revalidate'
    response['Pragma'] = 'no-cache'
    return response


def create_ics_feed_response(ics_content):
    """Create an HTTP response for calendar subscription feeds."""
    response = HttpResponse(ics_content, content_type='text/calendar; charset=utf-8')
    response['Cache-Control'] = 'public, max-age=3600'  # Cache for 1 hour
    response['Access-Control-Allow-Origin'] = '*'
    return response