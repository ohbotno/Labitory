# booking/management/commands/cleanup_backups.py
"""
Management command for cleaning up old backups.

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
from datetime import datetime, timedelta
import logging


class Command(BaseCommand):
    """
    Management command for cleaning up old backups.
    
    Usage:
        python manage.py cleanup_backups
        python manage.py cleanup_backups --days 7
        python manage.py cleanup_backups --dry-run
        python manage.py cleanup_backups --force
    """
    
    help = 'Clean up old backup files based on retention policy'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Override retention period (days). Uses system default if not specified.'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompts'
        )
        
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Minimize output (useful for cron jobs)'
        )
    
    def handle(self, *args, **options):
        """Execute the cleanup command."""
        from booking.backup_service import BackupService
        
        # Set up logging
        if options['quiet']:
            logging.getLogger().setLevel(logging.ERROR)
        else:
            logging.getLogger().setLevel(logging.INFO)
        
        backup_service = BackupService()
        
        # Override retention period if specified
        if options['days'] is not None:
            backup_service.max_backup_age_days = options['days']
        
        try:
            # Get backup information
            backups = backup_service.list_backups()
            stats = backup_service.get_backup_statistics()
            
            if not backups:
                if not options['quiet']:
                    self.stdout.write(self.style.WARNING("📦 No backups found."))
                return
            
            # Find old backups
            cutoff_date = datetime.now() - timedelta(days=backup_service.max_backup_age_days)
            old_backups = []
            
            for backup in backups:
                try:
                    backup_date = datetime.fromisoformat(backup['timestamp'].replace('Z', '+00:00'))
                    if backup_date.replace(tzinfo=None) < cutoff_date:
                        old_backups.append(backup)
                except (ValueError, TypeError):
                    # Skip backups with invalid timestamps
                    continue
            
            if not old_backups:
                if not options['quiet']:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✅ No backups older than {backup_service.max_backup_age_days} days found."
                        )
                    )
                return
            
            # Show what will be deleted
            if not options['quiet']:
                self.stdout.write(
                    self.style.WARNING(
                        f"🧹 Found {len(old_backups)} backup(s) older than {backup_service.max_backup_age_days} days:"
                    )
                )
                self.stdout.write("")
                
                total_size = 0
                for backup in old_backups:
                    size = backup.get('size', 0)
                    total_size += size
                    age_days = (datetime.now() - datetime.fromisoformat(backup['timestamp'].replace('Z', '+00:00')).replace(tzinfo=None)).days
                    
                    self.stdout.write(
                        f"  🗑️ {backup['backup_name']} "
                        f"({self.format_bytes(size)}, {age_days} days old)"
                    )
                
                self.stdout.write("")
                self.stdout.write(f"💾 Total space to be freed: {self.format_bytes(total_size)}")
                self.stdout.write("")
            
            # Dry run mode
            if options['dry_run']:
                self.stdout.write(self.style.WARNING("🔍 DRY RUN MODE - No files will be deleted"))
                return
            
            # Confirmation
            if not options['force'] and not options['quiet']:
                confirm = input(f"❓ Delete {len(old_backups)} old backup(s)? (y/N): ")
                if confirm.lower() not in ['y', 'yes']:
                    self.stdout.write(self.style.WARNING("❌ Cleanup cancelled."))
                    return
            
            # Perform cleanup
            if not options['quiet']:
                self.stdout.write(self.style.SUCCESS("🧹 Starting cleanup..."))
            
            result = backup_service.cleanup_old_backups()
            
            if result['success']:
                if not options['quiet']:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✅ Cleanup completed successfully!"
                        )
                    )
                    self.stdout.write(f"  📦 Deleted backups: {result['deleted_count']}")
                    
                    if result['deleted_backups']:
                        for backup_name in result['deleted_backups']:
                            self.stdout.write(f"    🗑️ {backup_name}")
                
                if result['errors']:
                    self.stdout.write(self.style.WARNING("⚠️ Some errors occurred:"))
                    for error in result['errors']:
                        self.stdout.write(f"    ❌ {error}")
                        
            else:
                error_msg = f"❌ Cleanup failed: {', '.join(result['errors'])}"
                self.stdout.write(self.style.ERROR(error_msg))
                raise CommandError("Cleanup operation failed")
                
        except Exception as e:
            error_msg = f"❌ Cleanup command failed: {str(e)}"
            self.stdout.write(self.style.ERROR(error_msg))
            raise CommandError(str(e))
    
    def format_bytes(self, bytes_count):
        """Format bytes into human-readable format."""
        if bytes_count == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_count < 1024.0:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024.0
        
        return f"{bytes_count:.1f} PB"