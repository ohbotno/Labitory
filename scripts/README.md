# Scripts Directory

This directory contains utility scripts for Labitory administration and maintenance.

## Available Scripts

### fix_admin_access.py
Quick fix script to grant site-admin access to admin users.

**Purpose:** Ensures admin/superuser accounts have proper UserProfile with sysadmin role for accessing the site-admin panel.

**Usage:**
```bash
# Run from the project root directory
python scripts/fix_admin_access.py
```

**When to use:**
- After initial installation if admin can't access /site-admin/
- When troubleshooting admin access issues
- For emergency admin access recovery

**What it does:**
- Finds admin/superuser accounts
- Creates or updates UserProfile with sysadmin role
- Sets required fields (staff_number, is_inducted, email_verified)
- Ensures access to both /site-admin/ and /admin/ panels