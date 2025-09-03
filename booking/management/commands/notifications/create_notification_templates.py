# booking/management/commands/create_notification_templates.py
"""
Create notification email templates for the Labitory system.

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
    """Create notification email templates."""
    
    help = 'Create notification email templates for the Labitory system'
    
    def handle(self, *args, **options):
        """Create the email templates."""
        templates = [
            {
                'notification_type': 'access_request_submitted',
                'name': 'Access Request Submitted',
                'subject_template': 'Access Request Submitted: {{ resource.name }}',
                'html_template': '''<p>Dear {{ user.get_full_name|default:user.username }},</p>
<p>Your access request for <strong>{{ resource.name }}</strong> has been submitted and is under review.</p>
<p>You will be notified once a decision has been made.</p>
<p>Best regards,<br>{{ site_name }} Team</p>''',
                'text_template': '''Dear {{ user.get_full_name|default:user.username }},

Your access request for {{ resource.name }} has been submitted and is under review.

You will be notified once a decision has been made.

Best regards,
{{ site_name }} Team''',
                'available_variables': 'user, resource, access_request, site_name, site_url'
            },
            {
                'notification_type': 'access_request_approved',
                'name': 'Access Request Approved',
                'subject_template': 'Access Granted: {{ resource.name }}',
                'html_template': '''<p>Dear {{ user.get_full_name|default:user.username }},</p>
<p>Great news! Your access request for <strong>{{ resource.name }}</strong> has been approved.</p>
<p>You can now view the calendar and book time slots for this resource.</p>
<p>Best regards,<br>{{ site_name }} Team</p>''',
                'text_template': '''Dear {{ user.get_full_name|default:user.username }},

Great news! Your access request for {{ resource.name }} has been approved.

You can now view the calendar and book time slots for this resource.

Best regards,
{{ site_name }} Team''',
                'available_variables': 'user, resource, access_request, site_name, site_url'
            },
            {
                'notification_type': 'access_request_rejected',
                'name': 'Access Request Rejected',
                'subject_template': 'Access Request Declined: {{ resource.name }}',
                'html_template': '''<p>Dear {{ user.get_full_name|default:user.username }},</p>
<p>Your access request for <strong>{{ resource.name }}</strong> has been declined.</p>
{% if access_request.review_notes %}<p><strong>Reason:</strong> {{ access_request.review_notes }}</p>{% endif %}
<p>Please contact the lab management team if you have questions.</p>
<p>Best regards,<br>{{ site_name }} Team</p>''',
                'text_template': '''Dear {{ user.get_full_name|default:user.username }},

Your access request for {{ resource.name }} has been declined.

{% if access_request.review_notes %}Reason: {{ access_request.review_notes }}{% endif %}

Please contact the lab management team if you have questions.

Best regards,
{{ site_name }} Team''',
                'available_variables': 'user, resource, access_request, site_name, site_url'
            },
            {
                'notification_type': 'training_request_submitted',
                'name': 'Training Request Submitted',
                'subject_template': 'Training Request Submitted: {{ resource.name }}',
                'html_template': '''<p>Dear {{ user.get_full_name|default:user.username }},</p>
<p>Your training request for <strong>{{ resource.name }}</strong> has been submitted.</p>
<p>You will be contacted with training schedule information.</p>
<p>Best regards,<br>{{ site_name }} Team</p>''',
                'text_template': '''Dear {{ user.get_full_name|default:user.username }},

Your training request for {{ resource.name }} has been submitted.

You will be contacted with training schedule information.

Best regards,
{{ site_name }} Team''',
                'available_variables': 'user, resource, training_request, site_name, site_url'
            },
            {
                'notification_type': 'training_request_scheduled',
                'name': 'Training Scheduled',
                'subject_template': 'Training Scheduled: {{ resource.name }}',
                'html_template': '''<p>Dear {{ user.get_full_name|default:user.username }},</p>
<p>Your training for <strong>{{ resource.name }}</strong> has been scheduled!</p>
{% if training_request.training_date %}<p><strong>Date:</strong> {{ training_request.training_date|date:"F d, Y" }} at {{ training_request.training_date|time:"g:i A" }}</p>{% endif %}
<p>Please arrive on time for your training session.</p>
<p>Best regards,<br>{{ site_name }} Team</p>''',
                'text_template': '''Dear {{ user.get_full_name|default:user.username }},

Your training for {{ resource.name }} has been scheduled!

{% if training_request.training_date %}Date: {{ training_request.training_date|date:"F d, Y" }} at {{ training_request.training_date|time:"g:i A" }}{% endif %}

Please arrive on time for your training session.

Best regards,
{{ site_name }} Team''',
                'available_variables': 'user, resource, training_request, site_name, site_url'
            },
            {
                'notification_type': 'training_request_completed',
                'name': 'Training Completed',
                'subject_template': 'Training Completed: {{ resource.name }}',
                'html_template': '''<p>Dear {{ user.get_full_name|default:user.username }},</p>
<p>Congratulations! You have successfully completed training for <strong>{{ resource.name }}</strong>.</p>
<p>You can now request access to this resource.</p>
<p>Best regards,<br>{{ site_name }} Team</p>''',
                'text_template': '''Dear {{ user.get_full_name|default:user.username }},

Congratulations! You have successfully completed training for {{ resource.name }}.

You can now request access to this resource.

Best regards,
{{ site_name }} Team''',
                'available_variables': 'user, resource, training_request, site_name, site_url'
            }
        ]
        
        created_count = 0
        updated_count = 0
        
        for template_data in templates:
            template, created = EmailTemplate.objects.update_or_create(
                notification_type=template_data['notification_type'],
                defaults={
                    'name': template_data['name'],
                    'subject_template': template_data['subject_template'],
                    'html_template': template_data['html_template'],
                    'text_template': template_data['text_template'],
                    'available_variables': template_data['available_variables'],
                    'is_active': True
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created template: {template.name}')
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f'Updated template: {template.name}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nSummary: {created_count} templates created, {updated_count} templates updated.'
            )
        )