# booking/log_viewer.py
"""
System log viewer for Django admin.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import os
import re
import subprocess
from datetime import datetime, timedelta
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.main import ChangeList
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import path
from django.utils.html import format_html
from django.contrib.auth.decorators import user_passes_test
from django.views.decorators.http import require_http_methods
import json


class LogEntry:
    """Represents a single log entry."""
    
    def __init__(self, timestamp, level, source, message, line_number=None):
        self.timestamp = timestamp
        self.level = level
        self.source = source
        self.message = message
        self.line_number = line_number
        self.id = f"{source}_{line_number}_{timestamp.timestamp()}"
    
    def get_level_color(self):
        """Get Bootstrap color class for log level."""
        level_colors = {
            'DEBUG': 'secondary',
            'INFO': 'info',
            'WARNING': 'warning',
            'ERROR': 'danger',
            'CRITICAL': 'danger',
        }
        return level_colors.get(self.level.upper(), 'secondary')


class LogViewer:
    """Service class for reading and parsing system logs."""
    
    def __init__(self):
        self.log_sources = self._get_log_sources()
    
    def _get_log_sources(self):
        """Get all available log sources."""
        sources = {}
        
        # System logs - Web Server
        nginx_logs = [
            ('/var/log/nginx/access.log', 'Nginx Access Log'),
            ('/var/log/nginx/error.log', 'Nginx Error Log'),
            ('/var/log/aperature-booking/access.log', 'App Nginx Access'),
            ('/var/log/aperature-booking/error.log', 'App Nginx Error'),
        ]
        
        for log_path, log_name in nginx_logs:
            if os.path.exists(log_path):
                source_key = os.path.basename(log_path).replace('.log', '').lower() + '_nginx'
                sources[source_key] = {
                    'name': log_name,
                    'path': log_path,
                    'type': 'file'
                }
        
        # System logs - Application Server
        gunicorn_logs = [
            ('/var/log/aperature-booking/gunicorn.log', 'Gunicorn Server'),
            ('/opt/aperature-booking/logs/gunicorn.log', 'Gunicorn App'),
        ]
        
        for log_path, log_name in gunicorn_logs:
            if os.path.exists(log_path):
                source_key = 'gunicorn_' + os.path.dirname(log_path).split('/')[-1]
                sources[source_key] = {
                    'name': log_name,
                    'path': log_path,
                    'type': 'file'
                }
        
        # System logs - Database
        postgres_logs = [
            ('/var/log/postgresql/postgresql-*.log', 'PostgreSQL'),
        ]
        
        for log_pattern, log_name in postgres_logs:
            import glob
            for log_path in glob.glob(log_pattern):
                if os.path.exists(log_path):
                    sources['postgresql'] = {
                        'name': log_name,
                        'path': log_path,
                        'type': 'file'
                    }
                    break
        
        # System logs - Linux System
        system_logs = [
            ('/var/log/syslog', 'System Log'),
            ('/var/log/auth.log', 'Authentication Log'),
            ('/var/log/kern.log', 'Kernel Log'),
            ('/var/log/dpkg.log', 'Package Manager Log'),
        ]
        
        for log_path, log_name in system_logs:
            if os.path.exists(log_path):
                source_key = os.path.basename(log_path).replace('.log', '')
                sources[source_key] = {
                    'name': log_name,
                    'path': log_path,
                    'type': 'file'
                }
        
        # Systemd journal for services
        services = [
            ('labitory.service', 'Labitory Service'),
            ('aperature-booking-scheduler.service', 'Scheduler Service'),
            ('nginx.service', 'Nginx Service'),
            ('postgresql.service', 'PostgreSQL Service'),
            ('systemd-timesyncd.service', 'Time Sync Service'),
            ('ssh.service', 'SSH Service'),
            ('networkd-dispatcher.service', 'Network Service'),
        ]
        
        for service, display_name in services:
            service_key = service.replace('.service', '').replace('-', '_')
            sources[f'systemd_{service_key}'] = {
                'name': f'{display_name} (systemd)',
                'path': service,
                'type': 'systemd'
            }
        
        return sources
    
    def _parse_django_log_line(self, line, line_number):
        """Parse a Django log line."""
        # Pattern: 2025-07-13 14:17:38,123 INFO django.request: ...
        pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) (\w+) ([^:]+): (.+)'
        match = re.match(pattern, line.strip())
        
        if match:
            timestamp_str, level, logger_name, message = match.groups()
            try:
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
            except ValueError:
                timestamp = datetime.now()
            
            return LogEntry(
                timestamp=timestamp,
                level=level,
                source=logger_name,
                message=message.strip(),
                line_number=line_number
            )
        
        return None
    
    def _parse_generic_log_line(self, line, line_number, source_name):
        """Parse a generic log line."""
        # Try to extract timestamp and level if possible
        timestamp_patterns = [
            (r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', '%Y-%m-%d %H:%M:%S'),
            (r'(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})', '%Y/%m/%d %H:%M:%S'),
            (r'(\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2})', '%d/%b/%Y:%H:%M:%S'),
            (r'(\w{3} \d{2} \d{2}:\d{2}:\d{2})', '%b %d %H:%M:%S'),
            (r'(\w{3}\s+\d{1,2} \d{2}:\d{2}:\d{2})', '%b %d %H:%M:%S'),
        ]
        
        timestamp = datetime.now()
        for pattern, date_format in timestamp_patterns:
            match = re.search(pattern, line)
            if match:
                try:
                    timestamp_str = match.group(1)
                    if date_format == '%b %d %H:%M:%S':
                        # Add current year for syslog format
                        timestamp_str = f"{datetime.now().year} {timestamp_str}"
                        date_format = '%Y %b %d %H:%M:%S'
                    timestamp = datetime.strptime(timestamp_str, date_format)
                    break
                except ValueError:
                    continue
        
        # Try to extract log level
        level = 'INFO'
        # Check for nginx error levels
        if 'nginx' in source_name.lower():
            if '[error]' in line:
                level = 'ERROR'
            elif '[warn]' in line:
                level = 'WARNING'
            elif '[crit]' in line:
                level = 'CRITICAL'
            elif '[alert]' in line or '[emerg]' in line:
                level = 'CRITICAL'
        else:
            # Standard log levels
            level_patterns = [
                ('CRITICAL', ['CRIT', 'FATAL', 'EMERG', 'ALERT']),
                ('ERROR', ['ERROR', 'ERR']),
                ('WARNING', ['WARN', 'WARNING']),
                ('INFO', ['INFO', 'NOTICE']),
                ('DEBUG', ['DEBUG']),
            ]
            for level_name, patterns in level_patterns:
                for pattern in patterns:
                    if re.search(r'\b' + pattern + r'\b', line, re.IGNORECASE):
                        level = level_name
                        break
                if level != 'INFO':
                    break
        
        # Clean up the message
        message = line.strip()
        # Remove common prefixes
        message = re.sub(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[,\.]?\d*\s*', '', message)
        message = re.sub(r'^\w{3}\s+\d{1,2} \d{2}:\d{2}:\d{2}\s*', '', message)
        message = re.sub(r'^\[\w+\]\s*', '', message)
        
        return LogEntry(
            timestamp=timestamp,
            level=level,
            source=source_name,
            message=message,
            line_number=line_number
        )
    
    def get_logs(self, source=None, level=None, search=None, hours=24, max_lines=1000):
        """Get logs from specified source with filtering."""
        logs = []
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        sources_to_read = [source] if source else list(self.log_sources.keys())
        
        for source_key in sources_to_read:
            if source_key not in self.log_sources:
                continue
                
            source_config = self.log_sources[source_key]
            
            try:
                if source_config['type'] == 'file':
                    logs.extend(self._read_file_logs(source_key, source_config, cutoff_time, max_lines))
                elif source_config['type'] == 'systemd':
                    logs.extend(self._read_systemd_logs(source_key, source_config, cutoff_time, max_lines))
            except Exception as e:
                # Create an error log entry if we can't read a source
                logs.append(LogEntry(
                    timestamp=datetime.now(),
                    level='ERROR',
                    source=f'LogViewer-{source_key}',
                    message=f'Failed to read logs: {str(e)}'
                ))
        
        # Filter logs
        if level:
            logs = [log for log in logs if log.level.upper() == level.upper()]
        
        if search:
            search_lower = search.lower()
            logs = [log for log in logs if search_lower in log.message.lower() or search_lower in log.source.lower()]
        
        # Sort by timestamp (newest first) and limit
        logs.sort(key=lambda x: x.timestamp, reverse=True)
        return logs[:max_lines]
    
    def _read_file_logs(self, source_key, source_config, cutoff_time, max_lines):
        """Read logs from a file."""
        logs = []
        
        if not os.path.exists(source_config['path']):
            return logs
        
        try:
            # Use tail to get last N lines for performance
            result = subprocess.run([
                'tail', '-n', str(max_lines * 2), source_config['path']
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for i, line in enumerate(lines):
                    if not line.strip():
                        continue
                    
                    # Parse based on source type
                    if source_key == 'django_app':
                        log_entry = self._parse_django_log_line(line, i)
                    else:
                        log_entry = self._parse_generic_log_line(line, i, source_config['name'])
                    
                    if log_entry and log_entry.timestamp >= cutoff_time:
                        logs.append(log_entry)
                        
        except Exception as e:
            # Return error entry
            logs.append(LogEntry(
                timestamp=datetime.now(),
                level='ERROR',
                source='LogViewer',
                message=f'Error reading {source_config["name"]}: {str(e)}'
            ))
        
        return logs
    
    def _read_systemd_logs(self, source_key, source_config, cutoff_time, max_lines):
        """Read logs from systemd journal."""
        logs = []
        service_name = source_config['path']
        
        try:
            # Use journalctl to get recent logs
            result = subprocess.run([
                'journalctl', '-u', service_name, '--no-pager', 
                '-n', str(max_lines), '--output=json'
            ], capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if not line.strip():
                        continue
                    
                    try:
                        entry = json.loads(line)
                        timestamp = datetime.fromtimestamp(int(entry.get('__REALTIME_TIMESTAMP', 0)) / 1000000)
                        
                        if timestamp >= cutoff_time:
                            logs.append(LogEntry(
                                timestamp=timestamp,
                                level=entry.get('PRIORITY', '6') == '3' and 'ERROR' or 'INFO',
                                source=f"systemd-{service_name}",
                                message=entry.get('MESSAGE', ''),
                                line_number=None
                            ))
                    except (json.JSONDecodeError, ValueError):
                        continue
                        
        except Exception as e:
            logs.append(LogEntry(
                timestamp=datetime.now(),
                level='ERROR',
                source='LogViewer',
                message=f'Error reading systemd logs for {service_name}: {str(e)}'
            ))
        
        return logs
    
    def get_available_sources(self):
        """Get list of available log sources."""
        available = []
        for key, config in self.log_sources.items():
            is_available = True
            if config['type'] == 'file':
                is_available = os.path.exists(config['path'])
            
            available.append({
                'key': key,
                'name': config['name'],
                'type': config['type'],
                'path': config['path'],
                'available': is_available
            })
        
        return available


# Global log viewer instance
log_viewer = LogViewer()


def log_viewer_ajax(request):
    """AJAX endpoint for fetching logs."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    source = request.GET.get('source')
    level = request.GET.get('level')
    search = request.GET.get('search')
    hours = int(request.GET.get('hours', 24))
    max_lines = int(request.GET.get('max_lines', 1000))
    
    logs = log_viewer.get_logs(source, level, search, hours, max_lines)
    
    log_data = []
    for log in logs:
        log_data.append({
            'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'level': log.level,
            'source': log.source,
            'message': log.message,
            'level_color': log.get_level_color()
        })
    
    return JsonResponse({
        'logs': log_data,
        'total': len(log_data)
    })


