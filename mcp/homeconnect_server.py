#!/usr/bin/env python3
"""
HomeConnect MCP Server
Provides HomeConnect dishwasher integration functionality via MCP protocol
Based on the original tomhomeconnect.py module
"""

import json
import os
import sys
import yaml
import requests
import time
import threading
from datetime import datetime
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import Tool, TextContent

# Add lib directory to path for imports
sys.path.insert(0, '/app/lib')
try:
    from tomlogger import init_logger
    import tomlogger
except ImportError:
    # Fallback if tomlogger is not available
    import logging
    logging.basicConfig(level=logging.INFO)
    tomlogger = None

# Initialize logging
log_level = os.environ.get('TOM_LOG_LEVEL', 'INFO')
if tomlogger:
    logger = init_logger(log_level)
    tomlogger.info(f"🚀 HomeConnect MCP Server starting with log level: {log_level}", module_name="homeconnect")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "Control and monitor Home-Connect compatible dishwashers including status checks, program management, and remote start capabilities."

# Initialize FastMCP server
server = FastMCP(name="homeconnect-server", stateless_http=True, host="0.0.0.0", port=80)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file"""
    config_path = '/data/config.yml'
    
    if tomlogger:
        tomlogger.info(f"Loading configuration from {config_path}", module_name="homeconnect")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        if tomlogger:
            tomlogger.error(f"Configuration file not found: {config_path}", module_name="homeconnect")
        else:
            print(f"ERROR: Configuration file not found: {config_path}")
        return {}
    except yaml.YAMLError as exc:
        if tomlogger:
            tomlogger.error(f"Error parsing YAML configuration: {exc}", module_name="homeconnect")
        else:
            print(f"ERROR: Error parsing YAML configuration: {exc}")
        return {}


class HomeConnectService:
    """HomeConnect service class based on original HomeConnect module"""
    
    _token_refresh_thread_started = False
    _token_refresh_thread = None
    _token_cache_file = '/data/homeconnect.json'
    
    def __init__(self, config: Dict[str, Any]):
        # Load homeconnect configuration from config
        homeconnect_config = config.get('homeconnect', {})
        
        # Token configuration from homeconnect.token
        token_config = homeconnect_config.get('token', {})
        self.config_access_token = token_config.get('access_token', '')
        self.config_refresh_token = token_config.get('refresh_token', '')
        
        if not self.config_access_token:
            if tomlogger:
                tomlogger.error("HomeConnect: No access_token found in homeconnect.token configuration", module_name="homeconnect")
            raise ValueError("HomeConnect access_token not configured")
        
        self.api_base_url = "https://api.home-connect.com"
        self.client_id = "F9ACB272F14EAEBABDC616492121073863A93923285BCA1904EDB53EE0CCA008"
        
        # Start token refresh thread only once across all instances
        if not HomeConnectService._token_refresh_thread_started:
            HomeConnectService._token_refresh_thread_started = True
            HomeConnectService._token_refresh_thread = threading.Thread(target=self._token_refresh_loop)
            HomeConnectService._token_refresh_thread.daemon = True
            HomeConnectService._token_refresh_thread.start()
        
        if tomlogger:
            tomlogger.info("✅ HomeConnect service initialized successfully", module_name="homeconnect")
    
    def _load_token_from_cache(self):
        """Load token from homeconnect.json cache file"""
        try:
            if not os.path.exists(self._token_cache_file):
                return None
                
            with open(self._token_cache_file, 'r', encoding='utf-8') as f:
                token_data = json.load(f)
                
            # Check if token is still valid (not expired)
            if self._is_token_valid(token_data):
                return token_data['access_token']
            else:
                if tomlogger:
                    tomlogger.info("HomeConnect: Cached token is expired", module_name="homeconnect")
                return None
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"HomeConnect: Error loading cached token: {e}", module_name="homeconnect")
            return None
    
    def _load_token_from_config(self):
        """Load token from configuration file"""
        try:
            if self.config_access_token:
                # Save full token data to cache if we have both access and refresh tokens
                if self.config_refresh_token:
                    self._save_token_to_cache(self.config_access_token, self.config_refresh_token)
                    if tomlogger:
                        tomlogger.info("HomeConnect: Loaded token with refresh token from config", module_name="homeconnect")
                
                return self.config_access_token
            else:
                if tomlogger:
                    tomlogger.error("HomeConnect: No access_token found in configuration", module_name="homeconnect")
                return None
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"HomeConnect: Error loading token from config: {e}", module_name="homeconnect")
            return None
    
    def _is_token_valid(self, token_data):
        """Check if token data is valid and not expired"""
        if not token_data or not isinstance(token_data, dict):
            return False
            
        required_fields = ['access_token', 'created_at', 'expires_in']
        if not all(field in token_data for field in required_fields):
            return False
            
        # Check if token is expired (with 5 minute buffer)
        current_time = time.time()
        expiry_time = token_data['created_at'] + token_data['expires_in'] - 300  # 5 minute buffer
        
        return current_time < expiry_time
    
    def _save_token_to_cache(self, access_token, refresh_token=None):
        """Save token to homeconnect.json cache file"""
        try:
            token_data = {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'created_at': time.time(),
                'expires_in': 86400  # 24 hours
            }
            
            with open(self._token_cache_file, 'w', encoding='utf-8') as f:
                json.dump(token_data, f, indent=2)
                
            if tomlogger:
                tomlogger.info("HomeConnect: Token saved to cache", module_name="homeconnect")
            return True
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"HomeConnect: Error saving token to cache: {e}", module_name="homeconnect")
            return False

    def _calculate_refresh_delay(self):
        """Calculate how long to wait before next token refresh (12h before expiration)"""
        try:
            if not os.path.exists(self._token_cache_file):
                return 0  # Refresh immediately if no cache
                
            with open(self._token_cache_file, 'r', encoding='utf-8') as f:
                token_data = json.load(f)
                
            if not self._is_token_valid(token_data):
                return 0  # Refresh immediately if expired
                
            # Calculate time until refresh (12h before expiration)
            current_time = time.time()
            created_at = token_data.get('created_at', current_time)
            expires_in = token_data.get('expires_in', 86400)  # Default 24h
            
            # Refresh 12 hours before expiration (43200 seconds = 12h)
            refresh_time = created_at + expires_in - 43200
            delay = max(0, refresh_time - current_time)
            
            if tomlogger:
                tomlogger.info(f"HomeConnect: Next token refresh in {delay/3600:.1f} hours", module_name="homeconnect")
            return delay
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"HomeConnect: Error calculating refresh delay: {e}", module_name="homeconnect")
            return 3600  # Default to 1 hour if error

    def _token_refresh_loop(self):
        """Background loop to refresh token 12 hours before expiration"""
        while True:
            try:
                # Calculate how long to wait before next refresh
                delay = self._calculate_refresh_delay()
                
                if delay > 0:
                    # Wait until it's time to refresh
                    time.sleep(delay)
                
                # Try to refresh the token
                if self._refresh_token():
                    if tomlogger:
                        tomlogger.info("HomeConnect: Token refreshed successfully", module_name="homeconnect")
                else:
                    if tomlogger:
                        tomlogger.error("HomeConnect: Token refresh failed", module_name="homeconnect")
                    # If refresh failed, try again in 1 hour
                    time.sleep(3600)
                    
            except Exception as e:
                if tomlogger:
                    tomlogger.error(f"HomeConnect: Token refresh loop error: {e}", module_name="homeconnect")
                # Continue loop even if there's an error
                time.sleep(3600)  # Wait 1 hour before retrying

    def _refresh_token_with_api(self, refresh_token):
        """Use refresh token to get a new access token from Home Connect API"""
        try:
            headers = {
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id
            }
            
            # Home Connect OAuth2 token endpoint
            token_url = "https://api.home-connect.com/security/oauth/token"
            response = requests.post(token_url, headers=headers, data=data, timeout=10)
            
            if response.status_code == 200:
                token_data = response.json()
                new_access_token = token_data.get('access_token')
                new_refresh_token = token_data.get('refresh_token', refresh_token)  # Keep old if not provided
                
                if new_access_token:
                    self._save_token_to_cache(new_access_token, new_refresh_token)
                    if tomlogger:
                        tomlogger.info("HomeConnect: Token refreshed successfully using refresh token", module_name="homeconnect")
                    return True
                    
            if tomlogger:
                tomlogger.error(f"HomeConnect: Failed to refresh token via API: {response.status_code} - {response.text}", module_name="homeconnect")
            return False
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"HomeConnect: Error refreshing token via API: {e}", module_name="homeconnect")
            return False

    def _refresh_token(self):
        """Refresh the access token using refresh token or config token as fallback"""
        # Check if we need to refresh (less than 12h remaining)
        refresh_delay = self._calculate_refresh_delay()
        if refresh_delay > 0:
            return True  # Not yet time to refresh
            
        # Time to refresh - try to use refresh token if available
        try:
            if os.path.exists(self._token_cache_file):
                with open(self._token_cache_file, 'r', encoding='utf-8') as f:
                    token_data = json.load(f)
                    
                refresh_token = token_data.get('refresh_token')
                if refresh_token:
                    if tomlogger:
                        tomlogger.info("HomeConnect: Attempting to refresh token using refresh token", module_name="homeconnect")
                    if self._refresh_token_with_api(refresh_token):
                        return True
                    else:
                        if tomlogger:
                            tomlogger.warning("HomeConnect: Refresh token failed, falling back to config token", module_name="homeconnect")
                        
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"HomeConnect: Error loading refresh token: {e}", module_name="homeconnect")
            
        # Fallback to config token
        config_token = self._load_token_from_config()
        if not config_token:
            if tomlogger:
                tomlogger.warning("HomeConnect: No token available in config", module_name="homeconnect")
            return False
            
        # Test if config token is valid by making a simple API call
        if self._test_token_validity(config_token):
            # Config token is valid, save it to cache
            self._save_token_to_cache(config_token)
            if tomlogger:
                tomlogger.info("HomeConnect: Config token validated and cached", module_name="homeconnect")
            return True
        else:
            if tomlogger:
                tomlogger.error("HomeConnect: Config token is invalid", module_name="homeconnect")
            return False
    
    def _test_token_validity(self, token):
        """Test if a token is valid by making a simple API call"""
        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept-Language": "en-US"
            }
            
            response = requests.get(f"{self.api_base_url}/api/homeappliances", headers=headers, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"HomeConnect: Error testing token validity: {e}", module_name="homeconnect")
            return False

    def _get_valid_token(self):
        """Get a valid access token, trying cache first, then config"""
        # Try cached token first
        cached_token = self._load_token_from_cache()
        if cached_token:
            return cached_token
            
        # No valid cached token, try config token
        config_token = self._load_token_from_config()
        if not config_token:
            return None
            
        # Test config token and cache it if valid
        if self._test_token_validity(config_token):
            self._save_token_to_cache(config_token)
            return config_token
        else:
            return None

    def _process_api_list(self, items):
        """Convert API list format ({key, value,...}) to dict {key: value}"""
        if not items:
            return {}
        return {item['key']: item.get('value') for item in items}

    def _create_summary(self, processed_status, processed_settings, active_program):
        """Create a readable summary from processed data"""
        summary = {
            "general_state": "Unknown", 
            "program": None, 
            "remaining_time_min": 0, 
            "alerts": []
        }
        
        op_state = processed_status.get('BSH.Common.Status.OperationState', '')
        
        if "Run" in op_state and active_program:
            summary["general_state"] = "Running"
            prog_key = active_program.get('key')
            if prog_key:
                summary["program"] = prog_key.split('.')[-1]
            
            # Search for remaining time in active program options
            rem_time = 0
            for option in active_program.get('options', []):
                if option.get('key') == 'BSH.Common.Option.RemainingProgramTime':
                    rem_time = option.get('value', 0)
                    break
            summary["remaining_time_min"] = rem_time // 60
            
        elif "Finished" in op_state:
            summary["general_state"] = "Finished"
        elif "Ready" in op_state:
            summary["general_state"] = "Ready"
        elif "Inactive" in op_state:
            summary["general_state"] = "Inactive"
        
        # Check for common alerts in settings
        if processed_settings.get("ConsumerProducts.Dishwasher.Setting.RinseAidLevel") == "Off":
            summary["alerts"].append("Low rinse aid level")
        if processed_settings.get("ConsumerProducts.Dishwasher.Setting.SaltLevel") == "Off":
            summary["alerts"].append("Low salt level")
            
        return summary

    def _get_appliance_details(self, haId, headers):
        """Get all details for a single appliance"""
        details = {}
        base_url = f"{self.api_base_url}/api/homeappliances/{haId}"
        
        # Status
        try:
            res = requests.get(f"{base_url}/status", headers=headers, timeout=10)
            details["raw_status"] = res.json().get('data', {}).get('status', []) if res.ok else []
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"HomeConnect: Error getting status for {haId}: {e}", module_name="homeconnect")
            details["raw_status"] = []
        
        # Settings
        try:
            res = requests.get(f"{base_url}/settings", headers=headers, timeout=10)
            details["raw_settings"] = res.json().get('data', {}).get('settings', []) if res.ok else []
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"HomeConnect: Error getting settings for {haId}: {e}", module_name="homeconnect")
            details["raw_settings"] = []
        
        # Active Program
        details["raw_active_program"] = None
        if any(isinstance(item.get('value'), str) and "Run" in item.get('value') for item in details["raw_status"]):
            try:
                res = requests.get(f"{base_url}/programs/active", headers=headers, timeout=10)
                if res.ok:
                    details["raw_active_program"] = res.json().get('data', {})
            except Exception as e:
                if tomlogger:
                    tomlogger.error(f"HomeConnect: Error getting active program for {haId}: {e}", module_name="homeconnect")
                
        return details

    def get_dishwasher_status(self) -> Dict[str, Any]:
        """Get the status of all connected dishwashers"""
        try:
            # Get valid token
            access_token = self._get_valid_token()
            if not access_token:
                return {"error": "Invalid or expired token. Please check HomeConnect configuration."}
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept-Language": "en-US"
            }
            
            # Get all appliances
            api_url = f"{self.api_base_url}/api/homeappliances"
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if not response.ok:
                if tomlogger:
                    tomlogger.error(f"HomeConnect: Failed to get appliances: {response.status_code} - {response.text}", module_name="homeconnect")
                return {"error": "Unable to retrieve appliance list", "details": response.text}
            
            all_appliances = response.json().get("data", {}).get("homeappliances", [])
            dishwashers = [app for app in all_appliances if app.get("type") == "Dishwasher"]
            
            if not dishwashers:
                return {"message": "No dishwashers found"}
            
            final_output = []
            for dw in dishwashers:
                haId = dw.get("haId")
                
                appliance_info = {
                    "name": dw.get("name"),
                    "haId": haId,
                    "brand": dw.get("brand"),
                    "type": dw.get("type"),
                    "connected": dw.get("connected"),
                    "summary": {},
                    "details": {}
                }
                
                if appliance_info["connected"]:
                    raw_details = self._get_appliance_details(haId, headers)
                    
                    # Process for better readability
                    processed_status = self._process_api_list(raw_details["raw_status"])
                    processed_settings = self._process_api_list(raw_details["raw_settings"])
                    
                    # Create summary
                    appliance_info["summary"] = self._create_summary(
                        processed_status, 
                        processed_settings, 
                        raw_details["raw_active_program"]
                    )
                    
                    # Add processed details
                    appliance_info["details"] = {
                        "status": processed_status,
                        "settings": processed_settings,
                        "active_program": raw_details["raw_active_program"]
                    }
                else:
                    appliance_info["summary"] = {"general_state": "Disconnected"}
                
                final_output.append(appliance_info)
            
            return {"dishwashers": final_output}
            
        except requests.exceptions.Timeout:
            if tomlogger:
                tomlogger.error("HomeConnect: Request timeout", module_name="homeconnect")
            return {"error": "Timeout connecting to Home-Connect API"}
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"HomeConnect: Error getting dishwasher status: {e}", module_name="homeconnect")
            return {"error": f"Error retrieving status: {str(e)}"}

    def start_dishwasher_program(self, haId: str, program_key: str, delayed_start_minutes: int = 0) -> Dict[str, Any]:
        """Start a dishwasher program"""
        try:
            # Get valid token
            access_token = self._get_valid_token()
            if not access_token:
                return {"error": "Invalid or expired token. Please check HomeConnect configuration."}
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept-Language": "en-US",
                "Content-Type": "application/vnd.bsh.sdk.v1+json"
            }
            
            # Prepare the program data
            program_data = {
                "data": {
                    "key": program_key,
                    "options": []
                }
            }
            
            # Add delayed start option if specified
            if delayed_start_minutes and delayed_start_minutes > 0:
                program_data["data"]["options"].append({
                    "key": "BSH.Common.Option.StartInRelative",
                    "value": delayed_start_minutes * 60,  # Convert minutes to seconds
                    "unit": "seconds"
                })
            
            # Start the program
            api_url = f"{self.api_base_url}/api/homeappliances/{haId}/programs/active"
            response = requests.put(api_url, headers=headers, json=program_data, timeout=10)
            
            if response.status_code == 204:
                # Success - program started
                delay_info = f" with {delayed_start_minutes} minutes delay" if delayed_start_minutes > 0 else ""
                return {
                    "success": True,
                    "message": f"Program '{program_key.split('.')[-1]}' started successfully{delay_info}",
                    "program_key": program_key,
                    "delayed_start_minutes": delayed_start_minutes
                }
            elif response.status_code == 409:
                # Conflict - dishwasher not ready
                return {"error": "Dishwasher is not ready to start a program. Check if it's powered on, door is closed, and remote control is enabled."}
            elif response.status_code == 404:
                # Not found - invalid haId or program
                return {"error": "Dishwasher or program not found. Check the appliance ID and program key."}
            else:
                if tomlogger:
                    tomlogger.error(f"HomeConnect: Failed to start program: {response.status_code} - {response.text}", module_name="homeconnect")
                return {"error": f"Failed to start program: HTTP {response.status_code}", "details": response.text}
            
        except requests.exceptions.Timeout:
            if tomlogger:
                tomlogger.error("HomeConnect: Request timeout while starting program", module_name="homeconnect")
            return {"error": "Timeout connecting to Home-Connect API"}
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"HomeConnect: Error starting dishwasher program: {e}", module_name="homeconnect")
            return {"error": f"Error starting program: {str(e)}"}

    def get_available_dishwasher_programs(self, haId: str) -> Dict[str, Any]:
        """Get available programs for a specific dishwasher"""
        try:
            # Get valid token
            access_token = self._get_valid_token()
            if not access_token:
                return {"error": "Invalid or expired token. Please check HomeConnect configuration."}
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept-Language": "en-US"
            }
            
            # Get available programs
            api_url = f"{self.api_base_url}/api/homeappliances/{haId}/programs/available"
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if not response.ok:
                if tomlogger:
                    tomlogger.error(f"HomeConnect: Failed to get available programs: {response.status_code} - {response.text}", module_name="homeconnect")
                return {"error": "Unable to retrieve available programs", "details": response.text}
            
            programs_data = response.json().get("data", {}).get("programs", [])
            
            # Process programs for better readability
            available_programs = []
            for program in programs_data:
                program_info = {
                    "key": program.get("key"),
                    "name": program.get("key", "").split(".")[-1] if program.get("key") else "Unknown",
                    "constraints": {}
                }
                
                # Add constraints if available
                if "constraints" in program:
                    program_info["constraints"] = program["constraints"]
                    
                available_programs.append(program_info)
            
            return {
                "success": True,
                "haId": haId,
                "available_programs": available_programs,
                "count": len(available_programs)
            }
            
        except requests.exceptions.Timeout:
            if tomlogger:
                tomlogger.error("HomeConnect: Request timeout while getting available programs", module_name="homeconnect")
            return {"error": "Timeout connecting to Home-Connect API"}
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"HomeConnect: Error getting available programs: {e}", module_name="homeconnect")
            return {"error": f"Error retrieving available programs: {str(e)}"}


# Load configuration and initialize homeconnect service
config = load_config()
homeconnect_service = HomeConnectService(config)


@server.tool()
def get_dishwasher_status() -> str:
    """Get the current status of all connected dishwashers including state, program, remaining time and alerts"""
    if tomlogger:
        tomlogger.info("Tool call: get_dishwasher_status", module_name="homeconnect")
    
    result = homeconnect_service.get_dishwasher_status()
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def start_dishwasher_program(haId: str, program_key: str, delayed_start_minutes: int = 0) -> str:
    """Start a dishwasher program. Use this when the user wants to start a specific wash cycle or program
    
    Args:
        haId: The Home Connect appliance ID of the dishwasher to start. Get this from get_dishwasher_status first if unknown.
        program_key: The program key to start. Common programs include: 'Dishcare.Dishwasher.Program.Eco50' (Eco program), 'Dishcare.Dishwasher.Program.Quick45' (Quick wash), 'Dishcare.Dishwasher.Program.Auto1' (Auto program), 'Dishcare.Dishwasher.Program.Intensive70' (Intensive program)
        delayed_start_minutes: Optional delay in minutes before starting the program (0 for immediate start)
    """
    if tomlogger:
        tomlogger.info(f"Tool call: start_dishwasher_program with haId={haId}, program_key={program_key}, delayed_start_minutes={delayed_start_minutes}", module_name="homeconnect")
    
    result = homeconnect_service.start_dishwasher_program(haId, program_key, delayed_start_minutes)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def get_available_dishwasher_programs(haId: str) -> str:
    """Get the list of available programs for a specific dishwasher
    
    Args:
        haId: The Home Connect appliance ID of the dishwasher. Get this from get_dishwasher_status first if unknown.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: get_available_dishwasher_programs with haId={haId}", module_name="homeconnect")
    
    result = homeconnect_service.get_available_dishwasher_programs(haId)
    return json.dumps(result, ensure_ascii=False)


@server.resource("description://homeconnect")
def description() -> str:
    """Return the server description."""
    return SERVER_DESCRIPTION


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting HomeConnect MCP Server on port 80", module_name="homeconnect")
    else:
        print("Starting HomeConnect MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()