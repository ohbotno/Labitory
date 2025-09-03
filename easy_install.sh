#!/bin/bash

# Labitory - Minimal Installation Script
# This script performs a bare-bones installation of Labitory
# Components: Nginx, PostgreSQL, Python, and the application code

set -e  # Exit on any error

# Ensure we're running with bash
if [ -z "$BASH_VERSION" ]; then
    echo "Error: This script must be run with bash, not sh"
    echo "Please run: bash $0"
    exit 1
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   print_error "This script must be run as root"
   exit 1
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    OS_VERSION=$VERSION_ID
else
    print_error "Cannot detect operating system"
    exit 1
fi

print_status "Detected OS: $OS $OS_VERSION"

# Get user inputs
echo ""
# Set default values (can be overridden with environment variables)
if test -z "$DOMAIN"; then
    DOMAIN="localhost"
fi

if test -z "$INSTALL_DIR"; then
    INSTALL_DIR="/opt/aperature-booking"
fi

# For non-interactive installation, try to detect the server IP
if test -z "$ALLOWED_HOSTS"; then
    # Try to get the public IP
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s icanhazip.com 2>/dev/null || hostname -I | awk '{print $1}')
    if test -n "$SERVER_IP"; then
        ALLOWED_HOSTS="localhost,127.0.0.1,$SERVER_IP"
        if test "$DOMAIN" != "localhost"; then
            ALLOWED_HOSTS="$ALLOWED_HOSTS,$DOMAIN"
        fi
    else
        ALLOWED_HOSTS="localhost,127.0.0.1"
    fi
fi

# Set CSRF trusted origins for common ports
if test -z "$CSRF_TRUSTED_ORIGINS"; then
    CSRF_TRUSTED_ORIGINS="http://localhost,http://127.0.0.1,https://localhost,https://127.0.0.1"
    if test -n "$SERVER_IP"; then
        CSRF_TRUSTED_ORIGINS="$CSRF_TRUSTED_ORIGINS,http://$SERVER_IP,https://$SERVER_IP,http://$SERVER_IP:8080,https://$SERVER_IP:8080"
    fi
    if test "$DOMAIN" != "localhost"; then
        CSRF_TRUSTED_ORIGINS="$CSRF_TRUSTED_ORIGINS,http://$DOMAIN,https://$DOMAIN,http://$DOMAIN:8080,https://$DOMAIN:8080"
    fi
fi

print_status "Using configuration:"
echo "  Domain: $DOMAIN"
echo "  Install Directory: $INSTALL_DIR"
echo "  Allowed Hosts: $ALLOWED_HOSTS"
echo "  CSRF Trusted Origins: $CSRF_TRUSTED_ORIGINS"
echo ""
print_status "To change these values, set DOMAIN, INSTALL_DIR, ALLOWED_HOSTS, and/or CSRF_TRUSTED_ORIGINS environment variables"

# Debug output
echo "DEBUG: DOMAIN is set to: '$DOMAIN'"
echo "DEBUG: INSTALL_DIR is set to: '$INSTALL_DIR'"

echo ""
print_warning "Database and admin passwords will be auto-generated"
print_warning "Check the .env file and final output for credentials"
echo ""

# Update system packages
print_status "Updating system packages..."
case $OS in
    ubuntu|debian)
        apt-get update -y
        apt-get upgrade -y
        ;;
    centos|rhel|fedora)
        yum update -y
        ;;
    *)
        print_error "Unsupported operating system: $OS"
        exit 1
        ;;
esac

# Install required packages
print_status "Installing required packages..."
case $OS in
    ubuntu|debian)
        # Install packages with explicit error checking
        apt-get install -y \
            python3 \
            python3-pip \
            python3-venv \
            postgresql \
            postgresql-contrib \
            nginx \
            git \
            curl \
            wget \
            pkg-config \
            pkgconf \
            default-libmysqlclient-dev \
            libmysqlclient-dev \
            python3-dev \
            build-essential
        
        # Verify critical packages are installed
        print_status "Verifying MySQL development packages..."
        if ! command -v pkg-config >/dev/null 2>&1; then
            print_error "pkg-config not found after installation"
            print_status "Attempting alternative installation..."
            apt-get install -y pkgconf
        fi
        
        if ! dpkg -l | grep -q libmysqlclient-dev; then
            print_error "MySQL development libraries not found"
            print_status "Attempting alternative installation..."
            apt-get install -y libmariadb-dev libmariadb-dev-compat
        fi
        
        # Final verification
        print_status "Package verification results:"
        echo "  pkg-config: $(command -v pkg-config || echo 'NOT FOUND')"
        echo "  MySQL dev libs: $(dpkg -l | grep -c 'mysql.*dev\|mariadb.*dev' || echo '0') packages found"
        ;;
    centos|rhel|fedora)
        yum install -y \
            python3 \
            python3-pip \
            postgresql \
            postgresql-server \
            postgresql-contrib \
            nginx \
            git \
            curl \
            wget \
            pkgconfig \
            mysql-devel \
            python3-devel \
            gcc \
            gcc-c++
        
        # Initialize PostgreSQL on RHEL-based systems
        postgresql-setup initdb
        ;;
