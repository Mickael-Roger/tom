#!/usr/bin/env python3
"""
HTTP Helper for Tom - Clean error handling for HTTP requests
Replaces direct requests calls with methods that provide intelligent logging
"""

import requests
from requests.exceptions import (
    ConnectTimeout, ReadTimeout, Timeout, ConnectionError, 
    HTTPError, RequestException, TooManyRedirects
)
from tomlogger import logger

class TomHttpHelper:
    """HTTP helper with clean error handling and logging"""
    
    def __init__(self, module_name, default_timeout=30):
        self.module_name = module_name
        self.default_timeout = default_timeout
        self.session = requests.Session()
    
    def _log_error(self, method, url, error, extra_context=""):
        """Log HTTP error in a readable format"""
        error_type = type(error).__name__
        
        if isinstance(error, ConnectTimeout):
            message = f"Connection timeout to {url}"
        elif isinstance(error, ReadTimeout):
            message = f"Read timeout from {url}"
        elif isinstance(error, ConnectionError):
            message = f"Connection error to {url}"
        elif isinstance(error, HTTPError):
            message = f"HTTP {error.response.status_code} error for {url}"
        elif isinstance(error, TooManyRedirects):
            message = f"Too many redirects for {url}"
        else:
            message = f"Request error {error_type} for {url}: {str(error)}"
        
        if extra_context:
            message = f"{message} - {extra_context}"
            
        logger.error(message, module_name=self.module_name)
        
    def get(self, url, timeout=None, **kwargs):
        """Execute GET request with error handling"""
        timeout = timeout or self.default_timeout
        try:
            response = self.session.get(url, timeout=timeout, **kwargs)
            response.raise_for_status()  # Raise exception for HTTP error codes
            return response
        except RequestException as e:
            self._log_error("GET", url, e)
            raise
    
    def post(self, url, timeout=None, **kwargs):
        """Execute POST request with error handling"""
        timeout = timeout or self.default_timeout
        try:
            response = self.session.post(url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except RequestException as e:
            self._log_error("POST", url, e)
            raise
    
    def put(self, url, timeout=None, **kwargs):
        """Execute PUT request with error handling"""
        timeout = timeout or self.default_timeout
        try:
            response = self.session.put(url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except RequestException as e:
            self._log_error("PUT", url, e)
            raise
    
    def delete(self, url, timeout=None, **kwargs):
        """Execute DELETE request with error handling"""
        timeout = timeout or self.default_timeout
        try:
            response = self.session.delete(url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except RequestException as e:
            self._log_error("DELETE", url, e)
            raise
    
    def safe_get(self, url, timeout=None, return_none_on_error=True, **kwargs):
        """Safe GET that doesn't raise exceptions but returns None on error"""
        try:
            return self.get(url, timeout, **kwargs)
        except RequestException:
            if return_none_on_error:
                return None
            raise
    
    def safe_post(self, url, timeout=None, return_none_on_error=True, **kwargs):
        """Safe POST that doesn't raise exceptions but returns None on error"""
        try:
            return self.post(url, timeout, **kwargs)
        except RequestException:
            if return_none_on_error:
                return None
            raise
    
    def close(self):
        """Close the session"""
        self.session.close()
    
    def __enter__(self):
        """Context manager support"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support"""
        self.close()


def create_http_helper(module_name, default_timeout=30):
    """Create a TomHttpHelper instance for a module"""
    return TomHttpHelper(module_name, default_timeout)

def safe_get(url, module_name, default_timeout=30, **kwargs):
    """Safe GET without persistent session"""
    with TomHttpHelper(module_name, default_timeout) as helper:
        return helper.safe_get(url, **kwargs)

def safe_post(url, module_name, default_timeout=30, **kwargs):
    """Safe POST without persistent session"""
    with TomHttpHelper(module_name, default_timeout) as helper:
        return helper.safe_post(url, **kwargs)