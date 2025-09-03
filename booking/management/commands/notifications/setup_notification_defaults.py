# booking/management/commands/setup_notification_defaults.py
"""
Setup default notification preferences for all users.

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
from django.contrib.auth.models import User
from booking.models import NotificationPreference
from booking.notifications import notification_service


class Command(BaseCommand):
    help = 'Setup default notification preferences for all users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            help='Setup preferences for specific user (username)'
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset existing preferences to defaults'
        )
        parser.add_argument(
            '--sms-enabled',
            action='store_true',
            help='Enable SMS notifications for emergency alerts by default'
        )
        parser.add_argument(
            '--push-enabled',
            action='store_true',
            default=True,
            help='Enable push notifications by default (default: True)'
        )

    def handle(self, *args, **options):
        self.stdout.write("🔔 Setting up notification preferences...")
        
        # Get users to process
        if options['user']:
            try:
                users = [User.objects.get(username=options['user'])]
                self.stdout.write(f"Processing user: {options['user']}")
            except User.DoesNotExist:
                self.stderr.write(f"User '{options['user']}' not found")
                return
        else:
            users = User.objects.all()
            self.stdout.write(f"Processing all {users.count()} users")
        
        # Get default preferences
        defaults = notification_service.default_preferences
        
        created_count = 0
        updated_count = 0
        
        for user in users:
            user_created = 0
            user_updated = 0
            
            for notification_type, delivery_prefs in defaults.items():
                for delivery_method, is_enabled in delivery_prefs.items():
                    
                    # Skip SMS unless explicitly enabled
                    if delivery_method == 'sms' and not options['sms_enabled']:
                        # Only enable SMS for emergency notifications
                        if notification_type not in ['emergency_alert', 'safety_alert', 'evacuation_notice']:
                            is_enabled = False
                    
                    # Handle push notification preference
                    if delivery_method == 'push' and not options['push_enabled']:
                        is_enabled = False
                    
                    preference, created = NotificationPreference.objects.get_or_create(
                        user=user,
                        notification_type=notification_type,
                        delivery_method=delivery_method,
                        defaults={
                            'is_enabled': is_enabled,
                            'frequency': 'immediate'
                        }
                    )
                    
                    if created:
                        user_created += 1
                        created_count += 1
                    elif options['reset'] and preference.is_enabled != is_enabled:
                        preference.is_enabled = is_enabled
                        preference.save()
                        user_updated += 1
                        updated_count += 1
            
            if user_created > 0 or user_updated > 0:
                self.stdout.write(
                    f"  {user.username}: {user_created} created, {user_updated} updated"
                )
        
        self.stdout.write("\n📊 Summary:")
        self.stdout.write(f"✓ Total preferences created: {created_count}")
        self.stdout.write(f"✓ Total preferences updated: {updated_count}")
        self.stdout.write(f"✓ Users processed: {len(users)}")
        
        # Show configuration summary
        self.stdout.write("\n⚙️ Configuration Applied:")
        self.stdout.write(f"  📧 Email: Enabled for most notifications")
        self.stdout.write(f"  📱 In-App: Enabled for most notifications")
        self.stdout.write(f"  🔔 Push: {'Enabled' if options['push_enabled'] else 'Disabled'} by default")
        self.stdout.write(f"  💬 SMS: {'Enabled for emergencies' if options['sms_enabled'] else 'Disabled'} by default")
        
        # Show notification types
        self.stdout.write(f"\n📋 Notification Types Configured: {len(defaults)}")
        for notif_type in sorted(defaults.keys()):
            self.stdout.write(f"  - {notif_type}")
        
        self.stdout.write("\n🎉 Default notification preferences setup completed!")
        
        # Suggest next steps
        self.stdout.write("\n💡 Next Steps:")
        self.stdout.write("  1. Configure TWILIO_* environment variables for SMS")
        self.stdout.write("  2. Configure VAPID_* environment variables for Push")
        self.stdout.write("  3. Create email templates: python manage.py create_notification_templates")
        self.stdout.write("  4. Test notifications: python manage.py test_notifications")