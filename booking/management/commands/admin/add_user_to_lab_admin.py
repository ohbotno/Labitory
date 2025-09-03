#!/usr/bin/env python3
"""
Management command to add users to the Lab Admin group.

Usage:
    python manage.py add_user_to_lab_admin username1 username2 ...
    python manage.py add_user_to_lab_admin --email user@example.com
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User, Group
from django.db import transaction


class Command(BaseCommand):
    help = 'Add users to the Lab Admin group'

    def add_arguments(self, parser):
        parser.add_argument(
            'usernames',
            nargs='*',
            type=str,
            help='Usernames to add to Lab Admin group',
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Add user by email address instead of username',
        )
        parser.add_argument(
            '--list',
            action='store_true',
            help='List current Lab Admin group members',
        )
        parser.add_argument(
            '--remove',
            action='store_true',
            help='Remove users from Lab Admin group instead of adding',
        )

    def handle(self, *args, **options):
        # Get the Lab Admin group
        try:
            lab_admin_group = Group.objects.get(name='Lab Admin')
        except Group.DoesNotExist:
            raise CommandError(
                'Lab Admin group does not exist. Run "python manage.py create_lab_admin_group" first.'
            )

        # List current members if requested
        if options['list']:
            self.list_members(lab_admin_group)
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
            raise CommandError('Please provide usernames or use --email option.')

        if not users_to_process:
            self.stdout.write(self.style.WARNING('No valid users found to process.'))
            return

        # Process users
        action = 'remove' if options['remove'] else 'add'
        
        with transaction.atomic():
            for user in users_to_process:
                if options['remove']:
                    if lab_admin_group in user.groups.all():
                        user.groups.remove(lab_admin_group)
                        self.stdout.write(
                            self.style.SUCCESS(f'✓ Removed {user.username} from Lab Admin group')
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(f'User {user.username} is not in Lab Admin group')
                        )
                else:
                    if lab_admin_group not in user.groups.all():
                        user.groups.add(lab_admin_group)
                        self.stdout.write(
                            self.style.SUCCESS(f'✓ Added {user.username} to Lab Admin group')
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(f'User {user.username} is already in Lab Admin group')
                        )

        self.stdout.write(
            self.style.SUCCESS(f'\n✓ Successfully processed {len(users_to_process)} user(s)')
        )

    def list_members(self, group):
        """List current members of the Lab Admin group."""
        members = User.objects.filter(groups=group).order_by('username')
        
        if members.exists():
            self.stdout.write(f'Lab Admin group members ({members.count()}):\n')
            for user in members:
                profile_info = ''
                if hasattr(user, 'userprofile'):
                    profile_info = f' - {user.userprofile.get_role_display()}'
                
                self.stdout.write(
                    f'  • {user.username} ({user.get_full_name()}){profile_info}'
                )
        else:
            self.stdout.write('Lab Admin group has no members.')