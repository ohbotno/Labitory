# booking/management/commands/check_updates.py
"""
Management command to check for application updates.

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
from booking.update_service import UpdateService


class Command(BaseCommand):
    help = 'Check for application updates from GitHub releases'

    def add_arguments(self, parser):
        parser.add_argument(
            '--repo',
            type=str,
            help='GitHub repository (username/repo-name)',
        )
        parser.add_argument(
            '--download',
            action='store_true',
            help='Download update if available',
        )
        parser.add_argument(
            '--install',
            action='store_true',
            help='Install update if ready (implies --download)',
        )
        parser.add_argument(
            '--no-backup',
            action='store_true',
            help='Skip backup creation before install',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force download/install even if already up to date',
        )

    def handle(self, *args, **options):
        update_service = UpdateService()
        
        # Configure repository if specified
        if options['repo']:
            from booking.models import UpdateInfo
            update_info = UpdateInfo.get_instance()
            update_info.github_repo = options['repo']
            update_info.save()
            self.stdout.write(
                self.style.SUCCESS(f'Repository set to: {options["repo"]}')
            )
        
        # Check for updates
        self.stdout.write('Checking for updates...')
        result = update_service.check_for_updates()
        
        if not result['success']:
            self.stdout.write(
                self.style.ERROR(f'Failed to check for updates: {result["error"]}')
            )
            return
        
        if result['update_available']:
            self.stdout.write(
                self.style.WARNING(
                    f'Update available: {result["current_version"]} -> {result["latest_version"]}'
                )
            )
            
            if result.get('release_notes'):
                self.stdout.write('\nRelease Notes:')
                self.stdout.write('-' * 50)
                self.stdout.write(result['release_notes'])
                self.stdout.write('-' * 50)
            
            # Download if requested
            if options['download'] or options['install']:
                self.stdout.write('\nDownloading update...')
                download_result = update_service.download_update()
                
                if download_result['success']:
                    self.stdout.write(
                        self.style.SUCCESS('Update downloaded successfully')
                    )
                    
                    # Install if requested
                    if options['install']:
                        self.stdout.write('\nInstalling update...')
                        create_backup = not options['no_backup']
                        
                        if create_backup:
                            self.stdout.write('Creating backup before install...')
                        
                        install_result = update_service.install_update(
                            backup_before_update=create_backup
                        )
                        
                        if install_result['success']:
                            self.stdout.write(
                                self.style.SUCCESS('Update installed successfully!')
                            )
                            if install_result.get('backup_created'):
                                self.stdout.write(
                                    f'Backup created: {install_result["backup_path"]}'
                                )
                            self.stdout.write(
                                self.style.WARNING(
                                    'Please restart the application to complete the update.'
                                )
                            )
                        else:
                            self.stdout.write(
                                self.style.ERROR(
                                    f'Failed to install update: {install_result["error"]}'
                                )
                            )
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f'Failed to download update: {download_result["error"]}'
                        )
                    )
        
        elif options['force'] and (options['download'] or options['install']):
            self.stdout.write(
                self.style.WARNING('Forcing download/install even though up to date')
            )
            # Force operations would be implemented here
        
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Already up to date: {result["current_version"]}'
                )
            )