# Operational Runbooks

This document provides step-by-step procedures for common operational tasks and troubleshooting scenarios for the Laboratory Management System.

## Table of Contents

1. [Service Operations](#service-operations)
2. [Authentication & User Management](#authentication--user-management)
3. [Database Operations](#database-operations)
4. [Background Tasks & Celery](#background-tasks--celery)
5. [Performance Issues](#performance-issues)
6. [Security Incidents](#security-incidents)
7. [Backup & Recovery](#backup--recovery)
8. [Monitoring & Health Checks](#monitoring--health-checks)
9. [Common Error Scenarios](#common-error-scenarios)

---

## Service Operations

### Starting the Application

**Prerequisites Check:**
```bash
# Verify services are running
sudo systemctl status postgresql
sudo systemctl status redis
sudo systemctl status nginx

# Check disk space
df -h

# Verify environment variables
cd /home/labitory/labitory
source venv/bin/activate
python manage.py check --deploy --settings=labitory.settings.production
```

**Start Sequence:**
```bash
# 1. Start database if not running
sudo systemctl start postgresql

# 2. Start Redis
sudo systemctl start redis

# 3. Start Celery workers
sudo systemctl start celery-labitory
sudo systemctl start celerybeat-labitory

# 4. Start web application
sudo systemctl start gunicorn-labitory

# 5. Start/reload web server
sudo systemctl start nginx
```

**Verify Startup:**
```bash
# Check all services are active
sudo systemctl status gunicorn-labitory celery-labitory celerybeat-labitory nginx

# Test health endpoints
curl http://localhost/health/
curl http://localhost/health/ready/
curl http://localhost/health/live/

# Check logs for errors
sudo journalctl -u gunicorn-labitory -f --lines=20
```

### Graceful Shutdown

**Shutdown Sequence:**
```bash
# 1. Stop accepting new requests (optional - for maintenance)
# Remove from load balancer or add maintenance page

# 2. Stop web application (allows current requests to complete)
sudo systemctl stop gunicorn-labitory

# 3. Stop background tasks
sudo systemctl stop celerybeat-labitory  # Stop scheduling new tasks
sudo systemctl stop celery-labitory      # Stop after current tasks complete

# 4. Stop supporting services if needed
sudo systemctl stop nginx
sudo systemctl stop redis
sudo systemctl stop postgresql
```

### Service Restart

**Application Only:**
```bash
# Quick restart (for code deployments)
sudo systemctl restart gunicorn-labitory

# Restart background workers
sudo systemctl restart celery-labitory
sudo systemctl restart celerybeat-labitory
```

**Full Stack Restart:**
```bash
# Stop all services
sudo systemctl stop gunicorn-labitory celery-labitory celerybeat-labitory

# Restart supporting services
sudo systemctl restart redis
sudo systemctl restart postgresql

# Start application services
sudo systemctl start celery-labitory
sudo systemctl start celerybeat-labitory
sudo systemctl start gunicorn-labitory

# Reload nginx configuration
sudo systemctl reload nginx
```

---

## Authentication & User Management

### User Account Lockout Issues

**Symptoms:**
- User reports inability to log in
- "Account locked" error messages
- Repeated failed login attempts in logs

**Investigation:**
```bash
# Check user lockout status
cd /home/labitory/labitory
source venv/bin/activate
python manage.py shell --settings=labitory.settings.production

# In Django shell:
from booking.models.auth import UserProfile
from django.contrib.auth.models import User

# Find locked users
locked_users = UserProfile.objects.filter(is_locked=True)
print(f"Locked users: {locked_users.count()}")

# Check specific user
username = "problematic_user"
try:
    user = User.objects.get(username=username)
    profile = user.profile
    print(f"User: {username}")
    print(f"Locked: {profile.is_locked}")
    print(f"Failed attempts: {profile.failed_login_attempts}")
    print(f"Last failed: {profile.last_failed_login}")
except User.DoesNotExist:
    print(f"User {username} not found")
```

**Resolution:**
```bash
# Unlock specific user
python manage.py unlock_user <username>

# Reset failed login attempts for all users (use carefully)
python manage.py shell --settings=labitory.settings.production
# In shell:
from booking.models.auth import UserProfile
UserProfile.objects.filter(is_locked=True).update(
    is_locked=False,
    failed_login_attempts=0,
    last_failed_login=None
)
```

### 2FA Issues

**Common 2FA Problems:**
1. User lost authenticator device
2. Backup codes not working
3. 2FA setup incomplete

**Investigation:**
```bash
# Check 2FA status for user
python manage.py report_2fa_status

# Check specific user 2FA setup
python manage.py shell --settings=labitory.settings.production
# In shell:
from django.contrib.auth.models import User
from django_otp.models import StaticDevice, TOTPDevice

username = "user_with_issues"
user = User.objects.get(username=username)

# Check TOTP devices
totp_devices = TOTPDevice.objects.filter(user=user)
print(f"TOTP devices: {totp_devices.count()}")

# Check backup codes
static_devices = StaticDevice.objects.filter(user=user)
for device in static_devices:
    tokens = device.token_set.filter(consumed=False)
    print(f"Unused backup codes: {tokens.count()}")
```

**Resolution:**
```bash
# Reset user's 2FA completely
python manage.py reset_2fa <username>

# Generate new backup codes only
python manage.py shell --settings=labitory.settings.production
# In shell:
from django.contrib.auth.models import User
from booking.utils.two_factor import generate_backup_codes

user = User.objects.get(username="username")
codes = generate_backup_codes(user)
print(f"New backup codes: {codes}")
```

### SSO Issues

**Symptoms:**
- Azure AD login fails
- Users created without proper role mapping
- SSO callback errors

**Investigation:**
```bash
# Check SSO configuration
grep -E "AZURE_AD|GOOGLE_OAUTH" /home/labitory/labitory/.env

# Check recent SSO logins in logs
grep -i "sso\|oauth\|azure" /var/log/gunicorn/access.log | tail -20

# Check Django logs for SSO errors
tail -f /home/labitory/labitory/logs/django.log | grep -i oauth
```

**Resolution:**
```bash
# Verify SSO settings in Django shell
python manage.py shell --settings=labitory.settings.production
# In shell:
from django.conf import settings
print(f"Azure tenant: {settings.AZURE_AD_TENANT_ID}")
print(f"Azure client: {settings.AZURE_AD_CLIENT_ID}")

# Test SSO callback URL
curl -I https://yourdomain.com/auth/sso/callback/
```

---

## Database Operations

### Database Connection Issues

**Symptoms:**
- "Connection refused" errors
- Timeouts on database queries
- Application health checks failing

**Investigation:**
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Check database connections
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"

# Check for long-running queries
sudo -u postgres psql -c "
SELECT query, query_start, state, wait_event 
FROM pg_stat_activity 
WHERE state != 'idle' 
ORDER BY query_start;
"

# Test application database connection
cd /home/labitory/labitory
source venv/bin/activate
python manage.py dbshell --settings=labitory.settings.production
```

**Resolution:**
```bash
# Restart PostgreSQL
sudo systemctl restart postgresql

# Kill problematic connections (if needed)
sudo -u postgres psql -c "
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE state = 'active' 
AND query_start < now() - interval '1 hour';
"

# Check database configuration
sudo -u postgres psql -c "SHOW all;" | grep -E "max_connections|shared_buffers"
```

### Database Performance Issues

**Symptoms:**
- Slow query response times
- High database CPU usage
- Query timeouts

**Investigation:**
```bash
# Check for slow queries
sudo -u postgres psql -c "
SELECT query, mean_exec_time, calls, total_exec_time
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;
"

# Check index usage
sudo -u postgres psql labitory_prod -c "
SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read
FROM pg_stat_user_indexes 
WHERE idx_scan = 0 
ORDER BY tablename;
"

# Check table sizes
sudo -u postgres psql labitory_prod -c "
SELECT table_name, 
       pg_size_pretty(pg_total_relation_size(table_name::regclass)) as size
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY pg_total_relation_size(table_name::regclass) DESC;
"
```

**Resolution:**
```bash
# Analyze and vacuum tables
sudo -u postgres psql labitory_prod -c "VACUUM ANALYZE;"

# Reindex if needed
sudo -u postgres psql labitory_prod -c "REINDEX DATABASE labitory_prod;"

# Update table statistics
sudo -u postgres psql labitory_prod -c "ANALYZE;"
```

---

## Background Tasks & Celery

### Celery Workers Not Processing Tasks

**Symptoms:**
- Tasks queued but not executing
- Email/SMS notifications not sending
- Reports not generating

**Investigation:**
```bash
# Check Celery worker status
sudo systemctl status celery-labitory

# Check active tasks
cd /home/labitory/labitory
source venv/bin/activate
celery -A labitory inspect active

# Check queue statistics
celery -A labitory inspect stats

# Check worker logs
sudo journalctl -u celery-labitory -f --lines=50

# Check Redis queue length
redis-cli -h 127.0.0.1 -p 6379
> LLEN celery  # Main queue length
> KEYS celery*  # See all queues
```

**Resolution:**
```bash
# Restart Celery workers
sudo systemctl restart celery-labitory

# Purge stuck tasks (use carefully)
celery -A labitory purge
# Confirm with 'yes' when prompted

# Reset worker state
celery -A labitory control pool_restart

# Check specific task status
celery -A labitory result <task_id>
```

### Celery Beat (Scheduler) Issues

**Symptoms:**
- Scheduled tasks not running
- Duplicate scheduled tasks
- Backup reports not generated

**Investigation:**
```bash
# Check Celery beat status
sudo systemctl status celerybeat-labitory

# Check beat logs
sudo journalctl -u celerybeat-labitory -f --lines=50

# Check scheduled tasks
cd /home/labitory/labitory
source venv/bin/activate
python manage.py shell --settings=labitory.settings.production
# In shell:
from celery import current_app
print(current_app.conf.beat_schedule)
```

**Resolution:**
```bash
# Restart Celery beat
sudo systemctl restart celerybeat-labitory

# Clear beat schedule (will recreate from settings)
rm -f /var/run/celery/celerybeat-schedule
sudo systemctl restart celerybeat-labitory

# Manually trigger backup
cd /home/labitory/labitory
source venv/bin/activate
python manage.py shell --settings=labitory.settings.production
# In shell:
from booking.tasks import backup_database
backup_database.delay()
```

---

## Performance Issues

### High Response Times

**Symptoms:**
- Pages loading slowly
- Timeouts in browser
- High server load

**Investigation:**
```bash
# Check system resources
top
htop
free -h
df -h

# Check web server status
sudo systemctl status nginx gunicorn-labitory

# Check response times
curl -w "@curl-format.txt" -o /dev/null -s "http://localhost/health/"
# Create curl-format.txt:
echo "time_namelookup:  %{time_namelookup}\ntime_connect:     %{time_connect}\ntime_appconnect:  %{time_appconnect}\ntime_pretransfer: %{time_pretransfer}\ntime_redirect:    %{time_redirect}\ntime_starttransfer: %{time_starttransfer}\ntime_total:       %{time_total}\n" > curl-format.txt

# Check database connections
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity;"

# Check Redis performance
redis-cli info stats
```

**Resolution:**
```bash
# Restart application services
sudo systemctl restart gunicorn-labitory

# Clear cache if issues persist
redis-cli FLUSHDB

# Scale workers if needed (edit gunicorn.conf.py)
sudo nano /home/labitory/labitory/gunicorn.conf.py
# Increase workers = 3 to workers = 5
sudo systemctl restart gunicorn-labitory

# Check for memory leaks
ps aux | grep gunicorn | awk '{print $2}' | xargs -I {} cat /proc/{}/status | grep VmRSS
```

### Memory Issues

**Symptoms:**
- High memory usage
- OOM killer messages in logs
- Application crashes

**Investigation:**
```bash
# Check memory usage
free -h
cat /proc/meminfo

# Check process memory usage
ps aux --sort=-%mem | head -20

# Check for memory leaks in Gunicorn workers
ps aux | grep "gunicorn: worker" | awk '{print $2, $4, $6}' | column -t

# Check system logs for OOM
dmesg | grep -i "killed process"
journalctl -p err -S "1 hour ago"
```

**Resolution:**
```bash
# Restart Gunicorn to clear memory
sudo systemctl restart gunicorn-labitory

# Reduce worker memory usage (edit gunicorn.conf.py)
sudo nano /home/labitory/labitory/gunicorn.conf.py
# Add: max_requests = 500, max_requests_jitter = 100

# Clear caches
redis-cli FLUSHALL

# Add swap if necessary (temporary solution)
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

## Security Incidents

### Suspicious Login Activity

**Symptoms:**
- Multiple failed login attempts
- Logins from unusual locations
- Security alert emails

**Investigation:**
```bash
# Check recent failed logins
grep "Invalid password" /var/log/auth.log | tail -20

# Check application authentication logs
cd /home/labitory/labitory
tail -f logs/security.log | grep -E "failed_login|suspicious"

# Check IP addresses with multiple failures
awk '/Invalid password/ {print $(NF-3)}' /var/log/auth.log | sort | uniq -c | sort -nr

# Check current active sessions
python manage.py shell --settings=labitory.settings.production
# In shell:
from django.contrib.sessions.models import Session
from django.utils import timezone
active_sessions = Session.objects.filter(expire_date__gte=timezone.now())
print(f"Active sessions: {active_sessions.count()}")
```

**Response:**
```bash
# Lock suspicious user accounts
python manage.py shell --settings=labitory.settings.production
# In shell:
from django.contrib.auth.models import User
from booking.models.auth import UserProfile

# Lock specific user
user = User.objects.get(username="suspicious_user")
profile = user.profile
profile.is_locked = True
profile.save()

# Block suspicious IP addresses (temporary)
sudo ufw deny from <suspicious_ip>

# Invalidate all sessions for user
user.session_set.all().delete()

# Force password reset
user.set_unusable_password()
user.save()
```

### Potential Data Breach

**Immediate Response:**
```bash
# 1. Isolate the system
sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default deny outgoing
sudo ufw allow from <admin_ip> to any port 22
sudo ufw enable

# 2. Stop all external-facing services
sudo systemctl stop nginx

# 3. Capture system state
sudo netstat -tulpn > /tmp/network_state.txt
ps aux > /tmp/process_state.txt
sudo iptables -L > /tmp/firewall_state.txt

# 4. Check for unauthorized changes
sudo find /home/labitory/labitory -type f -mtime -1 -ls
sudo find /etc -type f -mtime -1 -ls

# 5. Create forensic backup
sudo dd if=/dev/sda of=/mnt/external/forensic_$(date +%Y%m%d_%H%M%S).img
```

**Investigation:**
```bash
# Check audit logs
tail -1000 /home/labitory/labitory/logs/audit.log | grep -E "DELETE|sensitive"

# Check for unusual database activity
sudo -u postgres psql labitory_prod -c "
SELECT query, query_start, state, client_addr 
FROM pg_stat_activity 
WHERE query NOT LIKE '%pg_stat_activity%'
ORDER BY query_start;
"

# Check file integrity
sudo find /home/labitory/labitory -type f -name "*.py" -exec md5sum {} + > /tmp/current_checksums.txt
# Compare with known good checksums

# Review user access logs
grep -E "login|logout|admin" logs/django.log | tail -100
```

---

## Backup & Recovery

### Verify Backup Integrity

**Check Backup Status:**
```bash
# Check if backup task ran
cd /home/labitory/labitory
source venv/bin/activate
python manage.py shell --settings=labitory.settings.production
# In shell:
from django_celery_results.models import TaskResult
recent_backups = TaskResult.objects.filter(
    task_name='booking.tasks.backup_database',
    date_created__gte=timezone.now() - timedelta(days=7)
).order_by('-date_created')
for backup in recent_backups:
    print(f"{backup.date_created}: {backup.status}")

# Check backup files exist
ls -la /home/labitory/labitory/backups/

# Verify backup file integrity
latest_backup=$(ls -t /home/labitory/labitory/backups/backup_*.sql | head -1)
echo "Latest backup: $latest_backup"
file $latest_backup
```

**Test Backup Restoration:**
```bash
# Create test database
sudo -u postgres createdb labitory_test

# Restore to test database
sudo -u postgres psql labitory_test < $latest_backup

# Verify restoration
sudo -u postgres psql labitory_test -c "
SELECT count(*) as booking_count FROM booking_booking;
SELECT count(*) as user_count FROM auth_user;
"

# Clean up test database
sudo -u postgres dropdb labitory_test
```

### Emergency Database Recovery

**If Primary Database is Corrupted:**
```bash
# 1. Stop all services
sudo systemctl stop gunicorn-labitory celery-labitory

# 2. Backup current state (even if corrupted)
sudo -u postgres pg_dump labitory_prod > /tmp/corrupted_backup_$(date +%Y%m%d_%H%M%S).sql

# 3. Create new database
sudo -u postgres dropdb labitory_prod
sudo -u postgres createdb labitory_prod

# 4. Restore from latest good backup
latest_backup=$(ls -t /home/labitory/labitory/backups/backup_*.sql | head -1)
sudo -u postgres psql labitory_prod < $latest_backup

# 5. Run migrations (in case schema changed)
cd /home/labitory/labitory
source venv/bin/activate
python manage.py migrate --settings=labitory.settings.production

# 6. Restart services
sudo systemctl start celery-labitory
sudo systemctl start gunicorn-labitory
sudo systemctl start nginx
```

---

## Monitoring & Health Checks

### Health Check Failures

**Health Endpoints:**
- `/health/` - Basic application health
- `/health/ready/` - Readiness check (can serve traffic)
- `/health/live/` - Liveness check (application is running)

**Investigation:**
```bash
# Test each endpoint
curl -v http://localhost/health/
curl -v http://localhost/health/ready/
curl -v http://localhost/health/live/

# Check what's failing
cd /home/labitory/labitory
source venv/bin/activate
python manage.py shell --settings=labitory.settings.production
# In shell:
from django.db import connection
try:
    connection.ensure_connection()
    print("Database: OK")
except:
    print("Database: FAIL")

import redis
try:
    r = redis.Redis(host='127.0.0.1', port=6379, db=1)
    r.ping()
    print("Redis: OK")
except:
    print("Redis: FAIL")
```

**Resolution:**
```bash
# Fix database issues
sudo systemctl restart postgresql

# Fix Redis issues
sudo systemctl restart redis

# Fix application issues
sudo systemctl restart gunicorn-labitory
```

---

## Common Error Scenarios

### "Permission Denied" Errors

**File Permission Issues:**
```bash
# Check application file permissions
ls -la /home/labitory/labitory/
ls -la /home/labitory/labitory/.env

# Fix permission issues
sudo chown -R labitory:labitory /home/labitory/labitory/
chmod 640 /home/labitory/labitory/.env
chmod 750 /home/labitory/labitory/

# Check log directory permissions
ls -la /var/log/gunicorn/
sudo chown -R labitory:labitory /var/log/gunicorn/
sudo chown -R labitory:labitory /var/log/celery/
```

### SSL Certificate Issues

**Symptoms:**
- HTTPS not working
- SSL warnings in browser
- Certificate expired errors

**Investigation:**
```bash
# Check certificate status
sudo certbot certificates

# Check certificate expiration
openssl x509 -in /etc/letsencrypt/live/yourdomain.com/cert.pem -text -noout | grep "Not After"

# Test SSL configuration
curl -I https://yourdomain.com/
```

**Resolution:**
```bash
# Renew certificates
sudo certbot renew

# Force renewal if needed
sudo certbot renew --force-renewal

# Restart nginx to load new certificates
sudo systemctl restart nginx

# Test renewal automation
sudo certbot renew --dry-run
```

### Email/SMS Not Sending

**Investigation:**
```bash
# Check email configuration
cd /home/labitory/labitory
source venv/bin/activate
python manage.py shell --settings=labitory.settings.production
# In shell:
from django.core.mail import send_mail
from django.conf import settings

print(f"Email backend: {settings.EMAIL_BACKEND}")
print(f"Email host: {settings.EMAIL_HOST}")

# Test email sending
send_mail(
    'Test Email',
    'This is a test.',
    settings.DEFAULT_FROM_EMAIL,
    ['admin@yourdomain.com'],
    fail_silently=False,
)

# Check Celery email tasks
from booking.tasks import send_notification_email
result = send_notification_email.delay('test@example.com', 'Test', 'Test message')
print(f"Task ID: {result.id}")
print(f"Status: {result.status}")
```

**Common Fixes:**
```bash
# Check email credentials in .env file
grep -E "EMAIL_|SMTP_" /home/labitory/labitory/.env

# Test SMTP connection manually
telnet smtp.gmail.com 587

# Check firewall for SMTP ports
sudo ufw status | grep -E "587|465|25"

# Restart Celery workers
sudo systemctl restart celery-labitory
```

---

## Emergency Contacts

**Technical Escalation:**
- System Administrator: [Contact Information]
- Database Administrator: [Contact Information]
- Security Team: [Contact Information]

**Service Providers:**
- Hosting Provider: [Support Contact]
- Domain Registrar: [Support Contact]
- SSL Certificate Provider: [Support Contact]

**Communication Channels:**
- Status Page: [URL]
- Incident Management: [System/Process]
- Team Chat: [Channel Information]

---

## Quick Reference Commands

**Service Status:**
```bash
sudo systemctl status gunicorn-labitory celery-labitory celerybeat-labitory nginx postgresql redis
```

**Application Health:**
```bash
curl -s http://localhost/health/ | jq .
```

**View Recent Logs:**
```bash
sudo journalctl -u gunicorn-labitory -f --lines=20
tail -f /home/labitory/labitory/logs/django.log
```

**Database Quick Check:**
```bash
sudo -u postgres psql -c "SELECT version();"
sudo -u postgres psql labitory_prod -c "SELECT count(*) FROM auth_user;"
```

**Redis Quick Check:**
```bash
redis-cli ping
redis-cli info memory
```

---

*Last Updated: [Current Date]*  
*Document Version: 1.0*