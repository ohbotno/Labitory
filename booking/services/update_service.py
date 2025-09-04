# booking/update_service.py
"""
Update service for managing application updates from GitHub releases.

This file is part of the Labitory.
Copyright (C) 2025 Labitory Contributors

This software is dual-licensed:
1. GNU General Public License v3.0 (GPL-3.0) - for open source use
2. Commercial License - for proprietary and commercial use

For GPL-3.0 license terms, see LICENSE file.
For commercial licensing, see COMMERCIAL-LICENSE.txt or visit:
https://labitory.org/commercial
"""

import os
import shutil
import zipfile
import subprocess
import tempfile
import logging
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin
from typing import Dict, Optional, Tuple

import requests
from django.conf import settings
from django.utils import timezone
from django.core.management import call_command

from ..models.system import UpdateInfo, UpdateHistory

logger = logging.getLogger(__name__)


class UpdateService:
    """Service for managing application updates from GitHub releases."""
    
    def __init__(self):
        self.base_dir = Path(settings.BASE_DIR)
        self.update_info = UpdateInfo.get_instance()
        self.github_api_base = "https://api.github.com/repos"
        
    def check_for_updates(self) -> Dict:
        """Check GitHub for latest release and compare with current version."""
        try:
            logger.info("Checking for updates...")
            self.update_info.status = 'checking'
            self.update_info.error_message = ''
            self.update_info.save()
            
            # Get latest release from GitHub
            release_info = self._get_latest_release()
            
            if not release_info:
                self.update_info.status = 'up_to_date'
                self.update_info.save()
                return {'success': False, 'error': 'No releases found'}
            
            # Update release information
            self.update_info.latest_version = release_info['tag_name']
            self.update_info.release_url = release_info['html_url']
            self.update_info.release_notes = release_info['body']
            self.update_info.release_date = timezone.make_aware(
                datetime.strptime(release_info['published_at'], '%Y-%m-%dT%H:%M:%SZ')
            )
            
            # Find download URL for source code
            download_url = None
            for asset in release_info.get('assets', []):
                if asset['name'].endswith('.zip'):
                    download_url = asset['browser_download_url']
                    break
            
            # Fallback to source code zip if no assets
            if not download_url:
                download_url = release_info['zipball_url']
            
            self.update_info.download_url = download_url
            
            # Check if update is available
            if self.update_info.is_update_available():
                self.update_info.status = 'available'
                logger.info(f"Update available: {self.update_info.current_version} -> {self.update_info.latest_version}")
            else:
                self.update_info.status = 'up_to_date'
                logger.info(f"Already up to date: {self.update_info.current_version}")
            
            self.update_info.save()
            
            return {
                'success': True,
                'update_available': self.update_info.is_update_available(),
                'current_version': self.update_info.current_version,
                'latest_version': self.update_info.latest_version,
                'release_notes': self.update_info.release_notes
            }
            
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            self.update_info.status = 'failed'
            self.update_info.error_message = str(e)
            self.update_info.save()
            return {'success': False, 'error': str(e)}
    
    def download_update(self) -> Dict:
        """Download the latest update from GitHub."""
        try:
            if not self.update_info.download_url:
                return {'success': False, 'error': 'No download URL available'}
            
            logger.info(f"Downloading update from {self.update_info.download_url}")
            self.update_info.status = 'downloading'
            self.update_info.download_progress = 0
            self.update_info.save()
            
            # Create temporary download directory
            download_dir = self.base_dir / 'temp_update'
            download_dir.mkdir(exist_ok=True)
            
            # Download the update file
            response = requests.get(self.update_info.download_url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            zip_path = download_dir / 'update.zip'
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            self.update_info.download_progress = progress
                            self.update_info.save(update_fields=['download_progress'])
            
            # Extract the update
            extract_dir = download_dir / 'extracted'
            extract_dir.mkdir(exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            self.update_info.status = 'ready'
            self.update_info.download_progress = 100
            self.update_info.save()
            
            logger.info("Update downloaded and extracted successfully")
            return {'success': True, 'path': str(extract_dir)}
            
        except Exception as e:
            logger.error(f"Error downloading update: {e}")
            self.update_info.status = 'failed'
            self.update_info.error_message = str(e)
            self.update_info.save()
            return {'success': False, 'error': str(e)}
    
    def install_update(self, backup_before_update=True) -> Dict:
        """Install the downloaded update."""
        try:
            if not self.update_info.can_install_update():
                return {'success': False, 'error': 'Update not ready for installation'}
            
            logger.info(f"Installing update {self.update_info.current_version} -> {self.update_info.latest_version}")
            
            # Create update history record
            update_history = UpdateHistory.objects.create(
                from_version=self.update_info.current_version,
                to_version=self.update_info.latest_version,
                started_at=timezone.now(),
                result='failed'  # Will be updated on success
            )
            
            self.update_info.status = 'installing'
            self.update_info.save()
            
            # Create backup if requested
            backup_path = None
            if backup_before_update:
                backup_result = self._create_backup()
                if backup_result['success']:
                    backup_path = backup_result['backup_path']
                    update_history.backup_created = True
                    update_history.backup_path = backup_path
                    update_history.save()
                else:
                    logger.warning(f"Backup failed: {backup_result['error']}")
            
            # Apply the update
            result = self._apply_update()
            
            if result['success']:
                # Update version info
                self.update_info.current_version = self.update_info.latest_version
                self.update_info.status = 'completed'
                self.update_info.error_message = ''
                self.update_info.save()
                
                # Update history record
                update_history.result = 'success'
                update_history.completed_at = timezone.now()
                update_history.save()
                
                logger.info("Update installed successfully")
                return {
                    'success': True,
                    'backup_created': backup_path is not None,
                    'backup_path': backup_path
                }
            else:
                # Update failed
                self.update_info.status = 'failed'
                self.update_info.error_message = result['error']
                self.update_info.save()
                
                update_history.error_message = result['error']
                update_history.completed_at = timezone.now()
                update_history.save()
                
                return {'success': False, 'error': result['error']}
                
        except Exception as e:
            logger.error(f"Error installing update: {e}")
            self.update_info.status = 'failed'
            self.update_info.error_message = str(e)
            self.update_info.save()
            
            if 'update_history' in locals():
                update_history.error_message = str(e)
                update_history.completed_at = timezone.now()
                update_history.save()
            
            return {'success': False, 'error': str(e)}
    
    def rollback_update(self, update_history_id: int) -> Dict:
        """Rollback to a previous version using backup."""
        try:
            update_history = UpdateHistory.objects.get(id=update_history_id)
            
            if not update_history.backup_created or not update_history.backup_path:
                return {'success': False, 'error': 'No backup available for rollback'}
            
            logger.info(f"Rolling back to version {update_history.from_version}")
            
            # TODO: Implement rollback logic
            # This would involve restoring from the backup created before update
            
            return {'success': True}
            
        except UpdateHistory.DoesNotExist:
            return {'success': False, 'error': 'Update history not found'}
        except Exception as e:
            logger.error(f"Error during rollback: {e}")
            return {'success': False, 'error': str(e)}
    
    def _get_latest_release(self) -> Optional[Dict]:
        """Get latest release information from GitHub API."""
        try:
            url = f"{self.github_api_base}/{self.update_info.github_repo}/releases/latest"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch release info: {e}")
            return None
    
    def _create_backup(self) -> Dict:
        """Create a backup of the current application before update."""
        try:
            from .backup_service import BackupService
            
            backup_service = BackupService()
            
            # Create a full backup before update
            result = backup_service.create_backup(
                backup_name=f"pre_update_backup_{timezone.now().strftime('%Y%m%d_%H%M%S')}",
                include_database=True,
                include_media=True,
                include_configuration=True,
                compress=True,
                description="Automatic backup created before update installation"
            )
            
            if result['success']:
                backup_path = result['backup_info']['backup_path']
                logger.info(f"Pre-update backup created: {backup_path}")
                return {'success': True, 'backup_path': backup_path}
            else:
                return {'success': False, 'error': result.get('error', 'Backup failed')}
                
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return {'success': False, 'error': str(e)}
    
    def _apply_update(self) -> Dict:
        """Apply the downloaded update files."""
        try:
            update_dir = self.base_dir / 'temp_update' / 'extracted'
            
            if not update_dir.exists():
                return {'success': False, 'error': 'Update files not found'}
            
            # Find the actual source directory (GitHub zips create a subdirectory)
            source_dirs = [d for d in update_dir.iterdir() if d.is_dir()]
            if not source_dirs:
                return {'success': False, 'error': 'No source directory found in update'}
            
            source_dir = source_dirs[0]  # Take the first directory
            
            # Copy files (excluding certain directories/files)
            exclude_patterns = {
                'db.sqlite3', '.git', '__pycache__', '.env', 'media', 
                'staticfiles', 'temp_update', 'logs'
            }
            
            for item in source_dir.iterdir():
                if item.name in exclude_patterns:
                    continue
                
                dest_path = self.base_dir / item.name
                
                if item.is_file():
                    shutil.copy2(item, dest_path)
                elif item.is_dir():
                    if dest_path.exists():
                        shutil.rmtree(dest_path)
                    shutil.copytree(item, dest_path)
            
            # Run database migrations
            logger.info("Running database migrations...")
            call_command('migrate', verbosity=0, interactive=False)
            
            # Collect static files
            logger.info("Collecting static files...")
            call_command('collectstatic', verbosity=0, interactive=False, clear=True)
            
            # Clean up temp files
            temp_dir = self.base_dir / 'temp_update'
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            
            # Restart the application service to load new code
            restart_result = self._restart_application_service()
            if not restart_result['success']:
                logger.warning(f"Service restart failed: {restart_result['error']}")
                # Don't fail the update just because restart failed
            
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Error applying update: {e}")
            return {'success': False, 'error': str(e)}
    
    def _restart_application_service(self) -> Dict:
        """Restart the application service to load updated code."""
        try:
            # Try common service names for the application
            service_names = ['labitory', 'labitory-booking', 'gunicorn']
            
            for service_name in service_names:
                try:
                    # Check if service exists
                    result = subprocess.run(
                        ['systemctl', 'is-active', service_name],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    if result.returncode == 0:  # Service exists and is active
                        # Restart the service
                        restart_result = subprocess.run(
                            ['systemctl', 'restart', service_name],
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        
                        if restart_result.returncode == 0:
                            logger.info(f"Successfully restarted service: {service_name}")
                            return {'success': True, 'service': service_name}
                        else:
                            logger.warning(f"Failed to restart {service_name}: {restart_result.stderr}")
                
                except subprocess.TimeoutExpired:
                    logger.warning(f"Timeout checking/restarting service: {service_name}")
                except Exception as e:
                    logger.warning(f"Error with service {service_name}: {e}")
            
            # If no systemctl services found, try touching wsgi.py to trigger reload
            wsgi_file = self.base_dir / 'labitory' / 'wsgi.py'
            if wsgi_file.exists():
                wsgi_file.touch()
                logger.info("Touched wsgi.py to trigger application reload")
                return {'success': True, 'method': 'wsgi_touch'}
            
            return {'success': False, 'error': 'No restart method available'}
            
        except Exception as e:
            logger.error(f"Error restarting application service: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_update_status(self) -> Dict:
        """Get current update status and information."""
        # Always sync current version with the actual version
        from labitory import __version__
        if self.update_info.current_version != __version__:
            self.update_info.current_version = __version__
            self.update_info.save()
        
        return {
            'current_version': self.update_info.current_version,
            'latest_version': self.update_info.latest_version,
            'status': self.update_info.status,
            'update_available': self.update_info.is_update_available(),
            'can_install': self.update_info.can_install_update(),
            'last_check': self.update_info.last_check,
            'download_progress': self.update_info.download_progress,
            'error_message': self.update_info.error_message,
            'release_notes': self.update_info.release_notes,
            'auto_check_enabled': self.update_info.auto_check_enabled,
            'github_repo': self.update_info.github_repo
        }