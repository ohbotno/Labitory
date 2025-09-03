# booking/emergency_notifications.py
"""
Emergency notification system for the Labitory system.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

from django.contrib.auth.models import User
from django.utils import timezone
from typing import List, Optional, Dict
import logging

from .models import UserProfile, Resource, Notification
from .notifications import notification_service

logger = logging.getLogger(__name__)


class EmergencyNotificationSystem:
    """System for sending emergency notifications."""
    
    def __init__(self):
        self.emergency_contacts = []  # Could be loaded from settings
    
    def send_system_emergency(self, title: str, message: str, affected_resources: Optional[List[Resource]] = None):
        """Send emergency notification to all system administrators."""
        try:
            # Get all system administrators
            sysadmins = UserProfile.objects.filter(role='sysadmin').select_related('user')
            
            for admin_profile in sysadmins:
                notification_service.create_notification(
                    user=admin_profile.user,
                    notification_type='emergency_alert',
                    title=f"EMERGENCY: {title}",
                    message=message,
                    priority='urgent',
                    metadata={
                        'emergency_type': 'system',
                        'affected_resources': [r.id for r in affected_resources] if affected_resources else [],
                        'timestamp': timezone.now().isoformat()
                    }
                )
            
            logger.critical(f"Emergency notification sent: {title}")
            return len(sysadmins)
            
        except Exception as e:
            logger.error(f"Failed to send emergency notification: {e}")
            return 0
    
    def send_resource_emergency(self, resource: Resource, title: str, message: str, notify_users: bool = True):
        """Send emergency notification about a specific resource."""
        try:
            notifications_sent = 0
            
            # Notify system administrators first
            sysadmins = UserProfile.objects.filter(role='sysadmin').select_related('user')
            for admin_profile in sysadmins:
                notification_service.create_notification(
                    user=admin_profile.user,
                    notification_type='emergency_alert',
                    title=f"RESOURCE EMERGENCY: {resource.name}",
                    message=message,
                    priority='urgent',
                    resource=resource,
                    metadata={
                        'emergency_type': 'resource',
                        'resource_id': resource.id,
                        'timestamp': timezone.now().isoformat()
                    }
                )
                notifications_sent += 1
            
            # Notify lab managers
            lab_managers = UserProfile.objects.filter(role='lab_manager').select_related('user')
            for manager_profile in lab_managers:
                notification_service.create_notification(
                    user=manager_profile.user,
                    notification_type='emergency_alert',
                    title=f"RESOURCE EMERGENCY: {resource.name}",
                    message=message,
                    priority='urgent',
                    resource=resource,
                    metadata={
                        'emergency_type': 'resource',
                        'resource_id': resource.id,
                        'timestamp': timezone.now().isoformat()
                    }
                )
                notifications_sent += 1
            
            # Optionally notify users with access to this resource
            if notify_users:
                from .models import ResourceAccess
                users_with_access = ResourceAccess.objects.filter(
                    resource=resource,
                    is_active=True
                ).select_related('user')
                
                for access in users_with_access:
                    notification_service.create_notification(
                        user=access.user,
                        notification_type='emergency_alert',
                        title=f"RESOURCE ALERT: {resource.name}",
                        message=f"Important notice about {resource.name}: {message}",
                        priority='high',
                        resource=resource,
                        metadata={
                            'emergency_type': 'resource_user',
                            'resource_id': resource.id,
                            'timestamp': timezone.now().isoformat()
                        }
                    )
                    notifications_sent += 1
            
            logger.warning(f"Resource emergency notification sent for {resource.name}: {title}")
            return notifications_sent
            
        except Exception as e:
            logger.error(f"Failed to send resource emergency notification: {e}")
            return 0
    
    def send_safety_alert(self, title: str, message: str, affected_resources: Optional[List[Resource]] = None, 
                         affected_locations: Optional[List[str]] = None):
        """Send safety alert to relevant users."""
        try:
            notifications_sent = 0
            
            # Always notify administrators and managers for safety alerts
            staff_profiles = UserProfile.objects.filter(
                role__in=['sysadmin', 'lab_manager']
            ).select_related('user')
            
            for staff_profile in staff_profiles:
                notification_service.create_notification(
                    user=staff_profile.user,
                    notification_type='safety_alert',
                    title=f"SAFETY ALERT: {title}",
                    message=message,
                    priority='urgent',
                    metadata={
                        'emergency_type': 'safety',
                        'affected_resources': [r.id for r in affected_resources] if affected_resources else [],
                        'affected_locations': affected_locations or [],
                        'timestamp': timezone.now().isoformat()
                    }
                )
                notifications_sent += 1
            
            # If specific resources are affected, notify users with access
            if affected_resources:
                from .models import ResourceAccess
                for resource in affected_resources:
                    users_with_access = ResourceAccess.objects.filter(
                        resource=resource,
                        is_active=True
                    ).select_related('user')
                    
                    for access in users_with_access:
                        notification_service.create_notification(
                            user=access.user,
                            notification_type='safety_alert',
                            title=f"SAFETY ALERT: {title}",
                            message=f"Safety notice for {resource.name}: {message}",
                            priority='urgent',
                            resource=resource,
                            metadata={
                                'emergency_type': 'safety_resource',
                                'resource_id': resource.id,
                                'timestamp': timezone.now().isoformat()
                            }
                        )
                        notifications_sent += 1
            
            # If specific locations are affected, notify users in those locations
            if affected_locations:
                # This would require user location data - for now, notify all active users
                active_users = User.objects.filter(is_active=True)
                for user in active_users[:50]:  # Limit to prevent spam
                    notification_service.create_notification(
                        user=user,
                        notification_type='safety_alert',
                        title=f"SAFETY ALERT: {title}",
                        message=f"Safety notice for locations {', '.join(affected_locations)}: {message}",
                        priority='high',
                        metadata={
                            'emergency_type': 'safety_location',
                            'affected_locations': affected_locations,
                            'timestamp': timezone.now().isoformat()
                        }
                    )
                    notifications_sent += 1
            
            logger.critical(f"Safety alert sent: {title}")
            return notifications_sent
            
        except Exception as e:
            logger.error(f"Failed to send safety alert: {e}")
            return 0
    
    def send_evacuation_notice(self, title: str, message: str, affected_locations: List[str]):
        """Send evacuation notice to all users."""
        try:
            # This is the highest priority notification - send to everyone
            all_active_users = User.objects.filter(is_active=True)
            notifications_sent = 0
            
            for user in all_active_users:
                notification_service.create_notification(
                    user=user,
                    notification_type='evacuation_notice',
                    title=f"EVACUATION: {title}",
                    message=message,
                    priority='urgent',
                    metadata={
                        'emergency_type': 'evacuation',
                        'affected_locations': affected_locations,
                        'timestamp': timezone.now().isoformat(),
                        'requires_immediate_action': True
                    }
                )
                notifications_sent += 1
            
            logger.critical(f"Evacuation notice sent to {notifications_sent} users: {title}")
            return notifications_sent
            
        except Exception as e:
            logger.error(f"Failed to send evacuation notice: {e}")
            return 0
    
    def send_maintenance_emergency(self, title: str, message: str, resources: List[Resource], 
                                 estimated_duration: Optional[str] = None):
        """Send emergency maintenance notification."""
        try:
            notifications_sent = 0
            
            # Notify staff first
            staff_profiles = UserProfile.objects.filter(
                role__in=['sysadmin', 'lab_manager']
            ).select_related('user')
            
            staff_message = f"Emergency maintenance required: {message}"
            if estimated_duration:
                staff_message += f" Estimated duration: {estimated_duration}"
            
            for staff_profile in staff_profiles:
                notification_service.create_notification(
                    user=staff_profile.user,
                    notification_type='emergency_maintenance',
                    title=f"EMERGENCY MAINTENANCE: {title}",
                    message=staff_message,
                    priority='high',
                    metadata={
                        'emergency_type': 'maintenance',
                        'affected_resources': [r.id for r in resources],
                        'estimated_duration': estimated_duration,
                        'timestamp': timezone.now().isoformat()
                    }
                )
                notifications_sent += 1
            
            # Notify users with upcoming bookings on affected resources
            from .models import Booking
            upcoming_bookings = Booking.objects.filter(
                resource__in=resources,
                start_time__gte=timezone.now(),
                start_time__lte=timezone.now() + timezone.timedelta(hours=24),
                status='confirmed'
            ).select_related('user', 'resource')
            
            for booking in upcoming_bookings:
                user_message = f"Emergency maintenance on {booking.resource.name} may affect your booking on {booking.start_time.strftime('%B %d at %I:%M %p')}. {message}"
                
                notification_service.create_notification(
                    user=booking.user,
                    notification_type='emergency_maintenance',
                    title=f"URGENT: Maintenance May Affect Your Booking",
                    message=user_message,
                    priority='high',
                    booking=booking,
                    resource=booking.resource,
                    metadata={
                        'emergency_type': 'maintenance_booking',
                        'booking_id': booking.id,
                        'resource_id': booking.resource.id,
                        'timestamp': timezone.now().isoformat()
                    }
                )
                notifications_sent += 1
            
            logger.warning(f"Emergency maintenance notification sent for {len(resources)} resources: {title}")
            return notifications_sent
            
        except Exception as e:
            logger.error(f"Failed to send emergency maintenance notification: {e}")
            return 0
    
    def get_emergency_contact_list(self) -> List[Dict]:
        """Get list of emergency contacts."""
        try:
            contacts = []
            
            # System administrators
            sysadmins = UserProfile.objects.filter(role='sysadmin').select_related('user')
            for admin in sysadmins:
                contacts.append({
                    'name': admin.user.get_full_name() or admin.user.username,
                    'email': admin.user.email,
                    'role': 'System Administrator',
                    'phone': getattr(admin, 'phone', None)
                })
            
            # Lab managers
            lab_managers = UserProfile.objects.filter(role='lab_manager').select_related('user')
            for manager in lab_managers:
                contacts.append({
                    'name': manager.user.get_full_name() or manager.user.username,
                    'email': manager.user.email,
                    'role': 'Lab Manager',
                    'phone': getattr(manager, 'phone', None)
                })
            
            return contacts
            
        except Exception as e:
            logger.error(f"Failed to get emergency contact list: {e}")
            return []


# Global emergency system instance
emergency_notification_system = EmergencyNotificationSystem()