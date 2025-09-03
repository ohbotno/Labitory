# booking/management/commands/create_email_templates.py
"""
Management command to create default email templates.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

from django.core.management.base import BaseCommand
from booking.models import EmailTemplate


class Command(BaseCommand):
    help = 'Create default email templates for notifications'

    def handle(self, *args, **options):
        templates = [
            {
                'name': 'Booking Confirmed',
                'notification_type': 'booking_confirmed',
                'subject_template': 'Booking Confirmed: {{ booking.resource.name }}',
                'html_template': '''
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #28a745;">Booking Confirmed</h2>
                    
                    <p>Dear {{ user.first_name }},</p>
                    
                    <p>Your booking has been confirmed with the following details:</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">{{ booking.title }}</h3>
                        <p><strong>Resource:</strong> {{ booking.resource.name }}</p>
                        <p><strong>Date & Time:</strong> {{ booking.start_time|date:"F j, Y" }} from {{ booking.start_time|time:"g:i A" }} to {{ booking.end_time|time:"g:i A" }}</p>
                        <p><strong>Location:</strong> {{ booking.resource.location }}</p>
                        {% if booking.description %}
                        <p><strong>Description:</strong> {{ booking.description }}</p>
                        {% endif %}
                    </div>
                    
                    <p>Please arrive on time and follow all safety protocols.</p>
                    
                    <p>If you need to modify or cancel this booking, please log into the <a href="{{ site_url }}">Labitory</a>.</p>
                    
                    <p>Best regards,<br>
                    {{ site_name }} Team</p>
                </div>
                ''',
                'text_template': '''
                Booking Confirmed: {{ booking.resource.name }}
                
                Dear {{ user.first_name }},
                
                Your booking has been confirmed with the following details:
                
                Title: {{ booking.title }}
                Resource: {{ booking.resource.name }}
                Date & Time: {{ booking.start_time|date:"F j, Y" }} from {{ booking.start_time|time:"g:i A" }} to {{ booking.end_time|time:"g:i A" }}
                Location: {{ booking.resource.location }}
                {% if booking.description %}Description: {{ booking.description }}{% endif %}
                
                Please arrive on time and follow all safety protocols.
                
                If you need to modify or cancel this booking, please log into the Labitory at {{ site_url }}.
                
                Best regards,
                {{ site_name }} Team
                ''',
                'available_variables': [
                    'user.first_name', 'user.last_name', 'user.email',
                    'booking.title', 'booking.description', 'booking.start_time', 'booking.end_time',
                    'booking.resource.name', 'booking.resource.location',
                    'site_name', 'site_url'
                ]
            },
            {
                'name': 'Booking Cancelled',
                'notification_type': 'booking_cancelled',
                'subject_template': 'Booking Cancelled: {{ booking.resource.name }}',
                'html_template': '''
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #dc3545;">Booking Cancelled</h2>
                    
                    <p>Dear {{ user.first_name }},</p>
                    
                    <p>Your booking has been cancelled:</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">{{ booking.title }}</h3>
                        <p><strong>Resource:</strong> {{ booking.resource.name }}</p>
                        <p><strong>Date & Time:</strong> {{ booking.start_time|date:"F j, Y" }} from {{ booking.start_time|time:"g:i A" }} to {{ booking.end_time|time:"g:i A" }}</p>
                        {% if cancelled_by %}
                        <p><strong>Cancelled by:</strong> {{ cancelled_by }}</p>
                        {% endif %}
                    </div>
                    
                    <p>If you have any questions about this cancellation, please contact the lab management team.</p>
                    
                    <p>You can make a new booking anytime through the <a href="{{ site_url }}">Labitory</a>.</p>
                    
                    <p>Best regards,<br>
                    {{ site_name }} Team</p>
                </div>
                ''',
                'text_template': '''
                Booking Cancelled: {{ booking.resource.name }}
                
                Dear {{ user.first_name }},
                
                Your booking has been cancelled:
                
                Title: {{ booking.title }}
                Resource: {{ booking.resource.name }}
                Date & Time: {{ booking.start_time|date:"F j, Y" }} from {{ booking.start_time|time:"g:i A" }} to {{ booking.end_time|time:"g:i A" }}
                {% if cancelled_by %}Cancelled by: {{ cancelled_by }}{% endif %}
                
                If you have any questions about this cancellation, please contact the lab management team.
                
                You can make a new booking anytime through the Labitory at {{ site_url }}.
                
                Best regards,
                {{ site_name }} Team
                ''',
                'available_variables': [
                    'user.first_name', 'user.last_name', 'user.email',
                    'booking.title', 'booking.start_time', 'booking.end_time',
                    'booking.resource.name', 'cancelled_by',
                    'site_name', 'site_url'
                ]
            },
            {
                'name': 'Approval Request',
                'notification_type': 'approval_request',
                'subject_template': 'Approval Required: {{ booking.resource.name }}',
                'html_template': '''
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #ffc107;">Approval Required</h2>
                    
                    <p>Dear Lab Manager,</p>
                    
                    <p>A new booking requires your approval:</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">{{ booking.title }}</h3>
                        <p><strong>Requested by:</strong> {{ booking.user.get_full_name }} ({{ booking.user.email }})</p>
                        <p><strong>Resource:</strong> {{ booking.resource.name }}</p>
                        <p><strong>Date & Time:</strong> {{ booking.start_time|date:"F j, Y" }} from {{ booking.start_time|time:"g:i A" }} to {{ booking.end_time|time:"g:i A" }}</p>
                        {% if booking.description %}
                        <p><strong>Description:</strong> {{ booking.description }}</p>
                        {% endif %}
                    </div>
                    
                    <p>Please review and approve/reject this booking request in the <a href="{{ site_url }}/admin">Admin Panel</a>.</p>
                    
                    <p>Best regards,<br>
                    {{ site_name }} System</p>
                </div>
                ''',
                'text_template': '''
                Approval Required: {{ booking.resource.name }}
                
                Dear Lab Manager,
                
                A new booking requires your approval:
                
                Title: {{ booking.title }}
                Requested by: {{ booking.user.get_full_name }} ({{ booking.user.email }})
                Resource: {{ booking.resource.name }}
                Date & Time: {{ booking.start_time|date:"F j, Y" }} from {{ booking.start_time|time:"g:i A" }} to {{ booking.end_time|time:"g:i A" }}
                {% if booking.description %}Description: {{ booking.description }}{% endif %}
                
                Please review and approve/reject this booking request in the Admin Panel at {{ site_url }}/admin.
                
                Best regards,
                {{ site_name }} System
                ''',
                'available_variables': [
                    'booking.title', 'booking.description', 'booking.start_time', 'booking.end_time',
                    'booking.user.get_full_name', 'booking.user.email',
                    'booking.resource.name',
                    'site_name', 'site_url'
                ]
            },
            {
                'name': 'Maintenance Alert',
                'notification_type': 'maintenance_alert',
                'subject_template': 'Maintenance Scheduled: {{ maintenance.resource.name }}',
                'html_template': '''
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #fd7e14;">Maintenance Scheduled</h2>
                    
                    <p>Dear {{ user.first_name }},</p>
                    
                    <p>Maintenance has been scheduled for a resource you have bookings for:</p>
                    
                    <div style="background: #fff3cd; padding: 20px; border-radius: 5px; margin: 20px 0; border: 1px solid #ffeaa7;">
                        <h3 style="margin-top: 0;">{{ maintenance.title }}</h3>
                        <p><strong>Resource:</strong> {{ maintenance.resource.name }}</p>
                        <p><strong>Maintenance Period:</strong> {{ maintenance.start_time|date:"F j, Y g:i A" }} to {{ maintenance.end_time|date:"F j, Y g:i A" }}</p>
                        {% if maintenance.description %}
                        <p><strong>Details:</strong> {{ maintenance.description }}</p>
                        {% endif %}
                    </div>
                    
                    <p><strong>⚠️ Important:</strong> This maintenance may affect your upcoming bookings. Please check your bookings and reschedule if necessary.</p>
                    
                    <p>You can view and manage your bookings in the <a href="{{ site_url }}">Labitory</a>.</p>
                    
                    <p>If you have any questions, please contact the lab management team.</p>
                    
                    <p>Best regards,<br>
                    {{ site_name }} Team</p>
                </div>
                ''',
                'text_template': '''
                Maintenance Scheduled: {{ maintenance.resource.name }}
                
                Dear {{ user.first_name }},
                
                Maintenance has been scheduled for a resource you have bookings for:
                
                Title: {{ maintenance.title }}
                Resource: {{ maintenance.resource.name }}
                Maintenance Period: {{ maintenance.start_time|date:"F j, Y g:i A" }} to {{ maintenance.end_time|date:"F j, Y g:i A" }}
                {% if maintenance.description %}Details: {{ maintenance.description }}{% endif %}
                
                ⚠️ Important: This maintenance may affect your upcoming bookings. Please check your bookings and reschedule if necessary.
                
                You can view and manage your bookings in the Labitory at {{ site_url }}.
                
                If you have any questions, please contact the lab management team.
                
                Best regards,
                {{ site_name }} Team
                ''',
                'available_variables': [
                    'user.first_name', 'user.last_name',
                    'maintenance.title', 'maintenance.description', 'maintenance.start_time', 'maintenance.end_time',
                    'maintenance.resource.name',
                    'site_name', 'site_url'
                ]
            },
            {
                'name': 'Booking Reminder',
                'notification_type': 'booking_reminder',
                'subject_template': 'Reminder: Upcoming Booking - {{ booking.resource.name }}',
                'html_template': '''
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #17a2b8;">Booking Reminder</h2>
                    
                    <p>Dear {{ user.first_name }},</p>
                    
                    <p>This is a reminder about your upcoming booking:</p>
                    
                    <div style="background: #e7f3ff; padding: 20px; border-radius: 5px; margin: 20px 0; border: 1px solid #b3d7ff;">
                        <h3 style="margin-top: 0;">{{ booking.title }}</h3>
                        <p><strong>Resource:</strong> {{ booking.resource.name }}</p>
                        <p><strong>Date & Time:</strong> {{ booking.start_time|date:"F j, Y" }} from {{ booking.start_time|time:"g:i A" }} to {{ booking.end_time|time:"g:i A" }}</p>
                        <p><strong>Location:</strong> {{ booking.resource.location }}</p>
                        {% if hours_ahead %}
                        <p><strong>Starts in:</strong> {{ hours_ahead }} hours</p>
                        {% endif %}
                    </div>
                    
                    <p>📋 <strong>Before your session:</strong></p>
                    <ul>
                        <li>Review any safety protocols for {{ booking.resource.name }}</li>
                        <li>Gather any materials you need</li>
                        <li>Plan to arrive 5-10 minutes early</li>
                    </ul>
                    
                    <p>If you need to cancel or modify this booking, please do so through the <a href="{{ site_url }}">Labitory</a>.</p>
                    
                    <p>Best regards,<br>
                    {{ site_name }} Team</p>
                </div>
                ''',
                'text_template': '''
                Reminder: Upcoming Booking - {{ booking.resource.name }}
                
                Dear {{ user.first_name }},
                
                This is a reminder about your upcoming booking:
                
                Title: {{ booking.title }}
                Resource: {{ booking.resource.name }}
                Date & Time: {{ booking.start_time|date:"F j, Y" }} from {{ booking.start_time|time:"g:i A" }} to {{ booking.end_time|time:"g:i A" }}
                Location: {{ booking.resource.location }}
                {% if hours_ahead %}Starts in: {{ hours_ahead }} hours{% endif %}
                
                Before your session:
                - Review any safety protocols for {{ booking.resource.name }}
                - Gather any materials you need
                - Plan to arrive 5-10 minutes early
                
                If you need to cancel or modify this booking, please do so through the Labitory at {{ site_url }}.
                
                Best regards,
                {{ site_name }} Team
                ''',
                'available_variables': [
                    'user.first_name', 'user.last_name',
                    'booking.title', 'booking.start_time', 'booking.end_time',
                    'booking.resource.name', 'booking.resource.location',
                    'hours_ahead', 'site_name', 'site_url'
                ]
            }
        ]

        created_count = 0
        for template_data in templates:
            template, created = EmailTemplate.objects.get_or_create(
                name=template_data['name'],
                defaults=template_data
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created email template: {template.name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Email template already exists: {template.name}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created_count} email templates')
        )