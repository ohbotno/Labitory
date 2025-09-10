# Disaster Recovery Plan

This document outlines the disaster recovery procedures for the Laboratory Management System to ensure business continuity and minimize downtime during critical incidents.

## Table of Contents

1. [Recovery Objectives](#recovery-objectives)
2. [Disaster Classification](#disaster-classification)
3. [Recovery Team Structure](#recovery-team-structure)
4. [Backup & Recovery Procedures](#backup--recovery-procedures)
5. [Infrastructure Failure Scenarios](#infrastructure-failure-scenarios)
6. [Data Recovery Procedures](#data-recovery-procedures)
7. [Communication Protocols](#communication-protocols)
8. [Testing & Validation](#testing--validation)
9. [Post-Incident Procedures](#post-incident-procedures)
10. [Emergency Contacts](#emergency-contacts)

---

## Recovery Objectives

### Service Level Definitions

| **Metric** | **Target** | **Maximum Acceptable** | **Critical Systems** |
|------------|------------|------------------------|----------------------|
| **RTO** (Recovery Time Objective) | 2 hours | 4 hours | Authentication, Core Booking |
| **RPO** (Recovery Point Objective) | 15 minutes | 1 hour | User data, Bookings, Audit logs |
| **MTTR** (Mean Time to Repair) | 1 hour | 2 hours | Database, Web application |
| **Availability** | 99.5% | 99.0% | Overall system availability |

### Business Impact Assessment

**Critical Functions** (Must be restored within 2 hours):
- User authentication and authorization
- Booking creation and management
- Resource availability checking
- Emergency notifications

**Important Functions** (Must be restored within 4 hours):
- Reporting and analytics
- Admin functions
- File uploads and media
- Integration APIs

**Nice-to-Have Functions** (Can be restored within 24 hours):
- Advanced reporting features
- Historical data analysis
- Non-critical integrations

---

## Disaster Classification

### Level 1: Minor Service Disruption
**Impact**: Single component failure, < 30 minutes downtime  
**Examples**: Single worker failure, minor database issue  
**Response**: On-call engineer, automated recovery  

### Level 2: Major Service Disruption  
**Impact**: Multiple components affected, 30 minutes - 2 hours downtime  
**Examples**: Database failure, web server crash, network issues  
**Response**: Incident team activation, manual intervention required  

### Level 3: Complete Service Outage
**Impact**: Complete system unavailable, > 2 hours downtime  
**Examples**: Data center failure, major security breach, data corruption  
**Response**: Full disaster recovery team, emergency procedures  

### Level 4: Catastrophic Failure
**Impact**: Infrastructure destroyed, data loss potential  
**Examples**: Natural disaster, complete data center loss, major security incident  
**Response**: Business continuity plan, alternative site activation  

---

## Recovery Team Structure

### Primary Response Team

**Incident Commander** (Decision Authority)
- Name: [Primary Contact]
- Phone: [Emergency Number]
- Email: [Email Address]
- Responsibilities: Overall incident coordination, communication, decisions

**Technical Lead** (System Recovery)
- Name: [Technical Contact]
- Phone: [Emergency Number]
- Email: [Email Address]
- Responsibilities: Technical recovery coordination, system restoration

**Database Administrator** (Data Recovery)
- Name: [DBA Contact]
- Phone: [Emergency Number]
- Email: [Email Address]
- Responsibilities: Database recovery, data integrity validation

**Security Lead** (Security Assessment)
- Name: [Security Contact]
- Phone: [Emergency Number]
- Email: [Email Address]
- Responsibilities: Security assessment, breach containment

### Secondary Response Team

**Infrastructure Specialist**
- Responsibilities: Network, hardware, cloud infrastructure

**Communications Coordinator** 
- Responsibilities: User communications, stakeholder updates

**Business Liaison**
- Responsibilities: Business impact assessment, user coordination

---

## Backup & Recovery Procedures

### Backup Strategy

**Database Backups:**
```bash
# Automated daily backups via Celery
BACKUP_SCHEDULE = {
    'full_backup': '0 2 * * *',      # Daily at 2 AM
    'incremental': '0 */6 * * *',    # Every 6 hours
    'transaction_log': '*/15 * * * *' # Every 15 minutes
}
```

**Backup Locations:**
- Primary: Local server `/home/labitory/labitory/backups/`
- Secondary: Cloud storage (AWS S3/Azure Blob)
- Tertiary: Off-site physical storage (weekly)

**Backup Types:**
1. **Full Database Backup** (Daily)
   - Complete PostgreSQL dump
   - Includes schema and all data
   - Compressed and encrypted

2. **Incremental Backup** (6 hours)
   - WAL (Write-Ahead Log) archiving
   - Point-in-time recovery capability
   - Minimal storage overhead

3. **File System Backup** (Weekly)
   - Media files and uploads
   - Configuration files
   - Application code (for rollback)

### Backup Verification

**Automated Verification:**
```bash
#!/bin/bash
# Daily backup verification script
BACKUP_FILE="/home/labitory/labitory/backups/backup_$(date +%Y%m%d).sql"

# Test backup integrity
pg_dump_verify() {
    # Create test database
    sudo -u postgres createdb labitory_test_$(date +%H%M)
    
    # Restore backup
    sudo -u postgres psql labitory_test_$(date +%H%M) < "$BACKUP_FILE"
    
    # Verify data integrity
    ROW_COUNT=$(sudo -u postgres psql labitory_test_$(date +%H%M) -t -c "SELECT count(*) FROM auth_user;")
    
    if [ "$ROW_COUNT" -gt 0 ]; then
        echo "✅ Backup verification successful: $ROW_COUNT users found"
        sudo -u postgres dropdb labitory_test_$(date +%H%M)
        return 0
    else
        echo "❌ Backup verification failed: No users found"
        return 1
    fi
}
```

### Recovery Procedures

**Database Recovery:**

1. **Point-in-Time Recovery:**
```bash
# Stop application services
sudo systemctl stop gunicorn-labitory celery-labitory

# Create recovery database
sudo -u postgres createdb labitory_recovery

# Restore base backup
sudo -u postgres pg_restore -d labitory_recovery /path/to/base_backup.sql

# Apply WAL files for point-in-time recovery
sudo -u postgres pg_wal-replay --target-time="2024-01-01 12:00:00" labitory_recovery

# Validate data integrity
sudo -u postgres psql labitory_recovery -c "SELECT count(*) FROM auth_user;"
sudo -u postgres psql labitory_recovery -c "SELECT count(*) FROM booking_booking;"

# Switch to recovery database
sudo -u postgres psql -c "ALTER DATABASE labitory_prod RENAME TO labitory_old;"
sudo -u postgres psql -c "ALTER DATABASE labitory_recovery RENAME TO labitory_prod;"

# Restart services
sudo systemctl start celery-labitory
sudo systemctl start gunicorn-labitory
```

2. **Full System Recovery:**
```bash
# Recovery from complete backup
sudo -u postgres dropdb labitory_prod
sudo -u postgres createdb labitory_prod

# Restore from latest full backup
LATEST_BACKUP=$(ls -t /home/labitory/labitory/backups/backup_*.sql | head -1)
sudo -u postgres psql labitory_prod < "$LATEST_BACKUP"

# Run any necessary migrations
cd /home/labitory/labitory
source venv/bin/activate
python manage.py migrate --settings=labitory.settings.production

# Verify data integrity
python manage.py check --settings=labitory.settings.production
```

---

## Infrastructure Failure Scenarios

### Web Server Failure

**Symptoms:**
- HTTP 502/503 errors
- Connection timeouts
- Load balancer health checks failing

**Recovery Steps:**
```bash
# 1. Assess the situation
sudo systemctl status gunicorn-labitory nginx
curl -I http://localhost/health/

# 2. Restart services
sudo systemctl restart gunicorn-labitory
sudo systemctl restart nginx

# 3. Check logs for root cause
sudo journalctl -u gunicorn-labitory -f --lines=50
tail -f /var/log/nginx/error.log

# 4. If restart fails, check configuration
nginx -t
python manage.py check --deploy --settings=labitory.settings.production

# 5. Restore from backup if configuration corrupted
git checkout HEAD -- /etc/nginx/sites-available/labitory
sudo systemctl reload nginx
```

### Database Server Failure

**Primary Database Down:**
```bash
# 1. Immediate assessment
sudo systemctl status postgresql
sudo -u postgres pg_isready

# 2. Attempt restart
sudo systemctl restart postgresql

# 3. If restart fails, check logs
sudo journalctl -u postgresql -f --lines=100

# 4. Database corruption recovery
sudo -u postgres pg_resetwal /var/lib/postgresql/13/main

# 5. If complete failure, restore from backup
sudo systemctl stop postgresql
sudo mv /var/lib/postgresql/13/main /var/lib/postgresql/13/main.backup
sudo -u postgres initdb /var/lib/postgresql/13/main
sudo systemctl start postgresql
# Restore from latest backup (see Database Recovery section)
```

### Redis Cache/Message Broker Failure

**Redis Server Down:**
```bash
# 1. Check Redis status
sudo systemctl status redis
redis-cli ping

# 2. Restart Redis
sudo systemctl restart redis

# 3. Verify Redis data persistence
redis-cli LASTSAVE
redis-cli BGSAVE

# 4. If data loss occurred, warm up cache
cd /home/labitory/labitory
source venv/bin/activate
python manage.py shell --settings=labitory.settings.production
# Execute cache warming scripts
```

### Network Connectivity Issues

**Network Outage:**
```bash
# 1. Test connectivity
ping 8.8.8.8
dig yourdomain.com
nslookup yourdomain.com

# 2. Check network interfaces
ip addr show
sudo systemctl status networking

# 3. Restart networking if needed
sudo systemctl restart networking

# 4. Check firewall rules
sudo ufw status
sudo iptables -L

# 5. Contact ISP/hosting provider if external issue
```

### Storage Failure

**Disk Space Issues:**
```bash
# 1. Check disk usage
df -h
du -sh /home/labitory/labitory/*

# 2. Clean up temporary files
find /tmp -type f -mtime +7 -delete
docker system prune -f  # If using Docker

# 3. Rotate and compress logs
sudo logrotate -f /etc/logrotate.d/labitory

# 4. Archive old backups
find /home/labitory/labitory/backups -name "*.sql" -mtime +30 -exec gzip {} \;

# 5. Move to alternative storage if critical
rsync -av /home/labitory/labitory/backups/ user@backup-server:/backups/
```

---

## Data Recovery Procedures

### User Data Recovery

**Accidental Data Deletion:**
```sql
-- Check audit logs for deletion events
SELECT * FROM booking_auditlog 
WHERE action = 'DELETE' 
AND timestamp > NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC;

-- Find deleted user data
SELECT * FROM booking_auditlog 
WHERE table_name = 'auth_user' 
AND action = 'DELETE'
AND object_id = 'USER_ID';

-- Recovery process
-- 1. Restore from point-in-time backup before deletion
-- 2. Extract specific records from backup
-- 3. Insert into current database with conflict resolution
```

**Data Corruption Recovery:**
```bash
# 1. Identify corruption scope
sudo -u postgres psql labitory_prod -c "
SELECT tablename, n_tup_ins, n_tup_upd, n_tup_del 
FROM pg_stat_user_tables 
ORDER BY tablename;
"

# 2. Check data integrity
cd /home/labitory/labitory
source venv/bin/activate
python manage.py shell --settings=labitory.settings.production
# Run data integrity checks

# 3. Restore affected tables from backup
sudo -u postgres pg_dump labitory_prod --table=corrupted_table > corrupted_table_backup.sql
sudo -u postgres psql labitory_prod -c "DROP TABLE corrupted_table CASCADE;"
# Restore table from clean backup
sudo -u postgres psql labitory_prod < clean_table_backup.sql
```

### Configuration Recovery

**Application Configuration:**
```bash
# 1. Backup current configuration
cp /home/labitory/labitory/.env /home/labitory/labitory/.env.corrupted

# 2. Restore from version control
cd /home/labitory/labitory
git stash
git checkout HEAD -- .env.example
# Manually restore values from backup

# 3. Validate configuration
python manage.py check --deploy --settings=labitory.settings.production

# 4. Restart services
sudo systemctl restart gunicorn-labitory celery-labitory
```

---

## Communication Protocols

### Internal Communication

**Incident Declaration:**
1. Incident Commander declares incident level
2. Technical team notified via emergency contacts
3. Status page updated with initial information
4. Stakeholders notified based on incident level

**Communication Channels:**
- **Primary**: Emergency phone numbers
- **Secondary**: Email distribution lists
- **Tertiary**: Team chat/messaging systems
- **Public**: Status page and website notifications

### External Communication

**User Notifications:**

**Level 1 Incident:**
- No user notification required
- Internal monitoring only

**Level 2 Incident:**
```
Subject: [SERVICE NOTICE] Temporary Service Degradation

We are currently experiencing some performance issues with the Laboratory Management System. 
Our technical team is working to resolve the issue. 

Estimated Resolution: [TIME]
Current Status: [DESCRIPTION]

We will provide updates every 30 minutes until resolved.

Labitory Support Team
```

**Level 3/4 Incident:**
```
Subject: [URGENT] Laboratory Management System Unavailable

The Laboratory Management System is currently unavailable due to technical issues.
All laboratory bookings and access may be affected.

IMMEDIATE ACTIONS REQUIRED:
- Contact your laboratory supervisor for emergency access
- Refer to backup procedures for critical operations
- Monitor this page for updates: [STATUS_PAGE_URL]

Estimated Resolution: [TIME]
Next Update: [TIME]

For urgent issues, contact: [EMERGENCY_CONTACT]

Labitory Emergency Response Team
```

### Stakeholder Communication Matrix

| **Incident Level** | **Stakeholders** | **Notification Time** | **Update Frequency** |
|-------------------|------------------|----------------------|---------------------|
| Level 1 | Technical team only | Immediate | As needed |
| Level 2 | Technical team, Management | Within 15 minutes | Every 30 minutes |
| Level 3 | All stakeholders, Users | Within 5 minutes | Every 15 minutes |
| Level 4 | Executive team, Media | Immediate | Continuous |

---

## Testing & Validation

### Regular Testing Schedule

**Monthly Disaster Recovery Drill:**
- Simulate database failure and recovery
- Test backup restoration procedures
- Validate communication protocols
- Document lessons learned

**Quarterly Business Continuity Test:**
- Full system recovery simulation
- Alternative site activation (if applicable)
- End-to-end user workflow testing
- Stakeholder communication exercise

**Annual DR Plan Review:**
- Update contact information
- Review and update procedures
- Validate backup strategies
- Update RTO/RPO objectives

### Testing Procedures

**Backup Recovery Test:**
```bash
#!/bin/bash
# Monthly backup recovery test script

echo "Starting disaster recovery test: $(date)"

# 1. Create test environment
TEST_DB="labitory_dr_test_$(date +%Y%m%d)"
sudo -u postgres createdb $TEST_DB

# 2. Restore from latest backup
LATEST_BACKUP=$(ls -t /home/labitory/labitory/backups/backup_*.sql | head -1)
echo "Testing backup: $LATEST_BACKUP"
sudo -u postgres psql $TEST_DB < "$LATEST_BACKUP"

# 3. Validate data integrity
USER_COUNT=$(sudo -u postgres psql $TEST_DB -t -c "SELECT count(*) FROM auth_user;")
BOOKING_COUNT=$(sudo -u postgres psql $TEST_DB -t -c "SELECT count(*) FROM booking_booking;")

echo "Users restored: $USER_COUNT"
echo "Bookings restored: $BOOKING_COUNT"

# 4. Test application connectivity
export DATABASE_URL="postgresql://postgres@localhost/$TEST_DB"
cd /home/labitory/labitory
source venv/bin/activate
python manage.py check --settings=labitory.settings.development

# 5. Cleanup
sudo -u postgres dropdb $TEST_DB

echo "Disaster recovery test completed: $(date)"
```

**Communication Test:**
```bash
# Test emergency notification system
python manage.py shell --settings=labitory.settings.production
# In shell:
from booking.tasks import send_emergency_notification
result = send_emergency_notification.delay(
    'Disaster Recovery Test',
    'This is a test of the emergency notification system.',
    ['admin@yourdomain.com']
)
print(f"Test notification sent: {result.id}")
```

---

## Post-Incident Procedures

### Immediate Post-Recovery

**System Validation Checklist:**
- [ ] All services operational and responding
- [ ] Database integrity verified
- [ ] User authentication working
- [ ] Critical business functions available
- [ ] Monitoring and alerting restored
- [ ] Backup systems re-enabled
- [ ] Security controls validated

**Data Integrity Verification:**
```bash
# Post-recovery data validation script
cd /home/labitory/labitory
source venv/bin/activate

python manage.py shell --settings=labitory.settings.production
# In Django shell:
from django.contrib.auth.models import User
from booking.models import Booking, Resource

# Verify user data
user_count = User.objects.count()
print(f"Total users: {user_count}")

# Verify booking data
booking_count = Booking.objects.count()
active_bookings = Booking.objects.filter(status='confirmed').count()
print(f"Total bookings: {booking_count}")
print(f"Active bookings: {active_bookings}")

# Verify resource data
resource_count = Resource.objects.filter(is_active=True).count()
print(f"Active resources: {resource_count}")

# Check for data consistency issues
inconsistent_bookings = Booking.objects.filter(
    start_time__gt=F('end_time')
).count()
print(f"Inconsistent bookings: {inconsistent_bookings}")
```

### Incident Post-Mortem

**Post-Mortem Meeting (Within 48 hours):**
1. **Timeline Review**: Detailed incident timeline
2. **Root Cause Analysis**: Technical and process failures
3. **Response Evaluation**: What worked, what didn't
4. **Impact Assessment**: Business and user impact
5. **Action Items**: Preventive measures and improvements

**Post-Mortem Report Template:**
```markdown
# Incident Post-Mortem Report

## Incident Overview
- **Date/Time**: [INCIDENT_DATETIME]
- **Duration**: [TOTAL_DOWNTIME]
- **Severity**: Level [1-4]
- **Root Cause**: [PRIMARY_CAUSE]

## Timeline
- [TIME]: Initial incident detected
- [TIME]: Response team notified
- [TIME]: Issue identified
- [TIME]: Recovery initiated
- [TIME]: Service restored
- [TIME]: Full functionality confirmed

## Impact Assessment
- **Users Affected**: [NUMBER/PERCENTAGE]
- **Services Impacted**: [LIST_SERVICES]
- **Data Loss**: [YES/NO - DETAILS]
- **Business Impact**: [DESCRIPTION]

## Root Cause Analysis
[DETAILED_TECHNICAL_ANALYSIS]

## Response Evaluation
### What Went Well
- [LIST_POSITIVES]

### What Could Be Improved
- [LIST_IMPROVEMENTS]

## Action Items
| Action | Owner | Due Date | Priority |
|--------|-------|----------|----------|
| [ACTION_1] | [PERSON] | [DATE] | [HIGH/MED/LOW] |

## Lessons Learned
[KEY_TAKEAWAYS]
```

### Follow-up Actions

**Immediate Actions (24-48 hours):**
- Update monitoring and alerting
- Patch identified vulnerabilities
- Improve backup procedures
- Document new procedures

**Short-term Actions (1-2 weeks):**
- Implement additional monitoring
- Update disaster recovery procedures
- Conduct additional staff training
- Test identified improvements

**Long-term Actions (1-3 months):**
- Infrastructure improvements
- Process automation
- Redundancy implementation
- Annual DR plan updates

---

## Emergency Contacts

### Primary Emergency Contacts

**24/7 Emergency Hotline**: [EMERGENCY_NUMBER]

**Incident Commander**
- Name: [PRIMARY_COMMANDER]
- Mobile: [MOBILE_NUMBER]
- Email: [EMAIL]
- Alternate: [BACKUP_COMMANDER]

**Technical Emergency Contacts**

| Role | Primary Contact | Backup Contact |
|------|----------------|----------------|
| System Administrator | [NAME] - [PHONE] | [NAME] - [PHONE] |
| Database Administrator | [NAME] - [PHONE] | [NAME] - [PHONE] |
| Security Lead | [NAME] - [PHONE] | [NAME] - [PHONE] |
| Network Administrator | [NAME] - [PHONE] | [NAME] - [PHONE] |

### External Service Providers

**Hosting Provider**
- Provider: [PROVIDER_NAME]
- Support: [SUPPORT_NUMBER]
- Account: [ACCOUNT_INFO]
- SLA: [SLA_DETAILS]

**Internet Service Provider**
- Provider: [ISP_NAME]
- Support: [SUPPORT_NUMBER]
- Account: [ACCOUNT_INFO]

**Cloud Services**
- AWS Support: [AWS_SUPPORT]
- Azure Support: [AZURE_SUPPORT]
- Account IDs: [ACCOUNT_IDS]

### Escalation Matrix

**Level 1**: On-call engineer handles incident
**Level 2**: Technical lead and incident commander notified
**Level 3**: Management and business stakeholders involved
**Level 4**: Executive team and external authorities notified

### Communication Channels

**Primary**: Emergency phone numbers
**Secondary**: Email distribution lists
- technical-emergency@yourdomain.com
- management-alerts@yourdomain.com
- all-staff@yourdomain.com

**Tertiary**: Messaging systems
- Slack: #emergency-response
- Microsoft Teams: Emergency Response Team

**Public Communication**:
- Status Page: status.yourdomain.com
- Twitter: @yourdomain_status
- Website Banner: yourdomain.com

---

## Appendices

### Appendix A: Emergency Contact Cards
*Print and distribute to all team members*

### Appendix B: Quick Reference Procedures
*Laminated cards for common scenarios*

### Appendix C: Vendor Contact Information
*Complete list of all service providers*

### Appendix D: Recovery Time Estimates
*Detailed breakdown by scenario*

---

*Document Version: 1.0*  
*Last Updated: [CURRENT_DATE]*  
*Next Review: [REVIEW_DATE]*  
*Document Owner: [OWNER_NAME]*  
*Approved By: [APPROVER_NAME]*