# booking/management/commands/import_users_csv.py
"""
Management command to import users from CSV file.

This command allows bulk import of users with their profiles from a CSV file.
CSV format should include: username,email,first_name,last_name,role,group,faculty_code,college_code,department_code,student_id,staff_number,training_level
"""

import csv
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import transaction, IntegrityError
from booking.models import UserProfile, Faculty, College, Department

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import users from CSV file with profile information'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to CSV file')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without actually importing',
        )
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Update existing users instead of skipping them',
        )
        parser.add_argument(
            '--default-password',
            type=str,
            default='ChangeMe123!',
            help='Default password for new users',
        )

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        dry_run = options['dry_run']
        update_existing = options['update_existing']
        default_password = options['default_password']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))

        try:
            with open(csv_file, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                users_data = list(reader)
        except FileNotFoundError:
            raise CommandError(f'CSV file not found: {csv_file}')
        except Exception as e:
            raise CommandError(f'Error reading CSV file: {str(e)}')

        # Validate CSV headers
        required_headers = ['username', 'email', 'first_name', 'last_name', 'role']
        optional_headers = [
            'group', 'faculty_code', 'college_code', 'department_code',
            'student_id', 'staff_number', 'training_level', 'phone'
        ]
        
        if not users_data:
            raise CommandError('CSV file is empty')
        
        headers = users_data[0].keys()
        missing_headers = [h for h in required_headers if h not in headers]
        if missing_headers:
            raise CommandError(f'Missing required headers: {", ".join(missing_headers)}')

        self.stdout.write(f'Found {len(users_data)} users in CSV file')
        
        # Process users
        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0

        with transaction.atomic():
            for row_num, user_data in enumerate(users_data, start=1):
                try:
                    result = self.process_user(user_data, update_existing, default_password, dry_run)
                    if result == 'created':
                        created_count += 1
                    elif result == 'updated':
                        updated_count += 1
                    elif result == 'skipped':
                        skipped_count += 1
                except Exception as e:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(f'Error processing row {row_num}: {str(e)}')
                    )
                    logger.error(f'Error importing user from row {row_num}: {str(e)}')

            if dry_run:
                # Rollback transaction for dry run
                transaction.set_rollback(True)

        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS(f'Import Summary:'))
        if not dry_run:
            self.stdout.write(f'  Created: {created_count} users')
            self.stdout.write(f'  Updated: {updated_count} users')
        else:
            self.stdout.write(f'  Would create: {created_count} users')
            self.stdout.write(f'  Would update: {updated_count} users')
        self.stdout.write(f'  Skipped: {skipped_count} users')
        self.stdout.write(f'  Errors: {error_count} users')

    def process_user(self, user_data, update_existing, default_password, dry_run):
        """Process a single user from CSV data."""
        username = user_data['username'].strip()
        email = user_data['email'].strip()
        
        if not username or not email:
            raise ValueError('Username and email are required')

        # Check if user exists
        user_exists = User.objects.filter(username=username).exists()
        email_exists = User.objects.filter(email=email).exists()

        if user_exists and not update_existing:
            self.stdout.write(f'  Skipping existing user: {username}')
            return 'skipped'

        if email_exists and User.objects.get(email=email).username != username:
            raise ValueError(f'Email {email} already exists for different user')

        # Prepare user data
        user_fields = {
            'username': username,
            'email': email,
            'first_name': user_data.get('first_name', '').strip(),
            'last_name': user_data.get('last_name', '').strip(),
        }

        # Prepare profile data
        role = user_data.get('role', 'student').strip().lower()
        if role not in ['student', 'researcher', 'academic', 'technician', 'sysadmin']:
            raise ValueError(f'Invalid role: {role}')

        profile_fields = {
            'role': role,
            'group': user_data.get('group', '').strip(),
            'student_id': user_data.get('student_id', '').strip() or None,
            'staff_number': user_data.get('staff_number', '').strip() or None,
            'training_level': int(user_data.get('training_level', 1)),
            'phone': user_data.get('phone', '').strip(),
            'is_inducted': True,  # Default to inducted for bulk imports
            'email_verified': True,  # Default to verified for bulk imports
        }

        # Handle academic hierarchy
        faculty_code = user_data.get('faculty_code', '').strip()
        college_code = user_data.get('college_code', '').strip()
        department_code = user_data.get('department_code', '').strip()

        faculty = None
        college = None
        department = None

        if faculty_code:
            faculty = Faculty.objects.filter(code=faculty_code).first()
            if not faculty:
                self.stdout.write(
                    self.style.WARNING(f'  Faculty not found: {faculty_code} for user {username}')
                )

        if college_code:
            college_filter = {'code': college_code}
            if faculty:
                college_filter['faculty'] = faculty
            college = College.objects.filter(**college_filter).first()
            if not college:
                self.stdout.write(
                    self.style.WARNING(f'  College not found: {college_code} for user {username}')
                )

        if department_code:
            department_filter = {'code': department_code}
            if college:
                department_filter['college'] = college
            department = Department.objects.filter(**department_filter).first()
            if not department:
                self.stdout.write(
                    self.style.WARNING(f'  Department not found: {department_code} for user {username}')
                )

        profile_fields.update({
            'faculty': faculty,
            'college': college,
            'department': department,
        })

        if dry_run:
            if user_exists:
                self.stdout.write(f'  Would update user: {username} ({email})')
                return 'updated'
            else:
                self.stdout.write(f'  Would create user: {username} ({email})')
                return 'created'

        # Create or update user
        if user_exists:
            user = User.objects.get(username=username)
            for field, value in user_fields.items():
                setattr(user, field, value)
            user.save()

            # Update profile
            try:
                profile = user.userprofile
                for field, value in profile_fields.items():
                    setattr(profile, field, value)
                profile.save()
            except UserProfile.DoesNotExist:
                UserProfile.objects.create(user=user, **profile_fields)

            self.stdout.write(f'  Updated user: {username}')
            return 'updated'
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=default_password,
                first_name=user_fields['first_name'],
                last_name=user_fields['last_name'],
            )

            # Create profile (should be created by signal, but ensure it exists)
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults=profile_fields
            )
            if not created:
                for field, value in profile_fields.items():
                    setattr(profile, field, value)
                profile.save()

            self.stdout.write(f'  Created user: {username}')
            return 'created'

    def validate_csv_format(self, file_path):
        """Validate CSV file format and return sample data."""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                sample_rows = []
                for i, row in enumerate(reader):
                    if i < 3:  # Get first 3 rows as sample
                        sample_rows.append(row)
                    else:
                        break
                return sample_rows, reader.fieldnames
        except Exception as e:
            raise CommandError(f'Error validating CSV file: {str(e)}')