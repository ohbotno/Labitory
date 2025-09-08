# booking/management/commands/celery/start_beat.py
"""
Django management command to start Celery Beat scheduler.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import os
import subprocess
import sys
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


class Command(BaseCommand):
    help = 'Start Celery Beat scheduler for periodic tasks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--loglevel',
            default='info',
            help='Logging level (default: info)'
        )
        parser.add_argument(
            '--schedule-file',
            default='celerybeat-schedule',
            help='Path to schedule database file'
        )

    def handle(self, *args, **options):
        """Start Celery Beat scheduler."""
        
        # Check if we're in the right directory
        manage_py_path = os.path.join(os.getcwd(), 'manage.py')
        if not os.path.exists(manage_py_path):
            raise CommandError("Must be run from the project root directory where manage.py is located")

        # Build the celery beat command
        cmd = [
            sys.executable, '-m', 'celery',
            '-A', 'labitory',
            'beat',
            '--loglevel', options['loglevel'],
            '--schedule', options['schedule_file']
        ]

        # Add development-specific options
        if settings.DEBUG:
            self.stdout.write(
                self.style.WARNING(
                    '🚧 Running in development mode - scheduled tasks will run!'
                )
            )
            self.stdout.write(
                self.style.HTTP_INFO(
                    '💡 Set CELERY_TASK_ALWAYS_EAGER=True in .env to run tasks synchronously'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                '⏰ Starting Celery Beat scheduler'
            )
        )
        self.stdout.write(f'📊 Log level: {options["loglevel"]}')
        self.stdout.write(f'🗂️  Schedule file: {options["schedule_file"]}')
        self.stdout.write('')
        
        # Show the command being executed
        self.stdout.write(
            self.style.HTTP_INFO(f'Command: {" ".join(cmd)}')
        )
        self.stdout.write('')

        try:
            # Execute celery beat
            subprocess.run(cmd, check=True)
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.SUCCESS('\n✋ Beat scheduler stopped by user')
            )
        except subprocess.CalledProcessError as e:
            raise CommandError(f'❌ Celery Beat failed with exit code {e.returncode}')
        except FileNotFoundError:
            raise CommandError(
                '❌ Celery not found. Make sure it\'s installed: pip install celery[redis]'
            )