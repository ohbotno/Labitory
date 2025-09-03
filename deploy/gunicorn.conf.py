"""
Gunicorn configuration file for Labitory production deployment.

This configuration file provides production-ready settings for running
Django with Gunicorn WSGI server.
"""

import multiprocessing
import os

# Server socket
bind = f"127.0.0.1:{os.environ.get('GUNICORN_PORT', '8000')}"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers after this many requests, to prevent memory leaks
max_requests = 1000
max_requests_jitter = 100

# Worker timeouts
timeout = 30
graceful_timeout = 30

# Preload application code for better performance
preload_app = True

# User and group to run workers as (if running as root)
user = os.environ.get('GUNICORN_USER', 'www-data')
group = os.environ.get('GUNICORN_GROUP', 'www-data')

# Temporary work directory
tmp_upload_dir = None

# Logging
accesslog = os.environ.get('GUNICORN_ACCESS_LOG', '/var/log/aperature-booking/gunicorn-access.log')
errorlog = os.environ.get('GUNICORN_ERROR_LOG', '/var/log/aperature-booking/gunicorn-error.log')
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'aperature-booking'

# Server mechanics
daemon = False
pidfile = os.environ.get('GUNICORN_PID_FILE', '/var/run/aperature-booking/gunicorn.pid')
umask = 0o077
tmp_upload_dir = None

# SSL (if using HTTPS directly with Gunicorn)
keyfile = os.environ.get('SSL_KEYFILE')
certfile = os.environ.get('SSL_CERTFILE')

# Disable access log if behind reverse proxy
if os.environ.get('DISABLE_ACCESS_LOG', 'False').lower() == 'true':
    accesslog = None

# Development mode override
if os.environ.get('DJANGO_DEBUG', 'False').lower() == 'true':
    reload = True
    loglevel = 'debug'
    workers = 1

# Health check endpoint
def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Labitory server is ready. Server: %s", server.address)

def worker_int(worker):
    """Called just after a worker has been killed."""
    worker.log.info("Worker killed: %s", worker.pid)

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

# Memory optimization
def pre_request(worker, req):
    """Called just before a worker processes the request."""
    pass

def post_request(worker, req, environ, resp):
    """Called after a worker processes the request."""
    pass