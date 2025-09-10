# booking/management/commands/cleanup_tokens.py
"""
Management command to clean up expired JWT tokens.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from ...models import APIToken


class Command(BaseCommand):
    help = 'Clean up expired JWT tokens from the database'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        
        parser.add_argument(
            '--days',
            type=int,
            default=0,
            help='Also delete revoked tokens older than X days (default: 0, only expired)',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        days_old = options['days']
        
        # Find expired tokens
        expired_tokens = APIToken.objects.filter(
            expires_at__lt=timezone.now()
        )
        
        expired_count = expired_tokens.count()
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'[DRY RUN] Would delete {expired_count} expired tokens')
            )
        else:
            expired_tokens.delete()
            self.stdout.write(
                self.style.SUCCESS(f'Deleted {expired_count} expired tokens')
            )
        
        # Also clean up old revoked tokens if requested
        if days_old > 0:
            cutoff_date = timezone.now() - timezone.timedelta(days=days_old)
            old_revoked_tokens = APIToken.objects.filter(
                is_revoked=True,
                revoked_at__lt=cutoff_date
            )
            
            revoked_count = old_revoked_tokens.count()
            
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(f'[DRY RUN] Would delete {revoked_count} old revoked tokens')
                )
            else:
                old_revoked_tokens.delete()
                self.stdout.write(
                    self.style.SUCCESS(f'Deleted {revoked_count} old revoked tokens')
                )
        
        # Show current token statistics
        total_tokens = APIToken.objects.count()
        active_tokens = APIToken.objects.filter(
            is_revoked=False,
            expires_at__gt=timezone.now()
        ).count()
        
        self.stdout.write(f'Current tokens: {total_tokens} total, {active_tokens} active')