# booking/management/commands/celery/start_worker.py
"""
Django management command to start a Celery worker.

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
    help = 'Start a Celery worker with appropriate configuration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--loglevel',
            default='info',
            help='Logging level (default: info)'
        )
        parser.add_argument(
            '--concurrency',
            type=int,
            default=2,
            help='Number of concurrent processes (default: 2)'
        )
        parser.add_argument(
            '--queues',
            default='celery,notifications,reports,maintenance',
            help='Comma-separated list of queues to listen to'
        )
        parser.add_argument(
            '--worker-name',
            default='worker1',
            help='Name for this worker (default: worker1)'
        )

    def handle(self, *args, **options):
        """Start the Celery worker."""
        
        # Check if we're in the right directory
        manage_py_path = os.path.join(os.getcwd(), 'manage.py')
        if not os.path.exists(manage_py_path):
            raise CommandError("Must be run from the project root directory where manage.py is located")

        # Build the celery command
        cmd = [
            sys.executable, '-m', 'celery',
            '-A', 'labitory',
            'worker',
            '--loglevel', options['loglevel'],
            '--concurrency', str(options['concurrency']),
            '--queues', options['queues'],
            '--hostname', f"{options['worker_name']}@%h"
        ]

        # Add development-specific options
        if settings.DEBUG:
            self.stdout.write(
                self.style.WARNING(
                    '🚧 Running in development mode - using development settings'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'🚀 Starting Celery worker: {options["worker_name"]}'
            )
        )
        self.stdout.write(f'📋 Queues: {options["queues"]}')
        self.stdout.write(f'⚡ Concurrency: {options["concurrency"]}')
        self.stdout.write(f'📊 Log level: {options["loglevel"]}')
        self.stdout.write('')
        
        # Show the command being executed
        self.stdout.write(
            self.style.HTTP_INFO(f'Command: {" ".join(cmd)}')
        )
        self.stdout.write('')

        try:
            # Execute the celery worker
            subprocess.run(cmd, check=True)
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.SUCCESS('\n✋ Worker stopped by user')
            )
        except subprocess.CalledProcessError as e:
            raise CommandError(f'❌ Celery worker failed with exit code {e.returncode}')
        except FileNotFoundError:
            raise CommandError(
                '❌ Celery not found. Make sure it\'s installed: pip install celery[redis]'
            )