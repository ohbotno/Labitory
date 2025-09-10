# API Documentation

Complete documentation for the Laboratory Management System REST API.

## Table of Contents

1. [API Overview](#api-overview)
2. [Authentication](#authentication)
3. [Rate Limiting](#rate-limiting)
4. [Response Format](#response-format)
5. [Error Handling](#error-handling)
6. [API Endpoints](#api-endpoints)
7. [SDK Examples](#sdk-examples)
8. [Security Features](#security-features)
9. [Versioning](#versioning)
10. [Testing](#testing)

---

## API Overview

The Labitory API is a RESTful API that provides access to laboratory resource management functionality. The API follows REST principles with JSON data format and HTTP status codes.

### Base URL
```
Production: https://yourdomain.com/api/v1/
Development: http://localhost:8000/api/v1/
```

### Supported Formats
- **Request**: JSON (`application/json`)
- **Response**: JSON (`application/json`)

### HTTP Methods
- `GET` - Retrieve resources
- `POST` - Create new resources
- `PUT` - Update entire resources
- `PATCH` - Partial resource updates
- `DELETE` - Remove resources

---

## Authentication

The API supports multiple authentication methods for different use cases.

### JWT Token Authentication (Recommended)

**Step 1: Obtain Token**
```http
POST /api/v1/auth/token/
Content-Type: application/json

{
    "username": "your_username",
    "password": "your_password"
}
```

**Response:**
```json
{
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "access_token_expiry": "2024-01-01T15:30:00Z",
    "refresh_token_expiry": "2024-01-08T15:00:00Z",
    "user": {
        "id": 123,
        "username": "your_username",
        "email": "user@example.com"
    }
}
```

**Step 2: Use Access Token**
```http
GET /api/v1/resources/
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Step 3: Refresh Token (when access token expires)**
```http
POST /api/v1/auth/token/refresh/
Content-Type: application/json

{
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

### Token Management Endpoints

**Get Token Information:**
```http
GET /api/v1/auth/token/info/
Authorization: Bearer <access_token>
```

**List All User Tokens:**
```http
GET /api/v1/auth/tokens/
Authorization: Bearer <access_token>
```

**Revoke Specific Token:**
```http
POST /api/v1/auth/token/revoke/
Authorization: Bearer <access_token>
Content-Type: application/json

{
    "token_jti": "token_identifier"
}
```

**Revoke All Tokens:**
```http
POST /api/v1/auth/token/revoke-all/
Authorization: Bearer <access_token>
```

### API Key Authentication (Legacy)

For server-to-server integrations:

```http
GET /api/v1/resources/
Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
```

---

## Rate Limiting

API endpoints are protected by rate limiting to ensure fair usage and system stability.

### Rate Limit Quotas

| Endpoint Group | Rate Limit | Window |
|----------------|------------|---------|
| Authentication | 10 requests | 5 minutes |
| User Profiles | 50 requests | 1 hour |
| Resources | 100 requests | 1 hour |
| Bookings | 30 requests | 1 hour |
| Maintenance | 40 requests | 1 hour |
| Approval Rules | 20 requests | 1 hour |
| Waiting List | 25 requests | 1 hour |

### Rate Limit Headers

All API responses include rate limiting information:

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1640995200
X-RateLimit-Group: resources
```

### Rate Limit Exceeded Response

```json
{
    "error": {
        "code": "rate_limit_exceeded",
        "message": "Rate limit exceeded. Try again in 45 minutes.",
        "details": {
            "limit": 100,
            "window": "1 hour",
            "reset_time": "2024-01-01T16:00:00Z"
        }
    }
}
```

---

## Response Format

All API responses follow a consistent format for both success and error cases.

### Success Response Format

```json
{
    "data": {
        // Resource data or array of resources
    },
    "meta": {
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total_pages": 5,
            "total_count": 89
        },
        "version": "v1",
        "timestamp": "2024-01-01T12:00:00Z"
    }
}
```

### Pagination

List endpoints support pagination with query parameters:

```http
GET /api/v1/bookings/?page=2&page_size=10
```

**Pagination Metadata:**
```json
{
    "data": [...],
    "meta": {
        "pagination": {
            "page": 2,
            "page_size": 10,
            "total_pages": 15,
            "total_count": 147,
            "has_next": true,
            "has_previous": true,
            "next_page": 3,
            "previous_page": 1
        }
    }
}
```

---

## Error Handling

### HTTP Status Codes

| Status Code | Description |
|-------------|-------------|
| 200 | OK - Request successful |
| 201 | Created - Resource created successfully |
| 204 | No Content - Successful deletion |
| 400 | Bad Request - Invalid request data |
| 401 | Unauthorized - Authentication required |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Resource not found |
| 409 | Conflict - Resource conflict |
| 429 | Too Many Requests - Rate limit exceeded |
| 500 | Internal Server Error - Server error |

### Error Response Format

```json
{
    "error": {
        "code": "validation_error",
        "message": "Invalid input data",
        "details": {
            "field_errors": {
                "email": ["Enter a valid email address"],
                "start_time": ["Start time cannot be in the past"]
            },
            "non_field_errors": ["End time must be after start time"]
        },
        "timestamp": "2024-01-01T12:00:00Z",
        "request_id": "req_123456789"
    }
}
```

### Common Error Codes

| Error Code | Description |
|------------|-------------|
| `invalid_credentials` | Invalid username/password |
| `token_expired` | JWT token has expired |
| `token_invalid` | JWT token is malformed |
| `validation_error` | Request data validation failed |
| `permission_denied` | Insufficient permissions |
| `resource_not_found` | Requested resource doesn't exist |
| `resource_conflict` | Resource state conflict |
| `rate_limit_exceeded` | API rate limit exceeded |

---

## API Endpoints

### User Profiles

#### List User Profiles
```http
GET /api/v1/users/
Authorization: Bearer <token>
```

**Query Parameters:**
- `search` - Search by username or email
- `role` - Filter by user role
- `group` - Filter by user group

**Response:**
```json
{
    "data": [
        {
            "id": 1,
            "user": {
                "id": 123,
                "username": "john_doe",
                "email": "john@example.com",
                "first_name": "John",
                "last_name": "Doe"
            },
            "role": "student",
            "group": "Chemistry",
            "phone_number": "+1234567890",
            "training_level": "basic",
            "created_at": "2024-01-01T12:00:00Z"
        }
    ],
    "meta": {
        "pagination": {...}
    }
}
```

#### Get User Profile
```http
GET /api/v1/users/{id}/
Authorization: Bearer <token>
```

#### Update Theme Preference
```http
POST /api/v1/users/update-theme/
Authorization: Bearer <token>
Content-Type: application/json

{
    "theme": "dark"
}
```

**Response:**
```json
{
    "success": true,
    "theme": "dark",
    "message": "Theme preference updated successfully."
}
```

### Resources

#### List Resources
```http
GET /api/v1/resources/
Authorization: Bearer <token>
```

**Query Parameters:**
- `resource_type` - Filter by resource type
- `requires_induction` - Filter by induction requirement
- `required_training_level` - Filter by training level
- `search` - Search by name or description

**Response:**
```json
{
    "data": [
        {
            "id": 1,
            "name": "Microscope Lab A",
            "description": "Advanced optical microscope",
            "resource_type": "equipment",
            "location": "Room 101",
            "capacity": 1,
            "requires_induction": true,
            "required_training_level": "intermediate",
            "booking_advance_days": 7,
            "max_booking_duration": "04:00:00",
            "is_active": true,
            "created_at": "2024-01-01T12:00:00Z"
        }
    ]
}
```

#### Get Available Resources
```http
GET /api/v1/resources/available/
Authorization: Bearer <token>
```

Returns only resources available to the authenticated user based on their training level and permissions.

#### Create Resource (Admin Only)
```http
POST /api/v1/resources/
Authorization: Bearer <token>
Content-Type: application/json

{
    "name": "New Equipment",
    "description": "Description of the equipment",
    "resource_type": "equipment",
    "location": "Room 102",
    "capacity": 2,
    "requires_induction": false,
    "required_training_level": "basic"
}
```

#### Update Resource (Admin Only)
```http
PUT /api/v1/resources/{id}/
Authorization: Bearer <token>
Content-Type: application/json

{
    "name": "Updated Equipment Name",
    "description": "Updated description"
}
```

#### Delete Resource (Admin Only)
```http
DELETE /api/v1/resources/{id}/
Authorization: Bearer <token>
```

### Bookings

#### List Bookings
```http
GET /api/v1/bookings/
Authorization: Bearer <token>
```

**Query Parameters:**
- `resource` - Filter by resource ID
- `status` - Filter by booking status
- `start_date` - Filter bookings after this date (YYYY-MM-DD)
- `end_date` - Filter bookings before this date (YYYY-MM-DD)
- `user` - Filter by user ID (admin only)

**Response:**
```json
{
    "data": [
        {
            "id": 1,
            "resource": {
                "id": 1,
                "name": "Microscope Lab A"
            },
            "user": {
                "id": 123,
                "username": "john_doe"
            },
            "title": "Research Session",
            "description": "Analyzing samples",
            "start_time": "2024-01-02T09:00:00Z",
            "end_time": "2024-01-02T11:00:00Z",
            "status": "confirmed",
            "created_at": "2024-01-01T15:00:00Z",
            "attendees_count": 2
        }
    ]
}
```

#### Create Booking
```http
POST /api/v1/bookings/
Authorization: Bearer <token>
Content-Type: application/json

{
    "resource": 1,
    "title": "Research Session",
    "description": "Analyzing biological samples",
    "start_time": "2024-01-02T09:00:00Z",
    "end_time": "2024-01-02T11:00:00Z",
    "attendees": [123, 124]
}
```

**Response:**
```json
{
    "data": {
        "id": 42,
        "resource": 1,
        "title": "Research Session",
        "status": "pending",
        "approval_required": true,
        "estimated_approval_time": "2024-01-01T18:00:00Z"
    }
}
```

#### Update Booking
```http
PUT /api/v1/bookings/{id}/
Authorization: Bearer <token>
Content-Type: application/json

{
    "title": "Updated Research Session",
    "description": "Updated description",
    "end_time": "2024-01-02T12:00:00Z"
}
```

#### Cancel Booking
```http
DELETE /api/v1/bookings/{id}/
Authorization: Bearer <token>
```

### Maintenance Records

#### List Maintenance Records
```http
GET /api/v1/maintenance/
Authorization: Bearer <token>
```

**Query Parameters:**
- `resource` - Filter by resource ID
- `status` - Filter by maintenance status
- `scheduled_date` - Filter by scheduled date

**Response:**
```json
{
    "data": [
        {
            "id": 1,
            "resource": {
                "id": 1,
                "name": "Microscope Lab A"
            },
            "title": "Regular Calibration",
            "description": "Monthly calibration procedure",
            "maintenance_type": "calibration",
            "scheduled_date": "2024-01-15T10:00:00Z",
            "estimated_duration": "02:00:00",
            "status": "scheduled",
            "vendor": "Calibration Co.",
            "cost": "150.00",
            "created_at": "2024-01-01T12:00:00Z"
        }
    ]
}
```

#### Create Maintenance Record (Admin Only)
```http
POST /api/v1/maintenance/
Authorization: Bearer <token>
Content-Type: application/json

{
    "resource": 1,
    "title": "Emergency Repair",
    "description": "Fix broken component",
    "maintenance_type": "repair",
    "scheduled_date": "2024-01-05T14:00:00Z",
    "estimated_duration": "03:00:00",
    "vendor": "Repair Services Ltd",
    "estimated_cost": "250.00"
}
```

### Waiting List

#### List Waiting List Entries
```http
GET /api/v1/waiting-list/
Authorization: Bearer <token>
```

**Query Parameters:**
- `resource` - Filter by resource ID
- `status` - Filter by entry status

#### Join Waiting List
```http
POST /api/v1/waiting-list/
Authorization: Bearer <token>
Content-Type: application/json

{
    "resource": 1,
    "preferred_start_time": "2024-01-02T09:00:00Z",
    "preferred_end_time": "2024-01-02T11:00:00Z",
    "notification_preferences": ["email", "sms"]
}
```

#### Leave Waiting List
```http
DELETE /api/v1/waiting-list/{id}/
Authorization: Bearer <token>
```

### Approval Rules (Admin Only)

#### List Approval Rules
```http
GET /api/v1/approval-rules/
Authorization: Bearer <token>
```

#### Create Approval Rule
```http
POST /api/v1/approval-rules/
Authorization: Bearer <token>
Content-Type: application/json

{
    "resource_type": "equipment",
    "condition": "duration > 2 hours",
    "approver_role": "technician",
    "auto_approve": false,
    "priority": 1
}
```

---

## SDK Examples

### Python SDK Example

```python
import requests
from datetime import datetime, timezone

class LabitoryAPI:
    def __init__(self, base_url, username, password):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.access_token = None
        self.refresh_token = None
        self.authenticate(username, password)
    
    def authenticate(self, username, password):
        """Authenticate and get JWT tokens."""
        url = f"{self.base_url}/api/v1/auth/token/"
        data = {"username": username, "password": password}
        
        response = self.session.post(url, json=data)
        response.raise_for_status()
        
        tokens = response.json()
        self.access_token = tokens['access_token']
        self.refresh_token = tokens['refresh_token']
        
        # Set default authorization header
        self.session.headers.update({
            'Authorization': f'Bearer {self.access_token}'
        })
    
    def refresh_access_token(self):
        """Refresh the access token using refresh token."""
        url = f"{self.base_url}/api/v1/auth/token/refresh/"
        data = {"refresh_token": self.refresh_token}
        
        response = self.session.post(url, json=data)
        response.raise_for_status()
        
        tokens = response.json()
        self.access_token = tokens['access_token']
        self.refresh_token = tokens['refresh_token']
        
        self.session.headers.update({
            'Authorization': f'Bearer {self.access_token}'
        })
    
    def get_resources(self, **filters):
        """Get list of resources with optional filters."""
        url = f"{self.base_url}/api/v1/resources/"
        response = self.session.get(url, params=filters)
        response.raise_for_status()
        return response.json()
    
    def create_booking(self, resource_id, title, start_time, end_time, **kwargs):
        """Create a new booking."""
        url = f"{self.base_url}/api/v1/bookings/"
        data = {
            "resource": resource_id,
            "title": title,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            **kwargs
        }
        
        response = self.session.post(url, json=data)
        response.raise_for_status()
        return response.json()
    
    def get_my_bookings(self):
        """Get current user's bookings."""
        url = f"{self.base_url}/api/v1/bookings/"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

# Usage example
api = LabitoryAPI("https://yourdomain.com", "username", "password")

# Get available resources
resources = api.get_resources(resource_type="equipment")
print(f"Found {len(resources['data'])} resources")

# Create a booking
booking = api.create_booking(
    resource_id=1,
    title="Research Session",
    start_time=datetime(2024, 1, 2, 9, 0, tzinfo=timezone.utc),
    end_time=datetime(2024, 1, 2, 11, 0, tzinfo=timezone.utc),
    description="Analyzing samples"
)
print(f"Created booking {booking['data']['id']}")
```

### JavaScript SDK Example

```javascript
class LabitoryAPI {
    constructor(baseUrl, username, password) {
        this.baseUrl = baseUrl.replace(/\/$/, '');
        this.accessToken = null;
        this.refreshToken = null;
        this.authenticate(username, password);
    }
    
    async authenticate(username, password) {
        const response = await fetch(`${this.baseUrl}/api/v1/auth/token/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username, password }),
        });
        
        if (!response.ok) {
            throw new Error('Authentication failed');
        }
        
        const tokens = await response.json();
        this.accessToken = tokens.access_token;
        this.refreshToken = tokens.refresh_token;
    }
    
    async makeRequest(endpoint, options = {}) {
        const url = `${this.baseUrl}/api/v1${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${this.accessToken}`,
            ...options.headers,
        };
        
        const response = await fetch(url, {
            ...options,
            headers,
        });
        
        if (response.status === 401) {
            // Token expired, try to refresh
            await this.refreshAccessToken();
            // Retry the request
            return this.makeRequest(endpoint, options);
        }
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error?.message || 'Request failed');
        }
        
        return response.json();
    }
    
    async refreshAccessToken() {
        const response = await fetch(`${this.baseUrl}/api/v1/auth/token/refresh/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ refresh_token: this.refreshToken }),
        });
        
        if (!response.ok) {
            throw new Error('Token refresh failed');
        }
        
        const tokens = await response.json();
        this.accessToken = tokens.access_token;
        this.refreshToken = tokens.refresh_token;
    }
    
    async getResources(filters = {}) {
        const params = new URLSearchParams(filters);
        return this.makeRequest(`/resources/?${params}`);
    }
    
    async createBooking(bookingData) {
        return this.makeRequest('/bookings/', {
            method: 'POST',
            body: JSON.stringify(bookingData),
        });
    }
    
    async getMyBookings() {
        return this.makeRequest('/bookings/');
    }
}

// Usage example
const api = new LabitoryAPI('https://yourdomain.com', 'username', 'password');

// Get resources
api.getResources({ resource_type: 'equipment' })
    .then(data => console.log(`Found ${data.data.length} resources`))
    .catch(error => console.error('Error:', error));

// Create booking
api.createBooking({
    resource: 1,
    title: 'Research Session',
    start_time: '2024-01-02T09:00:00Z',
    end_time: '2024-01-02T11:00:00Z',
    description: 'Analyzing samples'
})
.then(data => console.log(`Created booking ${data.data.id}`))
.catch(error => console.error('Error:', error));
```

### cURL Examples

**Authenticate:**
```bash
curl -X POST https://yourdomain.com/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "your_username", "password": "your_password"}'
```

**Get Resources:**
```bash
curl -X GET https://yourdomain.com/api/v1/resources/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Create Booking:**
```bash
curl -X POST https://yourdomain.com/api/v1/bookings/ \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "resource": 1,
    "title": "Research Session",
    "start_time": "2024-01-02T09:00:00Z",
    "end_time": "2024-01-02T11:00:00Z",
    "description": "Analyzing samples"
  }'
```

---

## Security Features

### Request Signing (Optional)

For high-security integrations, the API supports HMAC request signing:

```python
import hashlib
import hmac
import base64
from datetime import datetime

def sign_request(method, path, body, secret_key, timestamp=None):
    if timestamp is None:
        timestamp = int(datetime.utcnow().timestamp())
    
    # Create string to sign
    string_to_sign = f"{method}\n{path}\n{body}\n{timestamp}"
    
    # Create signature
    signature = hmac.new(
        secret_key.encode('utf-8'),
        string_to_sign.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    return base64.b64encode(signature).decode('utf-8'), timestamp

# Usage
signature, timestamp = sign_request(
    'POST', 
    '/api/v1/bookings/', 
    '{"resource": 1, "title": "Test"}',
    'your_secret_key'
)

headers = {
    'Authorization': 'Bearer YOUR_TOKEN',
    'X-Signature': signature,
    'X-Timestamp': str(timestamp),
    'Content-Type': 'application/json'
}
```

### IP Whitelisting

Contact your administrator to configure IP whitelisting for additional security.

### Audit Logging

All API requests are logged for security auditing. Logs include:
- User identification
- Request details (method, path, IP)
- Response status
- Timestamp
- User agent

---

## Versioning

### URL Versioning (Current)
```
https://yourdomain.com/api/v1/resources/
https://yourdomain.com/api/v2/resources/  # Future version
```

### Header Versioning (Alternative)
```http
GET /api/resources/
Accept: application/vnd.labitory.v1+json
```

### Version Lifecycle

- **v1**: Current stable version
- **v2**: Planned future version with enhanced features
- **Deprecation**: 6 months notice before version retirement
- **Support**: Last 2 versions maintained

---

## Testing

### Testing Endpoints

The API provides testing utilities in development:

**Health Check:**
```http
GET /api/v1/health/
```

**API Status:**
```http
GET /api/v1/status/
```

### Test Data

Development environments include test data for integration testing:

```bash
# Create test data (development only)
curl -X POST https://dev.yourdomain.com/api/v1/test-data/create/ \
  -H "Authorization: Bearer DEV_TOKEN"

# Reset test data
curl -X POST https://dev.yourdomain.com/api/v1/test-data/reset/ \
  -H "Authorization: Bearer DEV_TOKEN"
```

### Postman Collection

Download the Postman collection for interactive API testing:
[Download Postman Collection](https://yourdomain.com/api/postman-collection.json)

---

## Support

### API Support

- **Documentation**: This document and inline API documentation
- **Support Email**: api-support@yourdomain.com
- **Status Page**: status.yourdomain.com
- **Issues**: Report bugs via GitHub issues

### Best Practices

1. **Always use HTTPS** in production
2. **Store tokens securely** - never in client-side code
3. **Implement token refresh** logic for long-running applications
4. **Handle rate limits** gracefully with exponential backoff
5. **Validate responses** and handle errors appropriately
6. **Monitor API usage** and performance
7. **Keep credentials secure** and rotate regularly

### Rate Limit Best Practices

```python
import time
import random

def api_request_with_backoff(api_func, *args, **kwargs):
    max_retries = 3
    base_delay = 1
    
    for attempt in range(max_retries):
        try:
            return api_func(*args, **kwargs)
        except RateLimitError as e:
            if attempt == max_retries - 1:
                raise
            
            # Exponential backoff with jitter
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            time.sleep(delay)
```

---

*Document Version: 1.0*  
*Last Updated: [Current Date]*  
*API Version: v1*  
*Contact: api-support@yourdomain.com*