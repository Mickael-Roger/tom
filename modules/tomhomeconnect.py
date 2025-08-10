import requests
import json
import time
import threading
import os
import yaml
import tomlogger
import functools

tom_config = {
    "module_name": "homeconnect",
    "class_name": "HomeConnect",
    "description": "Control and monitor Home-Connect compatible dishwashers",
    "type": "global",
    "complexity": 1,
    "configuration_parameters": {
        "token": {
            "type": "string",
            "description": "OAuth2 access token from Home-Connect API",
            "required": True
        }
    }
}

class HomeConnect:
    
    _token_refresh_thread_started = False
    _token_refresh_thread = None
    _config_path = '/data/config.yml'
    _token_cache_file = None  # Will be set during initialization
    
    def __init__(self, config, llm):
        self.config = config
        self.llm = llm
        self.api_base_url = "https://api.home-connect.com"
        self.client_id = "F9ACB272F14EAEBABDC616492121073863A93923285BCA1904EDB53EE0CCA008"
        
        # Set token cache file path from all_datadir
        all_datadir = config.get('all_datadir', '/data/all/')
        os.makedirs(all_datadir, exist_ok=True)
        HomeConnect._token_cache_file = os.path.join(all_datadir, 'homeconnect.json')
        
        # Start token refresh thread only once across all instances
        if not HomeConnect._token_refresh_thread_started:
            HomeConnect._token_refresh_thread_started = True
            HomeConnect._token_refresh_thread = threading.Thread(target=self._token_refresh_loop)
            HomeConnect._token_refresh_thread.daemon = True
            HomeConnect._token_refresh_thread.start()
        
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_dishwasher_status",
                    "description": "Get the current status of all connected dishwashers including state, program, remaining time and alerts",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "start_dishwasher_program",
                    "description": "Start a dishwasher program. Use this when the user wants to start a specific wash cycle or program",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "haId": {
                                "type": "string",
                                "description": "The Home Connect appliance ID of the dishwasher to start. Get this from get_dishwasher_status first if unknown."
                            },
                            "program_key": {
                                "type": "string",
                                "description": "The program key to start. Common programs include: 'Dishcare.Dishwasher.Program.Eco50' (Eco program), 'Dishcare.Dishwasher.Program.Quick45' (Quick wash), 'Dishcare.Dishwasher.Program.Auto1' (Auto program), 'Dishcare.Dishwasher.Program.Intensive70' (Intensive program)"
                            },
                            "delayed_start_minutes": {
                                "type": "integer",
                                "description": "Optional delay in minutes before starting the program (0 for immediate start)",
                                "minimum": 0,
                                "maximum": 1440
                            }
                        },
                        "required": ["haId", "program_key"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_available_dishwasher_programs",
                    "description": "Get the list of available programs for a specific dishwasher",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "haId": {
                                "type": "string",
                                "description": "The Home Connect appliance ID of the dishwasher. Get this from get_dishwasher_status first if unknown."
                            }
                        },
                        "required": ["haId"]
                    }
                }
            }
        ]
        
        self.functions = {
            "get_dishwasher_status": {
                "function": functools.partial(self.get_dishwasher_status)
            },
            "start_dishwasher_program": {
                "function": functools.partial(self.start_dishwasher_program)
            },
            "get_available_dishwasher_programs": {
                "function": functools.partial(self.get_available_dishwasher_programs)
            }
        }

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
                tomlogger.info("HomeConnect: Cached token is expired", module_name="homeconnect")
                return None
                
        except Exception as e:
            tomlogger.error(f"HomeConnect: Error loading cached token: {e}", module_name="homeconnect")
            return None
    
    def _load_token_from_config(self):
        """Load token from configuration file"""
        try:
            if not os.path.exists(self._config_path):
                tomlogger.error(f"HomeConnect: Config file not found: {self._config_path}", module_name="homeconnect")
                return None
                
            with open(self._config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
                
            token_string = config_data.get('services', {}).get('homeconnect', {}).get('token', '')
            if not token_string:
                tomlogger.error("HomeConnect: No token found in configuration", module_name="homeconnect")
                return None
                
            return token_string
            
        except Exception as e:
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
                
            tomlogger.info("HomeConnect: Token saved to cache", module_name="homeconnect")
            return True
            
        except Exception as e:
            tomlogger.error(f"HomeConnect: Error saving token to cache: {e}", module_name="homeconnect")
            return False

    def _token_refresh_loop(self):
        """Background loop to refresh token every 12 hours"""
        while True:
            try:
                # Wait 12 hours (12 * 3600 seconds)
                time.sleep(43200)
                
                if self._refresh_token():
                    pass
                else:
                    tomlogger.error("HomeConnect: Token refresh failed", module_name="homeconnect")
                    
            except Exception as e:
                tomlogger.error(f"HomeConnect: Token refresh loop error: {e}", module_name="homeconnect")
                # Continue loop even if there's an error
                time.sleep(3600)  # Wait 1 hour before retrying

    def _refresh_token(self):
        """Refresh the access token using config token if cache is invalid"""
        # Try to load from cache first
        cached_token = self._load_token_from_cache()
        if cached_token:
            return True  # Cache is still valid
            
        # Cache is invalid, try to use config token to regenerate cache
        config_token = self._load_token_from_config()
        if not config_token:
            tomlogger.warning("HomeConnect: No token available in config", module_name="homeconnect")
            return False
            
        # Test if config token is valid by making a simple API call
        if self._test_token_validity(config_token):
            # Config token is valid, save it to cache
            self._save_token_to_cache(config_token)
            tomlogger.info("HomeConnect: Config token validated and cached", module_name="homeconnect")
            return True
        else:
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
            tomlogger.error(f"HomeConnect: Error testing token validity: {e}", module_name="homeconnect")
            return False

    # Remove this method as we no longer update config.yml

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
            tomlogger.error(f"HomeConnect: Error getting status for {haId}: {e}", module_name="homeconnect")
            details["raw_status"] = []
        
        # Settings
        try:
            res = requests.get(f"{base_url}/settings", headers=headers, timeout=10)
            details["raw_settings"] = res.json().get('data', {}).get('settings', []) if res.ok else []
        except Exception as e:
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
                tomlogger.error(f"HomeConnect: Error getting active program for {haId}: {e}", module_name="homeconnect")
                
        return details

    def get_dishwasher_status(self):
        """Get the status of all connected dishwashers"""
        try:
            # Get valid token
            access_token = self._get_valid_token()
            if not access_token:
                return {"error": "Invalid or expired token. Please regenerate token with: python3 tools/home-connect.py"}
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept-Language": "en-US"
            }
            
            # Get all appliances
            api_url = f"{self.api_base_url}/api/homeappliances"
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if not response.ok:
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
            
            return final_output
            
        except requests.exceptions.Timeout:
            tomlogger.error("HomeConnect: Request timeout", module_name="homeconnect")
            return {"error": "Timeout connecting to Home-Connect API"}
        except Exception as e:
            tomlogger.error(f"HomeConnect: Error getting dishwasher status: {e}", module_name="homeconnect")
            return {"error": f"Error retrieving status: {str(e)}"}

    def start_dishwasher_program(self, haId, program_key, delayed_start_minutes=0):
        """Start a dishwasher program"""
        try:
            # Get valid token
            access_token = self._get_valid_token()
            if not access_token:
                return {"error": "Invalid or expired token. Please regenerate token with: python3 tools/home-connect.py"}
            
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
                tomlogger.error(f"HomeConnect: Failed to start program: {response.status_code} - {response.text}", module_name="homeconnect")
                return {"error": f"Failed to start program: HTTP {response.status_code}", "details": response.text}
            
        except requests.exceptions.Timeout:
            tomlogger.error("HomeConnect: Request timeout while starting program", module_name="homeconnect")
            return {"error": "Timeout connecting to Home-Connect API"}
        except Exception as e:
            tomlogger.error(f"HomeConnect: Error starting dishwasher program: {e}", module_name="homeconnect")
            return {"error": f"Error starting program: {str(e)}"}

    def get_available_dishwasher_programs(self, haId):
        """Get available programs for a specific dishwasher"""
        try:
            # Get valid token
            access_token = self._get_valid_token()
            if not access_token:
                return {"error": "Invalid or expired token. Please regenerate token with: python3 tools/home-connect.py"}
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept-Language": "en-US"
            }
            
            # Get available programs
            api_url = f"{self.api_base_url}/api/homeappliances/{haId}/programs/available"
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if not response.ok:
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
            tomlogger.error("HomeConnect: Request timeout while getting available programs", module_name="homeconnect")
            return {"error": "Timeout connecting to Home-Connect API"}
        except Exception as e:
            tomlogger.error(f"HomeConnect: Error getting available programs: {e}", module_name="homeconnect")
            return {"error": f"Error retrieving available programs: {str(e)}"}

    @property
    def systemContext(self):
        return """You are managing Home-Connect compatible dishwashers. You can:
- Check the status of dishwashers including current program, remaining time, and alerts
- Monitor dishwasher connection status
- Get detailed information about dishwasher settings and operation state
- Start dishwasher programs with optional delayed start
- Get the list of available programs for each dishwasher

When starting programs:
- Always get the dishwasher status first to obtain the haId
- Common program keys include: Eco50, Quick45, Auto1, Intensive70
- You can set a delayed start in minutes (0 for immediate start)
- Check that the dishwasher is ready (powered on, door closed, remote control enabled)

Always provide clear, actionable information about dishwasher status and any alerts that require user attention."""

    def __del__(self):
        """Clean up on module destruction"""
        pass