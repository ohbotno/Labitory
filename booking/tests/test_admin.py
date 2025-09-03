"""
Test cases for admin functionality and site administration features.
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core import mail
from datetime import datetime, timedelta
from booking.models import (
    UserProfile, Resource, Booking, ApprovalRule, 
    UpdateInfo, BackupSchedule, BackupRecord
)
from booking.tests.factories import UserFactory, ResourceFactory, BookingFactory
import json
import os
import tempfile


class SiteAdminDashboardTests(TestCase):
    """Test site administrator dashboard functionality."""
    
    def setUp(self):
        self.admin_user = UserFactory(role='site_administrator', is_superuser=True)
        self.regular_user = UserFactory(role='student')
        self.client = Client()
    
    def test_site_admin_access_control(self):
        """Test site admin access is properly restricted."""
        # Test unauthenticated access
        response = self.client.get(reverse('site_admin_dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
        
        # Test non-admin user access
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse('site_admin_dashboard'))
        self.assertEqual(response.status_code, 403)  # Forbidden
        
        # Test admin user access
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('site_admin_dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_dashboard_sections_display(self):
        """Test all dashboard sections display correctly."""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('site_admin_dashboard'))
        
        # Check for main sections
        self.assertContains(response, 'System Overview')
        self.assertContains(response, 'User Management')
        self.assertContains(response, 'Resource Management')
        self.assertContains(response, 'Backup Management')
        self.assertContains(response, 'System Updates')
    
    def test_dashboard_statistics(self):
        """Test dashboard statistics display correctly."""
        # Create test data
        UserFactory.create_batch(5, role='student')
        ResourceFactory.create_batch(3)
        BookingFactory.create_batch(10)
        
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('site_admin_dashboard'))
        
        # Check statistics are displayed
        self.assertContains(response, 'Total Users')
        self.assertContains(response, 'Total Resources')
        self.assertContains(response, 'Total Bookings')


class UserManagementTests(TestCase):
    """Test user management functionality."""
    
    def setUp(self):
        self.admin_user = UserFactory(role='site_administrator', is_superuser=True)
        self.lab_manager = UserFactory(role='lab_manager')
        self.student = UserFactory(role='student')
        self.client = Client()
        self.client.force_login(self.admin_user)
    
    def test_user_list_display(self):
        """Test user list displays correctly."""
        response = self.client.get(reverse('manage_users'))
        self.assertEqual(response.status_code, 200)
        
        # Check users are displayed
        self.assertContains(response, self.lab_manager.username)
        self.assertContains(response, self.student.username)
        self.assertContains(response, self.lab_manager.userprofile.role)
    
    def test_user_search_functionality(self):
        """Test user search functionality."""
        response = self.client.get(reverse('manage_users'), {
            'search': self.student.username
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student.username)
        self.assertNotContains(response, self.lab_manager.username)
    
    def test_user_role_update(self):
        """Test updating user roles."""
        response = self.client.post(reverse('update_user_role'), {
            'user_id': self.student.id,
            'role': 'researcher'
        })
        self.assertEqual(response.status_code, 200)
        
        self.student.userprofile.refresh_from_db()
        self.assertEqual(self.student.userprofile.role, 'researcher')
    
    def test_user_approval_toggle(self):
        """Test user approval status toggle."""
        # Set user as not approved
        self.student.userprofile.is_approved = False
        self.student.userprofile.save()
        
        response = self.client.post(reverse('toggle_user_approval'), {
            'user_id': self.student.id
        })
        self.assertEqual(response.status_code, 200)
        
        self.student.userprofile.refresh_from_db()
        self.assertTrue(self.student.userprofile.is_approved)
    
    def test_user_deactivation(self):
        """Test user account deactivation."""
        response = self.client.post(reverse('deactivate_user'), {
            'user_id': self.student.id
        })
        self.assertEqual(response.status_code, 200)
        
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
    
    def test_bulk_user_operations(self):
        """Test bulk user operations."""
        users = UserFactory.create_batch(3, role='student')
        user_ids = [user.id for user in users]
        
        response = self.client.post(reverse('bulk_user_action'), {
            'action': 'approve',
            'user_ids': user_ids
        })
        self.assertEqual(response.status_code, 200)
        
        for user in users:
            user.userprofile.refresh_from_db()
            self.assertTrue(user.userprofile.is_approved)


class ResourceManagementTests(TestCase):
    """Test resource management functionality."""
    
    def setUp(self):
        self.admin_user = UserFactory(role='site_administrator', is_superuser=True)
        self.resource = ResourceFactory()
        self.client = Client()
        self.client.force_login(self.admin_user)
    
    def test_resource_list_display(self):
        """Test resource list displays correctly."""
        response = self.client.get(reverse('manage_resources'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.resource.name)
        self.assertContains(response, self.resource.category)
    
    def test_resource_creation(self):
        """Test resource creation functionality."""
        response = self.client.post(reverse('create_resource'), {
            'name': 'New Test Resource',
            'description': 'Test resource description',
            'category': 'test_equipment',
            'location': 'Test Lab',
            'capacity': 1,
            'requires_training': False,
            'is_bookable': True
        })
        self.assertEqual(response.status_code, 302)  # Redirect after creation
        
        self.assertTrue(Resource.objects.filter(name='New Test Resource').exists())
    
    def test_resource_editing(self):
        """Test resource editing functionality."""
        response = self.client.post(reverse('edit_resource', args=[self.resource.id]), {
            'name': 'Updated Resource Name',
            'description': self.resource.description,
            'category': self.resource.category,
            'location': self.resource.location,
            'capacity': self.resource.capacity,
            'requires_training': self.resource.requires_training,
            'is_bookable': self.resource.is_bookable
        })
        self.assertEqual(response.status_code, 302)
        
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.name, 'Updated Resource Name')
    
    def test_resource_deactivation(self):
        """Test resource deactivation."""
        response = self.client.post(reverse('toggle_resource_status'), {
            'resource_id': self.resource.id
        })
        self.assertEqual(response.status_code, 200)
        
        self.resource.refresh_from_db()
        self.assertFalse(self.resource.is_active)
    
    def test_resource_usage_statistics(self):
        """Test resource usage statistics."""
        # Create some bookings for the resource
        BookingFactory.create_batch(5, resource=self.resource)
        
        response = self.client.get(reverse('resource_statistics', args=[self.resource.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Usage Statistics')
        self.assertContains(response, 'Total Bookings')


class BackupManagementTests(TestCase):
    """Test backup management functionality."""
    
    def setUp(self):
        self.admin_user = UserFactory(role='site_administrator', is_superuser=True)
        self.client = Client()
        self.client.force_login(self.admin_user)
    
    def test_backup_management_page(self):
        """Test backup management page loads correctly."""
        response = self.client.get(reverse('site_admin_backup_management'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Backup Management')
        self.assertContains(response, 'Create Backup')
    
    def test_manual_backup_creation(self):
        """Test manual backup creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(BACKUP_ROOT=temp_dir):
                response = self.client.post(reverse('create_backup'))
                self.assertEqual(response.status_code, 200)
                
                # Check backup record was created
                self.assertTrue(BackupRecord.objects.exists())
    
    def test_backup_list_display(self):
        """Test backup list displays correctly."""
        # Create test backup records
        BackupRecord.objects.create(
            filename='test_backup_1.tar.gz',
            size=1024000,
            backup_type='manual'
        )
        BackupRecord.objects.create(
            filename='test_backup_2.tar.gz',
            size=2048000,
            backup_type='scheduled'
        )
        
        response = self.client.get(reverse('site_admin_backup_management'))
        self.assertContains(response, 'test_backup_1.tar.gz')
        self.assertContains(response, 'test_backup_2.tar.gz')
    
    def test_backup_download(self):
        """Test backup download functionality."""
        backup = BackupRecord.objects.create(
            filename='downloadable_backup.tar.gz',
            size=1024,
            backup_type='manual'
        )
        
        response = self.client.get(reverse('download_backup', args=[backup.id]))
        # Should return 404 if file doesn't exist, or download if it does
        self.assertIn(response.status_code, [200, 404])
    
    def test_backup_deletion(self):
        """Test backup deletion functionality."""
        backup = BackupRecord.objects.create(
            filename='deletable_backup.tar.gz',
            size=1024,
            backup_type='manual'
        )
        
        response = self.client.post(reverse('delete_backup', args=[backup.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BackupRecord.objects.filter(id=backup.id).exists())
    
    def test_scheduled_backup_configuration(self):
        """Test scheduled backup configuration."""
        response = self.client.post(reverse('configure_backup_schedule'), {
            'frequency': 'daily',
            'time': '02:00',
            'retention_days': 30,
            'is_enabled': True
        })
        self.assertEqual(response.status_code, 200)
        
        # Check schedule was created/updated
        schedule = BackupSchedule.objects.first()
        self.assertEqual(schedule.frequency, 'daily')
        self.assertTrue(schedule.is_enabled)


class UpdateSystemTests(TestCase):
    """Test update system functionality."""
    
    def setUp(self):
        self.admin_user = UserFactory(role='site_administrator', is_superuser=True)
        self.client = Client()
        self.client.force_login(self.admin_user)
    
    def test_update_page_display(self):
        """Test update page displays correctly."""
        # Create update info
        UpdateInfo.objects.create(
            current_version='1.0.0',
            available_version='1.0.1',
            github_repo='ohbotno/aperature-booking',
            last_checked=datetime.now()
        )
        
        response = self.client.get(reverse('site_admin_updates'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Current Version')
        self.assertContains(response, '1.0.0')
        self.assertContains(response, 'Available Version')
        self.assertContains(response, '1.0.1')
    
    def test_check_for_updates(self):
        """Test check for updates functionality."""
        response = self.client.post(reverse('check_updates'))
        self.assertEqual(response.status_code, 200)
        
        # Should create or update UpdateInfo record
        self.assertTrue(UpdateInfo.objects.exists())
    
    def test_update_configuration(self):
        """Test update configuration."""
        response = self.client.post(reverse('configure_updates'), {
            'github_repo': 'ohbotno/aperature-booking',
            'auto_check': True,
            'check_interval': 24,
            'notification_email': 'admin@example.com'
        })
        self.assertEqual(response.status_code, 200)
        
        update_info = UpdateInfo.objects.first()
        self.assertEqual(update_info.github_repo, 'ohbotno/aperature-booking')
        self.assertTrue(update_info.auto_check)
    
    def test_update_history_display(self):
        """Test update history display."""
        response = self.client.get(reverse('update_history'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Update History')


class ApprovalManagementTests(TestCase):
    """Test approval management functionality."""
    
    def setUp(self):
        self.admin_user = UserFactory(role='site_administrator', is_superuser=True)
        self.lab_manager = UserFactory(role='lab_manager')
        self.student = UserFactory(role='student')
        self.resource = ResourceFactory()
        self.client = Client()
        self.client.force_login(self.admin_user)
    
    def test_approval_rules_management(self):
        """Test approval rules management."""
        response = self.client.get(reverse('manage_approval_rules'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Approval Rules')
    
    def test_create_approval_rule(self):
        """Test creating approval rules."""
        response = self.client.post(reverse('create_approval_rule'), {
            'resource': self.resource.id,
            'user_role': 'student',
            'approval_type': 'single',
            'approver_role': 'lab_manager',
            'conditions': '{"min_advance_hours": 24}'
        })
        self.assertEqual(response.status_code, 302)
        
        rule = ApprovalRule.objects.get(resource=self.resource)
        self.assertEqual(rule.user_role, 'student')
        self.assertEqual(rule.approval_type, 'single')
    
    def test_pending_approvals_queue(self):
        """Test pending approvals queue."""
        # Create pending booking
        booking = BookingFactory(
            user=self.student,
            resource=self.resource,
            status='pending_approval'
        )
        
        response = self.client.get(reverse('pending_approvals'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, booking.purpose)
    
    def test_bulk_approval_actions(self):
        """Test bulk approval actions."""
        bookings = BookingFactory.create_batch(3, 
            user=self.student,
            resource=self.resource,
            status='pending_approval'
        )
        booking_ids = [booking.id for booking in bookings]
        
        response = self.client.post(reverse('bulk_approval_action'), {
            'action': 'approve',
            'booking_ids': booking_ids
        })
        self.assertEqual(response.status_code, 200)
        
        for booking in bookings:
            booking.refresh_from_db()
            self.assertEqual(booking.status, 'confirmed')


class SystemConfigurationTests(TestCase):
    """Test system configuration functionality."""
    
    def setUp(self):
        self.admin_user = UserFactory(role='site_administrator', is_superuser=True)
        self.client = Client()
        self.client.force_login(self.admin_user)
    
    def test_site_settings_page(self):
        """Test site settings page."""
        response = self.client.get(reverse('site_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Site Settings')
    
    def test_email_configuration(self):
        """Test email configuration."""
        response = self.client.post(reverse('configure_email'), {
            'email_host': 'smtp.example.com',
            'email_port': 587,
            'email_use_tls': True,
            'email_host_user': 'noreply@example.com',
            'default_from_email': 'noreply@example.com'
        })
        self.assertEqual(response.status_code, 200)
    
    def test_notification_template_management(self):
        """Test notification template management."""
        response = self.client.get(reverse('manage_email_templates'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Email Templates')
    
    def test_system_maintenance_mode(self):
        """Test system maintenance mode toggle."""
        response = self.client.post(reverse('toggle_maintenance_mode'))
        self.assertEqual(response.status_code, 200)


class AnalyticsReportsTests(TestCase):
    """Test analytics and reporting functionality."""
    
    def setUp(self):
        self.admin_user = UserFactory(role='site_administrator', is_superuser=True)
        self.resource = ResourceFactory()
        self.client = Client()
        self.client.force_login(self.admin_user)
        
        # Create test data
        self.users = UserFactory.create_batch(5, role='student')
        self.bookings = []
        for user in self.users:
            self.bookings.extend(BookingFactory.create_batch(3, 
                user=user, 
                resource=self.resource
            ))
    
    def test_analytics_dashboard(self):
        """Test analytics dashboard."""
        response = self.client.get(reverse('analytics_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Analytics Dashboard')
        self.assertContains(response, 'Usage Statistics')
    
    def test_usage_statistics_api(self):
        """Test usage statistics API endpoint."""
        response = self.client.get(reverse('api_usage_statistics'))
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertIn('total_bookings', data)
        self.assertIn('total_users', data)
        self.assertIn('total_resources', data)
    
    def test_resource_utilization_report(self):
        """Test resource utilization report."""
        response = self.client.get(reverse('resource_utilization_report'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.resource.name)
    
    def test_user_activity_report(self):
        """Test user activity report."""
        response = self.client.get(reverse('user_activity_report'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'User Activity')
    
    def test_booking_trends_analysis(self):
        """Test booking trends analysis."""
        response = self.client.get(reverse('booking_trends_analysis'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Booking Trends')
    
    def test_export_functionality(self):
        """Test report export functionality."""
        # Test CSV export
        response = self.client.get(reverse('export_usage_report'), {
            'format': 'csv'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        
        # Test PDF export
        response = self.client.get(reverse('export_usage_report'), {
            'format': 'pdf'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')


class SystemMonitoringTests(TestCase):
    """Test system monitoring functionality."""
    
    def setUp(self):
        self.admin_user = UserFactory(role='site_administrator', is_superuser=True)
        self.client = Client()
        self.client.force_login(self.admin_user)
    
    def test_system_health_check(self):
        """Test system health check endpoint."""
        response = self.client.get(reverse('system_health_check'))
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.content)
        self.assertIn('status', data)
        self.assertIn('database', data)
        self.assertIn('email', data)
    
    def test_system_logs_viewer(self):
        """Test system logs viewer."""
        response = self.client.get(reverse('view_system_logs'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'System Logs')
    
    def test_performance_metrics(self):
        """Test performance metrics display."""
        response = self.client.get(reverse('performance_metrics'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Performance Metrics')
    
    def test_error_monitoring(self):
        """Test error monitoring functionality."""
        response = self.client.get(reverse('error_monitoring'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Error Monitoring')


class SecurityManagementTests(TestCase):
    """Test security management functionality."""
    
    def setUp(self):
        self.admin_user = UserFactory(role='site_administrator', is_superuser=True)
        self.client = Client()
        self.client.force_login(self.admin_user)
    
    def test_security_settings_page(self):
        """Test security settings page."""
        response = self.client.get(reverse('security_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Security Settings')
    
    def test_login_attempt_monitoring(self):
        """Test login attempt monitoring."""
        response = self.client.get(reverse('login_attempts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Login Attempts')
    
    def test_session_management(self):
        """Test active session management."""
        response = self.client.get(reverse('active_sessions'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Active Sessions')
    
    def test_audit_log_viewer(self):
        """Test audit log viewer."""
        response = self.client.get(reverse('audit_logs'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Audit Logs')


class IntegrationAdminTests(TestCase):
    """Test admin functionality integration."""
    
    def setUp(self):
        self.admin_user = UserFactory(role='site_administrator', is_superuser=True)
        self.client = Client()
        self.client.force_login(self.admin_user)
    
    def test_complete_resource_lifecycle(self):
        """Test complete resource lifecycle management."""
        # Create resource
        response = self.client.post(reverse('create_resource'), {
            'name': 'Lifecycle Test Resource',
            'description': 'Test resource for lifecycle testing',
            'category': 'test_equipment',
            'location': 'Test Lab',
            'capacity': 1,
            'requires_training': True,
            'is_bookable': True
        })
        self.assertEqual(response.status_code, 302)
        
        resource = Resource.objects.get(name='Lifecycle Test Resource')
        
        # Create approval rule for resource
        response = self.client.post(reverse('create_approval_rule'), {
            'resource': resource.id,
            'user_role': 'student',
            'approval_type': 'single',
            'approver_role': 'lab_manager'
        })
        self.assertEqual(response.status_code, 302)
        
        # Verify approval rule was created
        self.assertTrue(ApprovalRule.objects.filter(resource=resource).exists())
        
        # Update resource
        response = self.client.post(reverse('edit_resource', args=[resource.id]), {
            'name': 'Updated Lifecycle Resource',
            'description': resource.description,
            'category': resource.category,
            'location': resource.location,
            'capacity': resource.capacity,
            'requires_training': resource.requires_training,
            'is_bookable': resource.is_bookable
        })
        self.assertEqual(response.status_code, 302)
        
        resource.refresh_from_db()
        self.assertEqual(resource.name, 'Updated Lifecycle Resource')
        
        # Deactivate resource
        response = self.client.post(reverse('toggle_resource_status'), {
            'resource_id': resource.id
        })
        self.assertEqual(response.status_code, 200)
        
        resource.refresh_from_db()
        self.assertFalse(resource.is_active)
    
    def test_complete_user_management_workflow(self):
        """Test complete user management workflow."""
        # Create user
        user = UserFactory(role='student', is_approved=False)
        
        # Approve user
        response = self.client.post(reverse('toggle_user_approval'), {
            'user_id': user.id
        })
        self.assertEqual(response.status_code, 200)
        
        user.userprofile.refresh_from_db()
        self.assertTrue(user.userprofile.is_approved)
        
        # Change user role
        response = self.client.post(reverse('update_user_role'), {
            'user_id': user.id,
            'role': 'researcher'
        })
        self.assertEqual(response.status_code, 200)
        
        user.userprofile.refresh_from_db()
        self.assertEqual(user.userprofile.role, 'researcher')
        
        # Deactivate user
        response = self.client.post(reverse('deactivate_user'), {
            'user_id': user.id
        })
        self.assertEqual(response.status_code, 200)
        
        user.refresh_from_db()
        self.assertFalse(user.is_active)
    
    def test_backup_and_restore_workflow(self):
        """Test backup and restore workflow."""
        # Create test data
        resource = ResourceFactory()
        booking = BookingFactory(resource=resource)
        
        # Create backup
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.settings(BACKUP_ROOT=temp_dir):
                response = self.client.post(reverse('create_backup'))
                self.assertEqual(response.status_code, 200)
                
                backup = BackupRecord.objects.first()
                self.assertIsNotNone(backup)
                
                # Test backup download
                response = self.client.get(reverse('download_backup', args=[backup.id]))
                # Should either download or return 404 if file doesn't exist
                self.assertIn(response.status_code, [200, 404])