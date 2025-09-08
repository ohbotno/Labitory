# booking/management/commands/cache/cache_status.py
"""
Django management command to show cache status and statistics.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

from django.core.management.base import BaseCommand
from django.core.cache import cache
from django.conf import settings

from ....utils.cache_utils import get_cache_stats


class Command(BaseCommand):
    help = 'Show cache status and statistics'

    def add_arguments(self, parser):
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed cache information'
        )

    def handle(self, *args, **options):
        """Show cache status."""
        
        self.stdout.write(
            self.style.SUCCESS('📊 Cache Status Report')
        )
        self.stdout.write('=' * 50)
        
        # Basic cache configuration
        self.show_cache_config()
        
        # Cache statistics
        self.show_cache_stats()
        
        # Test cache connectivity
        self.test_cache_connectivity()
        
        if options['detailed']:
            self.show_detailed_info()

    def show_cache_config(self):
        """Display cache configuration."""
        self.stdout.write('')
        self.stdout.write('🔧 Cache Configuration:')
        
        try:
            cache_config = settings.CACHES.get('default', {})
            backend = cache_config.get('BACKEND', 'Unknown')
            location = cache_config.get('LOCATION', 'Not specified')
            
            self.stdout.write(f'  Backend: {backend}')
            self.stdout.write(f'  Location: {location}')
            
            if 'TIMEOUT' in cache_config:
                self.stdout.write(f'  Default Timeout: {cache_config["TIMEOUT"]}s')
                
            if 'OPTIONS' in cache_config:
                options = cache_config['OPTIONS']
                if options:
                    self.stdout.write('  Options:')
                    for key, value in options.items():
                        self.stdout.write(f'    {key}: {value}')
                        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  ❌ Error reading cache config: {e}')
            )

    def show_cache_stats(self):
        """Display cache statistics."""
        self.stdout.write('')
        self.stdout.write('📈 Cache Statistics:')
        
        try:
            stats = get_cache_stats()
            
            self.stdout.write(f'  Status: {stats.get("status", "unknown")}')
            
            if stats.get('keys_count'):
                self.stdout.write(f'  Keys Count: {stats["keys_count"]}')
                
            if stats.get('memory_usage'):
                self.stdout.write(f'  Memory Usage: {stats["memory_usage"]}')
                
            if stats.get('error'):
                self.stdout.write(
                    self.style.WARNING(f'  ⚠️  Error: {stats["error"]}')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  ❌ Error retrieving cache stats: {e}')
            )

    def test_cache_connectivity(self):
        """Test cache connectivity."""
        self.stdout.write('')
        self.stdout.write('🔍 Cache Connectivity Test:')
        
        try:
            # Test basic cache operations
            test_key = 'cache_status_test'
            test_value = 'test_value_123'
            
            # Set value
            cache.set(test_key, test_value, timeout=60)
            
            # Get value
            retrieved_value = cache.get(test_key)
            
            if retrieved_value == test_value:
                self.stdout.write(
                    self.style.SUCCESS('  ✅ Cache read/write test passed')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('  ❌ Cache read/write test failed')
                )
            
            # Clean up
            cache.delete(test_key)
            
            # Test cache deletion
            if cache.get(test_key) is None:
                self.stdout.write(
                    self.style.SUCCESS('  ✅ Cache deletion test passed')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('  ⚠️  Cache deletion test failed')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  ❌ Cache connectivity test failed: {e}')
            )

    def show_detailed_info(self):
        """Show detailed cache information."""
        self.stdout.write('')
        self.stdout.write('📋 Detailed Information:')
        
        try:
            # Show cache key patterns (if Redis)
            backend = settings.CACHES.get('default', {}).get('BACKEND', '')
            
            if 'redis' in backend.lower():
                self.stdout.write('  Redis-specific information:')
                self.stdout.write('    • Supports key patterns and expiration')
                self.stdout.write('    • Memory-based storage')
                self.stdout.write('    • Atomic operations available')
            elif 'locmem' in backend.lower():
                self.stdout.write('  Local memory cache information:')
                self.stdout.write('    • Process-specific storage')
                self.stdout.write('    • Does not persist between restarts')
                self.stdout.write('    • Limited to single server instance')
            elif 'database' in backend.lower():
                self.stdout.write('  Database cache information:')
                self.stdout.write('    • Persistent storage')
                self.stdout.write('    • Shared across multiple servers')
                self.stdout.write('    • May be slower than Redis')
                
            # Show environment-specific info
            debug_mode = getattr(settings, 'DEBUG', False)
            self.stdout.write(f'  Debug Mode: {debug_mode}')
            
            # Cache-related middleware
            middleware = getattr(settings, 'MIDDLEWARE', [])
            cache_middleware = [mw for mw in middleware if 'cache' in mw.lower()]
            
            if cache_middleware:
                self.stdout.write('  Cache Middleware:')
                for mw in cache_middleware:
                    self.stdout.write(f'    • {mw}')
            else:
                self.stdout.write('  No cache middleware detected')
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  ❌ Error showing detailed info: {e}')
            )