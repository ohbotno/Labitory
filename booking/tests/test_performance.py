"""
Performance and Load Tests for Labitory Booking System

Tests system performance under various load conditions and identifies
performance bottlenecks in critical operations.
"""

import pytest
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.test import TestCase, TransactionTestCase
from django.test import Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import connections, transaction
from django.core.cache import cache
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, Mock

from booking.models.core import (
    UserProfile, LabSettings, Resource, Booking, 
    TrainingRecord, MaintenanceSchedule
)
from booking.models.approvals import ApprovalRule, ApprovalRequest
from booking.models.billing import BillingPeriod, BillingRate, ChargeRecord
from booking.models.notifications import Notification
from booking.tests.factories import (
    UserFactory, UserProfileFactory, ResourceFactory, 
    BookingFactory, ApprovalRuleFactory
)


class DatabasePerformanceTests(TransactionTestCase):
    """Test database query performance and optimization"""
    
    def setUp(self):
        self.lab_settings = LabSettings.objects.create(
            lab_name="Performance Test Lab",
            timezone='UTC'
        )
        
        # Create test data
        self.users = [UserProfileFactory() for _ in range(50)]
        self.resources = ResourceFactory.create_batch(10)
        
        # Clear cache to ensure fresh queries
        cache.clear()
    
    def test_booking_list_query_performance(self):
        """Test performance of booking list queries with large datasets"""
        
        # Create many bookings
        bookings = []
        for i in range(500):
            booking = BookingFactory(
                resource=self.resources[i % len(self.resources)],
                user=self.users[i % len(self.users)].user
            )
            bookings.append(booking)
        
        # Test query performance
        start_time = time.time()
        
        # Simulate typical booking list query with filters
        from django.db import connection
        with self.assertNumQueries(lambda: self.assertLess(len(connection.queries), 10)):
            # Should use select_related and prefetch_related for efficiency
            bookings_query = Booking.objects.select_related(
                'user', 'resource'
            ).prefetch_related(
                'user__userprofile'
            ).filter(
                status__in=['pending', 'approved', 'in_progress']
            )[:50]  # Paginated
            
            # Force evaluation
            list(bookings_query)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete quickly
        self.assertLess(execution_time, 1.0, 
            f"Booking list query took {execution_time:.3f}s, too slow")
    
    def test_conflict_detection_performance(self):
        """Test performance of booking conflict detection"""
        
        resource = self.resources[0]
        
        # Create many existing bookings
        existing_bookings = []
        for i in range(200):
            booking = BookingFactory(
                resource=resource,
                start_time=timezone.now() + timedelta(days=i, hours=1),
                end_time=timezone.now() + timedelta(days=i, hours=3),
                status='approved'
            )
            existing_bookings.append(booking)
        
        # Test conflict detection performance
        start_time = time.time()
        
        new_start = timezone.now() + timedelta(days=100, hours=2)
        new_end = timezone.now() + timedelta(days=100, hours=4)
        
        # Check for conflicts
        conflicts = Booking.objects.filter(
            resource=resource,
            status__in=['approved', 'in_progress'],
            start_time__lt=new_end,
            end_time__gt=new_start
        )
        
        # Force evaluation
        conflict_list = list(conflicts)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should be fast with proper indexing
        self.assertLess(execution_time, 0.1, 
            f"Conflict detection took {execution_time:.3f}s, too slow")
        
        # Should find the conflicting booking
        self.assertEqual(len(conflict_list), 1)
    
    def test_user_booking_history_performance(self):
        """Test performance of user booking history queries"""
        
        user = self.users[0]
        
        # Create many bookings for user
        for i in range(100):
            BookingFactory(
                user=user.user,
                resource=self.resources[i % len(self.resources)],
                start_time=timezone.now() - timedelta(days=i),
                end_time=timezone.now() - timedelta(days=i, hours=-2)
            )
        
        start_time = time.time()
        
        # Query user's booking history with proper optimization
        user_bookings = Booking.objects.filter(
            user=user.user
        ).select_related(
            'resource'
        ).order_by('-start_time')[:20]  # Recent bookings only
        
        # Force evaluation
        list(user_bookings)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should be fast
        self.assertLess(execution_time, 0.5, 
            f"User history query took {execution_time:.3f}s, too slow")
    
    def test_resource_utilization_calculation_performance(self):
        """Test performance of resource utilization calculations"""
        
        resource = self.resources[0]
        
        # Create bookings over time period
        for i in range(300):
            BookingFactory(
                resource=resource,
                start_time=timezone.now() - timedelta(days=30-i//10),
                end_time=timezone.now() - timedelta(days=30-i//10, hours=-2),
                status='completed'
            )
        
        start_time = time.time()
        
        # Calculate utilization for last 30 days
        thirty_days_ago = timezone.now() - timedelta(days=30)
        
        utilization_bookings = Booking.objects.filter(
            resource=resource,
            status='completed',
            start_time__gte=thirty_days_ago
        ).aggregate(
            total_hours=models.Sum(
                models.F('end_time') - models.F('start_time')
            )
        )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should be reasonably fast
        self.assertLess(execution_time, 0.5, 
            f"Utilization calculation took {execution_time:.3f}s, too slow")


class ConcurrentAccessTests(TransactionTestCase):
    """Test system behavior under concurrent access"""
    
    def setUp(self):
        self.resource = ResourceFactory(capacity=1)
        self.users = [UserProfileFactory() for _ in range(10)]
    
    def test_concurrent_booking_creation(self):
        """Test concurrent booking creation with race conditions"""
        
        booking_time_start = timezone.now() + timedelta(hours=1)
        booking_time_end = timezone.now() + timedelta(hours=3)
        
        results = []
        errors = []
        
        def create_booking(user_index):
            try:
                with transaction.atomic():
                    # Simulate race condition
                    time.sleep(0.01)  # Small delay to increase chance of conflict
                    
                    booking = Booking.objects.create(
                        resource=self.resource,
                        user=self.users[user_index].user,
                        title=f'Concurrent Booking {user_index}',
                        start_time=booking_time_start,
                        end_time=booking_time_end,
                        status='approved'
                    )
                    results.append(booking)
                    return True
            except Exception as e:
                errors.append(e)
                return False
        
        # Launch concurrent booking attempts
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for i in range(5):
                future = executor.submit(create_booking, i)
                futures.append(future)
            
            # Wait for all to complete
            for future in as_completed(futures):
                future.result()
        
        # Only one booking should succeed (resource capacity = 1)
        successful_bookings = len(results)
        self.assertEqual(successful_bookings, 1, 
            f"Expected 1 successful booking, got {successful_bookings}")
        
        # Others should fail with appropriate errors
        self.assertGreater(len(errors), 0, "Expected some booking attempts to fail")
    
    def test_concurrent_approval_processing(self):
        """Test concurrent approval processing"""
        
        # Create bookings requiring approval
        bookings = []
        approval_rules = []
        
        for i in range(5):
            booking = BookingFactory(
                resource=self.resource,
                user=self.users[i].user,
                status='pending'
            )
            bookings.append(booking)
            
            approval_rule = ApprovalRuleFactory(resource=self.resource)
            approval_rules.append(approval_rule)
            
            ApprovalRequest.objects.create(
                booking=booking,
                approval_rule=approval_rule,
                status='pending'
            )
        
        def process_approval(booking_index):
            try:
                with transaction.atomic():
                    approval_request = ApprovalRequest.objects.select_for_update().get(
                        booking=bookings[booking_index]
                    )
                    
                    # Simulate processing time
                    time.sleep(0.02)
                    
                    approval_request.status = 'approved'
                    approval_request.approved_by = self.users[0].user
                    approval_request.approved_at = timezone.now()
                    approval_request.save()
                    
                    return True
            except Exception as e:
                return False
        
        # Process approvals concurrently
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(process_approval, i) for i in range(5)]
            results = [future.result() for future in as_completed(futures)]
        
        # All approvals should succeed without conflicts
        successful_approvals = sum(results)
        self.assertEqual(successful_approvals, 5, "All approvals should succeed")
    
    def test_concurrent_user_registration(self):
        """Test concurrent user registration"""
        
        def create_user(user_index):
            try:
                user = User.objects.create_user(
                    username=f'concurrent_user_{user_index}',
                    email=f'user{user_index}@test.com',
                    password='testpass123'
                )
                
                profile = UserProfile.objects.create(
                    user=user,
                    role='student',
                    department='Test Department'
                )
                
                return True
            except Exception as e:
                return False
        
        # Create users concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_user, i) for i in range(20)]
            results = [future.result() for future in as_completed(futures)]
        
        # All user creations should succeed
        successful_registrations = sum(results)
        self.assertEqual(successful_registrations, 20, "All registrations should succeed")
        
        # Verify all users were created
        created_users = User.objects.filter(username__startswith='concurrent_user_').count()
        self.assertEqual(created_users, 20)


class LoadTestingTests(TransactionTestCase):
    """Test system behavior under high load"""
    
    def setUp(self):
        self.resources = ResourceFactory.create_batch(5)
        self.users = [UserProfileFactory() for _ in range(100)]
        
    def test_high_volume_booking_creation(self):
        """Test creating many bookings rapidly"""
        
        start_time = time.time()
        
        bookings_created = 0
        batch_size = 50
        
        # Create bookings in batches for better performance
        for batch in range(5):  # 250 total bookings
            batch_bookings = []
            
            for i in range(batch_size):
                booking = Booking(
                    resource=self.resources[i % len(self.resources)],
                    user=self.users[(batch * batch_size + i) % len(self.users)].user,
                    title=f'Load Test Booking {batch * batch_size + i}',
                    start_time=timezone.now() + timedelta(days=batch, hours=i),
                    end_time=timezone.now() + timedelta(days=batch, hours=i+2),
                    status='approved'
                )
                batch_bookings.append(booking)
            
            # Bulk create for performance
            Booking.objects.bulk_create(batch_bookings)
            bookings_created += len(batch_bookings)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should handle high volume efficiently
        self.assertEqual(bookings_created, 250)
        self.assertLess(execution_time, 5.0, 
            f"High volume booking creation took {execution_time:.3f}s, too slow")
        
        # Verify bookings were created
        created_count = Booking.objects.filter(title__startswith='Load Test Booking').count()
        self.assertEqual(created_count, 250)
    
    def test_bulk_notification_processing(self):
        """Test processing large numbers of notifications"""
        
        # Create many notifications
        notifications = []
        for i in range(1000):
            notification = Notification(
                user=self.users[i % len(self.users)].user,
                title=f'Load Test Notification {i}',
                message=f'This is test notification number {i}',
                notification_type='info'
            )
            notifications.append(notification)
        
        start_time = time.time()
        
        # Bulk create notifications
        Notification.objects.bulk_create(notifications)
        
        # Simulate processing (mark as sent)
        Notification.objects.filter(
            title__startswith='Load Test Notification'
        ).update(is_sent=True)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should handle bulk operations efficiently
        self.assertLess(execution_time, 2.0, 
            f"Bulk notification processing took {execution_time:.3f}s, too slow")
    
    def test_complex_query_performance(self):
        """Test performance of complex queries with joins"""
        
        # Create complex data relationships
        for i in range(100):
            user = self.users[i % len(self.users)]
            resource = self.resources[i % len(self.resources)]
            
            booking = BookingFactory(
                user=user.user,
                resource=resource,
                status='completed'
            )
            
            # Add billing records
            billing_rate = BillingRate.objects.create(
                resource=resource,
                user_type=user.role,
                hourly_rate=Decimal('25.00')
            )
            
            ChargeRecord.objects.create(
                booking=booking,
                billing_rate=billing_rate,
                hours_charged=Decimal('2.0'),
                amount_charged=Decimal('50.00')
            )
        
        start_time = time.time()
        
        # Complex query with multiple joins
        complex_query = ChargeRecord.objects.select_related(
            'booking',
            'booking__user',
            'booking__user__userprofile',
            'booking__resource',
            'billing_rate'
        ).filter(
            booking__status='completed',
            amount_charged__gt=Decimal('0.00')
        ).order_by('-booking__start_time')
        
        # Force evaluation
        results = list(complex_query)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should handle complex queries efficiently
        self.assertLess(execution_time, 1.0, 
            f"Complex query took {execution_time:.3f}s, too slow")
        
        self.assertGreater(len(results), 0, "Should return results")


class MemoryUsageTests(TestCase):
    """Test memory usage patterns"""
    
    def setUp(self):
        self.resources = ResourceFactory.create_batch(3)
        self.users = [UserProfileFactory() for _ in range(20)]
    
    def test_large_queryset_memory_usage(self):
        """Test memory usage when processing large querysets"""
        
        # Create many bookings
        for i in range(1000):
            BookingFactory(
                resource=self.resources[i % len(self.resources)],
                user=self.users[i % len(self.users)].user
            )
        
        # Process in chunks to avoid loading all into memory
        chunk_size = 100
        processed_count = 0
        
        # Use iterator() to avoid caching
        bookings_queryset = Booking.objects.all().iterator(chunk_size=chunk_size)
        
        for booking in bookings_queryset:
            # Simulate processing
            processed_count += 1
        
        self.assertEqual(processed_count, 1000, "Should process all bookings")
    
    def test_bulk_operations_memory_efficiency(self):
        """Test memory efficiency of bulk operations"""
        
        # Prepare large dataset for bulk operations
        bookings_to_update = []
        for i in range(500):
            booking = BookingFactory(
                resource=self.resources[i % len(self.resources)],
                user=self.users[i % len(self.users)].user,
                status='pending'
            )
            bookings_to_update.append(booking.id)
        
        # Bulk update status
        updated_count = Booking.objects.filter(
            id__in=bookings_to_update
        ).update(status='approved')
        
        self.assertEqual(updated_count, 500, "Should update all bookings")


class CachePerformanceTests(TestCase):
    """Test caching performance and efficiency"""
    
    def setUp(self):
        self.resource = ResourceFactory()
        self.users = [UserProfileFactory() for _ in range(10)]
        
        # Clear cache
        cache.clear()
    
    def test_resource_availability_caching(self):
        """Test caching of resource availability calculations"""
        
        # Create some bookings
        for i in range(20):
            BookingFactory(
                resource=self.resource,
                user=self.users[i % len(self.users)].user,
                start_time=timezone.now() + timedelta(days=i, hours=1),
                end_time=timezone.now() + timedelta(days=i, hours=3),
                status='approved'
            )
        
        # First call - should hit database
        start_time = time.time()
        
        cache_key = f'resource_availability_{self.resource.id}'
        availability = cache.get(cache_key)
        
        if availability is None:
            # Simulate availability calculation
            upcoming_bookings = Booking.objects.filter(
                resource=self.resource,
                start_time__gte=timezone.now(),
                status__in=['approved', 'in_progress']
            ).count()
            
            availability = {
                'upcoming_bookings': upcoming_bookings,
                'calculated_at': timezone.now().isoformat()
            }
            
            # Cache for 5 minutes
            cache.set(cache_key, availability, 300)
        
        first_call_time = time.time() - start_time
        
        # Second call - should use cache
        start_time = time.time()
        
        cached_availability = cache.get(cache_key)
        
        second_call_time = time.time() - start_time
        
        # Cache should be much faster
        self.assertIsNotNone(cached_availability)
        self.assertLess(second_call_time, first_call_time / 10, 
            "Cache should be significantly faster")
    
    def test_user_booking_summary_caching(self):
        """Test caching of user booking summaries"""
        
        user = self.users[0]
        
        # Create user's bookings
        for i in range(30):
            BookingFactory(
                user=user.user,
                resource=self.resources[i % len(self.resources)],
                status='completed' if i < 20 else 'pending'
            )
        
        def get_user_booking_summary(user_id):
            cache_key = f'user_booking_summary_{user_id}'
            summary = cache.get(cache_key)
            
            if summary is None:
                summary = {
                    'total_bookings': Booking.objects.filter(user_id=user_id).count(),
                    'completed_bookings': Booking.objects.filter(
                        user_id=user_id, status='completed'
                    ).count(),
                    'pending_bookings': Booking.objects.filter(
                        user_id=user_id, status='pending'
                    ).count(),
                }
                
                cache.set(cache_key, summary, 600)  # Cache for 10 minutes
            
            return summary
        
        # First call
        start_time = time.time()
        summary1 = get_user_booking_summary(user.user.id)
        first_call_time = time.time() - start_time
        
        # Second call (cached)
        start_time = time.time()
        summary2 = get_user_booking_summary(user.user.id)
        second_call_time = time.time() - start_time
        
        # Verify results
        self.assertEqual(summary1['total_bookings'], 30)
        self.assertEqual(summary1['completed_bookings'], 20)
        self.assertEqual(summary1['pending_bookings'], 10)
        
        # Results should be identical
        self.assertEqual(summary1, summary2)
        
        # Cache should be faster
        self.assertLess(second_call_time, first_call_time / 5)


@pytest.mark.slow
class StressTests(TransactionTestCase):
    """Stress tests for system limits"""
    
    def test_maximum_concurrent_bookings(self):
        """Test system behavior at maximum concurrent booking capacity"""
        
        # Create resource with high capacity
        high_capacity_resource = ResourceFactory(capacity=100)
        users = [UserProfileFactory() for _ in range(150)]
        
        # Create many concurrent bookings
        booking_time = timezone.now() + timedelta(hours=1)
        
        bookings_created = 0
        errors = []
        
        for i in range(120):  # Exceed capacity to test limits
            try:
                booking = Booking.objects.create(
                    resource=high_capacity_resource,
                    user=users[i].user,
                    title=f'Stress Test Booking {i}',
                    start_time=booking_time,
                    end_time=booking_time + timedelta(hours=2),
                    status='approved'
                )
                bookings_created += 1
            except Exception as e:
                errors.append(e)
        
        # Should create up to capacity, then fail gracefully
        self.assertLessEqual(bookings_created, 100, "Should not exceed capacity")
        
        if bookings_created == 100:
            self.assertGreater(len(errors), 0, "Should reject bookings over capacity")
    
    def test_database_connection_pooling(self):
        """Test database connection handling under load"""
        
        def create_booking_with_connection(thread_id):
            try:
                # Each thread should get its own connection
                booking = BookingFactory()
                return True
            except Exception:
                return False
        
        # Test with many concurrent database operations
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [
                executor.submit(create_booking_with_connection, i) 
                for i in range(50)
            ]
            results = [future.result() for future in as_completed(futures)]
        
        # Most operations should succeed
        success_rate = sum(results) / len(results)
        self.assertGreater(success_rate, 0.9, "Should handle concurrent connections well")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])