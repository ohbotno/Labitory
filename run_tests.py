#!/usr/bin/env python
"""
Test runner for Labitory system.
Runs tests with appropriate settings and configuration.
"""
import os
import sys
import django
from django.conf import settings
from django.test.utils import get_runner

if __name__ == "__main__":
    # Set up Django settings for testing
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'booking.tests.test_settings')
    
    # Import settings after setting environment variable
    django.setup()
    
    # Get test runner and run tests
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=False, keepdb=False)
    
    # Specify which tests to run
    test_labels = sys.argv[1:] if len(sys.argv) > 1 else ['booking.tests']
    
    failures = test_runner.run_tests(test_labels)
    
    if failures:
        sys.exit(1)
    else:
        print("\n✅ All tests passed!")
        sys.exit(0)