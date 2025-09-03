# booking/management/commands/update_status.py
"""
Management command to show application update status.

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
from django.utils import timezone
from booking.update_service import UpdateService
from booking.models import UpdateHistory


class Command(BaseCommand):
    help = 'Show application update status and history'

    def add_arguments(self, parser):
        parser.add_argument(
            '--history',
            action='store_true',
            help='Show update history',
        )
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed status information',
        )

    def handle(self, *args, **options):
        update_service = UpdateService()
        status = update_service.get_update_status()
        
        # Basic status
        self.stdout.write(
            self.style.HTTP_INFO('📋 Application Update Status')
        )
        self.stdout.write('')
        
        self.stdout.write(f'Current Version: {status["current_version"]}')
        self.stdout.write(f'Latest Version: {status.get("latest_version", "Unknown")}')
        
        # Status indicator
        status_text = status['status'].replace('_', ' ').title()
        if status['status'] == 'up_to_date':
            status_color = self.style.SUCCESS
            status_icon = '✅'
        elif status['status'] == 'available':
            status_color = self.style.WARNING
            status_icon = '⚠️'
        elif status['status'] in ['downloading', 'installing']:
            status_color = self.style.HTTP_INFO
            status_icon = '🔄'
        elif status['status'] == 'failed':
            status_color = self.style.ERROR
            status_icon = '❌'
        else:
            status_color = self.style.NOTICE
            status_icon = 'ℹ️'
        
        self.stdout.write(f'Status: {status_icon} {status_color(status_text)}')
        
        if status['update_available']:
            self.stdout.write(
                self.style.WARNING('🔔 Update Available!')
            )
        
        if status.get('download_progress', 0) > 0:
            self.stdout.write(f'Download Progress: {status["download_progress"]}%')
        
        if status.get('error_message'):
            self.stdout.write('')
            self.stdout.write(
                self.style.ERROR(f'Error: {status["error_message"]}')
            )
        
        self.stdout.write(f'Last Check: {status["last_check"].strftime("%Y-%m-%d %H:%M:%S")}')
        
        # Detailed information
        if options['detailed']:
            self.stdout.write('')
            self.stdout.write('📝 Detailed Information:')
            self.stdout.write(f'  • Can Install: {status["can_install"]}')
            self.stdout.write(f'  • Auto Check: {status["auto_check_enabled"]}')
            
            if status.get('release_notes'):
                self.stdout.write('')
                self.stdout.write('📄 Release Notes:')
                self.stdout.write('-' * 50)
                self.stdout.write(status['release_notes'])
                self.stdout.write('-' * 50)
        
        # Update history
        if options['history']:
            self.stdout.write('')
            self.stdout.write('📚 Update History:')
            
            history = UpdateHistory.objects.all()[:10]
            if history:
                self.stdout.write('')
                for update in history:
                    result_icon = {
                        'success': '✅',
                        'failed': '❌',
                        'cancelled': '⚠️'
                    }.get(update.result, '❓')
                    
                    duration_str = ''
                    if update.duration:
                        duration_str = f' ({update.duration})'
                    
                    backup_str = ''
                    if update.backup_created:
                        backup_str = ' [Backup Created]'
                    
                    self.stdout.write(
                        f'  {result_icon} {update.from_version} → {update.to_version} '
                        f'({update.started_at.strftime("%Y-%m-%d %H:%M")}){duration_str}{backup_str}'
                    )
                    
                    if update.error_message:
                        self.stdout.write(f'     Error: {update.error_message}')
            else:
                self.stdout.write('  No update history found')
        
        self.stdout.write('')
        
        # Action suggestions
        if status['update_available'] and status['status'] == 'available':
            self.stdout.write(
                self.style.WARNING(
                    '💡 To download the update, run: python manage.py check_updates --download'
                )
            )
        elif status['can_install']:
            self.stdout.write(
                self.style.SUCCESS(
                    '💡 To install the update, run: python manage.py check_updates --install'
                )
            )