# booking/forms/__init__.py
"""
Modularized forms for the Aperture Booking system.
"""

# Import all forms from modules to maintain backward compatibility
from .auth import *
from .bookings import *
from .resources import *
from .admin import *
from .billing import *
from .maintenance import *

# Import utility functions
from ..utils.email import get_logo_base64, get_email_branding_context

# Import any remaining forms from the original forms.py for backward compatibility
# This will be needed while we transition to the modular structure

# Re-export commonly used forms
__all__ = [
    # Auth forms
    'UserRegistrationForm',
    'UserProfileForm',
    'CustomPasswordResetForm',
    'CustomSetPasswordForm',
    'CustomAuthenticationForm',
    'CalendarSyncPreferencesForm',
    
    # Booking forms
    'BookingForm',
    'RecurringBookingForm',
    'BookingTemplateForm',
    'CreateBookingFromTemplateForm',
    'SaveAsTemplateForm',
    
    # Resource forms
    'AccessRequestForm',
    'AccessRequestReviewForm',
    'ResourceForm',
    'ResourceResponsibleForm',
    'ChecklistItemForm',
    'ResourceChecklistConfigForm',
    'RiskAssessmentForm',
    'UserRiskAssessmentForm',
    'TrainingCourseForm',
    'UserTrainingEnrollForm',
    'ResourceIssueReportForm',
    'ResourceIssueUpdateForm',
    'IssueFilterForm',
    
    # Admin forms
    'AboutPageEditForm',
    'SMSConfigurationForm',
    'SMSConfigurationTestForm',
    'EmailConfigurationForm',
    'EmailConfigurationTestForm',
    
    # Billing forms
    'BillingRateForm',
    
    # Maintenance forms
    'MaintenanceVendorForm',
    'MaintenanceForm',
    'MaintenanceDocumentForm',
    'MaintenanceAlertForm',
    'MaintenanceFilterForm',
    
    # Utility functions (imported from utils.email)
    'get_logo_base64',
    'get_email_branding_context',
]