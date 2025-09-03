#!/usr/bin/env python3
"""
Management command to create the Lab Admin group with appropriate permissions.

Lab Admins are responsible for:
- Managing user access requests
- Conducting and approving training
- Managing resource access permissions
- Overseeing user onboarding

Usage:
    python manage.py create_lab_admin_group
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from booking.models import (
    UserProfile, AccessRequest, TrainingRequest, ResourceAccess, 
    Resource, UserTraining, TrainingCourse
)


class Command(BaseCommand):
    help = 'Create Lab Admin group with appropriate permissions for training and access management'

    def add_arguments(self, parser):
        parser.add_argument(
            '--update',
            action='store_true',
            help='Update existing group permissions if group already exists',
        )

    def handle(self, *args, **options):
        self.stdout.write('Creating Lab Admin group...')
        
        # Create or get the Lab Admin group
        group, created = Group.objects.get_or_create(name='Lab Admin')
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(f'✓ Created new group: {group.name}')
            )
        elif options['update']:
            self.stdout.write(f'Updating existing group: {group.name}')
            # Clear existing permissions to start fresh
            group.permissions.clear()
        else:
            self.stdout.write(
                self.style.WARNING(f'Group "{group.name}" already exists. Use --update to modify permissions.')
            )
            return

        # Define permissions for Lab Admins
        permissions_to_add = []

        # User Profile Management
        user_profile_ct = ContentType.objects.get_for_model(UserProfile)
        permissions_to_add.extend([
            Permission.objects.get_or_create(
                codename='view_userprofile',
                name='Can view user profile',
                content_type=user_profile_ct,
            )[0],
            Permission.objects.get_or_create(
                codename='change_userprofile',
                name='Can change user profile',
                content_type=user_profile_ct,
            )[0],
        ])

        # Access Request Management
        access_request_ct = ContentType.objects.get_for_model(AccessRequest)
        permissions_to_add.extend([
            Permission.objects.get_or_create(
                codename='view_accessrequest',
                name='Can view access request',
                content_type=access_request_ct,
            )[0],
            Permission.objects.get_or_create(
                codename='change_accessrequest',
                name='Can change access request',
                content_type=access_request_ct,
            )[0],
            Permission.objects.get_or_create(
                codename='approve_accessrequest',
                name='Can approve access requests',
                content_type=access_request_ct,
            )[0],
        ])

        # Resource Access Management
        resource_access_ct = ContentType.objects.get_for_model(ResourceAccess)
        permissions_to_add.extend([
            Permission.objects.get_or_create(
                codename='view_resourceaccess',
                name='Can view resource access',
                content_type=resource_access_ct,
            )[0],
            Permission.objects.get_or_create(
                codename='add_resourceaccess',
                name='Can add resource access',
                content_type=resource_access_ct,
            )[0],
            Permission.objects.get_or_create(
                codename='change_resourceaccess',
                name='Can change resource access',
                content_type=resource_access_ct,
            )[0],
            Permission.objects.get_or_create(
                codename='delete_resourceaccess',
                name='Can delete resource access',
                content_type=resource_access_ct,
            )[0],
        ])

        # Training Request Management
        training_request_ct = ContentType.objects.get_for_model(TrainingRequest)
        permissions_to_add.extend([
            Permission.objects.get_or_create(
                codename='view_trainingrequest',
                name='Can view training request',
                content_type=training_request_ct,
            )[0],
            Permission.objects.get_or_create(
                codename='change_trainingrequest',
                name='Can change training request',
                content_type=training_request_ct,
            )[0],
            Permission.objects.get_or_create(
                codename='approve_trainingrequest',
                name='Can approve training requests',
                content_type=training_request_ct,
            )[0],
        ])

        # User Training Management
        user_training_ct = ContentType.objects.get_for_model(UserTraining)
        permissions_to_add.extend([
            Permission.objects.get_or_create(
                codename='view_usertraining',
                name='Can view user training',
                content_type=user_training_ct,
            )[0],
            Permission.objects.get_or_create(
                codename='add_usertraining',
                name='Can add user training',
                content_type=user_training_ct,
            )[0],
            Permission.objects.get_or_create(
                codename='change_usertraining',
                name='Can change user training',
                content_type=user_training_ct,
            )[0],
            Permission.objects.get_or_create(
                codename='conduct_training',
                name='Can conduct training sessions',
                content_type=user_training_ct,
            )[0],
        ])

        # Training Course Management
        training_course_ct = ContentType.objects.get_for_model(TrainingCourse)
        permissions_to_add.extend([
            Permission.objects.get_or_create(
                codename='view_trainingcourse',
                name='Can view training course',
                content_type=training_course_ct,
            )[0],
            Permission.objects.get_or_create(
                codename='add_trainingcourse',
                name='Can add training course',
                content_type=training_course_ct,
            )[0],
            Permission.objects.get_or_create(
                codename='change_trainingcourse',
                name='Can change training course',
                content_type=training_course_ct,
            )[0],
        ])

        # Resource Management (view only for access management)
        resource_ct = ContentType.objects.get_for_model(Resource)
        permissions_to_add.extend([
            Permission.objects.get_or_create(
                codename='view_resource',
                name='Can view resource',
                content_type=resource_ct,
            )[0],
        ])

        # Add all permissions to the group
        group.permissions.set(permissions_to_add)
        
        self.stdout.write(
            self.style.SUCCESS(f'✓ Added {len(permissions_to_add)} permissions to Lab Admin group')
        )

        # Display summary of permissions
        self.stdout.write('\nLab Admin group permissions:')
        for permission in permissions_to_add:
            self.stdout.write(f'  • {permission.name} ({permission.content_type.model})')

        self.stdout.write(
            self.style.SUCCESS(f'\n✓ Lab Admin group setup complete!')
        )
        self.stdout.write(
            'Lab Admins can now:\n'
            '  - View and manage user profiles\n'
            '  - Approve access requests\n'
            '  - Manage resource access permissions\n' 
            '  - Approve and conduct training\n'
            '  - Manage training courses\n'
            '  - View resources for access management'
        )