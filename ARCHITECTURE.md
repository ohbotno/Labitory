# System Architecture Documentation

This document describes the system architecture, design decisions, and technical rationale for the Laboratory Management System (Labitory).

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Principles](#architecture-principles)
3. [System Components](#system-components)
4. [Technology Stack](#technology-stack)
5. [Database Architecture](#database-architecture)
6. [Authentication & Authorization](#authentication--authorization)
7. [Background Processing](#background-processing)
8. [Caching Strategy](#caching-strategy)
9. [Security Architecture](#security-architecture)
10. [File Storage & Media](#file-storage--media)
11. [API Design](#api-design)
12. [Performance Optimizations](#performance-optimizations)
13. [Monitoring & Observability](#monitoring--observability)
14. [Architecture Decision Records](#architecture-decision-records)

---

## System Overview

### High-Level Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Load Balancer │    │     CDN/Static  │    │   External APIs │
│     (Nginx)     │    │   File Serving  │    │ (Azure AD, SMS) │
└─────────┬───────┘    └─────────────────┘    └─────────┬───────┘
          │                                              │
          │                                              │
┌─────────▼───────┐                                      │
│   Web Layer     │                                      │
│  (Django App)   │                                      │
└─────────┬───────┘                                      │
          │                                              │
          │            ┌─────────────────┐               │
          │            │   Task Queue    │               │
          └────────────│    (Celery)     │◄──────────────┘
                       └─────────┬───────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
┌─────────▼───────┐    ┌─────────▼───────┐    ┌─────────▼───────┐
│    Database     │    │   Cache Layer   │    │  Message Broker │
│  (PostgreSQL)   │    │    (Redis)      │    │    (Redis)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Core Principles

1. **Modular Design**: Clear separation between components and domains
2. **Security by Design**: Security considerations integrated throughout
3. **Scalability**: Horizontal scaling capabilities through background processing
4. **Reliability**: Fault tolerance and graceful degradation
5. **Maintainability**: Clean code architecture and comprehensive documentation

---

## Architecture Principles

### Design Philosophy

**Domain-Driven Design (DDD)**
- Models organized by business domains (bookings, users, resources, analytics)
- Clear bounded contexts between different areas of the system
- Rich domain models with business logic encapsulation

**SOLID Principles**
- Single Responsibility: Each model/service has one clear purpose
- Open/Closed: Extensible through plugins and hooks
- Liskov Substitution: Polymorphic behavior through abstract base classes
- Interface Segregation: Specific interfaces for different use cases
- Dependency Inversion: Dependency injection for testability

**Security-First Approach**
- Defense in depth with multiple security layers
- Principle of least privilege
- Comprehensive audit logging
- Input validation at all levels

---

## System Components

### Web Application (Django)

**Architecture Pattern**: Model-View-Template (MVT) with service layer

```
┌─────────────────────────────────────────────────────────────┐
│                        Web Layer                            │
├─────────────────────────────────────────────────────────────┤
│  Views    │  Forms    │  Templates    │  Static Assets      │
├─────────────────────────────────────────────────────────────┤
│                     Service Layer                           │
├─────────────────────────────────────────────────────────────┤
│  Business Logic   │  Validation   │  Notifications          │
├─────────────────────────────────────────────────────────────┤
│                     Model Layer                             │
├─────────────────────────────────────────────────────────────┤
│  Core Models  │  Auth Models  │  Analytics  │  Audit        │
└─────────────────────────────────────────────────────────────┘
```

**Key Components:**
- **Core Models**: Bookings, Resources, Users, Maintenance
- **Authentication**: User management, 2FA, SSO integration
- **API Layer**: RESTful APIs with versioning and rate limiting
- **Admin Interface**: Customized Django admin for system management
- **Middleware**: Security, audit logging, request processing

### Background Processing (Celery)

**Worker Architecture**:
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Celery Beat   │    │  Celery Worker  │    │  Celery Worker  │
│   (Scheduler)   │    │   (General)     │    │    (Email)      │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          │              ┌───────▼───────┐              │
          └──────────────►│ Redis Message │◄─────────────┘
                         │    Broker     │
                         └───────────────┘
```

**Task Categories:**
- **Scheduled Tasks**: Backups, reports, maintenance checks
- **Event-Driven**: Notifications, status updates
- **Batch Processing**: Data exports, analytics generation
- **Integration**: External API calls, file processing

---

## Technology Stack

### Core Technologies

| Component | Technology | Version | Rationale |
|-----------|------------|---------|-----------|
| **Backend Framework** | Django | 4.2+ | Mature, secure, rapid development |
| **Database** | PostgreSQL | 13+ | ACID compliance, JSON support, performance |
| **Cache & Message Broker** | Redis | 6.0+ | High performance, persistence, pub/sub |
| **Task Queue** | Celery | 5.3+ | Robust background processing |
| **Web Server** | Nginx | 1.20+ | High performance, SSL termination |
| **WSGI Server** | Gunicorn | 20.1+ | Python WSGI HTTP server |
| **Process Manager** | Systemd | - | Reliable service management |

### Additional Libraries

**Authentication & Security:**
- `django-otp`: Two-factor authentication
- `django-ratelimit`: Rate limiting
- `cryptography`: Encryption utilities
- `pyjwt`: JWT token handling

**API & Integration:**
- `djangorestframework`: REST API framework
- `django-cors-headers`: CORS handling
- `requests`: HTTP client library
- `python-social-auth`: OAuth integration

**Background Processing:**
- `celery[redis]`: Task queue with Redis support
- `django-celery-beat`: Database-backed periodic tasks
- `django-celery-results`: Task result storage

**Monitoring & Logging:**
- `sentry-sdk`: Error tracking
- `structlog`: Structured logging
- `django-debug-toolbar`: Development debugging

---

## Database Architecture

### Schema Design Principles

**Normalization**: 3NF normalization with strategic denormalization for performance
**Constraints**: Foreign keys, check constraints, and unique constraints for data integrity
**Indexing**: Strategic indexing for query performance
**Partitioning**: Date-based partitioning for large audit tables

### Core Domain Models

```sql
-- Simplified schema representation
Users (auth_user)
├── UserProfile (booking_userprofile)
├── UserPreferences (booking_userpreferences)
└── AuthAttempts (booking_authenticationattempt)

Resources (booking_resource)
├── ResourceType (booking_resourcetype)
├── ResourceCalendar (booking_resourcecalendar)
└── MaintenanceRecord (booking_maintenancerecord)

Bookings (booking_booking)
├── BookingStatus (booking_bookingstatus)
├── BookingApproval (booking_bookingapproval)
└── BookingAttendee (booking_bookingattendee)

Analytics (booking_analyticsdata)
├── UsageStatistics (booking_usagestatistics)
└── PerformanceMetrics (booking_performancemetrics)

Audit (booking_auditlog)
├── SecurityEvent (booking_securityevent)
└── SystemLog (booking_systemlog)
```

### Database Optimization Strategies

**Index Strategy:**
```sql
-- Performance-critical indexes
CREATE INDEX CONCURRENTLY idx_booking_status_date ON booking_booking(status, start_time);
CREATE INDEX CONCURRENTLY idx_resource_availability ON booking_resource(is_active, resource_type_id);
CREATE INDEX CONCURRENTLY idx_audit_timestamp ON booking_auditlog(timestamp DESC);
CREATE INDEX CONCURRENTLY idx_user_last_login ON auth_user(last_login DESC) WHERE is_active = true;

-- Partial indexes for common queries
CREATE INDEX CONCURRENTLY idx_booking_active ON booking_booking(start_time) WHERE status = 'confirmed';
CREATE INDEX CONCURRENTLY idx_user_staff ON auth_user(username) WHERE is_staff = true;
```

**Query Optimization:**
- `select_related()` for foreign key relationships
- `prefetch_related()` for reverse foreign keys and many-to-many
- Query result caching for expensive operations
- Database connection pooling

**Data Archival:**
- Automatic archival of old audit logs
- Soft deletion with cleanup procedures
- Backup strategy with point-in-time recovery

---

## Authentication & Authorization

### Multi-Layer Authentication

```
┌─────────────────────────────────────────────────────────────┐
│                    Authentication Flow                      │
├─────────────────────────────────────────────────────────────┤
│  1. Primary Auth     │  Username/Password + Rate Limiting   │
│  2. Two-Factor Auth  │  TOTP + Backup Codes                │
│  3. SSO Integration  │  Azure AD / Google OAuth2            │
│  4. Session Mgmt     │  Secure Sessions + CSRF Protection   │
└─────────────────────────────────────────────────────────────┘
```

### Security Features

**Password Security:**
- Strong password requirements with complexity validation
- Password history to prevent reuse
- Secure password hashing (PBKDF2 with high iterations)
- Account lockout after failed attempts

**Multi-Factor Authentication:**
- TOTP (Time-based One-Time Password) support
- Backup codes for recovery
- Device management and trusted devices
- 2FA enforcement policies

**Session Security:**
- Secure session cookies (HttpOnly, Secure, SameSite)
- Session timeout and idle detection
- Concurrent session limits
- Session invalidation on security events

**Authorization Model:**
- Role-based access control (RBAC)
- Permission-based authorization
- Group-based permissions
- Resource-level access control

---

## Background Processing

### Task Architecture

**Task Categories:**

1. **Real-time Tasks** (< 5 seconds)
   - User notifications
   - Status updates
   - Cache invalidation

2. **Standard Tasks** (5-60 seconds)
   - Email sending
   - Report generation
   - Data processing

3. **Long-running Tasks** (> 1 minute)
   - Database backups
   - Large exports
   - System maintenance

**Queue Configuration:**
```python
# Celery routing
CELERY_ROUTES = {
    'booking.tasks.send_notification': {'queue': 'notifications'},
    'booking.tasks.generate_report': {'queue': 'reports'},
    'booking.tasks.backup_database': {'queue': 'maintenance'},
}
```

**Error Handling & Retry Logic:**
- Exponential backoff for retries
- Dead letter queues for failed tasks
- Task result storage and monitoring
- Alert system for critical task failures

### Scheduled Tasks

**Periodic Task Schedule:**
- **Every minute**: Health checks, urgent notifications
- **Every 5 minutes**: Cache warming, status updates
- **Hourly**: Analytics aggregation, cleanup tasks
- **Daily**: Reports, backups, maintenance
- **Weekly**: Long-term analytics, system optimization

---

## Caching Strategy

### Multi-Level Caching

```
┌─────────────────────────────────────────────────────────────┐
│                      Caching Layers                        │
├─────────────────────────────────────────────────────────────┤
│  Browser Cache     │  Static assets, API responses         │
│  CDN Cache         │  Static files, media content          │
│  Application Cache │  Database queries, computed results   │
│  Database Cache    │  Query result cache, shared buffers   │
└─────────────────────────────────────────────────────────────┘
```

### Cache Types

**Database Query Cache:**
- Cache expensive query results
- TTL-based expiration (5-60 minutes)
- Automatic invalidation on data changes
- Cache warming for critical queries

**Page Fragment Cache:**
- Template fragment caching
- User-specific cache keys
- Conditional caching based on permissions
- Cache versioning for updates

**Session Cache:**
- Redis-backed session storage
- Session data persistence
- Distributed session sharing
- Session cleanup and garbage collection

**API Response Cache:**
- HTTP response caching
- ETag-based validation
- Cache headers for client-side caching
- Rate limit bypass for cached responses

### Cache Invalidation

**Event-driven Invalidation:**
```python
# Django signals for cache invalidation
@receiver(post_save, sender=Resource)
def invalidate_resource_cache(sender, instance, **kwargs):
    cache_keys = [
        f'resource_{instance.id}',
        f'resource_list_{instance.resource_type_id}',
        'resource_availability_*'
    ]
    cache.delete_many(cache_keys)
```

---

## Security Architecture

### Defense in Depth

**Network Security:**
- HTTPS enforcement with HSTS
- Security headers (CSP, X-Frame-Options, etc.)
- Rate limiting and DDoS protection
- Firewall configuration

**Application Security:**
- Input validation and sanitization
- SQL injection prevention
- XSS protection with CSP
- CSRF protection

**Data Security:**
- Field-level encryption for sensitive data
- Encryption at rest and in transit
- Secure key management
- PII data handling

**Access Control:**
- Role-based access control
- API authentication and authorization
- Audit logging for all access
- Privilege escalation protection

### Security Monitoring

**Audit Logging:**
```python
# Comprehensive audit trail
AUDIT_EVENTS = [
    'user_login', 'user_logout', 'password_change',
    'permission_granted', 'data_accessed', 'data_modified',
    'admin_action', 'security_event', 'system_error'
]
```

**Security Headers:**
```python
SECURE_HEADERS = {
    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
    'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'",
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'X-XSS-Protection': '1; mode=block'
}
```

---

## File Storage & Media

### Storage Architecture

**Local Development:**
- File system storage for development
- Media files served by Django
- Static files collected and served

**Production:**
- Cloud storage (AWS S3, Azure Blob)
- CDN for static file delivery
- Media file processing pipeline
- Backup and redundancy

### File Processing

**Upload Validation:**
- File type validation (MIME type checking)
- File size limits by type
- Virus scanning integration
- Content validation

**Image Processing:**
- Thumbnail generation
- Format optimization
- EXIF data stripping
- Compression and resizing

**File Management:**
- Orphaned file cleanup
- Storage usage monitoring
- Backup and archival
- Access logging

---

## API Design

### RESTful API Architecture

**Design Principles:**
- RESTful resource-based URLs
- HTTP status codes for responses
- JSON data format
- Consistent error handling

**API Versioning:**
```
URL-based: /api/v1/resources/
Header-based: Accept: application/vnd.labitory.v1+json
```

**Authentication:**
- JWT token-based authentication
- API key authentication for integrations
- OAuth2 for third-party access
- Rate limiting per client

**Request/Response Format:**
```json
{
  "data": { ... },
  "meta": {
    "pagination": { "page": 1, "total": 100 },
    "version": "1.0",
    "timestamp": "2024-01-01T00:00:00Z"
  },
  "errors": []
}
```

### Security Features

**Request Signing:**
- HMAC-based request signing
- Timestamp validation
- Replay attack prevention
- Signature verification

**Rate Limiting:**
- Per-user rate limits
- Per-endpoint rate limits
- Burst protection
- Graceful degradation

---

## Performance Optimizations

### Database Optimizations

**Query Optimization:**
- Selective field loading with `only()` and `defer()`
- Bulk operations for multiple records
- Database function usage for calculations
- Connection pooling and optimization

**Index Strategy:**
- Composite indexes for multi-column queries
- Partial indexes for filtered queries
- Expression indexes for computed values
- Index monitoring and maintenance

### Application Optimizations

**Code-Level Optimizations:**
- Lazy loading of expensive operations
- Caching at multiple levels
- Asynchronous processing for non-critical tasks
- Resource pooling and reuse

**Frontend Optimizations:**
- Static file compression and minification
- Image optimization and lazy loading
- CDN usage for static assets
- Browser caching strategies

---

## Monitoring & Observability

### Application Monitoring

**Health Checks:**
- Database connectivity
- Redis availability
- External service status
- Application resource usage

**Performance Metrics:**
- Response time monitoring
- Database query performance
- Cache hit rates
- Background task metrics

**Error Tracking:**
- Sentry integration for error monitoring
- Structured logging with correlation IDs
- Performance monitoring and alerting
- User experience monitoring

### Infrastructure Monitoring

**System Metrics:**
- CPU, memory, disk usage
- Network performance
- Service availability
- Log aggregation

**Alerting:**
- Critical error notifications
- Performance threshold alerts
- Security event notifications
- Capacity planning alerts

---

## Architecture Decision Records

### ADR-001: Database Choice (PostgreSQL vs MySQL)

**Decision**: Use PostgreSQL as the primary database

**Context**: Need for ACID compliance, JSON support, and advanced features

**Rationale**:
- Superior JSON/JSONB support for flexible data structures
- Better performance for complex queries
- Stronger data integrity guarantees
- Advanced indexing capabilities (GIN, GiST)
- Better support for full-text search

**Consequences**:
- ✅ Better performance for complex queries
- ✅ JSON field support for flexible schemas
- ✅ Strong consistency guarantees
- ❌ Slightly higher memory usage
- ❌ More complex backup procedures

### ADR-002: Caching Strategy (Redis vs Memcached)

**Decision**: Use Redis for caching and message brokering

**Context**: Need for caching, session storage, and message broker

**Rationale**:
- Dual purpose as cache and message broker
- Data persistence capabilities
- Advanced data structures (lists, sets, hashes)
- Pub/sub capabilities for real-time features
- Better clustering and high availability

**Consequences**:
- ✅ Single technology for multiple use cases
- ✅ Data persistence and durability
- ✅ Rich feature set for complex caching
- ❌ Higher memory usage than Memcached
- ❌ More complex configuration

### ADR-003: Background Processing (Celery vs RQ)

**Decision**: Use Celery for background task processing

**Context**: Need for reliable background task processing

**Rationale**:
- Mature and battle-tested in production
- Advanced scheduling and routing capabilities
- Multiple broker support (Redis, RabbitMQ)
- Comprehensive monitoring and management tools
- Built-in retry and error handling

**Consequences**:
- ✅ Robust task processing capabilities
- ✅ Advanced scheduling features
- ✅ Good monitoring and debugging tools
- ❌ More complex setup and configuration
- ❌ Higher learning curve

### ADR-004: Authentication Strategy (Custom vs Third-party)

**Decision**: Hybrid approach with Django auth + 2FA + SSO

**Context**: Need for secure, flexible authentication

**Rationale**:
- Django's built-in auth for core functionality
- django-otp for two-factor authentication
- OAuth2 integration for SSO capabilities
- Maintains compatibility with Django ecosystem
- Allows for future extensibility

**Consequences**:
- ✅ Flexible authentication options
- ✅ Strong security with 2FA
- ✅ Enterprise SSO support
- ❌ Multiple authentication paths to maintain
- ❌ Complex configuration management

### ADR-005: API Design (GraphQL vs REST)

**Decision**: Use REST API with potential GraphQL addition

**Context**: Need for API access to system functionality

**Rationale**:
- REST is well-understood and standardized
- Better tooling and ecosystem support
- Easier to implement rate limiting and caching
- Simpler debugging and monitoring
- More predictable performance characteristics

**Consequences**:
- ✅ Mature tooling and ecosystem
- ✅ Better caching and rate limiting
- ✅ Easier to secure and monitor
- ❌ Multiple requests for related data
- ❌ Over-fetching or under-fetching data

---

## Future Considerations

### Scalability Improvements

**Microservices Migration:**
- Identify service boundaries
- Extract notification service
- Separate authentication service
- Implement API gateway

**Database Scaling:**
- Read replicas for query scaling
- Database sharding for data scaling
- Event sourcing for audit data
- CQRS for read/write separation

### Technology Evolution

**Container Orchestration:**
- Kubernetes deployment
- Service mesh implementation
- Auto-scaling capabilities
- Blue-green deployments

**Modern Frontend:**
- Single Page Application (SPA)
- Progressive Web App (PWA)
- Real-time updates with WebSockets
- Mobile application development

---

*Document Version: 1.0*  
*Last Updated: [Current Date]*  
*Next Review: [Schedule Review]*