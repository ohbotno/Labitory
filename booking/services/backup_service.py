# booking/backup_service.py
"""
Backup management service for the Labitory.

This file is part of Labitory.
Copyright (c) 2025 Labitory Contributors
Licensed under the MIT License - see LICENSE file for details.
"""

import os
import shutil
import subprocess
import gzip
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.core.files.storage import default_storage
import tempfile


logger = logging.getLogger(__name__)


class BackupService:
    """
    Comprehensive backup service for database, media files, and system configuration.
    """
    
    def __init__(self):
        self.backup_dir = getattr(settings, 'BACKUP_DIR', os.path.join(settings.BASE_DIR, 'backups'))
        self.max_backup_age_days = getattr(settings, 'BACKUP_RETENTION_DAYS', 30)
        self.compression_enabled = getattr(settings, 'BACKUP_COMPRESSION', True)
        self.ensure_backup_directory()
    
    def ensure_backup_directory(self) -> None:
        """Ensure backup directory exists with proper permissions."""
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Set secure permissions (owner read/write/execute only)
        try:
            os.chmod(self.backup_dir, 0o700)
        except OSError as e:
            logger.warning(f"Could not set backup directory permissions: {e}")
    
    def create_full_backup(self, include_media: bool = True, description: str = "") -> Dict[str, Any]:
        """
        Create a complete backup including database, media files, and configuration.
        
        Args:
            include_media: Whether to include media files in backup
            description: Optional description for the backup
            
        Returns:
            Dictionary with backup information and status
        """
        backup_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"full_backup_{backup_timestamp}"
        backup_path = os.path.join(self.backup_dir, backup_name)
        
        os.makedirs(backup_path, exist_ok=True)
        
        result = {
            'backup_name': backup_name,
            'backup_path': backup_path,
            'timestamp': datetime.now(),
            'description': description,
            'components': {},
            'success': True,
            'errors': [],
            'total_size': 0
        }
        
        try:
            # Backup database
            logger.info("Starting database backup...")
            db_result = self.backup_database(backup_path)
            result['components']['database'] = db_result
            if not db_result['success']:
                result['errors'].extend(db_result.get('errors', []))
            
            # Backup media files if requested
            if include_media:
                logger.info("Starting media files backup...")
                media_result = self.backup_media_files(backup_path)
                result['components']['media'] = media_result
                if not media_result['success']:
                    result['errors'].extend(media_result.get('errors', []))
            
            # Backup configuration
            logger.info("Starting configuration backup...")
            config_result = self.backup_configuration(backup_path)
            result['components']['configuration'] = config_result
            if not config_result['success']:
                result['errors'].extend(config_result.get('errors', []))
            
            # Calculate total backup size
            result['total_size'] = self._calculate_directory_size(backup_path)
            
            # Create backup manifest
            self._create_backup_manifest(backup_path, result)
            
            # Compress backup if enabled
            if self.compression_enabled:
                logger.info("Compressing backup...")
                compressed_path = self._compress_backup(backup_path)
                if compressed_path:
                    # Remove uncompressed directory
                    shutil.rmtree(backup_path)
                    result['backup_path'] = compressed_path
                    result['compressed'] = True
                    result['total_size'] = os.path.getsize(compressed_path)
                else:
                    result['errors'].append("Failed to compress backup")
            
            result['success'] = len(result['errors']) == 0
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            result['success'] = False
            result['errors'].append(str(e))
            
            # Cleanup failed backup
            if os.path.exists(backup_path):
                shutil.rmtree(backup_path, ignore_errors=True)
        
        return result
    
    def backup_database(self, backup_path: str) -> Dict[str, Any]:
        """Backup the database to the specified path."""
        result = {
            'success': True,
            'errors': [],
            'file_path': '',
            'size': 0
        }
        
        try:
            db_config = settings.DATABASES['default']
            engine = db_config['ENGINE']
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            if 'sqlite' in engine.lower():
                result.update(self._backup_sqlite(backup_path, db_config, timestamp))
            elif 'mysql' in engine.lower():
                result.update(self._backup_mysql(backup_path, db_config, timestamp))
            elif 'postgresql' in engine.lower():
                result.update(self._backup_postgresql(backup_path, db_config, timestamp))
            else:
                # Fallback to Django's dumpdata
                result.update(self._backup_django_dumpdata(backup_path, timestamp))
                
        except Exception as e:
            logger.error(f"Database backup failed: {e}")
            result['success'] = False
            result['errors'].append(str(e))
        
        return result
    
    def _backup_sqlite(self, backup_path: str, db_config: Dict, timestamp: str) -> Dict[str, Any]:
        """Backup SQLite database."""
        db_file = db_config['NAME']
        backup_file = os.path.join(backup_path, f'database_sqlite_{timestamp}.db')
        
        try:
            shutil.copy2(db_file, backup_file)
            
            if self.compression_enabled:
                compressed_file = f"{backup_file}.gz"
                with open(backup_file, 'rb') as f_in:
                    with gzip.open(compressed_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(backup_file)
                backup_file = compressed_file
            
            return {
                'success': True,
                'file_path': backup_file,
                'size': os.path.getsize(backup_file),
                'errors': []
            }
            
        except Exception as e:
            return {
                'success': False,
                'file_path': '',
                'size': 0,
                'errors': [str(e)]
            }
    
    def _backup_mysql(self, backup_path: str, db_config: Dict, timestamp: str) -> Dict[str, Any]:
        """Backup MySQL database using mysqldump."""
        backup_file = os.path.join(backup_path, f'database_mysql_{timestamp}.sql')
        
        try:
            cmd = [
                'mysqldump',
                f"--host={db_config.get('HOST', 'localhost')}",
                f"--port={db_config.get('PORT', 3306)}",
                f"--user={db_config['USER']}",
                f"--password={db_config['PASSWORD']}",
                '--single-transaction',
                '--routines',
                '--triggers',
                db_config['NAME']
            ]
            
            with open(backup_file, 'w') as f:
                subprocess.run(cmd, stdout=f, check=True, stderr=subprocess.PIPE)
            
            if self.compression_enabled:
                compressed_file = f"{backup_file}.gz"
                with open(backup_file, 'rb') as f_in:
                    with gzip.open(compressed_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(backup_file)
                backup_file = compressed_file
            
            return {
                'success': True,
                'file_path': backup_file,
                'size': os.path.getsize(backup_file),
                'errors': []
            }
            
        except subprocess.CalledProcessError as e:
            return {
                'success': False,
                'file_path': '',
                'size': 0,
                'errors': [f"mysqldump failed: {e.stderr.decode() if e.stderr else str(e)}"]
            }
        except Exception as e:
            return {
                'success': False,
                'file_path': '',
                'size': 0,
                'errors': [str(e)]
            }
    
    def _backup_postgresql(self, backup_path: str, db_config: Dict, timestamp: str) -> Dict[str, Any]:
        """Backup PostgreSQL database using pg_dump."""
        backup_file = os.path.join(backup_path, f'database_postgresql_{timestamp}.sql')
        
        try:
            env = os.environ.copy()
            env['PGPASSWORD'] = db_config['PASSWORD']
            
            cmd = [
                'pg_dump',
                f"--host={db_config.get('HOST', 'localhost')}",
                f"--port={db_config.get('PORT', 5432)}",
                f"--username={db_config['USER']}",
                '--no-password',
                '--verbose',
                '--clean',
                '--no-acl',
                '--no-owner',
                db_config['NAME']
            ]
            
            with open(backup_file, 'w') as f:
                subprocess.run(cmd, stdout=f, check=True, stderr=subprocess.PIPE, env=env)
            
            if self.compression_enabled:
                compressed_file = f"{backup_file}.gz"
                with open(backup_file, 'rb') as f_in:
                    with gzip.open(compressed_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(backup_file)
                backup_file = compressed_file
            
            return {
                'success': True,
                'file_path': backup_file,
                'size': os.path.getsize(backup_file),
                'errors': []
            }
            
        except subprocess.CalledProcessError as e:
            return {
                'success': False,
                'file_path': '',
                'size': 0,
                'errors': [f"pg_dump failed: {e.stderr.decode() if e.stderr else str(e)}"]
            }
        except Exception as e:
            return {
                'success': False,
                'file_path': '',
                'size': 0,
                'errors': [str(e)]
            }
    
    def _backup_django_dumpdata(self, backup_path: str, timestamp: str) -> Dict[str, Any]:
        """Backup using Django's dumpdata command as fallback."""
        backup_file = os.path.join(backup_path, f'database_django_{timestamp}.json')
        
        try:
            with open(backup_file, 'w') as f:
                call_command('dumpdata', stdout=f, indent=2)
            
            if self.compression_enabled:
                compressed_file = f"{backup_file}.gz"
                with open(backup_file, 'rb') as f_in:
                    with gzip.open(compressed_file, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(backup_file)
                backup_file = compressed_file
            
            return {
                'success': True,
                'file_path': backup_file,
                'size': os.path.getsize(backup_file),
                'errors': []
            }
            
        except Exception as e:
            return {
                'success': False,
                'file_path': '',
                'size': 0,
                'errors': [str(e)]
            }
    
    def backup_media_files(self, backup_path: str) -> Dict[str, Any]:
        """Backup media files."""
        result = {
            'success': True,
            'errors': [],
            'file_path': '',
            'size': 0,
            'file_count': 0
        }
        
        try:
            media_root = settings.MEDIA_ROOT
            if not os.path.exists(media_root):
                return {
                    'success': True,
                    'errors': ['No media directory found'],
                    'file_path': '',
                    'size': 0,
                    'file_count': 0
                }
            
            media_backup_path = os.path.join(backup_path, 'media')
            
            # Copy media files
            shutil.copytree(media_root, media_backup_path, dirs_exist_ok=True)
            
            # Count files and calculate size
            file_count = 0
            total_size = 0
            for root, dirs, files in os.walk(media_backup_path):
                file_count += len(files)
                for file in files:
                    total_size += os.path.getsize(os.path.join(root, file))
            
            result.update({
                'file_path': media_backup_path,
                'size': total_size,
                'file_count': file_count
            })
            
        except Exception as e:
            logger.error(f"Media files backup failed: {e}")
            result['success'] = False
            result['errors'].append(str(e))
        
        return result
    
    def backup_configuration(self, backup_path: str) -> Dict[str, Any]:
        """Backup system configuration and important files."""
        result = {
            'success': True,
            'errors': [],
            'files': [],
            'size': 0
        }
        
        try:
            config_backup_path = os.path.join(backup_path, 'configuration')
            os.makedirs(config_backup_path, exist_ok=True)
            
            # Backup requirements.txt
            requirements_path = os.path.join(settings.BASE_DIR, 'requirements.txt')
            if os.path.exists(requirements_path):
                shutil.copy2(requirements_path, config_backup_path)
                result['files'].append('requirements.txt')
            
            # Backup environment variables (sanitized)
            env_backup = self._create_sanitized_env_backup()
            env_file = os.path.join(config_backup_path, 'environment.json')
            with open(env_file, 'w') as f:
                json.dump(env_backup, f, indent=2)
            result['files'].append('environment.json')
            
            # Backup Django settings structure (sanitized)
            settings_backup = self._create_sanitized_settings_backup()
            settings_file = os.path.join(config_backup_path, 'django_settings.json')
            with open(settings_file, 'w') as f:
                json.dump(settings_backup, f, indent=2)
            result['files'].append('django_settings.json')
            
            # Calculate total size
            result['size'] = self._calculate_directory_size(config_backup_path)
            
        except Exception as e:
            logger.error(f"Configuration backup failed: {e}")
            result['success'] = False
            result['errors'].append(str(e))
        
        return result
    
    def _create_sanitized_env_backup(self) -> Dict[str, Any]:
        """Create a sanitized backup of environment variables."""
        sensitive_keys = [
            'SECRET_KEY', 'DB_PASSWORD', 'EMAIL_HOST_PASSWORD', 
            'AWS_SECRET_ACCESS_KEY', 'API_KEY', 'TOKEN'
        ]
        
        env_backup = {}
        for key, value in os.environ.items():
            if any(sensitive in key.upper() for sensitive in sensitive_keys):
                env_backup[key] = '[REDACTED]'
            elif key.startswith(('LABITORY_', 'DJANGO_')):
                env_backup[key] = value
        
        return env_backup
    
    def _create_sanitized_settings_backup(self) -> Dict[str, Any]:
        """Create a sanitized backup of Django settings."""
        sensitive_settings = [
            'SECRET_KEY', 'DATABASES', 'EMAIL_HOST_PASSWORD',
            'AWS_SECRET_ACCESS_KEY', 'API_KEYS'
        ]
        
        settings_backup = {}
        for attr in dir(settings):
            if not attr.startswith('_') and attr.isupper():
                if attr in sensitive_settings:
                    settings_backup[attr] = '[REDACTED]'
                else:
                    try:
                        value = getattr(settings, attr)
                        # Only include serializable values
                        json.dumps(value)
                        settings_backup[attr] = value
                    except (TypeError, ValueError):
                        settings_backup[attr] = str(value)
        
        return settings_backup
    
    def _compress_backup(self, backup_path: str) -> Optional[str]:
        """Compress backup directory into a tar.gz file."""
        try:
            compressed_path = f"{backup_path}.tar.gz"
            shutil.make_archive(backup_path, 'gztar', backup_path)
            return compressed_path
        except Exception as e:
            logger.error(f"Backup compression failed: {e}")
            return None
    
    def _create_backup_manifest(self, backup_path: str, backup_info: Dict[str, Any]) -> None:
        """Create a manifest file with backup information."""
        manifest = {
            'backup_name': backup_info['backup_name'],
            'timestamp': backup_info['timestamp'].isoformat(),
            'description': backup_info['description'],
            'components': backup_info['components'],
            'total_size': backup_info['total_size'],
            'django_version': getattr(settings, 'DJANGO_VERSION', 'unknown'),
            'python_version': f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
            'created_by': 'Labitory Backup Service'
        }
        
        manifest_file = os.path.join(backup_path, 'backup_manifest.json')
        with open(manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2, default=str)
    
    def _calculate_directory_size(self, directory: str) -> int:
        """Calculate total size of a directory in bytes."""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
        return total_size
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups with their information."""
        backups = []
        
        if not os.path.exists(self.backup_dir):
            return backups
        
        for item in os.listdir(self.backup_dir):
            item_path = os.path.join(self.backup_dir, item)
            backup_info = self._get_backup_info(item_path)
            if backup_info:
                backups.append(backup_info)
        
        # Sort by timestamp, newest first
        backups.sort(key=lambda x: x['timestamp'], reverse=True)
        return backups
    
    def _get_backup_info(self, backup_path: str) -> Optional[Dict[str, Any]]:
        """Get information about a backup from its manifest."""
        try:
            # Handle compressed backups
            if backup_path.endswith('.tar.gz'):
                # Extract manifest from compressed backup
                import tarfile
                with tarfile.open(backup_path, 'r:gz') as tar:
                    try:
                        manifest_member = tar.getmember('backup_manifest.json')
                        manifest_file = tar.extractfile(manifest_member)
                        if manifest_file:
                            manifest_data = json.loads(manifest_file.read().decode())
                            manifest_data['file_path'] = backup_path
                            manifest_data['size'] = os.path.getsize(backup_path)
                            manifest_data['compressed'] = True
                            return manifest_data
                    except KeyError:
                        pass
            else:
                # Handle uncompressed backups
                manifest_file = os.path.join(backup_path, 'backup_manifest.json')
                if os.path.exists(manifest_file):
                    with open(manifest_file, 'r') as f:
                        manifest_data = json.load(f)
                        manifest_data['file_path'] = backup_path
                        manifest_data['size'] = self._calculate_directory_size(backup_path)
                        manifest_data['compressed'] = False
                        return manifest_data
            
            # Fallback for backups without manifest
            stat = os.stat(backup_path)
            return {
                'backup_name': os.path.basename(backup_path),
                'timestamp': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'description': 'Legacy backup (no manifest)',
                'file_path': backup_path,
                'size': stat.st_size if os.path.isfile(backup_path) else self._calculate_directory_size(backup_path),
                'compressed': backup_path.endswith(('.tar.gz', '.zip')),
                'components': {}
            }
            
        except Exception as e:
            logger.error(f"Error getting backup info for {backup_path}: {e}")
            return None
    
    def delete_backup(self, backup_name: str) -> Dict[str, Any]:
        """Delete a specific backup."""
        result = {'success': False, 'message': ''}
        
        try:
            backup_path = os.path.join(self.backup_dir, backup_name)
            compressed_path = f"{backup_path}.tar.gz"
            
            if os.path.exists(compressed_path):
                os.remove(compressed_path)
                result['success'] = True
                result['message'] = f"Backup {backup_name} deleted successfully"
            elif os.path.exists(backup_path):
                if os.path.isdir(backup_path):
                    shutil.rmtree(backup_path)
                else:
                    os.remove(backup_path)
                result['success'] = True
                result['message'] = f"Backup {backup_name} deleted successfully"
            else:
                result['message'] = f"Backup {backup_name} not found"
                
        except Exception as e:
            logger.error(f"Error deleting backup {backup_name}: {e}")
            result['message'] = str(e)
        
        return result
    
    def cleanup_old_backups(self) -> Dict[str, Any]:
        """Remove backups older than the retention period."""
        result = {
            'success': True,
            'deleted_count': 0,
            'errors': [],
            'deleted_backups': []
        }
        
        try:
            cutoff_date = datetime.now() - timedelta(days=self.max_backup_age_days)
            backups = self.list_backups()
            
            for backup in backups:
                backup_date = datetime.fromisoformat(backup['timestamp'].replace('Z', '+00:00'))
                if backup_date < cutoff_date:
                    delete_result = self.delete_backup(backup['backup_name'])
                    if delete_result['success']:
                        result['deleted_count'] += 1
                        result['deleted_backups'].append(backup['backup_name'])
                    else:
                        result['errors'].append(f"Failed to delete {backup['backup_name']}: {delete_result['message']}")
                        
        except Exception as e:
            logger.error(f"Error during backup cleanup: {e}")
            result['success'] = False
            result['errors'].append(str(e))
        
        return result
    
    def get_backup_statistics(self) -> Dict[str, Any]:
        """Get backup statistics and information."""
        backups = self.list_backups()
        
        if not backups:
            return {
                'total_backups': 0,
                'total_size': 0,
                'oldest_backup': None,
                'newest_backup': None,
                'backup_dir': self.backup_dir,
                'retention_days': self.max_backup_age_days
            }
        
        total_size = sum(backup.get('size', 0) for backup in backups)
        
        return {
            'total_backups': len(backups),
            'total_size': total_size,
            'oldest_backup': backups[-1] if backups else None,
            'newest_backup': backups[0] if backups else None,
            'backup_dir': self.backup_dir,
            'retention_days': self.max_backup_age_days,
            'compressed_backups': sum(1 for backup in backups if backup.get('compressed', False)),
            'recent_backups': [backup for backup in backups[:5]]  # Last 5 backups
        }
    
    def restore_backup(self, backup_name: str, restore_components: Dict[str, bool], 
                      confirmation_token: str = None) -> Dict[str, Any]:
        """
        Restore a backup with specified components.
        
        Args:
            backup_name: Name of the backup to restore
            restore_components: Dict specifying which components to restore
                - 'database': bool - Restore database
                - 'media': bool - Restore media files  
                - 'configuration': bool - Restore configuration
            confirmation_token: Safety token to confirm destructive operation
            
        Returns:
            Dictionary with restoration results and status
        """
        result = {
            'success': True,
            'backup_name': backup_name,
            'timestamp': datetime.now(),
            'components_restored': {},
            'errors': [],
            'warnings': []
        }
        
        try:
            # Safety check - require confirmation token for database restoration
            if restore_components.get('database', False) and not confirmation_token:
                result['success'] = False
                result['errors'].append("Database restoration requires confirmation token")
                return result
            
            # Find and validate backup
            backup_info = self._find_backup(backup_name)
            if not backup_info:
                result['success'] = False
                result['errors'].append(f"Backup '{backup_name}' not found")
                return result
            
            # Extract backup if compressed
            extraction_path = self._extract_backup(backup_info)
            if not extraction_path:
                result['success'] = False
                result['errors'].append("Failed to extract backup")
                return result
            
            try:
                # Restore database if requested
                if restore_components.get('database', False):
                    logger.info("Starting database restoration...")
                    db_result = self._restore_database(extraction_path, backup_info)
                    result['components_restored']['database'] = db_result
                    if not db_result['success']:
                        result['errors'].extend(db_result.get('errors', []))
                
                # Restore media files if requested
                if restore_components.get('media', False):
                    logger.info("Starting media files restoration...")
                    media_result = self._restore_media_files(extraction_path)
                    result['components_restored']['media'] = media_result
                    if not media_result['success']:
                        result['errors'].extend(media_result.get('errors', []))
                
                # Restore configuration if requested (informational only)
                if restore_components.get('configuration', False):
                    logger.info("Analyzing configuration restoration...")
                    config_result = self._analyze_configuration_restore(extraction_path)
                    result['components_restored']['configuration'] = config_result
                    if config_result.get('warnings'):
                        result['warnings'].extend(config_result['warnings'])
                
                result['success'] = len(result['errors']) == 0
                
            finally:
                # Cleanup extracted files if they were temporary
                if extraction_path != backup_info['file_path']:
                    shutil.rmtree(extraction_path, ignore_errors=True)
            
        except Exception as e:
            logger.error(f"Backup restoration failed: {e}")
            result['success'] = False
            result['errors'].append(str(e))
        
        return result
    
    def _find_backup(self, backup_name: str) -> Optional[Dict[str, Any]]:
        """Find backup information by name."""
        backups = self.list_backups()
        for backup in backups:
            if backup['backup_name'] == backup_name:
                return backup
        return None
    
    def _extract_backup(self, backup_info: Dict[str, Any]) -> Optional[str]:
        """Extract backup to temporary location if compressed."""
        backup_path = backup_info['file_path']
        
        if backup_info.get('compressed', False) and backup_path.endswith('.tar.gz'):
            # Extract to temporary directory
            import tarfile
            temp_dir = tempfile.mkdtemp(prefix='backup_restore_')
            
            try:
                with tarfile.open(backup_path, 'r:gz') as tar:
                    tar.extractall(temp_dir)
                
                # Find the extracted backup directory
                extracted_dirs = [d for d in os.listdir(temp_dir) 
                                if os.path.isdir(os.path.join(temp_dir, d))]
                
                if extracted_dirs:
                    return os.path.join(temp_dir, extracted_dirs[0])
                else:
                    return temp_dir
                    
            except Exception as e:
                logger.error(f"Failed to extract backup: {e}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None
        else:
            # Backup is already uncompressed
            return backup_path
    
    def _restore_database(self, backup_path: str, backup_info: Dict[str, Any]) -> Dict[str, Any]:
        """Restore database from backup."""
        result = {
            'success': True,
            'errors': [],
            'restored_file': '',
            'backup_created': False
        }
        
        try:
            # Create a backup of current database before restoration
            current_backup_result = self._create_current_db_backup()
            result['backup_created'] = current_backup_result['success']
            
            if not current_backup_result['success']:
                result['warnings'] = [f"Could not backup current database: {current_backup_result.get('error', 'Unknown error')}"]
            
            db_config = settings.DATABASES['default']
            engine = db_config['ENGINE']
            
            # Find database backup file in the extracted backup
            db_files = []
            for file in os.listdir(backup_path):
                if file.startswith('database_') and (file.endswith('.sql') or file.endswith('.db') 
                                                   or file.endswith('.json') or file.endswith('.gz')):
                    db_files.append(file)
            
            if not db_files:
                result['success'] = False
                result['errors'].append("No database backup file found in backup")
                return result
            
            # Use the most appropriate database file
            db_file = db_files[0]  # Take the first one found
            db_file_path = os.path.join(backup_path, db_file)
            
            if 'sqlite' in engine.lower():
                result.update(self._restore_sqlite(db_file_path, db_config))
            elif 'mysql' in engine.lower():
                result.update(self._restore_mysql(db_file_path, db_config))
            elif 'postgresql' in engine.lower():
                result.update(self._restore_postgresql(db_file_path, db_config))
            else:
                result.update(self._restore_django_loaddata(db_file_path))
            
        except Exception as e:
            logger.error(f"Database restoration failed: {e}")
            result['success'] = False
            result['errors'].append(str(e))
        
        return result
    
    def _create_current_db_backup(self) -> Dict[str, Any]:
        """Create a backup of the current database before restoration."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"pre_restore_backup_{timestamp}"
            
            result = self.create_full_backup(
                include_media=False,
                description=f"Automatic backup before restoration - {timestamp}"
            )
            
            return {
                'success': result['success'],
                'backup_name': backup_name,
                'error': ', '.join(result.get('errors', []))
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _restore_sqlite(self, db_file_path: str, db_config: Dict) -> Dict[str, Any]:
        """Restore SQLite database."""
        try:
            current_db = db_config['NAME']
            
            # Handle compressed file
            if db_file_path.endswith('.gz'):
                with gzip.open(db_file_path, 'rb') as f_in:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                        temp_db_path = f_out.name
            else:
                temp_db_path = db_file_path
            
            # Close all database connections
            from django.db import connections
            connections.close_all()
            
            # Replace current database
            shutil.copy2(temp_db_path, current_db)
            
            # Cleanup temporary file if created
            if temp_db_path != db_file_path:
                os.unlink(temp_db_path)
            
            return {
                'success': True,
                'restored_file': db_file_path,
                'errors': []
            }
            
        except Exception as e:
            return {
                'success': False,
                'restored_file': '',
                'errors': [str(e)]
            }
    
    def _restore_mysql(self, db_file_path: str, db_config: Dict) -> Dict[str, Any]:
        """Restore MySQL database."""
        try:
            # Handle compressed file
            if db_file_path.endswith('.gz'):
                import gzip
                with gzip.open(db_file_path, 'rt') as f:
                    sql_content = f.read()
                
                # Write to temporary file
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.sql') as temp_file:
                    temp_file.write(sql_content)
                    temp_sql_path = temp_file.name
            else:
                temp_sql_path = db_file_path
            
            # Close Django database connections
            from django.db import connections
            connections.close_all()
            
            cmd = [
                'mysql',
                f"--host={db_config.get('HOST', 'localhost')}",
                f"--port={db_config.get('PORT', 3306)}",
                f"--user={db_config['USER']}",
                f"--password={db_config['PASSWORD']}",
                db_config['NAME']
            ]
            
            with open(temp_sql_path, 'r') as f:
                subprocess.run(cmd, stdin=f, check=True, stderr=subprocess.PIPE)
            
            # Cleanup temporary file if created
            if temp_sql_path != db_file_path:
                os.unlink(temp_sql_path)
            
            return {
                'success': True,
                'restored_file': db_file_path,
                'errors': []
            }
            
        except subprocess.CalledProcessError as e:
            return {
                'success': False,
                'restored_file': '',
                'errors': [f"mysql restore failed: {e.stderr.decode() if e.stderr else str(e)}"]
            }
        except Exception as e:
            return {
                'success': False,
                'restored_file': '',
                'errors': [str(e)]
            }
    
    def _restore_postgresql(self, db_file_path: str, db_config: Dict) -> Dict[str, Any]:
        """Restore PostgreSQL database."""
        try:
            # Handle compressed file
            if db_file_path.endswith('.gz'):
                import gzip
                with gzip.open(db_file_path, 'rt') as f:
                    sql_content = f.read()
                
                # Write to temporary file
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.sql') as temp_file:
                    temp_file.write(sql_content)
                    temp_sql_path = temp_file.name
            else:
                temp_sql_path = db_file_path
            
            # Close Django database connections
            from django.db import connections
            connections.close_all()
            
            env = os.environ.copy()
            env['PGPASSWORD'] = db_config['PASSWORD']
            
            cmd = [
                'psql',
                f"--host={db_config.get('HOST', 'localhost')}",
                f"--port={db_config.get('PORT', 5432)}",
                f"--username={db_config['USER']}",
                '--no-password',
                f"--dbname={db_config['NAME']}",
                f"--file={temp_sql_path}"
            ]
            
            subprocess.run(cmd, check=True, stderr=subprocess.PIPE, env=env)
            
            # Cleanup temporary file if created
            if temp_sql_path != db_file_path:
                os.unlink(temp_sql_path)
            
            return {
                'success': True,
                'restored_file': db_file_path,
                'errors': []
            }
            
        except subprocess.CalledProcessError as e:
            return {
                'success': False,
                'restored_file': '',
                'errors': [f"psql restore failed: {e.stderr.decode() if e.stderr else str(e)}"]
            }
        except Exception as e:
            return {
                'success': False,
                'restored_file': '',
                'errors': [str(e)]
            }
    
    def _restore_django_loaddata(self, db_file_path: str) -> Dict[str, Any]:
        """Restore using Django's loaddata command."""
        try:
            # Handle compressed file
            if db_file_path.endswith('.gz'):
                import gzip
                with gzip.open(db_file_path, 'rt') as f:
                    json_content = f.read()
                
                # Write to temporary file
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
                    temp_file.write(json_content)
                    temp_json_path = temp_file.name
            else:
                temp_json_path = db_file_path
            
            # Close Django database connections and flush
            from django.db import connections
            from django.core.management import call_command
            connections.close_all()
            
            # Flush existing data and load backup
            call_command('flush', '--noinput')
            call_command('loaddata', temp_json_path)
            
            # Cleanup temporary file if created
            if temp_json_path != db_file_path:
                os.unlink(temp_json_path)
            
            return {
                'success': True,
                'restored_file': db_file_path,
                'errors': []
            }
            
        except Exception as e:
            return {
                'success': False,
                'restored_file': '',
                'errors': [str(e)]
            }
    
    def _restore_media_files(self, backup_path: str) -> Dict[str, Any]:
        """Restore media files from backup."""
        result = {
            'success': True,
            'errors': [],
            'restored_count': 0,
            'backup_created': False
        }
        
        try:
            media_backup_path = os.path.join(backup_path, 'media')
            
            if not os.path.exists(media_backup_path):
                result['success'] = False
                result['errors'].append("No media files found in backup")
                return result
            
            media_root = settings.MEDIA_ROOT
            
            # Create backup of current media before restoration
            if os.path.exists(media_root):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                media_backup_dir = f"{media_root}_backup_{timestamp}"
                shutil.copytree(media_root, media_backup_dir)
                result['backup_created'] = True
            
            # Remove existing media directory
            if os.path.exists(media_root):
                shutil.rmtree(media_root)
            
            # Restore media files
            shutil.copytree(media_backup_path, media_root)
            
            # Count restored files
            file_count = 0
            for root, dirs, files in os.walk(media_root):
                file_count += len(files)
            
            result['restored_count'] = file_count
            
        except Exception as e:
            logger.error(f"Media files restoration failed: {e}")
            result['success'] = False
            result['errors'].append(str(e))
        
        return result
    
    def _analyze_configuration_restore(self, backup_path: str) -> Dict[str, Any]:
        """Analyze configuration files in backup (informational only)."""
        result = {
            'success': True,
            'files_found': [],
            'warnings': [],
            'recommendations': []
        }
        
        try:
            config_path = os.path.join(backup_path, 'configuration')
            
            if not os.path.exists(config_path):
                result['warnings'].append("No configuration backup found")
                return result
            
            # List configuration files found
            for file in os.listdir(config_path):
                result['files_found'].append(file)
            
            # Add warnings about manual restoration
            result['warnings'].extend([
                "Configuration files require manual review and restoration",
                "Check environment.json for environment variables",
                "Review django_settings.json for configuration changes",
                "Sensitive values have been redacted for security"
            ])
            
            result['recommendations'].extend([
                "Compare backup configuration with current settings",
                "Update environment variables manually if needed",
                "Restart application after configuration changes",
                "Verify all settings before going to production"
            ])
            
        except Exception as e:
            logger.error(f"Configuration analysis failed: {e}")
            result['success'] = False
            result['warnings'].append(f"Configuration analysis failed: {str(e)}")
        
        return result
    
    def get_backup_restoration_info(self, backup_name: str) -> Dict[str, Any]:
        """Get detailed information about what can be restored from a backup."""
        backup_info = self._find_backup(backup_name)
        
        if not backup_info:
            return {
                'success': False,
                'error': f"Backup '{backup_name}' not found"
            }
        
        # Extract or examine backup to see what components are available
        extraction_path = self._extract_backup(backup_info)
        
        if not extraction_path:
            return {
                'success': False,
                'error': "Failed to examine backup contents"
            }
        
        try:
            components = {
                'database': False,
                'media': False,
                'configuration': False
            }
            
            component_details = {}
            
            # Check for database files
            db_files = [f for f in os.listdir(extraction_path) 
                       if f.startswith('database_') and 
                       (f.endswith('.sql') or f.endswith('.db') or f.endswith('.json') or f.endswith('.gz'))]
            
            if db_files:
                components['database'] = True
                component_details['database'] = {
                    'files': db_files,
                    'primary_file': db_files[0]
                }
            
            # Check for media directory
            media_path = os.path.join(extraction_path, 'media')
            if os.path.exists(media_path):
                components['media'] = True
                file_count = sum(len(files) for _, _, files in os.walk(media_path))
                component_details['media'] = {
                    'file_count': file_count,
                    'path': 'media/'
                }
            
            # Check for configuration
            config_path = os.path.join(extraction_path, 'configuration')
            if os.path.exists(config_path):
                components['configuration'] = True
                config_files = os.listdir(config_path)
                component_details['configuration'] = {
                    'files': config_files
                }
            
            # Cleanup if temporary extraction
            if extraction_path != backup_info['file_path']:
                shutil.rmtree(extraction_path, ignore_errors=True)
            
            return {
                'success': True,
                'backup_info': backup_info,
                'available_components': components,
                'component_details': component_details,
                'warnings': [
                    "Database restoration will overwrite current data",
                    "Media restoration will replace current files",
                    "Configuration requires manual review"
                ]
            }
            
        except Exception as e:
            if extraction_path != backup_info['file_path']:
                shutil.rmtree(extraction_path, ignore_errors=True)
            
            return {
                'success': False,
                'error': f"Failed to analyze backup: {str(e)}"
            }
    
    def run_scheduled_backups(self) -> Dict[str, Any]:
        """
        Execute all scheduled backups that are due to run.
        
        Returns:
            Dictionary with results of all scheduled backup runs
        """
        from .models import BackupSchedule
        
        results = {
            'total_schedules': 0,
            'executed': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'schedule_results': [],
            'errors': []
        }
        
        try:
            # Get all enabled backup schedules
            schedules = BackupSchedule.objects.filter(enabled=True).exclude(frequency='disabled')
            results['total_schedules'] = schedules.count()
            
            for schedule in schedules:
                schedule_result = self._execute_scheduled_backup(schedule)
                results['schedule_results'].append(schedule_result)
                
                if schedule_result['executed']:
                    results['executed'] += 1
                    if schedule_result['success']:
                        results['successful'] += 1
                    else:
                        results['failed'] += 1
                        results['errors'].extend(schedule_result.get('errors', []))
                else:
                    results['skipped'] += 1
            
            logger.info(f"Scheduled backup run completed: {results['successful']}/{results['executed']} successful")
            
        except Exception as e:
            error_msg = f"Failed to run scheduled backups: {str(e)}"
            logger.error(error_msg)
            results['errors'].append(error_msg)
        
        return results
    
    def _execute_scheduled_backup(self, schedule, force_run: bool = False) -> Dict[str, Any]:
        """
        Execute a single scheduled backup.
        
        Args:
            schedule: BackupSchedule instance
            force_run: If True, bypass schedule timing checks
            
        Returns:
            Dictionary with execution results
        """
        result = {
            'schedule_id': schedule.id,
            'schedule_name': schedule.name,
            'executed': False,
            'success': False,
            'backup_name': '',
            'errors': [],
            'skipped_reason': ''
        }
        
        try:
            # Check if backup should run now (unless forced)
            if not force_run and not schedule.should_run_now():
                result['skipped_reason'] = 'Not scheduled to run at this time'
                return result
            
            result['executed'] = True
            
            # Determine backup components based on schedule settings
            description = f"Automated backup - {schedule.name} ({schedule.frequency})"
            
            # Create the backup with the components specified in the schedule
            if schedule.include_database and schedule.include_media:
                # Full backup with media
                backup_result = self.create_full_backup(
                    include_media=True,
                    description=description
                )
            elif schedule.include_database:
                # Database-only backup
                backup_result = self.create_database_backup(description=description)
            else:
                # Fallback to database backup if no database is selected but media is
                # (media-only backups aren't supported by this service)
                backup_result = self.create_database_backup(description=description)
            
            if backup_result['success']:
                result['success'] = True
                result['backup_name'] = backup_result['backup_name']
                
                # Record successful run
                schedule.record_run(
                    success=True,
                    backup_name=backup_result['backup_name']
                )
                
                # Clean up old automated backups
                self._cleanup_automated_backups(schedule)
                
                logger.info(f"Automated backup '{backup_result['backup_name']}' created successfully for schedule '{schedule.name}'")
                
            else:
                result['success'] = False
                result['errors'] = backup_result.get('errors', [])
                
                # Record failed run
                error_msg = '; '.join(backup_result.get('errors', ['Unknown error']))
                schedule.record_run(
                    success=False,
                    error_message=error_msg
                )
                
                logger.error(f"Automated backup failed for schedule '{schedule.name}': {error_msg}")
                logger.error(f"Backup result details: {backup_result}")
                
                # Send notification email if configured (but not for test runs)
                if not force_run:
                    self._send_backup_failure_notification(schedule, error_msg)
                
        except Exception as e:
            error_msg = f"Failed to execute scheduled backup '{schedule.name}': {str(e)}"
            result['errors'].append(error_msg)
            logger.error(error_msg)
            
            # Record the exception
            schedule.record_run(
                success=False,
                error_message=str(e)
            )
        
        return result
    
    def _cleanup_automated_backups(self, schedule) -> None:
        """
        Clean up old automated backups based on schedule settings.
        
        Args:
            schedule: BackupSchedule instance
        """
        try:
            backups = self.list_backups()
            
            # Filter for automated backups from this schedule
            automated_backups = []
            schedule_pattern = f"Automated backup - {schedule.name}"
            
            for backup in backups:
                if backup.get('description', '').startswith(schedule_pattern):
                    backup['timestamp_obj'] = datetime.fromisoformat(
                        backup['timestamp'].replace('Z', '+00:00')
                    ).replace(tzinfo=None)
                    automated_backups.append(backup)
            
            # Sort by timestamp (newest first)
            automated_backups.sort(key=lambda x: x['timestamp_obj'], reverse=True)
            
            # Remove backups exceeding max count
            if len(automated_backups) > schedule.max_backups_to_keep:
                excess_backups = automated_backups[schedule.max_backups_to_keep:]
                for backup in excess_backups:
                    self._delete_backup_files(backup['backup_name'])
                    logger.info(f"Deleted excess automated backup: {backup['backup_name']}")
            
            # Remove backups older than retention period
            cutoff_date = datetime.now() - timedelta(days=schedule.retention_days)
            for backup in automated_backups:
                if backup['timestamp_obj'] < cutoff_date:
                    self._delete_backup_files(backup['backup_name'])
                    logger.info(f"Deleted expired automated backup: {backup['backup_name']}")
                    
        except Exception as e:
            logger.error(f"Failed to cleanup automated backups for schedule '{schedule.name}': {str(e)}")
    
    def _send_backup_failure_notification(self, schedule, error_message: str) -> None:
        """
        Send email notification for backup failures.
        
        Args:
            schedule: BackupSchedule instance
            error_message: Error message to include
        """
        if not schedule.notification_email:
            return
        
        try:
            from django.core.mail import send_mail
            from django.conf import settings
            
            subject = f"Backup Failure Alert - {schedule.name}"
            message = f"""
Automated backup '{schedule.name}' has failed.

Schedule Details:
- Name: {schedule.name}
- Frequency: {schedule.frequency}
- Last Success: {schedule.last_success or 'Never'}
- Consecutive Failures: {schedule.consecutive_failures}

Error Details:
{error_message}

Please check the backup system and resolve any issues.

This is an automated message from the Labitory backup system.
            """.strip()
            
            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@localhost'),
                recipient_list=[schedule.notification_email],
                fail_silently=True
            )
            
            logger.info(f"Backup failure notification sent to {schedule.notification_email}")
            
        except Exception as e:
            logger.error(f"Failed to send backup failure notification: {str(e)}")
    
    def get_backup_schedules_status(self) -> Dict[str, Any]:
        """
        Get status information for all backup schedules.
        
        Returns:
            Dictionary with schedule status information
        """
        from .models import BackupSchedule
        
        try:
            schedules = BackupSchedule.objects.all()
            
            status = {
                'total_schedules': schedules.count(),
                'enabled_schedules': schedules.filter(enabled=True).exclude(frequency='disabled').count(),
                'healthy_schedules': 0,
                'schedules': [],
                'next_run': None
            }
            
            next_run_times = []
            
            for schedule in schedules:
                schedule_info = {
                    'id': schedule.id,
                    'name': schedule.name,
                    'enabled': schedule.enabled,
                    'frequency': schedule.frequency,
                    'next_run': schedule.get_next_run_time(),
                    'last_run': schedule.last_run,
                    'last_success': schedule.last_success,
                    'success_rate': schedule.success_rate,
                    'is_healthy': schedule.is_healthy,
                    'consecutive_failures': schedule.consecutive_failures
                }
                
                if schedule.is_healthy:
                    status['healthy_schedules'] += 1
                
                if schedule_info['next_run']:
                    next_run_times.append(schedule_info['next_run'])
                
                status['schedules'].append(schedule_info)
            
            # Find the next overall run time
            if next_run_times:
                status['next_run'] = min(next_run_times)
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to get backup schedules status: {str(e)}")
            return {
                'error': str(e),
                'total_schedules': 0,
                'enabled_schedules': 0,
                'healthy_schedules': 0,
                'schedules': [],
                'next_run': None
            }
    
    def test_scheduled_backup(self, schedule_id: int) -> Dict[str, Any]:
        """
        Test a scheduled backup without waiting for the scheduled time.
        
        Args:
            schedule_id: ID of the BackupSchedule to test
            
        Returns:
            Dictionary with test results
        """
        from .models import BackupSchedule
        
        try:
            schedule = BackupSchedule.objects.get(id=schedule_id)
            
            # Execute the backup with force flag
            result = self._execute_scheduled_backup(schedule, force_run=True)
            result['test_mode'] = True
            
            return result
            
        except BackupSchedule.DoesNotExist:
            return {
                'success': False,
                'error': f"Backup schedule with ID {schedule_id} not found"
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Failed to test scheduled backup: {str(e)}"
            }