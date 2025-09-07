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
    
    # Billing forms
    'BillingRateForm',
    
    # Utility function
    'get_logo_base64',
]