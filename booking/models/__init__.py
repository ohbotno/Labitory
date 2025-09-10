"""
Models package for the Labitory.

This file re-exports all models for backward compatibility.
Import models from this package directly:
    from booking.models import Resource, Booking, UserProfile

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

# Core models
from .core import (
    AboutPage,
    LabSettings,
    Faculty,
    College,
    Department,
    UserProfile,
)

# Authentication models
from .auth import (
    PasswordResetToken,
    EmailVerificationToken,
    TwoFactorAuthentication,
    TwoFactorSession,
    APIToken,
    SecurityEvent,
)

# Notification models
from .notifications import (
    NotificationPreference,
    PushSubscription,
    Notification,
    EmailTemplate,
    EmailConfiguration,
    SMSConfiguration,
)

# Resource models
from .resources import (
    Resource,
    ResourceAccess,
    ResourceResponsible,
    ResourceTrainingRequirement,
    ResourceIssue,
)

# Booking models
from .bookings import (
    BookingTemplate,
    Booking,
    BookingAttendee,
    BookingHistory,
    CheckInOutEvent,
)

# Approval models
from .approvals import (
    ApprovalRule,
    ApprovalStatistics,
    AccessRequest,
    TrainingRequest,
)

# Maintenance models
from .maintenance import (
    MaintenanceVendor,
    Maintenance,
    MaintenanceDocument,
    MaintenanceAlert,
    MaintenanceAnalytics,
)

# Training models
from .training import (
    RiskAssessment,
    UserRiskAssessment,
    TrainingCourse,
    UserTraining,
)

# Waiting list models
from .waiting_list import (
    WaitingListEntry,
    WaitingListNotification,
)

# System models
from .system import (
    SystemSetting,
    PDFExportSettings,
    UpdateInfo,
    UpdateHistory,
    BackupSchedule,
)


# Tutorial models
from .tutorials import (
    TutorialCategory,
    Tutorial,
    UserTutorialProgress,
    TutorialAnalytics,
)

# Calendar models
from .calendar import (
    GoogleCalendarIntegration,
    GoogleCalendarSyncLog,
    CalendarSyncPreferences,
)

# Analytics models
from .analytics import (
    UsageAnalytics,
)

# Billing models
from .billing import (
    BillingPeriod,
    BillingRate,
    BillingRecord,
    DepartmentBilling,
)

# Checklist models
from .checklists import (
    ChecklistItem,
    ResourceChecklistItem,
    ChecklistResponse,
)

# Audit models
from .audit import (
    AuditLog,
    DataAccessLog,
    LoginAttempt,
    AdminAction,
)

# Export all models for backward compatibility
__all__ = [
    # Core
    'AboutPage',
    'LabSettings',
    'Faculty',
    'College',
    'Department',
    'UserProfile',
    # Auth
    'PasswordResetToken',
    'EmailVerificationToken',
    'TwoFactorAuthentication',
    'TwoFactorSession',
    'APIToken',
    'SecurityEvent',
    # Notifications
    'NotificationPreference',
    'PushSubscription',
    'Notification',
    'EmailTemplate',
    'EmailConfiguration',
    'SMSConfiguration',
    # Resources
    'Resource',
    'ResourceAccess',
    'ResourceResponsible',
    'ResourceTrainingRequirement',
    'ResourceChecklistItem',
    'ResourceIssue',
    # Bookings
    'BookingTemplate',
    'Booking',
    'BookingAttendee',
    'BookingHistory',
    'CheckInOutEvent',
    # Approvals
    'ApprovalRule',
    'ApprovalStatistics',
    'AccessRequest',
    'TrainingRequest',
    # Maintenance
    'MaintenanceVendor',
    'Maintenance',
    'MaintenanceDocument',
    'MaintenanceAlert',
    'MaintenanceAnalytics',
    # Training
    'RiskAssessment',
    'UserRiskAssessment',
    'TrainingCourse',
    'UserTraining',
    # Waiting List
    'WaitingListEntry',
    'WaitingListNotification',
    # System
    'SystemSetting',
    'PDFExportSettings',
    'UpdateInfo',
    'UpdateHistory',
    'BackupSchedule',
    # Tutorials
    'TutorialCategory',
    'Tutorial',
    'UserTutorialProgress',
    'TutorialAnalytics',
    # Calendar
    'GoogleCalendarIntegration',
    'GoogleCalendarSyncLog',
    'CalendarSyncPreferences',
    # Analytics
    'UsageAnalytics',
    # Billing
    'BillingPeriod',
    'BillingRate',
    'BillingRecord',
    'DepartmentBilling',
    # Checklists
    'ChecklistItem',
    'ResourceChecklistItem',
    'ChecklistResponse',
]