esac

# Start and enable services
print_status "Starting services..."
systemctl start postgresql
systemctl enable postgresql
systemctl start nginx
systemctl enable nginx

# Create database and user
print_status "Setting up PostgreSQL database..."
DB_NAME="aperture_booking"
DB_USER="aperture_user"

# Generate database password
if test -z "$DB_PASSWORD"; then
    DB_PASSWORD=$(openssl rand -base64 32)
    print_status "Generated database password: $DB_PASSWORD"
fi

# Drop existing database and user if they exist (for clean installation)
print_status "Cleaning up existing database and user..."
sudo -u postgres psql <<EOF
DROP DATABASE IF EXISTS $DB_NAME;
DROP USER IF EXISTS $DB_USER;
\q
EOF

# Create database and user with superuser privileges
print_status "Creating database and user..."
if sudo -u postgres psql <<EOF
CREATE DATABASE $DB_NAME;
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD' SUPERUSER CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
\q
EOF
then
    print_status "Database and superuser created successfully"
    print_warning "Note: $DB_USER has superuser privileges for Django migrations"
else
    print_error "Failed to create database or user"
    exit 1
fi

# Test database connection
print_status "Testing database connection..."
if sudo -u postgres psql -d $DB_NAME -c "SELECT 1;" >/dev/null 2>&1; then
    print_status "Database connection test successful"
else
    print_error "Database connection test failed"
    exit 1
fi

# Clone the repository
print_status "Cloning Labitory from GitHub..."
if [ -d "$INSTALL_DIR" ]; then
    print_warning "Directory $INSTALL_DIR already exists"
    print_status "Removing existing directory..."
    rm -rf "$INSTALL_DIR"
fi

git clone https://github.com/ohbotno/aperature-booking.git "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Create virtual environment
print_status "Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
print_status "Installing Python dependencies..."
pip install --upgrade pip

# Set environment variables for mysqlclient compilation
export MYSQLCLIENT_CFLAGS="-I/usr/include/mysql"
export MYSQLCLIENT_LDFLAGS="-L/usr/lib/x86_64-linux-gnu -lmysqlclient"

# Try alternative paths if default doesn't exist
if [ ! -d "/usr/include/mysql" ]; then
    export MYSQLCLIENT_CFLAGS="-I/usr/include/mariadb"
    export MYSQLCLIENT_LDFLAGS="-L/usr/lib/x86_64-linux-gnu -lmariadb"
fi

print_status "Using MySQL client flags: $MYSQLCLIENT_CFLAGS $MYSQLCLIENT_LDFLAGS"

pip install -r requirements.txt
pip install gunicorn

# Create .env file
print_status "Creating environment configuration..."

