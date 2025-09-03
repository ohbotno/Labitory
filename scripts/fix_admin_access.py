#!/usr/bin/env python
"""
Quick fix script to grant site-admin access to the admin user.
Run this from the project directory with the virtual environment activated:
    python scripts/fix_admin_access.py
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'labitory.settings')
django.setup()

from django.contrib.auth import get_user_model
from booking.models import UserProfile

User = get_user_model()

def fix_admin_access():
    # Try to find the admin user
    admin_user = None
    
    # First try username 'admin'
    try:
        admin_user = User.objects.get(username='admin')
        print(f"Found admin user: {admin_user.username} ({admin_user.email})")
    except User.DoesNotExist:
        # Try to find any superuser
        superusers = User.objects.filter(is_superuser=True)
        if superusers.exists():
            admin_user = superusers.first()
            print(f"Found superuser: {admin_user.username} ({admin_user.email})")
        else:
            print("ERROR: No admin/superuser found in the system!")
            return False
    
    # Check/create UserProfile
    if not hasattr(admin_user, 'userprofile'):
        UserProfile.objects.create(
            user=admin_user,
            role='sysadmin',
            phone='+0000000000',
            staff_number='ADMIN001',
            is_inducted=True,
            email_verified=True
        )
        print("✓ Created UserProfile with sysadmin role")
    else:
        # Update existing profile
        profile = admin_user.userprofile
        updated = False
        
        if profile.role != 'sysadmin':
            profile.role = 'sysadmin'
            updated = True
            print("✓ Updated role to sysadmin")
        
        if not profile.staff_number:
            profile.staff_number = 'ADMIN001'
            updated = True
            print("✓ Added staff number")
        
        if not profile.is_inducted:
            profile.is_inducted = True
            updated = True
            print("✓ Marked as inducted")
        
        if not profile.email_verified:
            profile.email_verified = True
            updated = True
            print("✓ Marked email as verified")
        
        if updated:
            profile.save()
        else:
            print("✓ User already has proper sysadmin access")
    
    print(f"\nAdmin user '{admin_user.username}' now has full access to:")
    print(f"  - Site Admin Panel: /site-admin/")
    print(f"  - Django Admin: /admin/")
    
    return True

if __name__ == '__main__':
    fix_admin_access()