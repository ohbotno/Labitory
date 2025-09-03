# booking/management/commands/restore_backup.py
"""
Management command for restoring backups.

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
import secrets


class Command(BaseCommand):
    """
    Management command for restoring system backups.
    
    Usage:
        python manage.py restore_backup <backup_name>
        python manage.py restore_backup <backup_name> --database
        python manage.py restore_backup <backup_name> --media
        python manage.py restore_backup <backup_name> --database --media
        python manage.py restore_backup <backup_name> --all
        python manage.py restore_backup <backup_name> --force
        python manage.py restore_backup --list
    """
    
    help = 'Restore a system backup with specified components'
    
    def add_arguments(self, parser):
        parser.add_argument(
            'backup_name',
            nargs='?',
            type=str,
            help='Name of the backup to restore'
        )
        
        parser.add_argument(
            '--database',
            action='store_true',
            help='Restore database component'
        )
        
        parser.add_argument(
            '--media',
            action='store_true',
            help='Restore media files component'
        )
        
        parser.add_argument(
            '--configuration',
            action='store_true',
            help='Analyze configuration component (informational only)'
        )
        
        parser.add_argument(
            '--all',
            action='store_true',
            help='Restore all available components'
        )
        
        parser.add_argument(
            '--list',
            action='store_true',
            help='List available backups'
        )
        
        parser.add_argument(
            '--info',
            action='store_true',
            help='Show detailed information about the backup'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompts (DANGEROUS for database restoration)'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be restored without actually restoring'
        )
        
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Minimize output'
        )
    
    def handle(self, *args, **options):
        """Execute the restore command."""
        from booking.backup_service import BackupService
        
        # Set up logging
        if options['quiet']:
            logging.getLogger().setLevel(logging.ERROR)
        else:
            logging.getLogger().setLevel(logging.INFO)
        
        backup_service = BackupService()
        
        # List backups mode
        if options['list']:
            self.list_backups(backup_service)
            return
        
        # Validate backup name
        backup_name = options['backup_name']
        if not backup_name:
            raise CommandError("Backup name is required. Use --list to see available backups.")
        
        # Info mode
        if options['info']:
            self.show_backup_info(backup_service, backup_name)
            return
        
        # Determine components to restore
        restore_components = self.get_restore_components(options)
        
        if not any(restore_components.values()):
            raise CommandError(
                "No components specified for restoration. "
                "Use --database, --media, --configuration, or --all"
            )
        
        # Show restoration plan in dry-run mode
        if options['dry_run']:
            self.show_restore_plan(backup_service, backup_name, restore_components)
            return
        
        # Safety confirmation for database restoration
        if restore_components['database'] and not options['force']:
            if not self.confirm_database_restoration(backup_name):
                self.stdout.write(self.style.WARNING("❌ Restoration cancelled by user."))
                return
        
        # Execute restoration
        try:
            if not options['quiet']:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"🔄 Starting restoration of backup: {backup_name}"
                    )
                )
                self.stdout.write(f"⏰ Started at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Generate confirmation token for database restoration
            confirmation_token = None
            if restore_components['database']:
                confirmation_token = f"RESTORE_{backup_name}_{secrets.token_hex(8)}"
            
            result = backup_service.restore_backup(
                backup_name=backup_name,
                restore_components=restore_components,
                confirmation_token=confirmation_token
            )
            
            if result['success']:
                if not options['quiet']:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✅ Restoration completed successfully!"
                        )
                    )
                    self.show_restore_results(result)
                
            else:
                error_msg = f"❌ Restoration failed: {', '.join(result['errors'])}"
                self.stdout.write(self.style.ERROR(error_msg))
                
                if not options['quiet']:
                    self.show_error_details(result)
                
                raise CommandError("Restoration failed")
                
        except Exception as e:
            error_msg = f"❌ Restoration command failed: {str(e)}"
            self.stdout.write(self.style.ERROR(error_msg))
            raise CommandError(str(e))
    
    def list_backups(self, backup_service):
        """List available backups."""
        try:
            backups = backup_service.list_backups()
            
            if not backups:
                self.stdout.write(self.style.WARNING("📦 No backups found."))
                return
            
            self.stdout.write(self.style.HTTP_INFO(f"📦 Available Backups ({len(backups)} total):"))
            self.stdout.write("")
            
            for backup in backups:
                age_days = (datetime.now() - datetime.fromisoformat(backup['timestamp'].replace('Z', '+00:00')).replace(tzinfo=None)).days
                size = self.format_bytes(backup.get('size', 0))
                compressed = "🗜️" if backup.get('compressed', False) else "📁"
                
                self.stdout.write(
                    f"  {compressed} {backup['backup_name']}"
                )
                self.stdout.write(
                    f"      📅 {backup['timestamp'][:19]} ({age_days} days ago)"
                )
                self.stdout.write(
                    f"      📏 {size}"
                )
                if backup.get('description'):
                    self.stdout.write(f"      📝 {backup['description']}")
                self.stdout.write("")
                
        except Exception as e:
            raise CommandError(f"Failed to list backups: {str(e)}")
    
    def show_backup_info(self, backup_service, backup_name):
        """Show detailed backup information."""
        try:
            result = backup_service.get_backup_restoration_info(backup_name)
            
            if not result['success']:
                raise CommandError(result.get('error', 'Failed to get backup information'))
            
            backup_info = result['backup_info']
            components = result['available_components']
            details = result['component_details']
            warnings = result.get('warnings', [])
            
            self.stdout.write(self.style.HTTP_INFO(f"📦 Backup Information: {backup_name}"))
            self.stdout.write("")
            
            # Basic info
            self.stdout.write("📋 Basic Information:")
            self.stdout.write(f"  📅 Created: {backup_info['timestamp']}")
            self.stdout.write(f"  📏 Size: {self.format_bytes(backup_info['size'])}")
            self.stdout.write(f"  🗜️ Compressed: {'Yes' if backup_info.get('compressed') else 'No'}")
            if backup_info.get('description'):
                self.stdout.write(f"  📝 Description: {backup_info['description']}")
            self.stdout.write("")
            
            # Available components
            self.stdout.write("🔧 Available Components:")
            
            if components['database']:
                files = details.get('database', {}).get('files', [])
                primary = details.get('database', {}).get('primary_file', 'Unknown')
                self.stdout.write(f"  ✅ Database: {primary} ({len(files)} files)")
            else:
                self.stdout.write("  ❌ Database: Not available")
            
            if components['media']:
                count = details.get('media', {}).get('file_count', 0)
                self.stdout.write(f"  ✅ Media Files: {count} files")
            else:
                self.stdout.write("  ❌ Media Files: Not available")
            
            if components['configuration']:
                files = details.get('configuration', {}).get('files', [])
                self.stdout.write(f"  ✅ Configuration: {len(files)} files (analysis only)")
            else:
                self.stdout.write("  ❌ Configuration: Not available")
            
            self.stdout.write("")
            
            # Warnings
            if warnings:
                self.stdout.write(self.style.WARNING("⚠️ Important Warnings:"))
                for warning in warnings:
                    self.stdout.write(f"  • {warning}")
                self.stdout.write("")
            
        except Exception as e:
            raise CommandError(f"Failed to get backup information: {str(e)}")
    
    def get_restore_components(self, options):
        """Determine which components to restore based on options."""
        if options['all']:
            return {
                'database': True,
                'media': True,
                'configuration': True
            }
        
        return {
            'database': options['database'],
            'media': options['media'],
            'configuration': options['configuration']
        }
    
    def show_restore_plan(self, backup_service, backup_name, restore_components):
        """Show what the restoration would do (dry-run mode)."""
        try:
            result = backup_service.get_backup_restoration_info(backup_name)
            
            if not result['success']:
                raise CommandError(result.get('error', 'Failed to get backup information'))
            
            backup_info = result['backup_info']
            available_components = result['available_components']
            
            self.stdout.write(self.style.WARNING("🔍 DRY RUN MODE - No restoration will be performed"))
            self.stdout.write("")
            
            self.stdout.write(self.style.HTTP_INFO("Restoration Plan:"))
            self.stdout.write(f"  📦 Backup: {backup_name}")
            self.stdout.write(f"  📅 Created: {backup_info['timestamp']}")
            self.stdout.write(f"  📏 Size: {self.format_bytes(backup_info['size'])}")
            self.stdout.write("")
            
            self.stdout.write(self.style.HTTP_INFO("Components to restore:"))
            
            for component, requested in restore_components.items():
                if requested:
                    available = available_components.get(component, False)
                    status = "✅ Available" if available else "❌ Not available"
                    action = "Would restore" if available else "Cannot restore"
                    
                    self.stdout.write(f"  🔧 {component.title()}: {status} - {action}")
                    
                    if component == 'database' and available:
                        self.stdout.write("      ⚠️ Would overwrite current database")
                        self.stdout.write("      📋 Would create backup of current database first")
                    elif component == 'media' and available:
                        self.stdout.write("      ⚠️ Would replace current media files")
                        self.stdout.write("      📋 Would backup current media files first")
                    elif component == 'configuration' and available:
                        self.stdout.write("      ℹ️ Would analyze configuration files (no changes)")
            
            self.stdout.write("")
            
        except Exception as e:
            raise CommandError(f"Failed to create restoration plan: {str(e)}")
    
    def confirm_database_restoration(self, backup_name):
        """Get user confirmation for database restoration."""
        self.stdout.write("")
        self.stdout.write(self.style.ERROR("⚠️ CRITICAL WARNING: DATABASE RESTORATION"))
        self.stdout.write("")
        self.stdout.write(f"This will PERMANENTLY OVERWRITE your current database")
        self.stdout.write(f"with data from backup: {backup_name}")
        self.stdout.write("")
        self.stdout.write("Before proceeding:")
        self.stdout.write("• A backup of your current database will be created automatically")
        self.stdout.write("• All current data will be permanently replaced")
        self.stdout.write("• All users will be logged out")
        self.stdout.write("• This action cannot be undone")
        self.stdout.write("")
        
        try:
            confirmation = input("Type 'CONFIRM RESTORE' to proceed: ")
            return confirmation == 'CONFIRM RESTORE'
        except KeyboardInterrupt:
            self.stdout.write("")
            return False
    
    def show_restore_results(self, result):
        """Show detailed restoration results."""
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("📋 Restoration Results:"))
        self.stdout.write(f"  📦 Backup: {result['backup_name']}")
        self.stdout.write(f"  ⏰ Completed: {result['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write("")
        
        # Show component results
        for component, details in result.get('components_restored', {}).items():
            if details.get('success'):
                self.stdout.write(f"  ✅ {component.title()}: Success")
                
                if component == 'database':
                    if details.get('backup_created'):
                        self.stdout.write("      📋 Current database backed up before restoration")
                    restored_file = details.get('restored_file', '')
                    if restored_file:
                        self.stdout.write(f"      📄 Restored from: {restored_file}")
                        
                elif component == 'media':
                    count = details.get('restored_count', 0)
                    self.stdout.write(f"      📁 Restored {count} files")
                    if details.get('backup_created'):
                        self.stdout.write("      📋 Current media files backed up before restoration")
                        
                elif component == 'configuration':
                    files = details.get('files_found', [])
                    self.stdout.write(f"      📄 Analyzed {len(files)} configuration files")
                    
            else:
                self.stdout.write(f"  ❌ {component.title()}: Failed")
                for error in details.get('errors', []):
                    self.stdout.write(f"      ⚠️ {error}")
        
        # Show warnings
        warnings = result.get('warnings', [])
        if warnings:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("⚠️ Warnings:"))
            for warning in warnings:
                self.stdout.write(f"  • {warning}")
    
    def show_error_details(self, result):
        """Show detailed error information."""
        self.stdout.write("")
        self.stdout.write(self.style.ERROR("💥 Error Details:"))
        
        for error in result.get('errors', []):
            self.stdout.write(f"  ❌ {error}")
        
        # Show component-specific errors
        for component, details in result.get('components_restored', {}).items():
            if details.get('errors'):
                self.stdout.write(f"  📦 {component.title()} errors:")
                for error in details['errors']:
                    self.stdout.write(f"      ⚠️ {error}")
    
    def format_bytes(self, bytes_count):
        """Format bytes into human-readable format."""
        if bytes_count == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_count < 1024.0:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024.0
        
        return f"{bytes_count:.1f} PB"