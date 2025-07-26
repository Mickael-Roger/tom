"""
Test configuration loader utility for integration tests.

This module provides utilities for loading test configuration from config.yml
and preparing module configurations for integration tests.
"""

import os
import yaml
import tempfile
from typing import Dict, Any, Optional, Union


class TestConfig:
    """Test configuration loader and manager"""
    
    def __init__(self):
        self.config_loaded = False
        self.config = {}
        self.temp_dirs = {}
        self.temp_all_datadir = None
        
    def load_config(self):
        """Load configuration from config.yml file"""
        try:
            config_path = self._find_config_file()
            if not config_path:
                print("Warning: No config.yml file found. Integration tests will be skipped.")
                return False
                
            with open(config_path, 'r', encoding='utf-8') as file:
                self.config = yaml.safe_load(file) or {}
                self.config_loaded = True
                return True
                
        except Exception as e:
            print(f"Warning: Failed to load config.yml: {e}. Integration tests will be skipped.")
            return False
    
    def _find_config_file(self) -> Optional[str]:
        """Find config.yml file in project directory"""
        # Try common locations
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)  # Go up from tests/ to project root
        
        # Look for config.yml in project root
        config_paths = [
            os.path.join(project_root, 'config.yml'),
            '/config.yml',  # Docker path
            os.path.join(os.getcwd(), 'config.yml'),
        ]
        
        for path in config_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def get_global_config(self) -> Dict[str, Any]:
        """Get global configuration section"""
        return self.config.get('global', {})
    
    def has_service_config(self, service_name: str) -> bool:
        """Check if a service is configured in global services"""
        services = self.config.get('services', {})
        return service_name in services and services[service_name] is not None
    
    def has_user_service_config(self, username: str, service_name: str) -> bool:
        """Check if a service is configured for a specific user"""
        users = self.config.get('users', [])
        for user in users:
            if user.get('username') == username:
                user_services = user.get('services', {})
                return service_name in user_services and user_services[service_name] is not None
        return False
    
    def get_service_config(self, service_name: str) -> Dict[str, Any]:
        """Get global service configuration"""
        return self.config.get('services', {}).get(service_name, {})
    
    def get_user_service_config(self, username: str, service_name: str) -> Dict[str, Any]:
        """Get user-specific service configuration"""
        users = self.config.get('users', [])
        for user in users:
            if user.get('username') == username:
                return user.get('services', {}).get(service_name, {})
        return {}
    
    def create_temp_user_dir(self, username: str) -> str:
        """Create temporary user directory for tests"""
        if username not in self.temp_dirs:
            temp_dir = tempfile.mkdtemp(prefix=f'test_user_{username}_')
            self.temp_dirs[username] = temp_dir
        return self.temp_dirs[username]
    
    def create_temp_all_datadir(self) -> str:
        """Create temporary all_datadir for tests"""
        if self.temp_all_datadir is None:
            self.temp_all_datadir = tempfile.mkdtemp(prefix='test_all_data_')
        return self.temp_all_datadir
    
    def cleanup_temp_dirs(self):
        """Clean up temporary directories"""
        import shutil
        for temp_dir in self.temp_dirs.values():
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
        if self.temp_all_datadir:
            try:
                shutil.rmtree(self.temp_all_datadir)
            except Exception:
                pass
        self.temp_dirs.clear()
        self.temp_all_datadir = None


# Global instance
_test_config = None


def load_test_config() -> TestConfig:
    """Load test configuration (singleton pattern)"""
    global _test_config
    if _test_config is None:
        _test_config = TestConfig()
        _test_config.load_config()
    return _test_config


def skip_if_no_config(test_func):
    """Decorator to skip test if no configuration is available"""
    def wrapper(self):
        test_config = load_test_config()
        if not test_config.config_loaded:
            self.skipTest("Test configuration not available - skipping integration tests")
        return test_func(self)
    return wrapper


def get_module_config_for_test(module_name: str, global_config: Dict[str, Any], 
                              is_personal: bool = False, username: str = 'test_user') -> Dict[str, Any]:
    """
    Get module configuration for integration tests.
    
    Args:
        module_name: Name of the module
        global_config: Global configuration dict
        is_personal: Whether this is a personal module
        username: Username for personal modules
        
    Returns:
        Configuration dict for the module
    """
    test_config = load_test_config()
    
    if not test_config.config_loaded:
        return {}
    
    # Base configuration from global section
    # Use temporary directories for test isolation
    all_datadir = test_config.create_temp_all_datadir()
    config = {
        'all_datadir': global_config.get('all_datadir', all_datadir),
        'user_datadir': global_config.get('user_datadir', '/tmp/test_user_data/'),
        'sessions': global_config.get('sessions', '/tmp/test_sessions/'),
        'username': username,
    }
    
    if is_personal:
        # Personal module - get config from user services
        user_service_config = test_config.get_user_service_config(username, module_name)
        config.update(user_service_config)
        
        # Create user-specific directory
        user_dir = test_config.create_temp_user_dir(username)
        config['user_datadir'] = os.path.dirname(user_dir)  # Parent dir
    else:
        # Global module - get config from global services
        service_config = test_config.get_service_config(module_name)
        config.update(service_config)
    
    # Ensure data directories exist
    os.makedirs(config['all_datadir'], exist_ok=True)
    os.makedirs(config['user_datadir'], exist_ok=True)
    if 'sessions' in config:
        os.makedirs(config['sessions'], exist_ok=True)
    
    return config


def cleanup_test_config():
    """Clean up test configuration resources"""
    global _test_config
    if _test_config:
        _test_config.cleanup_temp_dirs()