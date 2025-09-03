# booking/management/commands/create_backup.py
"""
Management command for creating automated backups.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import datetime
import logging
import sys


class Command(BaseCommand):
    """
    Management command for creating system backups.
    
    Usage:
        python manage.py create_backup
        python manage.py create_backup --no-media
        python manage.py create_backup --description "Pre-update backup"
        python manage.py create_backup --cleanup-old
        python manage.py create_backup --quiet
    """
    
    help = 'Create a complete system backup including database, media files, and configuration'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--no-media',
            action='store_false',
            dest='include_media',
            default=True,
            help='Exclude media files from backup'
        )
        
        parser.add_argument(
            '--description',
            type=str,
            default='',
            help='Description for the backup'
        )
        
        parser.add_argument(
            '--cleanup-old',
            action='store_true',
            help='Clean up old backups after creating new one'
        )
        
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Minimize output (useful for cron jobs)'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually creating backup'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force backup creation even if another backup is in progress'
        )
    
    def handle(self, *args, **options):
        """Execute the backup command."""
        from booking.backup_service import BackupService
        
        # Set up logging
        if options['quiet']:
            logging.getLogger().setLevel(logging.ERROR)
        else:
            logging.getLogger().setLevel(logging.INFO)
        
        backup_service = BackupService()
        
        # Show configuration in dry-run mode
        if options['dry_run']:
            self.show_backup_plan(backup_service, options)
            return
        
        # Create backup
        try:
            if not options['quiet']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Starting backup creation at {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                )
            
            # Create the backup
            result = backup_service.create_full_backup(
                include_media=options['include_media'],
                description=options['description'] or f"Automated backup - {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            if result['success']:
                # Report success
                if not options['quiet']:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✅ Backup created successfully: {result['backup_name']}"
                        )
                    )
                    self.show_backup_details(result)
                
                # Cleanup old backups if requested
                if options['cleanup_old']:
                    self.cleanup_old_backups(backup_service, options['quiet'])
                
            else:
                # Report errors
                error_msg = f"❌ Backup failed: {', '.join(result['errors'])}"
                self.stdout.write(self.style.ERROR(error_msg))
                
                if not options['quiet']:
                    self.show_error_details(result)
                
                raise CommandError("Backup creation failed")
                
        except Exception as e:
            error_msg = f"❌ Backup command failed: {str(e)}"
            self.stdout.write(self.style.ERROR(error_msg))
            raise CommandError(str(e))
    
    def show_backup_plan(self, backup_service, options):
        """Show what the backup would include (dry-run mode)."""
        self.stdout.write(self.style.WARNING("🔍 DRY RUN MODE - No backup will be created"))
        self.stdout.write("")
        
        self.stdout.write(self.style.HTTP_INFO("Backup Configuration:"))
        self.stdout.write(f"  📁 Backup Directory: {backup_service.backup_dir}")
        self.stdout.write(f"  🗜️ Compression: {'Enabled' if backup_service.compression_enabled else 'Disabled'}")
        self.stdout.write(f"  📅 Retention Period: {backup_service.max_backup_age_days} days")
        self.stdout.write("")
        
        self.stdout.write(self.style.HTTP_INFO("Components to backup:"))
        self.stdout.write("  🗄️ Database: Yes")
        self.stdout.write(f"  📷 Media Files: {'Yes' if options['include_media'] else 'No'}")
        self.stdout.write("  ⚙️ Configuration: Yes")
        self.stdout.write("")
        
        if options['description']:
            self.stdout.write(f"📝 Description: {options['description']}")
        
        if options['cleanup_old']:
            stats = backup_service.get_backup_statistics()
            self.stdout.write(f"🧹 Would cleanup backups older than {backup_service.max_backup_age_days} days")
            self.stdout.write(f"   Current backup count: {stats.get('total_backups', 0)}")
    
    def show_backup_details(self, result):
        """Show detailed backup information."""
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Backup Details:"))
        self.stdout.write(f"  📦 Name: {result['backup_name']}")
        self.stdout.write(f"  📅 Created: {result['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"  📏 Size: {self.format_bytes(result['total_size'])}")
        
        if result.get('compressed'):
            self.stdout.write("  🗜️ Compressed: Yes")
        
        if result['description']:
            self.stdout.write(f"  📝 Description: {result['description']}")
        
        # Show component details
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Components:"))
        
        for component, details in result.get('components', {}).items():
            status = "✅" if details.get('success', False) else "❌"
            size = self.format_bytes(details.get('size', 0))
            self.stdout.write(f"  {status} {component.title()}: {size}")
            
            if details.get('errors'):
                for error in details['errors']:
                    self.stdout.write(f"      ⚠️ {error}")
    
    def show_error_details(self, result):
        """Show detailed error information."""
        self.stdout.write("")
        self.stdout.write(self.style.ERROR("Error Details:"))
        
        for error in result.get('errors', []):
            self.stdout.write(f"  ❌ {error}")
        
        # Show component-specific errors
        for component, details in result.get('components', {}).items():
            if details.get('errors'):
                self.stdout.write(f"  📦 {component.title()} errors:")
                for error in details['errors']:
                    self.stdout.write(f"      ⚠️ {error}")
    
    def cleanup_old_backups(self, backup_service, quiet=False):
        """Clean up old backups."""
        try:
            if not quiet:
                self.stdout.write("")
                self.stdout.write(self.style.WARNING("🧹 Cleaning up old backups..."))
            
            result = backup_service.cleanup_old_backups()
            
            if result['success']:
                if not quiet:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✅ Cleanup completed: {result['deleted_count']} old backups removed"
                        )
                    )
                    
                    if result['deleted_backups']:
                        self.stdout.write("  Deleted backups:")
                        for backup_name in result['deleted_backups']:
                            self.stdout.write(f"    🗑️ {backup_name}")
                
            else:
                self.stdout.write(self.style.ERROR("❌ Cleanup failed"))
                for error in result.get('errors', []):
                    self.stdout.write(f"    ⚠️ {error}")
                    
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Cleanup failed: {str(e)}"))
    
    def format_bytes(self, bytes_count):
        """Format bytes into human-readable format."""
        if bytes_count == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_count < 1024.0:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024.0
        
        return f"{bytes_count:.1f} PB"