class LogViewerAdmin:
    """Custom admin view for system logs."""
    
    def __init__(self):
        self.log_viewer = log_viewer
    
    def get_urls(self):
        """Get URL patterns for the log viewer."""
        return [
            path('logs/', self.log_viewer_view, name='log_viewer'),
            path('logs/ajax/', log_viewer_ajax, name='log_viewer_ajax'),
        ]
    
    def log_viewer_view(self, request):
        """Main log viewer page."""
        if not request.user.is_staff:
            return HttpResponse('Access denied', status=403)
        
        # Get initial logs
        hours = int(request.GET.get('hours', 24))
        source = request.GET.get('source')
        level = request.GET.get('level')
        search = request.GET.get('search')
        
        logs = self.log_viewer.get_logs(source, level, search, hours, 500)
        sources = self.log_viewer.get_available_sources()
        
        context = {
            'title': 'System Logs',
            'logs': logs,
            'sources': sources,
            'current_source': source,
            'current_level': level,
            'current_search': search,
            'current_hours': hours,
            'log_levels': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
            'opts': type('MockOpts', (), {
                'app_label': 'booking',
                'model_name': 'systemlog',
                'verbose_name': 'System Log',
                'verbose_name_plural': 'System Logs'
            })()
        }
        
        return render(request, 'admin/booking/systemlog/change_list.html', context)


# Initialize the log viewer admin
log_viewer_admin = LogViewerAdmin()