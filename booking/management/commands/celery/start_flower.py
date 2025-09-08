# booking/management/commands/celery/start_flower.py
"""
Django management command to start Flower monitoring for Celery.

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
    help = 'Start Flower monitoring and administration tool for Celery'

    def add_arguments(self, parser):
        parser.add_argument(
            '--port',
            type=int,
            default=5555,
            help='Port to run Flower on (default: 5555)'
        )
        parser.add_argument(
            '--address',
            default='127.0.0.1',
            help='Address to bind to (default: 127.0.0.1)'
        )
        parser.add_argument(
            '--url-prefix',
            default='',
            help='URL prefix for Flower (default: none)'
        )

    def handle(self, *args, **options):
        """Start Flower monitoring tool."""
        
        # Check if we're in the right directory
        manage_py_path = os.path.join(os.getcwd(), 'manage.py')
        if not os.path.exists(manage_py_path):
            raise CommandError("Must be run from the project root directory where manage.py is located")

        # Get broker URL from settings
        broker_url = getattr(settings, 'CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')

        # Build the flower command
        cmd = [
            sys.executable, '-m', 'flower',
            '--broker', broker_url,
            '--port', str(options['port']),
            '--address', options['address']
        ]

        if options['url_prefix']:
            cmd.extend(['--url_prefix', options['url_prefix']])

        # Add development-specific options
        if settings.DEBUG:
            self.stdout.write(
                self.style.WARNING(
                    '🚧 Running in development mode'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                '🌸 Starting Flower monitoring tool'
            )
        )
        self.stdout.write(f'🔗 Address: http://{options["address"]}:{options["port"]}')
        self.stdout.write(f'📡 Broker: {broker_url}')
        if options['url_prefix']:
            self.stdout.write(f'🔗 URL Prefix: {options["url_prefix"]}')
        self.stdout.write('')
        
        # Show the command being executed
        self.stdout.write(
            self.style.HTTP_INFO(f'Command: {" ".join(cmd)}')
        )
        self.stdout.write('')
        
        self.stdout.write(
            self.style.HTTP_SUCCESS(
                '💡 Open your browser and go to the address above to view Flower dashboard'
            )
        )
        self.stdout.write('')

        try:
            # Execute flower
            subprocess.run(cmd, check=True)
        except KeyboardInterrupt:
            self.stdout.write(
                self.style.SUCCESS('\n✋ Flower monitoring stopped by user')
            )
        except subprocess.CalledProcessError as e:
            raise CommandError(f'❌ Flower failed with exit code {e.returncode}')
        except FileNotFoundError:
            raise CommandError(
                '❌ Flower not found. Make sure it\'s installed: pip install flower'
            )