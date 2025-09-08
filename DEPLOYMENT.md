# Production Deployment Guide

This guide provides comprehensive instructions for deploying the Laboratory Management System to production.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Database Configuration](#database-configuration)
4. [Redis & Celery Setup](#redis--celery-setup)
5. [Web Server Configuration](#web-server-configuration)
6. [Security Configuration](#security-configuration)
7. [Monitoring & Logging](#monitoring--logging)
8. [Deployment Process](#deployment-process)
9. [Post-Deployment Checklist](#post-deployment-checklist)
10. [Maintenance & Updates](#maintenance--updates)
11. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements
- **OS**: Ubuntu 20.04+ / CentOS 8+ / Debian 11+
- **Python**: 3.9+
- **Database**: PostgreSQL 13+ (recommended) or MySQL 8.0+
- **Cache**: Redis 6.0+
- **Memory**: 4GB RAM minimum, 8GB+ recommended
- **Storage**: 50GB+ available space
- **Network**: HTTPS capable domain

### Required Services
- Web server (Nginx recommended)
- WSGI server (Gunicorn recommended)  
- Process manager (systemd or supervisor)
- SSL certificate (Let's Encrypt recommended)

---

## Environment Setup

### 1. Create Application User
```bash
# Create dedicated user for the application
sudo useradd -m -s /bin/bash labitory
sudo usermod -aG sudo labitory

# Switch to application user
sudo -u labitory -H bash
cd ~
```

### 2. Clone Repository
```bash
git clone <repository-url> labitory
cd labitory
```

### 3. Python Environment
```bash
# Install Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Additional production packages
pip install gunicorn psycopg2-binary celery redis
```

### 4. Environment Variables
```bash
# Copy and configure environment file
cp .env.example .env
nano .env
```

**Critical Environment Variables:**
```bash
# Basic Configuration
DJANGO_ENVIRONMENT=production
SECRET_KEY=<generate-secure-key>
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Database
DB_ENGINE=postgresql
DB_NAME=labitory_prod
DB_USER=labitory_user
DB_PASSWORD=<secure-password>
DB_HOST=localhost
DB_PORT=5432

# Cache & Tasks
REDIS_URL=redis://127.0.0.1:6379/1
CELERY_BROKER_URL=redis://127.0.0.1:6379/0

# Email (example with Gmail)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-app@gmail.com
EMAIL_HOST_PASSWORD=<app-password>
DEFAULT_FROM_EMAIL=noreply@yourdomain.com

# SMS (Twilio)
TWILIO_ACCOUNT_SID=<your-account-sid>
TWILIO_AUTH_TOKEN=<your-auth-token>
TWILIO_PHONE_NUMBER=+1234567890

# Monitoring
SENTRY_DSN=<your-sentry-dsn>
APP_VERSION=2.0.0
ENVIRONMENT=production
```

---

## Database Configuration

### PostgreSQL Setup
```bash
# Install PostgreSQL
sudo apt update
sudo apt install postgresql postgresql-contrib

# Create database and user
sudo -u postgres psql
```

```sql
-- In PostgreSQL shell
CREATE DATABASE labitory_prod;
CREATE USER labitory_user WITH PASSWORD 'secure-password';
GRANT ALL PRIVILEGES ON DATABASE labitory_prod TO labitory_user;
ALTER USER labitory_user CREATEDB;  -- For running tests
\q
```

### Database Initialization
```bash
# Run migrations
python manage.py migrate --settings=labitory.settings.production

# Create superuser
python manage.py createsuperuser --settings=labitory.settings.production

# Collect static files
python manage.py collectstatic --noinput --settings=labitory.settings.production
```

---

## Redis & Celery Setup

### Install Redis
```bash
# Ubuntu/Debian
sudo apt install redis-server

# CentOS/RHEL
sudo yum install redis

# Start and enable Redis
sudo systemctl start redis
sudo systemctl enable redis

# Test Redis connection
redis-cli ping  # Should return PONG
```

### Celery Configuration

**Create Celery systemd service:**
```bash
# Create celery worker service
sudo nano /etc/systemd/system/celery-labitory.service
```

```ini
[Unit]
Description=Celery Service (Labitory)
After=network.target redis.service postgresql.service

[Service]
Type=forking
User=labitory
Group=labitory
EnvironmentFile=/home/labitory/labitory/.env
WorkingDirectory=/home/labitory/labitory
ExecStart=/home/labitory/labitory/venv/bin/celery multi start worker1 -A labitory --pidfile=/var/run/celery/%n.pid --logfile=/var/log/celery/%n.log --loglevel=INFO
ExecStop=/home/labitory/labitory/venv/bin/celery multi stopwait worker1 --pidfile=/var/run/celery/%n.pid
ExecReload=/home/labitory/labitory/venv/bin/celery multi restart worker1 -A labitory --pidfile=/var/run/celery/%n.pid --logfile=/var/log/celery/%n.log --loglevel=INFO
KillMode=mixed
TimeoutStopSec=300

[Install]
WantedBy=multi-user.target
```

**Create Celery Beat service:**
```bash
sudo nano /etc/systemd/system/celerybeat-labitory.service
```

```ini
[Unit]
Description=Celery Beat Service (Labitory)
After=network.target redis.service postgresql.service

[Service]
Type=simple
User=labitory
Group=labitory
EnvironmentFile=/home/labitory/labitory/.env
WorkingDirectory=/home/labitory/labitory
ExecStart=/home/labitory/labitory/venv/bin/celery -A labitory beat --loglevel=INFO --pidfile=/var/run/celery/celerybeat.pid --schedule=/var/run/celery/celerybeat-schedule
KillMode=mixed
TimeoutStopSec=300

[Install]
WantedBy=multi-user.target
```

**Create directories and start services:**
```bash
# Create directories
sudo mkdir -p /var/log/celery /var/run/celery
sudo chown labitory:labitory /var/log/celery /var/run/celery

# Start services
sudo systemctl daemon-reload
sudo systemctl start celery-labitory
sudo systemctl start celerybeat-labitory
sudo systemctl enable celery-labitory
sudo systemctl enable celerybeat-labitory
```

---

## Web Server Configuration

### Gunicorn Setup
```bash
# Create Gunicorn configuration
nano /home/labitory/labitory/gunicorn.conf.py
```

```python
# gunicorn.conf.py
bind = "127.0.0.1:8000"
workers = 3
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 120
keepalive = 5
preload_app = True

# Logging
accesslog = "/var/log/gunicorn/access.log"
errorlog = "/var/log/gunicorn/error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "labitory"

# Worker configuration
worker_tmp_dir = "/dev/shm"
```

**Create Gunicorn systemd service:**
```bash
sudo nano /etc/systemd/system/gunicorn-labitory.service
```

```ini
[Unit]
Description=Gunicorn daemon for Labitory
Requires=gunicorn-labitory.socket
After=network.target

[Service]
Type=notify
User=labitory
Group=labitory
RuntimeDirectory=gunicorn-labitory
WorkingDirectory=/home/labitory/labitory
EnvironmentFile=/home/labitory/labitory/.env
ExecStart=/home/labitory/labitory/venv/bin/gunicorn --config gunicorn.conf.py labitory.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

**Create Gunicorn socket:**
```bash
sudo nano /etc/systemd/system/gunicorn-labitory.socket
```

```ini
[Unit]
Description=Gunicorn socket for Labitory

[Socket]
ListenStream=/run/gunicorn-labitory.sock
SocketUser=www-data

[Install]
WantedBy=sockets.target
```

### Nginx Configuration
```bash
sudo nano /etc/nginx/sites-available/labitory
```

```nginx
upstream labitory_app {
    server 127.0.0.1:8000 fail_timeout=0;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;
    
    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    
    # SSL Security Settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_stapling on;
    ssl_stapling_verify on;
    
    # Security Headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload";
    add_header Referrer-Policy "strict-origin-when-cross-origin";
    
    # Application
    client_max_body_size 100M;
    
    location / {
        proxy_pass http://labitory_app;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Health checks (no auth required)
    location /health/ {
        proxy_pass http://labitory_app;
        access_log off;
    }
    
    # Static files
    location /static/ {
        alias /home/labitory/labitory/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # Media files
    location /media/ {
        alias /home/labitory/labitory/media/;
        expires 1y;
        add_header Cache-Control "public";
    }
    
    # Favicon
    location /favicon.ico {
        alias /home/labitory/labitory/staticfiles/images/favicon.ico;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

**Enable site and start services:**
```bash
# Create log directories
sudo mkdir -p /var/log/gunicorn
sudo chown labitory:labitory /var/log/gunicorn

# Enable Nginx site
sudo ln -s /etc/nginx/sites-available/labitory /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Start Gunicorn
sudo systemctl daemon-reload
sudo systemctl start gunicorn-labitory.socket
sudo systemctl enable gunicorn-labitory.socket
sudo systemctl start gunicorn-labitory
sudo systemctl enable gunicorn-labitory
```

---

## Security Configuration

### SSL Certificate (Let's Encrypt)
```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Test renewal
sudo certbot renew --dry-run
```

### Firewall Setup
```bash
# Configure UFW firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

### File Permissions
```bash
# Set proper permissions
chmod 750 /home/labitory/labitory
chmod 640 /home/labitory/labitory/.env
chown -R labitory:labitory /home/labitory/labitory
```

---

## Monitoring & Logging

### Log Rotation
```bash
sudo nano /etc/logrotate.d/labitory
```

```
/var/log/gunicorn/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 labitory labitory
    postrotate
        systemctl reload gunicorn-labitory
    endscript
}

/var/log/celery/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 labitory labitory
}

/home/labitory/labitory/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 labitory labitory
}
```

### Health Monitoring Script
```bash
nano /home/labitory/health_check.sh
```

```bash
#!/bin/bash
# Health check script for Labitory

# Check application health
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/health/)

if [ "$HTTP_STATUS" -eq 200 ]; then
    echo "$(date): Application is healthy (HTTP $HTTP_STATUS)"
    exit 0
else
    echo "$(date): Application is unhealthy (HTTP $HTTP_STATUS)"
    
    # Restart services if unhealthy
    sudo systemctl restart gunicorn-labitory
    sudo systemctl restart celery-labitory
    
    # Send alert (configure your alerting system)
    echo "Labitory application unhealthy - services restarted" | mail -s "Labitory Alert" admin@yourdomain.com
    
    exit 1
fi
```

```bash
# Make executable and add to crontab
chmod +x /home/labitory/health_check.sh

# Add to crontab (check every 5 minutes)
crontab -e
# Add line: */5 * * * * /home/labitory/health_check.sh >> /var/log/labitory_health.log 2>&1
```

---

## Deployment Process

### 1. Pre-deployment Checks
```bash
# Verify environment variables
python manage.py check --deploy --settings=labitory.settings.production

# Test database connection
python manage.py dbshell --settings=labitory.settings.production

# Verify static files
python manage.py collectstatic --dry-run --settings=labitory.settings.production
```

### 2. Database Migration
```bash
# Backup database
pg_dump labitory_prod > backup_$(date +%Y%m%d_%H%M%S).sql

# Run migrations
python manage.py migrate --settings=labitory.settings.production
```

### 3. Deploy Application
```bash
# Pull latest code
git pull origin main

# Install/update dependencies
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --noinput --settings=labitory.settings.production

# Restart services
sudo systemctl restart gunicorn-labitory
sudo systemctl restart celery-labitory
sudo systemctl restart celerybeat-labitory
```

---

## Post-Deployment Checklist

- [ ] Health endpoints responding (200 OK)
  - `curl https://yourdomain.com/health/`
  - `curl https://yourdomain.com/health/ready/`
  - `curl https://yourdomain.com/health/live/`

- [ ] Admin interface accessible
  - `https://yourdomain.com/admin/`

- [ ] SSL certificate valid
  - Check with SSL Labs: https://www.ssllabs.com/ssltest/

- [ ] Static files loading correctly
  - Check CSS/JS in browser developer tools

- [ ] Email notifications working
  - Test with Django shell: `python manage.py shell --settings=labitory.settings.production`

- [ ] Celery tasks processing
  - Check: `celery -A labitory inspect active`

- [ ] Database backups scheduled
  - Verify backup cron job or automated backup service

- [ ] Monitoring alerts configured
  - Sentry errors reporting
  - Health check alerts

- [ ] Performance baseline established
  - Response times measured
  - Resource usage monitored

---

## Maintenance & Updates

### Regular Maintenance Tasks

**Daily:**
- Monitor health check logs
- Review error logs
- Check disk space usage

**Weekly:**
- Review application performance metrics  
- Check SSL certificate expiration
- Verify backup integrity

**Monthly:**
- Update system packages: `sudo apt update && sudo apt upgrade`
- Review and rotate logs
- Security audit
- Performance optimization review

### Update Process
1. Create database backup
2. Test updates in staging environment
3. Schedule maintenance window
4. Deploy updates following deployment process
5. Verify all systems operational
6. Monitor for issues post-deployment

---

## Troubleshooting

### Common Issues

**Application won't start:**
```bash
# Check logs
sudo journalctl -u gunicorn-labitory -f
tail -f /var/log/gunicorn/error.log

# Check configuration
python manage.py check --deploy --settings=labitory.settings.production
```

**Database connection issues:**
```bash
# Test database connection
python manage.py dbshell --settings=labitory.settings.production

# Check PostgreSQL status
sudo systemctl status postgresql
```

**Celery tasks not processing:**
```bash
# Check Celery status
sudo systemctl status celery-labitory
celery -A labitory inspect active

# Purge and restart
celery -A labitory purge
sudo systemctl restart celery-labitory
```

**SSL certificate issues:**
```bash
# Check certificate
sudo certbot certificates

# Renew if needed
sudo certbot renew
```

### Performance Issues

**Slow response times:**
1. Check database query performance
2. Review cache hit rates
3. Analyze application profiling
4. Consider scaling resources

**High memory usage:**
1. Monitor Gunicorn worker memory
2. Check for memory leaks
3. Adjust worker configuration
4. Review cache settings

### Emergency Contacts
- System Administrator: [contact info]
- Database Administrator: [contact info]  
- Application Developer: [contact info]
- Hosting Provider Support: [contact info]

---

## Security Notes

⚠️ **Critical Security Items:**

1. **Never commit .env file to version control**
2. **Regularly rotate secrets and passwords**
3. **Monitor security logs for suspicious activity**
4. **Keep system packages updated**
5. **Use strong, unique passwords for all accounts**
6. **Enable 2FA where possible**
7. **Regular security audits and penetration testing**

---

## Support

For technical support or questions about this deployment:

- Documentation: [link to docs]
- Issue Tracker: [link to issues]
- Support Email: support@yourdomain.com

---

**Last Updated:** [Current Date]  
**Version:** 2.0.0