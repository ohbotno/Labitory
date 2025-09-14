# Manual Testing Checklist for Labitory

This comprehensive checklist covers all major pages and functions in the Labitory application. Use this to ensure everything is working correctly after changes or deployment.

## 🔐 Authentication & User Management

### Login & Registration
- [x] Standard login with email/password works
- [ ] Azure SSO login works (`/auth/azure/login/`)
- [x] User registration form works (`/register/`)
- [ ] Email verification after registration
- [ ] Password reset request works (`/password-reset/`)
- [ ] Password reset via email token works
- [ ] Account lockout after failed attempts
- [x] Login redirects to intended page after authentication

### Two-Factor Authentication
- [x] 2FA setup page works (`/2fa/setup/`)
- [x] QR code generation for authenticator apps
- [x] 2FA verification during login (`/2fa/verify/`)
- [x] Backup codes generation (`/2fa/backup-codes/`)
- [x] Backup codes download (`/2fa/download-codes/`)
- [x] 2FA status page (`/2fa/status/`)
- [x] 2FA disable functionality (`/2fa/disable/`)
- [x] 2FA regenerate backup codes

### User Profile
- [x] Profile view page (`/profile/`)
- [x] Profiling works
- [x] Theme preference (light/dark mode) switching
- [x Avatar upload functionality
- [x] Department/college selection

## 📋 Dashboard & Navigation

### Main Pages
- [x] Calendar view loads correctly (`/`)
- [x] Dashboard view works (`/dashboard/`)
- [x] About page displays (`/about/`)
- [x] About page editing (admin) (`/about/edit/`)
- [x] Navigation menu works across all user roles
- [ ] Responsive design on mobile/tablet
- [x] Dark mode toggle functionality

## 🏢 Resource Management

### Resource Viewing
- [x] Resources list page (`/resources/`)
- [x] Resource detail page (`/resources/<id>/`)
- [x] Resource availability calendar view
- [x] Resource images display correctly
- [x] Resource access requirements shown

### Resource Access
- [x] Request resource access form (`/resources/<id>/request-access/`)
- [x] Access request status tracking
- [x] Training requirements display
- [x] Risk assessment requirements

### Resource Issues
- [x] Report resource issue form (`/resources/<id>/report-issue/`)
- [x] Issue tracking page (`/issues/<id>/`)
- [x] My reported issues page (`/my-issues/`)
- [x] Issues dashboard for admins (`/lab-admin/issues/`)

## 📅 Booking System

### Basic Booking Operations
- [x] Create booking form (`/booking/create/`)
- [x] Booking detail view (`/booking/<id>/`)
- [x] Edit booking form (`/booking/<id>/edit/`)
- [x] Cancel booking (`/booking/<id>/cancel/`)
- [x] Delete booking (`/booking/<id>/delete/`)
- [ ] Duplicate booking (`/booking/<id>/duplicate/`)

### Advanced Booking Features
- [ ] Recurring booking creation (`/booking/<id>/recurring/`)
- [ ] Cancel recurring series (`/booking/<id>/cancel-series/`)
- [ ] My bookings page (`/my-bookings/`)
- [ ] Bulk booking operations (`/bookings/bulk/`)
- [ ] Booking conflict detection
- [ ] Calendar invitation download

### Booking Templates
- [ ] Templates list page (`/templates/`)
- [ ] Create template (`/templates/create/`)
- [ ] Edit template (`/templates/<id>/edit/`)
- [ ] Delete template (`/templates/<id>/delete/`)
- [ ] Create booking from template (`/templates/create-booking/`)
- [ ] Save booking as template (`/booking/<id>/save-template/`)

## ✅ Check-in/Check-out System

### Check-in Operations
- [ ] Booking check-in (`/booking/<id>/checkin/`)
- [ ] Booking check-out (`/booking/<id>/checkout/`)
- [ ] Check-in status view (`/checkin-status/`)
- [ ] Resource check-in status (`/resource/<id>/checkin-status/`)
- [ ] Usage analytics view (`/usage-analytics/`)

## 📋 Approval Workflows

### Access Requests
- [x] Approval dashboard (`/approval/`)
- [x] Access requests list (`/approval/access-requests/`)
- [x] Access request detail (`/approval/access-requests/<id>/`)
- [x] Approve access request (`/approval/access-requests/<id>/approve/`)
- [x] Reject access request (`/approval/access-requests/<id>/reject/`)

### Training & Risk Assessments
- [ ] Risk assessments list (`/risk-assessments/`)
- [ ] Risk assessment detail (`/risk-assessments/<id>/`)
- [ ] Start risk assessment (`/risk-assessments/<id>/start/`)
- [ ] Submit risk assessment (`/risk-assessments/<id>/submit/`)
- [ ] Create risk assessment (`/risk-assessments/create/`)

## 🎓 Training System

### Training Courses
- [ ] Training dashboard (`/training/`)
- [ ] Training courses list (`/training/courses/`)
- [ ] Course detail page (`/training/courses/<id>/`)
- [ ] Course enrollment (`/training/courses/<id>/enroll/`)
- [ ] My training page (`/training/my-training/`)
- [ ] Training management (`/training/manage/`)

### Resource Training Requirements
- [ ] Manage resource training (`/resources/<id>/manage/`)
- [ ] Assign responsible person (`/resources/<id>/assign-responsible/`)
- [ ] Training requirements (`/resources/<id>/training-requirements/`)

## 🔧 Lab Admin Functions

### Dashboard & Overview
- [ ] Lab admin dashboard (`/lab-admin/`)
- [ ] Approval statistics (`/lab-admin/statistics/`)
- [ ] Booking management (`/lab-admin/manage/`)

### User Management
- [ ] Users list (`/lab-admin/users/`)
- [ ] User detail view (`/lab-admin/users/<id>/`)
- [ ] Edit user (`/lab-admin/users/<id>/edit/`)
- [ ] Delete user (`/lab-admin/users/<id>/delete/`)
- [ ] Toggle user status (`/lab-admin/users/<id>/toggle/`)
- [ ] Add new user (`/lab-admin/users/add/`)
- [ ] Bulk import users (`/lab-admin/users/bulk-import/`)
- [ ] Bulk user actions (`/lab-admin/users/bulk-action/`)
- [ ] Export users (`/lab-admin/users/export/`)

### Resource Management
- [ ] Resources management (`/lab-admin/resources/`)
- [ ] Add new resource (`/lab-admin/resources/add/`)
- [ ] Bulk import resources (`/lab-admin/resources/bulk-import/`)
- [ ] Edit resource (`/lab-admin/resources/<id>/edit/`)
- [ ] Resource checklist (`/lab-admin/resources/<id>/checklist/`)
- [ ] Delete resource (`/lab-admin/resources/<id>/delete/`)
- [ ] Close resource (`/lab-admin/resources/<id>/close/`)
- [ ] Open resource (`/lab-admin/resources/<id>/open/`)

### Training Management
- [ ] Lab admin training view (`/lab-admin/training/`)
- [ ] Training requirements management
- [ ] Training course management
- [ ] User training completion tracking

### Approval Rules
- [ ] Approval rules management (`/lab-admin/approval-rules/`)
- [ ] Toggle approval rules (`/lab-admin/approval-rules/<id>/toggle/`)

### Maintenance Management
- [ ] Maintenance dashboard (`/lab-admin/maintenance/`)
- [ ] Add maintenance (`/lab-admin/maintenance/add/`)
- [ ] View maintenance (`/lab-admin/maintenance/<id>/`)
- [ ] Edit maintenance (`/lab-admin/maintenance/<id>/edit/`)
- [ ] Delete maintenance (`/lab-admin/maintenance/<id>/delete/`)

### Inductions & Risk Assessments
- [ ] Inductions management (`/lab-admin/inductions/`)
- [ ] Risk assessments management (`/lab-admin/risk-assessments/`)

## 💰 Billing System

### Billing Dashboard
- [ ] Billing dashboard (`/lab-admin/billing/`)
- [ ] Billing analytics (`/lab-admin/billing/analytics/`)

### Billing Periods
- [ ] Billing periods list (`/lab-admin/billing/periods/`)
- [ ] Create billing period (`/lab-admin/billing/periods/create/`)
- [ ] Billing period detail (`/lab-admin/billing/periods/<id>/`)
- [ ] Close billing period (`/lab-admin/billing/periods/<id>/close/`)

### Billing Rates
- [ ] Billing rates management (`/lab-admin/billing/rates/`)
- [ ] Create billing rate (`/lab-admin/billing/rates/create/`)
- [ ] Edit billing rate (`/lab-admin/billing/rates/<id>/edit/`)
- [ ] Delete billing rate (`/lab-admin/billing/rates/<id>/delete/`)

### Billing Records
- [ ] Billing records list (`/lab-admin/billing/records/`)
- [ ] Confirm billing records (`/lab-admin/billing/records/confirm/`)
- [ ] User billing history (`/lab-admin/billing/users/<id>/`)
- [ ] Department billing (`/lab-admin/billing/departments/<id>/`)
- [ ] Export billing data (`/lab-admin/billing/export/`)

## 🔧 Site Admin Functions (System Admin Only)

### System Dashboard
- [ ] Site admin dashboard (`/site-admin/`)
- [ ] Health check page (`/site-admin/health-check/`)

### User Management
- [ ] Site admin users list (`/site-admin/users/`)
- [ ] Delete user (`/site-admin/users/<id>/delete/`)

### System Configuration
- [ ] System config page (`/site-admin/config/`)
- [ ] Lab settings (`/site-admin/lab-settings/`)
- [ ] Branding configuration (`/site-admin/branding/`)

### Email & SMS Configuration
- [ ] Email configuration (`/site-admin/email-config/`)
- [ ] Create email config (`/site-admin/email-config/create/`)
- [ ] Edit email config (`/site-admin/email-config/edit/<id>/`)
- [ ] Test email (`/site-admin/test-email/`)
- [ ] SMS configuration (`/site-admin/sms-config/`)
- [ ] Create SMS config (`/site-admin/sms-config/create/`)
- [ ] Edit SMS config (`/site-admin/sms-config/edit/<id>/`)

### Backup Management
- [ ] Backup management (`/site-admin/backup/`)
- [ ] Create backup (AJAX)
- [ ] Backup status (AJAX)
- [ ] Download backup
- [ ] Restore backup
- [ ] Backup automation (`/site-admin/backup/automation/`)

### Security Management
- [ ] Security dashboard (`/site-admin/security/`)
- [ ] API tokens management (`/site-admin/security/api-tokens/`)
- [ ] Revoke API tokens
- [ ] Security events (`/site-admin/security/events/`)
- [ ] Enhanced audit logs (`/site-admin/security/audit-enhanced/`)
- [ ] GDPR management (`/site-admin/security/gdpr/`)
- [ ] Export user data

### Academic Hierarchy Management
- [ ] Academic hierarchy (`/site-admin/academic-hierarchy/`)
- [ ] Faculties management (`/site-admin/faculties/`)
- [ ] Create faculty (`/site-admin/faculties/create/`)
- [ ] Edit faculty (`/site-admin/faculties/<id>/edit/`)
- [ ] Delete faculty (`/site-admin/faculties/<id>/delete/`)
- [ ] Colleges management (`/site-admin/colleges/`)
- [ ] Create college (`/site-admin/colleges/create/`)
- [ ] Edit college (`/site-admin/colleges/<id>/edit/`)
- [ ] Delete college (`/site-admin/colleges/<id>/delete/`)
- [ ] Departments management (`/site-admin/departments/`)
- [ ] Create department (`/site-admin/departments/create/`)
- [ ] Edit department (`/site-admin/departments/<id>/edit/`)
- [ ] Delete department (`/site-admin/departments/<id>/delete/`)

### Audit & Updates
- [ ] Audit logs (`/site-admin/audit/`)
- [ ] System updates (`/site-admin/updates/`)

## 📅 Calendar Features

### Calendar Integration
- [ ] Calendar export (`/calendar/export/`)
- [ ] Personal calendar feed (`/calendar/feed/<token>/`)
- [ ] Public calendar feed (`/calendar/public/<token>/`)
- [ ] Resource calendar export (`/calendar/resource/<id>/export/`)
- [ ] Calendar sync settings (`/calendar/sync-settings/`)

### Google Calendar Integration
- [ ] Google Calendar auth (`/calendar/google/auth/`)
- [ ] Google Calendar callback (`/calendar/google/callback/`)
- [ ] Google Calendar settings (`/calendar/google/settings/`)
- [ ] Google Calendar sync (`/calendar/google/sync/`)
- [ ] Google Calendar disconnect (`/calendar/google/disconnect/`)

## 🔔 Notification System

### Notifications
- [ ] Notifications list (`/notifications/`)
- [ ] Notification preferences (`/notifications/preferences/`)
- [ ] Email notifications delivery
- [ ] SMS notifications delivery
- [ ] Push notifications (if enabled)
- [ ] Emergency notifications

### Email Templates
- [ ] Email template management
- [ ] Email template preview
- [ ] Template variable substitution

## ⏳ Waiting List

### Waiting List Operations
- [ ] Waiting list view (`/waiting-list/`)
- [ ] Join waiting list (`/waiting-list/join/<resource_id>/`)
- [ ] Leave waiting list (`/waiting-list/leave/<entry_id>/`)
- [ ] Respond to availability (`/waiting-list/respond/<notification_id>/`)
- [ ] Automatic notifications when slots available
- [ ] Time-limited availability responses

## 👥 Group Management

### Group Operations (Manager Only)
- [ ] Group management view (`/groups/`)
- [ ] Group detail view (`/groups/<group_name>/`)
- [ ] Add user to group (`/groups/<group_name>/add-user/`)
- [ ] Group permissions and access control

## 🔌 API Endpoints

### Authentication API
- [ ] JWT token obtain (`/api/v1/auth/token/`)
- [ ] JWT token refresh (`/api/v1/auth/token/refresh/`)
- [ ] Token revocation (`/api/v1/auth/token/revoke/`)
- [ ] List user tokens (`/api/v1/auth/tokens/`)
- [ ] Token info (`/api/v1/auth/token/info/`)

### Data API Endpoints
- [ ] Users API (`/api/v1/users/`)
- [ ] Resources API (`/api/v1/resources/`)
- [ ] Bookings API (`/api/v1/bookings/`)
- [ ] Approval rules API (`/api/v1/approval-rules/`)
- [ ] Maintenance API (`/api/v1/maintenance/`)
- [ ] Waiting list API (`/api/v1/waiting-list/`)

### API Permissions
- [ ] API authentication required
- [ ] Role-based access control
- [ ] Rate limiting (if implemented)
- [ ] CORS handling for frontend apps

## 🔧 AJAX & Dynamic Features

### Dynamic Loading
- [ ] Load colleges AJAX (`/ajax/load-colleges/`)
- [ ] Load departments AJAX (`/ajax/load-departments/`)
- [ ] Create checklist item AJAX (`/ajax/checklist-item/create/`)
- [ ] Real-time calendar updates
- [ ] Dynamic form validation

### File Uploads
- [ ] Avatar image upload
- [ ] Resource image upload
- [ ] Risk assessment file upload
- [ ] Maintenance document upload
- [ ] CSV bulk import files

## 🛡️ Security Features

### Access Control
- [ ] Role-based page access (student/technician/sysadmin)
- [ ] Resource-level permissions
- [ ] Group-based access control
- [ ] API endpoint authorization

### Data Protection
- [ ] CSRF protection on forms
- [ ] XSS prevention
- [ ] SQL injection protection
- [ ] File upload validation
- [ ] Session security

## 📱 Mobile Responsiveness

### Mobile Interface
- [ ] Calendar view on mobile
- [ ] Booking forms on mobile
- [ ] Navigation menu on mobile
- [ ] Touch interactions
- [ ] Mobile-optimized layouts

## 🔍 Error Handling

### Error Pages
- [ ] 404 error page
- [ ] 500 error page
- [ ] Permission denied pages
- [ ] Maintenance mode (if applicable)
- [ ] User-friendly error messages

## 📊 Performance & Monitoring

### Health Checks
- [ ] Health check endpoint (`/health/`)
- [ ] Readiness check (`/health/ready/`)
- [ ] Liveness check (`/health/live/`)


---

## Testing Notes

**Date Tested:** ___________  
**Tested By:** ___________  
**Version:** ___________  
**Environment:** [ ] Development [ ] Staging [ ] Production  

**Issues Found:**
_Use this space to note any issues discovered during testing_

**Additional Comments:**
_Any additional observations or recommendations_