# booking/views/modules/__init__.py
"""
Modularized views for the Aperture Booking system.
"""

# Import all views from modules to maintain backward compatibility
from .auth import *
from .api import *
from .bookings import *
from .resources import *
from .core import *
from .checkin import *
from .issues import *
from .notifications import *
from .conflicts import *
from .templates import *
from .analytics import *
from .approvals import *
from .training import *
from .lab_admin import *
from .site_admin import *
from .calendar import *
from .hierarchy import *
from .maintenance import *

# Re-export commonly used items
__all__ = [
    # Auth views
    'register_view',
    'verify_email_view', 
    'resend_verification_view',
    'CustomPasswordResetView',
    'password_reset_confirm_view',
    'password_reset_done_view',
    'password_reset_complete_view',
    'CustomLoginView',
    
    # API ViewSets
    'UserProfileViewSet',
    'ResourceViewSet', 
    'BookingViewSet',
    'ApprovalRuleViewSet',
    'MaintenanceViewSet',
    'WaitingListEntryViewSet',
    
    # Booking views
    'create_booking_view',
    'booking_detail_view',
    'my_bookings_view',
    'edit_booking_view',
    'cancel_booking_view',
    'duplicate_booking_view',
    'template_list_view',
    'template_create_view',
    'create_booking_from_template_view',
    'save_booking_as_template_view',
    
    # Resource views
    'resources_list_view',
    'resource_detail_view',
    'request_resource_access_view',
    'access_requests_view',
    'access_request_detail_view',
    
    # Core views
    'dashboard_view',
    'profile_view',
    'calendar_view',
    'about_page_view',
    'about_page_edit_view',
    'ajax_load_colleges',
    'ajax_load_departments',
    
    # Checkin views
    'checkin_view',
    'checkout_view',
    'checkin_status_view',
    'resource_checkin_status_view',
    'api_checkin_booking',
    'api_checkout_booking',
    
    # Issue views
    'report_resource_issue',
    'issues_dashboard',
    'issue_detail',
    'my_reported_issues',
    
    # Notification views
    'notifications_list',
    'notification_preferences',
    'notification_preferences_view',
    'waiting_list_view',
    'join_waiting_list',
    'leave_waiting_list',
    'respond_to_availability',
    'NotificationViewSet',
    'WaitingListEntryViewSet',
    
    # Conflict views
    'conflict_detection_view',
    'resolve_conflict_view',
    'bulk_resolve_conflicts_view',
    
    # Template views
    'template_edit_view',
    'template_delete_view',
    'create_booking_from_template_view',
    'save_booking_as_template_view',
    'bulk_booking_operations_view',
    'booking_management_view',
    
    # Analytics views
    'usage_analytics_view',
    
    # Permissions
    'IsOwnerOrManagerPermission',
    'IsManagerPermission',
]