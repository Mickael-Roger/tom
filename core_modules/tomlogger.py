import logging
import sys
from datetime import datetime
from enum import Enum
from typing import Optional
import threading

class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class TomLogger:
    """
    Centralized logging system for Tom application with formatted output including:
    - Timestamp
    - Log level
    - Username (if available)
    - Client type (web, pwa, tui)
    - Message
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(TomLogger, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self._context = threading.local()
        
        # Configure the logger
        self.logger = logging.getLogger('tom')
        self.logger.setLevel(logging.DEBUG)
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # Create custom formatter
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(username)-12s | %(module_name)-15s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # Prevent propagation to avoid duplicate logs
        self.logger.propagate = False
    
    def set_context(self, username: Optional[str] = None, client_type: Optional[str] = None, module_name: Optional[str] = None):
        """Set the context for the current thread"""
        if not hasattr(self._context, 'username'):
            self._context.username = None
        if not hasattr(self._context, 'client_type'):
            self._context.client_type = None
        if not hasattr(self._context, 'module_name'):
            self._context.module_name = None
            
        if username is not None:
            self._context.username = username
        if client_type is not None:
            self._context.client_type = client_type
        if module_name is not None:
            self._context.module_name = module_name
        elif module_name is None and hasattr(self._context, 'module_name'):
            # Explicitly reset module name when None is passed
            self._context.module_name = None
    
    def get_context(self):
        """Get the current context"""
        username = getattr(self._context, 'username', None) or "system"
        client_type = getattr(self._context, 'client_type', None) or "sys"
        module_name = getattr(self._context, 'module_name', None) or "system"
        return username, client_type, module_name
    
    def _log(self, level: LogLevel, message: str, username: Optional[str] = None, client_type: Optional[str] = None, module_name: Optional[str] = None):
        """Internal logging method"""
        # Use provided context or fall back to thread context
        if username is None or client_type is None or module_name is None:
            ctx_username, ctx_client_type, ctx_module_name = self.get_context()
            username = username or ctx_username
            client_type = client_type or ctx_client_type
            module_name = module_name or ctx_module_name
        
        # Create log record with extra fields
        extra = {
            'username': username[:12] if username else "system",
            'client_type': client_type[:4] if client_type else "sys",
            'module_name': module_name[:15] if module_name else "system"
        }
        
        # Map our enum to logging levels
        level_map = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL
        }
        
        self.logger.log(level_map[level], message, extra=extra)
    
    def debug(self, message: str, username: Optional[str] = None, client_type: Optional[str] = None, module_name: Optional[str] = None):
        """Log debug message"""
        self._log(LogLevel.DEBUG, message, username, client_type, module_name)
    
    def info(self, message: str, username: Optional[str] = None, client_type: Optional[str] = None, module_name: Optional[str] = None):
        """Log info message"""
        self._log(LogLevel.INFO, message, username, client_type, module_name)
    
    def warning(self, message: str, username: Optional[str] = None, client_type: Optional[str] = None, module_name: Optional[str] = None):
        """Log warning message"""
        self._log(LogLevel.WARNING, message, username, client_type, module_name)
    
    def error(self, message: str, username: Optional[str] = None, client_type: Optional[str] = None, module_name: Optional[str] = None):
        """Log error message"""
        self._log(LogLevel.ERROR, message, username, client_type, module_name)
    
    def critical(self, message: str, username: Optional[str] = None, client_type: Optional[str] = None, module_name: Optional[str] = None):
        """Log critical message"""
        self._log(LogLevel.CRITICAL, message, username, client_type, module_name)
    
    def module_load(self, module_name: str, username: Optional[str] = None, success: bool = True):
        """Log module loading"""
        if success:
            self.info(f"✅ Module '{module_name}' loaded successfully", username, module_name="modules")
        else:
            self.error(f"❌ Failed to load module '{module_name}'", username, module_name="modules")
    
    def module_reload(self, module_name: str, username: Optional[str] = None, success: bool = True):
        """Log module hot reload"""
        if success:
            self.info(f"🔄 Module '{module_name}' hot reloaded successfully", username, module_name="modules")
        else:
            self.error(f"❌ Failed to hot reload module '{module_name}'", username, module_name="modules")
    
    def file_sync(self, filename: str, success: bool = True):
        """Log file synchronization"""
        if success:
            self.info(f"📄 Copied module: {filename}", module_name="modules")
        else:
            self.error(f"❌ Failed to copy module: {filename}", module_name="modules")
    
    def config_reload(self, success: bool = True):
        """Log configuration reload"""
        if success:
            self.info("✅ Configuration reload completed", module_name="system")
        else:
            self.error("❌ Configuration reload failed", module_name="system")
    
    def user_request(self, message: str, username: str, client_type: str = "web"):
        """Log user request"""
        self.info(f"📥 User request: {message}", username, client_type, module_name="system")
    
    def user_response(self, message: str, username: str, client_type: str = "web"):
        """Log user response"""
        self.info(f"📤 Response sent: {message[:100]}{'...' if len(message) > 100 else ''}", username, client_type, module_name="system")
    
    def auth_event(self, event: str, username: str, client_type: str = "web", success: bool = True):
        """Log authentication events"""
        if success:
            self.info(f"🔐 Auth {event}: {username}", username, client_type, module_name="system")
        else:
            self.warning(f"🔒 Auth {event} failed: {username}", username, client_type, module_name="system")
    
    def startup(self, message: str):
        """Log startup messages"""
        self.info(f"🚀 {message}", module_name="system")
    
    def shutdown(self, message: str):
        """Log shutdown messages"""
        self.info(f"🛑 {message}", module_name="system")
    
    def file_watcher(self, message: str):
        """Log file watcher events"""
        self.info(f"🔍 {message}", module_name="system")

# Global logger instance
logger = TomLogger()

# Convenience functions for easy access
def set_log_context(username: Optional[str] = None, client_type: Optional[str] = None, module_name: Optional[str] = None):
    """Set logging context for current thread"""
    logger.set_context(username, client_type, module_name)

def debug(message: str, username: Optional[str] = None, client_type: Optional[str] = None, module_name: Optional[str] = None):
    logger.debug(message, username, client_type, module_name)

def info(message: str, username: Optional[str] = None, client_type: Optional[str] = None, module_name: Optional[str] = None):
    logger.info(message, username, client_type, module_name)

def warning(message: str, username: Optional[str] = None, client_type: Optional[str] = None, module_name: Optional[str] = None):
    logger.warning(message, username, client_type, module_name)

def error(message: str, username: Optional[str] = None, client_type: Optional[str] = None, module_name: Optional[str] = None):
    logger.error(message, username, client_type, module_name)

def critical(message: str, username: Optional[str] = None, client_type: Optional[str] = None, module_name: Optional[str] = None):
    logger.critical(message, username, client_type, module_name)