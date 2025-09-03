#!/usr/bin/env python3
"""
Static files collection script for production deployment.

This script ensures static files are properly collected and configured
for production serving with Nginx.
"""

import os
import sys
import django
from pathlib import Path

# Add the project directory to the Python path
project_dir = Path(__file__).parent.parent
sys.path.insert(0, str(project_dir))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'labitory.settings_production')
django.setup()

from django.core.management import execute_from_command_line
from django.conf import settings
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.management.commands.collectstatic import Command as CollectStaticCommand

def collect_static_files():
    """Collect static files for production."""
    print("🔧 Collecting static files for production...")
    
    # Ensure static root directory exists
    static_root = settings.STATIC_ROOT
    os.makedirs(static_root, exist_ok=True)
    
    # Run collectstatic
    try:
        execute_from_command_line(['manage.py', 'collectstatic', '--noinput', '--clear'])
        print(f"✅ Static files collected to: {static_root}")
    except Exception as e:
        print(f"❌ Error collecting static files: {e}")
        return False
    
    return True

def verify_static_files():
    """Verify that critical static files are present."""
    print("🔍 Verifying static files...")
    
    static_root = settings.STATIC_ROOT
    critical_files = [
        'admin/css/base.css',
        'admin/js/core.js',
        'rest_framework/css/bootstrap.min.css',
        'rest_framework/js/jquery-3.7.1.min.js',
    ]
    
    missing_files = []
    for file_path in critical_files:
        full_path = os.path.join(static_root, file_path)
        if not os.path.exists(full_path):
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ Missing critical static files:")
        for file_path in missing_files:
            print(f"   - {file_path}")
        return False
    else:
        print("✅ All critical static files present")
        return True

def configure_nginx_static_serving():
    """Generate Nginx configuration snippet for static files."""
    print("📝 Generating Nginx static files configuration...")
    
    static_root = settings.STATIC_ROOT
    media_root = settings.MEDIA_ROOT
    
    nginx_config = f"""
# Static files configuration for Nginx
# Add this to your Nginx server block

# Static files (CSS, JavaScript, Images)
location {settings.STATIC_URL} {{
    alias {static_root}/;
    expires 1y;
    add_header Cache-Control "public, immutable";
    
    # Handle static file versioning
    location ~* \\.(css|js)$ {{
        expires 1y;
        add_header Cache-Control "public, immutable";
    }}
    
    location ~* \\.(jpg|jpeg|png|gif|ico|svg|webp)$ {{
        expires 1y;
        add_header Cache-Control "public, immutable";
    }}
}}

# Media files (user uploads)
location {settings.MEDIA_URL} {{
    alias {media_root}/;
    expires 1M;
    add_header Cache-Control "public";
    
    # Security: prevent execution of uploaded files
    location ~* \\.(php|py|pl|sh|cgi)$ {{
        deny all;
    }}
}}
"""
    
    config_file = os.path.join(os.path.dirname(__file__), 'nginx_static_config.conf')
    with open(config_file, 'w') as f:
        f.write(nginx_config)
    
    print(f"✅ Nginx configuration written to: {config_file}")
    return True

def check_permissions():
    """Check that static files have correct permissions."""
    print("🔐 Checking file permissions...")
    
    static_root = settings.STATIC_ROOT
    
    # Check if static root is readable by web server
    if not os.access(static_root, os.R_OK):
        print(f"❌ Static root not readable: {static_root}")
        print("   Run: sudo chown -R www-data:www-data /opt/labitory/staticfiles")
        return False
    
    # Check some critical files
    test_files = []
    for root, dirs, files in os.walk(static_root):
        for file in files[:5]:  # Check first 5 files
            test_files.append(os.path.join(root, file))
        if len(test_files) >= 5:
            break
    
    for file_path in test_files:
        if not os.access(file_path, os.R_OK):
            print(f"❌ File not readable: {file_path}")
            return False
    
    print("✅ File permissions look correct")
    return True

def display_summary():
    """Display summary information."""
    print("\n" + "=" * 50)
    print("📊 Static Files Configuration Summary")
    print("=" * 50)
    print(f"Static URL: {settings.STATIC_URL}")
    print(f"Static Root: {settings.STATIC_ROOT}")
    print(f"Media URL: {settings.MEDIA_URL}")
    print(f"Media Root: {settings.MEDIA_ROOT}")
    
    # Count static files
    static_count = 0
    static_size = 0
    for root, dirs, files in os.walk(settings.STATIC_ROOT):
        for file in files:
            static_count += 1
            static_size += os.path.getsize(os.path.join(root, file))
    
    print(f"Static Files: {static_count} files ({static_size / 1024 / 1024:.1f} MB)")
    
    print("\n📋 Next Steps:")
    print("1. Ensure Nginx is configured to serve static files")
    print("2. Check file permissions: sudo chown -R www-data:www-data /opt/labitory/staticfiles")
    print("3. Test static file serving: curl http://yoursite.com/static/admin/css/base.css")
    print("4. Monitor Nginx access logs for 404s on static files")

def main():
    """Main function."""
    print("🚀 Starting static files configuration...")
    
    success = True
    
    # Collect static files
    if not collect_static_files():
        success = False
    
    # Verify files
    if not verify_static_files():
        success = False
    
    # Generate Nginx config
    if not configure_nginx_static_serving():
        success = False
    
    # Check permissions
    if not check_permissions():
        success = False
    
    # Display summary
    display_summary()
    
    if success:
        print("\n✅ Static files configuration completed successfully!")
        return 0
    else:
        print("\n❌ Static files configuration completed with errors!")
        return 1

if __name__ == "__main__":
    exit(main())