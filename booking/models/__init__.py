"""
Models package for the Labitory.

This file re-exports all models for backward compatibility.
Import models from this package directly:
    from booking.models import Resource, Booking, UserProfile

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://aperature-booking.org/commercial
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
)

# Notification models
from .notifications import (
    NotificationPreference,
    PushSubscription,
    Notification,
    EmailTemplate,
    EmailConfiguration,
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

# Licensing models
from .licensing import (
    LicenseConfiguration,
    BrandingConfiguration,
    LicenseValidationLog,
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

# Checklist models
from .checklists import (
    ChecklistItem,
    ResourceChecklistItem,
    ChecklistResponse,
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
    # Notifications
    'NotificationPreference',
    'PushSubscription',
    'Notification',
    'EmailTemplate',
    'EmailConfiguration',
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
    # Licensing
    'LicenseConfiguration',
    'BrandingConfiguration',
    'LicenseValidationLog',
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
    # Checklists
    'ChecklistItem',
    'ResourceChecklistItem',
    'ChecklistResponse',
]