# Generate secret key
SECRET_KEY=$(python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')

# Generate Django admin credentials
if test -z "$ADMIN_EMAIL"; then
    ADMIN_EMAIL="admin@$DOMAIN"
fi

if test -z "$ADMIN_PASSWORD"; then
    ADMIN_PASSWORD=$(openssl rand -base64 16)
fi

print_status "Creating .env file in $INSTALL_DIR..."
cat > .env <<EOF
# Django settings
SECRET_KEY=$SECRET_KEY
DEBUG=False
ALLOWED_HOSTS=$ALLOWED_HOSTS
CSRF_TRUSTED_ORIGINS=$CSRF_TRUSTED_ORIGINS

# Database settings
DB_ENGINE=postgresql
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_HOST=localhost
DB_PORT=5432

# Basic settings
TIME_ZONE=UTC

# Admin user details
ADMIN_EMAIL=$ADMIN_EMAIL
ADMIN_PASSWORD=$ADMIN_PASSWORD
EOF

# Debug: Show .env file contents
print_status "Verifying .env file contents:"
echo "--- .env file contents ---"
cat .env
echo "--- end of .env file ---"
echo ""

# Debug: Check file location and permissions
print_status "Checking .env file location and permissions:"
ls -la .env
echo ""

# Test if Django can read the .env file
print_status "Testing Django configuration with .env file..."
python -c "
from aperture_booking import settings
print('ALLOWED_HOSTS from Django:', settings.ALLOWED_HOSTS)
print('DB_ENGINE from Django:', settings.DB_ENGINE)
print('DEBUG from Django:', settings.DEBUG)
"
echo ""

# Run Django setup
print_status "Setting up Django application..."

# Create required directories with proper permissions
print_status "Creating required directories..."
mkdir -p logs media static staticfiles
chown www-data:www-data logs media static staticfiles
chmod 755 logs media static staticfiles

# Create log files with proper permissions
print_status "Creating log files..."
touch logs/errors.log logs/django.log
chown www-data:www-data logs/errors.log logs/django.log
chmod 664 logs/errors.log logs/django.log

python manage.py migrate
print_status "Collecting static files..."
python manage.py collectstatic --clear --noinput

# Create superuser
print_status "Creating Django admin user..."
python manage.py shell <<EOF
from django.contrib.auth import get_user_model
from booking.models import UserProfile
User = get_user_model()

# Try to get or create the admin user
try:
    admin_user = User.objects.get(username='admin')
    print("Found existing admin user")
    created = False
except User.DoesNotExist:
    try:
        admin_user = User.objects.create_superuser('admin', '$ADMIN_EMAIL', '$ADMIN_PASSWORD')
        print("Created new admin user")
        created = True
    except Exception as e:
        print(f"Error creating admin user: {e}")
        # Try to find by email instead
        try:
            admin_user = User.objects.get(email='$ADMIN_EMAIL')
            print("Found existing user by email")
            created = False
        except User.DoesNotExist:
            print("Failed to create or find admin user")
            exit(1)

# Ensure the user is a superuser
if not admin_user.is_superuser:
    admin_user.is_superuser = True
    admin_user.is_staff = True
    admin_user.save()
    print("Updated user to superuser status")

# Handle UserProfile - use get_or_create to avoid conflicts with signals
profile, profile_created = UserProfile.objects.get_or_create(
    user=admin_user,
    defaults={
        'role': 'sysadmin',
        'phone': '+0000000000',
        'staff_number': 'ADMIN001',
        'is_inducted': True,
        'email_verified': True
    }
)

if profile_created:
    print("Created UserProfile with sysadmin access")
else:
    # Update existing profile if needed
    updated = False
    if profile.role != 'sysadmin':
        profile.role = 'sysadmin'
        updated = True
    if not profile.staff_number:
        profile.staff_number = 'ADMIN001'
        updated = True
    if not profile.is_inducted:
        profile.is_inducted = True
        updated = True
    if not profile.email_verified:
        profile.email_verified = True
        updated = True
    
    if updated:
        profile.save()
        print("Updated existing UserProfile with sysadmin access")
    else:
        print("Admin user already has proper site-admin access")

print(f"Admin user setup complete - username: admin, email: {admin_user.email}")
EOF

python manage.py create_email_templates || true

# Create systemd service
print_status "Creating systemd service..."
cat > /etc/systemd/system/aperature-booking.service <<EOF
[Unit]
Description=Labitory
After=network.target postgresql.service

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/gunicorn aperture_booking.wsgi:application --bind 127.0.0.1:8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# Configure Nginx
print_status "Configuring Nginx..."

# First, ensure client_max_body_size is set in the main nginx.conf
print_status "Adding client_max_body_size to nginx.conf..."
if ! grep -q "client_max_body_size" /etc/nginx/nginx.conf; then
    # Add client_max_body_size to the http section
    sed -i '/^http {/a\    client_max_body_size 100M;' /etc/nginx/nginx.conf
    print_status "Added client_max_body_size 100M to nginx.conf"
else
    print_status "client_max_body_size already configured in nginx.conf"
fi

# Create the site configuration
cat > /etc/nginx/sites-available/aperature-booking <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    
    # Also set client_max_body_size in server block for redundancy
    client_max_body_size 100M;

    location /static/ {
        alias $INSTALL_DIR/staticfiles/;
    }

    location /media/ {
        alias $INSTALL_DIR/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Enable Nginx site
ln -sf /etc/nginx/sites-available/aperature-booking /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test nginx configuration
print_status "Testing nginx configuration..."
if nginx -t; then
    print_status "Nginx configuration is valid"
else
    print_error "Nginx configuration test failed"
    exit 1
fi

# Set permissions
print_status "Setting permissions..."
chown -R www-data:www-data "$INSTALL_DIR"
chmod -R 755 "$INSTALL_DIR"
chmod 644 "$INSTALL_DIR/.env"

# Ensure static files have correct permissions
print_status "Setting static files permissions..."
chmod -R 755 "$INSTALL_DIR/static/" "$INSTALL_DIR/staticfiles/"
chown -R www-data:www-data "$INSTALL_DIR/static/" "$INSTALL_DIR/staticfiles/"

# Reload services
print_status "Starting Labitory service..."
systemctl daemon-reload
systemctl enable aperature-booking
systemctl start aperature-booking

# Restart the service to load the new .env file
print_status "Restarting Labitory service to load .env configuration..."
systemctl restart aperature-booking
systemctl restart nginx

# Final status check
print_status "Checking service status..."
if systemctl is-active --quiet aperature-booking; then
    print_status "Labitory is running"
else
    print_error "Labitory failed to start"
    journalctl -u aperature-booking -n 50
fi

echo ""
print_status "Installation complete!"
echo ""
echo "Access your installation at: http://$DOMAIN"
echo ""
echo "=== Admin Credentials ==="
echo "Username: admin"
echo "Password: $ADMIN_PASSWORD"
echo "Email: $ADMIN_EMAIL"
echo ""
echo "=== Admin Access Points ==="
echo "Site Admin Panel: http://$DOMAIN/site-admin/"
echo "Django Admin: http://$DOMAIN/admin/"
echo ""
print_warning "IMPORTANT: Save these credentials in a secure location!"
echo ""
print_warning "For production use, you should:"
echo "  1. Configure SSL/HTTPS"
echo "  2. Set up email settings in .env"
echo "  3. Configure firewall rules"
echo "  4. Set up regular backups"
echo ""