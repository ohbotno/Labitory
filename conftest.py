"""
Pytest configuration for Labitory tests.
"""
import pytest
import os
import django
from django.conf import settings
from django.test.utils import get_runner

# Configure Django settings for pytest
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'booking.tests.test_settings')


def pytest_configure(config):
    """Configure Django for pytest."""
    if not settings.configured:
        django.setup()


@pytest.fixture(scope='session')
def django_db_setup():
    """Set up the test database."""
    pass


@pytest.fixture
def user(db):
    """Create a test user."""
    from booking.tests.factories import UserFactory
    return UserFactory()


@pytest.fixture
def user_profile(db):
    """Create a test user profile."""
    from booking.tests.factories import UserProfileFactory
    return UserProfileFactory()


@pytest.fixture
def resource(db):
    """Create a test resource."""
    from booking.tests.factories import ResourceFactory
    return ResourceFactory()


@pytest.fixture
def booking(db):
    """Create a test booking."""
    from booking.tests.factories import BookingFactory
    return BookingFactory()


@pytest.fixture
def authenticated_client(client, user):
    """Create an authenticated client."""
    client.force_login(user)
    return client


@pytest.fixture
def api_client():
    """Create an API test client."""
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def authenticated_api_client(api_client, user):
    """Create an authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client


# Custom markers for test organization
pytest_plugins = [
    'django'
]


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their location and name."""
    for item in items:
        # Add markers based on test file names
        if 'test_models' in item.fspath.basename:
            item.add_marker(pytest.mark.models)
            item.add_marker(pytest.mark.unit)
        elif 'test_views' in item.fspath.basename:
            item.add_marker(pytest.mark.views)
            item.add_marker(pytest.mark.integration)
        elif 'test_forms' in item.fspath.basename:
            item.add_marker(pytest.mark.forms)
            item.add_marker(pytest.mark.unit)
        elif 'test_services' in item.fspath.basename:
            item.add_marker(pytest.mark.services)
            item.add_marker(pytest.mark.unit)
        elif 'test_api' in item.fspath.basename:
            item.add_marker(pytest.mark.api)
            item.add_marker(pytest.mark.integration)
        elif 'test_auth' in item.fspath.basename:
            item.add_marker(pytest.mark.auth)
        elif 'test_billing' in item.fspath.basename:
            item.add_marker(pytest.mark.billing)
        elif 'test_integration' in item.fspath.basename:
            item.add_marker(pytest.mark.integration)
        
        # Mark slow tests
        if 'backup' in item.name.lower() or 'maintenance' in item.name.lower():
            item.add_marker(pytest.mark.slow)
        
        # Mark external service tests
        if any(keyword in item.name.lower() for keyword in ['email', 'sms', 'calendar', 'google']):
            item.add_marker(pytest.mark.external)


# Test database configuration
@pytest.fixture(scope='session')
def django_db_modify_db_settings():
    """Modify database settings for testing."""
    pass


# Performance testing fixtures
@pytest.fixture
def benchmark_timer():
    """Simple benchmark timer for performance tests."""
    import time
    
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def start(self):
            self.start_time = time.time()
        
        def stop(self):
            self.end_time = time.time()
        
        @property
        def elapsed(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None
    
    return Timer()


# Mock fixtures for external services
@pytest.fixture
def mock_email_backend():
    """Mock email backend for testing."""
    from unittest.mock import Mock
    return Mock()


@pytest.fixture
def mock_sms_service():
    """Mock SMS service for testing."""
    from unittest.mock import Mock
    return Mock()


@pytest.fixture
def mock_google_calendar():
    """Mock Google Calendar service for testing."""
    from unittest.mock import Mock
    return Mock()


# Data fixtures
@pytest.fixture
def sample_booking_data():
    """Sample booking data for tests."""
    from django.utils import timezone
    from datetime import timedelta
    
    start_time = timezone.now() + timedelta(hours=1)
    end_time = start_time + timedelta(hours=2)
    
    return {
        'title': 'Test Booking',
        'description': 'Test description',
        'start_time': start_time,
        'end_time': end_time,
        'purpose': 'research'
    }


@pytest.fixture
def sample_user_data():
    """Sample user registration data for tests."""
    return {
        'username': 'testuser123',
        'email': 'test@example.com',
        'password1': 'ComplexPass123!',
        'password2': 'ComplexPass123!',
        'first_name': 'Test',
        'last_name': 'User',
        'role': 'student'
    }


# Cleanup fixtures
@pytest.fixture(autouse=True)
def cleanup_files():
    """Clean up any files created during tests."""
    yield
    # Add any cleanup logic here
    pass


# Database transaction fixtures
@pytest.fixture
def transactional_db(db):
    """Database fixture that uses transactions."""
    return db


# Cache fixtures
@pytest.fixture
def clear_cache():
    """Clear Django cache before each test."""
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()