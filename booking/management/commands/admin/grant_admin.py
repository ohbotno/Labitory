#!/usr/bin/env python3
"""
Management command to grant or revoke site-admin privileges to users.

Usage:
    python manage.py grant_admin username1 username2 ...
    python manage.py grant_admin --email user@example.com
    python manage.py grant_admin --list
    python manage.py grant_admin --remove username
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import transaction
from booking.models import UserProfile


class Command(BaseCommand):
    help = 'Grant or revoke site-admin privileges (sysadmin role) to users'

    def add_arguments(self, parser):
        parser.add_argument(
            'usernames',
            nargs='*',
            type=str,
            help='Usernames to grant site-admin privileges',
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Grant privileges to user by email address instead of username',
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='List current site-admin users (sysadmin role)',
        )
        parser.add_argument(
            '--remove',
            action='store_true',
            help='Remove site-admin privileges instead of granting',
        )
        parser.add_argument(
            '--superuser',
            action='store_true',
            help='Also make the user a Django superuser for /admin/ access',
        )

    def handle(self, *args, **options):
        # List current site-admin users if requested
        if options['list']:
            self.list_site_admins()
            return

        # Get users to process
        users_to_process = []
        
        if options['email']:
            try:
                user = User.objects.get(email=options['email'])
                users_to_process.append(user)
            except User.DoesNotExist:
                raise CommandError(f'User with email "{options["email"]}" does not exist.')
        elif options['usernames']:
            for username in options['usernames']:
                try:
                    user = User.objects.get(username=username)
                    users_to_process.append(user)
                except User.DoesNotExist:
                    self.stdout.write(
                        self.style.ERROR(f'User "{username}" does not exist. Skipping.')
                    )
        else:
            raise CommandError('Please provide usernames, use --email option, or --list to view current site-admins.')

        if not users_to_process:
            self.stdout.write(self.style.WARNING('No valid users found to process.'))
            return

        # Process users
        action = 'remove' if options['remove'] else 'grant'
        
        with transaction.atomic():
            for user in users_to_process:
                if options['remove']:
                    self.remove_admin_privileges(user)
                else:
                    self.grant_admin_privileges(user, make_superuser=options['superuser'])

        self.stdout.write(
            self.style.SUCCESS(f'\n✓ Successfully processed {len(users_to_process)} user(s)')
        )

    def grant_admin_privileges(self, user, make_superuser=False):
        """Grant site-admin privileges to a user."""
        # Create or update UserProfile
        if not hasattr(user, 'userprofile'):
            # Generate a staff number if user doesn't have one
            staff_number = f'ADMIN{user.id:03d}'
            
            UserProfile.objects.create(
                user=user,
                role='sysadmin',
                phone='+0000000000',  # Default phone number
                staff_number=staff_number,
                is_inducted=True,
                email_verified=True
            )
            self.stdout.write(
                self.style.SUCCESS(f'✓ Created UserProfile for {user.username} with sysadmin role')
            )
        else:
            # Update existing profile
            profile = user.userprofile
            updated_fields = []
            
            if profile.role != 'sysadmin':
                profile.role = 'sysadmin'
                updated_fields.append('role to sysadmin')
            
            if not profile.staff_number:
                profile.staff_number = f'ADMIN{user.id:03d}'
                updated_fields.append('staff number')
            
            if not profile.is_inducted:
                profile.is_inducted = True
                updated_fields.append('induction status')
            
            if not profile.email_verified:
                profile.email_verified = True
                updated_fields.append('email verification')
            
            if updated_fields:
                profile.save()
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Updated {user.username}: {", ".join(updated_fields)}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'User {user.username} already has site-admin privileges')
                )

        # Make Django superuser if requested
        if make_superuser and not user.is_superuser:
            user.is_superuser = True
            user.is_staff = True
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f'✓ Made {user.username} a Django superuser')
            )

        # Show access information
        access_info = ['/site-admin/']
        if user.is_superuser:
            access_info.append('/admin/')
        
        self.stdout.write(f'  → {user.username} can now access: {", ".join(access_info)}')

    def remove_admin_privileges(self, user):
        """Remove site-admin privileges from a user."""
        if hasattr(user, 'userprofile'):
            profile = user.userprofile
            if profile.role == 'sysadmin':
                # Change role to researcher (common fallback)
                profile.role = 'researcher'
                profile.save()
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Removed site-admin privileges from {user.username}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'User {user.username} does not have site-admin privileges')
                )
        else:
            self.stdout.write(
                self.style.WARNING(f'User {user.username} has no UserProfile')
            )

    def list_site_admins(self):
        """List current site-admin users."""
        sysadmin_profiles = UserProfile.objects.filter(role='sysadmin').select_related('user')
        
        if sysadmin_profiles.exists():
            self.stdout.write(f'Site-Admin users ({sysadmin_profiles.count()}):\n')
            for profile in sysadmin_profiles.order_by('user__username'):
                user = profile.user
                superuser_status = ' (Django Superuser)' if user.is_superuser else ''
                staff_number = f' - Staff #{profile.staff_number}' if profile.staff_number else ''
                
                self.stdout.write(
                    f'  • {user.username} ({user.get_full_name()}){staff_number}{superuser_status}'
                )
                self.stdout.write(f'    Email: {user.email}')
                self.stdout.write(f'    Inducted: {"Yes" if profile.is_inducted else "No"}')
                self.stdout.write(f'    Email Verified: {"Yes" if profile.email_verified else "No"}')
                self.stdout.write('')
        else:
            self.stdout.write('No site-admin users found.')