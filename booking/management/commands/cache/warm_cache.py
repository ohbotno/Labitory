# booking/management/commands/cache/warm_cache.py
"""
Django management command to warm up application caches.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.cache import cache

from ....models import Resource
from ....signals.cache_signals import warm_common_caches
from ....utils.cache_utils import CacheWarmer


class Command(BaseCommand):
    help = 'Warm up application caches with commonly accessed data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--users',
            type=int,
            default=50,
            help='Number of recent users to warm (default: 50)'
        )
        parser.add_argument(
            '--resources',
            type=int,
            default=20,
            help='Number of resources to warm (default: 20)'
        )
        parser.add_argument(
            '--days-ahead',
            type=int,
            default=7,
            help='Number of days ahead to warm availability (default: 7)'
        )
        parser.add_argument(
            '--clear-first',
            action='store_true',
            help='Clear cache before warming'
        )

    def handle(self, *args, **options):
        """Execute the cache warming."""
        
        if options['clear_first']:
            self.stdout.write('🧹 Clearing cache before warming...')
            cache.clear()
            self.stdout.write(
                self.style.SUCCESS('✅ Cache cleared')
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'🔥 Starting cache warming process...'
            )
        )

        # Warm user permissions
        self.warm_user_permissions(options['users'])
        
        # Warm resource availability
        self.warm_resource_availability(options['resources'], options['days_ahead'])
        
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS('🎉 Cache warming completed successfully!')
        )

    def warm_user_permissions(self, user_limit: int):
        """Warm user permission caches."""
        self.stdout.write('')
        self.stdout.write('👥 Warming user permission caches...')
        
        try:
            # Get recent active users
            recent_users = User.objects.filter(
                is_active=True,
                last_login__gte=timezone.now() - timezone.timedelta(days=30)
            ).order_by('-last_login')[:user_limit]
            
            warmed_count = 0
            for user in recent_users:
                try:
                    CacheWarmer.warm_user_permissions(user.id)
                    warmed_count += 1
                    
                    if warmed_count % 10 == 0:
                        self.stdout.write(f'  📊 Warmed {warmed_count} users...')
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'  ⚠️  Failed to warm user {user.id}: {e}')
                    )
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ User permissions warmed for {warmed_count} users')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error warming user permissions: {e}')
            )

    def warm_resource_availability(self, resource_limit: int, days_ahead: int):
        """Warm resource availability caches."""
        self.stdout.write('')
        self.stdout.write('🏢 Warming resource availability caches...')
        
        try:
            # Get active resources
            active_resources = Resource.objects.filter(
                is_active=True
            ).order_by('-created_at')[:resource_limit]
            
            warmed_count = 0
            for resource in active_resources:
                try:
                    CacheWarmer.warm_resource_availability(resource.id, days_ahead)
                    warmed_count += 1
                    
                    if warmed_count % 5 == 0:
                        self.stdout.write(f'  📊 Warmed {warmed_count} resources...')
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'  ⚠️  Failed to warm resource {resource.id}: {e}')
                    )
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Resource availability warmed for {warmed_count} resources')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error warming resource availability: {e}')
            )