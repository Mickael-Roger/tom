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
    
    def __init__(self, config, llm):
        self.config = config
        self.llm = llm
        self.api_base_url = "https://api.home-connect.com"
        self.client_id = "F9ACB272F14EAEBABDC616492121073863A93923285BCA1904EDB53EE0CCA008"
        
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
            }
        ]
        
        self.functions = {
            "get_dishwasher_status": {
                "function": functools.partial(self.get_dishwasher_status)
            }
        }

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
            tomlogger.error(f"HomeConnect: Error loading token: {e}", module_name="homeconnect")
            return None

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
        """Refresh the access token and update config.yml"""
        # Load current token from config
        current_token = self._load_token_from_config()
        if not current_token:
            tomlogger.warning("HomeConnect: No token available to refresh", module_name="homeconnect")
            return False
            
        # For now, we don't have refresh tokens with Home-Connect Device Flow
        # This is a placeholder for future enhancement
        return True

    def _update_config_token(self, new_token):
        """Update the config.yml file with the new token"""
        try:
            if not os.path.exists(self._config_path):
                tomlogger.error(f"HomeConnect: config.yml not found: {self._config_path}", module_name="homeconnect")
                return
                
            with open(self._config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
                
            # Update the token in the config
            if 'services' not in config_data:
                config_data['services'] = {}
            if 'homeconnect' not in config_data['services']:
                config_data['services']['homeconnect'] = {}
                
            config_data['services']['homeconnect']['token'] = new_token
            
            # Write back to file
            with open(self._config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config_data, f, default_flow_style=False, allow_unicode=True)
                
            
        except Exception as e:
            tomlogger.error(f"HomeConnect: Failed to update config.yml: {e}", module_name="homeconnect")

    def _get_valid_token(self):
        """Get a valid access token from config"""
        return self._load_token_from_config()

    def _process_api_list(self, items):
        """Convert API list format ({key, value,...}) to dict {key: value}"""
        if not items:
            return {}
        return {item['key']: item.get('value') for item in items}

    def _create_summary(self, processed_status, processed_settings, active_program):
        """Create a readable summary from processed data"""
        summary = {
            "etat_general": "Inconnu", 
            "programme": None, 
            "temps_restant_min": 0, 
            "alertes": []
        }
        
        op_state = processed_status.get('BSH.Common.Status.OperationState', '')
        
        if "Run" in op_state and active_program:
            summary["etat_general"] = "En marche"
            prog_key = active_program.get('key')
            if prog_key:
                summary["programme"] = prog_key.split('.')[-1]
            
            # Search for remaining time in active program options
            rem_time = 0
            for option in active_program.get('options', []):
                if option.get('key') == 'BSH.Common.Option.RemainingProgramTime':
                    rem_time = option.get('value', 0)
                    break
            summary["temps_restant_min"] = rem_time // 60
            
        elif "Finished" in op_state:
            summary["etat_general"] = "Termine"
        elif "Ready" in op_state:
            summary["etat_general"] = "Pret"
        elif "Inactive" in op_state:
            summary["etat_general"] = "Inactif"
        
        # Check for common alerts in settings
        if processed_settings.get("ConsumerProducts.Dishwasher.Setting.RinseAidLevel") == "Off":
            summary["alertes"].append("Niveau de liquide de rincage bas")
        if processed_settings.get("ConsumerProducts.Dishwasher.Setting.SaltLevel") == "Off":
            summary["alertes"].append("Niveau de sel bas")
            
        return summary

    def _get_appliance_details(self, haId, headers):
        """Get all details for a single appliance"""
        details = {}
        base_url = f"{self.api_base_url}/api/homeappliances/{haId}"
        
        # Status
        try:
            res = requests.get(f"{base_url}/status", headers=headers, timeout=10)
            details["status_brut"] = res.json().get('data', {}).get('status', []) if res.ok else []
        except Exception as e:
            tomlogger.error(f"HomeConnect: Error getting status for {haId}: {e}", module_name="homeconnect")
            details["status_brut"] = []
        
        # Settings
        try:
            res = requests.get(f"{base_url}/settings", headers=headers, timeout=10)
            details["settings_brut"] = res.json().get('data', {}).get('settings', []) if res.ok else []
        except Exception as e:
            tomlogger.error(f"HomeConnect: Error getting settings for {haId}: {e}", module_name="homeconnect")
            details["settings_brut"] = []
        
        # Active Program
        details["programme_actif_brut"] = None
        if any(isinstance(item.get('value'), str) and "Run" in item.get('value') for item in details["status_brut"]):
            try:
                res = requests.get(f"{base_url}/programs/active", headers=headers, timeout=10)
                if res.ok:
                    details["programme_actif_brut"] = res.json().get('data', {})
            except Exception as e:
                tomlogger.error(f"HomeConnect: Error getting active program for {haId}: {e}", module_name="homeconnect")
                
        return details

    def get_dishwasher_status(self):
        """Get the status of all connected dishwashers"""
        try:
            # Get valid token
            access_token = self._get_valid_token()
            if not access_token:
                return {"erreur": "Token invalide ou expire. Veuillez regenerer le token avec tools/home-connect.py"}
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept-Language": "en-US"
            }
            
            # Get all appliances
            api_url = f"{self.api_base_url}/api/homeappliances"
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if not response.ok:
                tomlogger.error(f"HomeConnect: Failed to get appliances: {response.status_code} - {response.text}", module_name="homeconnect")
                return {"erreur": "Impossible de recuperer la liste des appareils", "details": response.text}
            
            all_appliances = response.json().get("data", {}).get("homeappliances", [])
            dishwashers = [app for app in all_appliances if app.get("type") == "Dishwasher"]
            
            if not dishwashers:
                return {"message": "Aucun lave-vaisselle trouve"}
            
            final_output = []
            for dw in dishwashers:
                haId = dw.get("haId")
                
                appliance_info = {
                    "nom": dw.get("name"),
                    "haId": haId,
                    "marque": dw.get("brand"),
                    "type": dw.get("type"),
                    "connecte": dw.get("connected"),
                    "resume": {},
                    "details": {}
                }
                
                if appliance_info["connecte"]:
                    details_bruts = self._get_appliance_details(haId, headers)
                    
                    # Process for better readability
                    status_traite = self._process_api_list(details_bruts["status_brut"])
                    settings_traites = self._process_api_list(details_bruts["settings_brut"])
                    
                    # Create summary
                    appliance_info["resume"] = self._create_summary(
                        status_traite, 
                        settings_traites, 
                        details_bruts["programme_actif_brut"]
                    )
                    
                    # Add processed details
                    appliance_info["details"] = {
                        "status": status_traite,
                        "settings": settings_traites,
                        "programme_actif": details_bruts["programme_actif_brut"]
                    }
                else:
                    appliance_info["resume"] = {"etat_general": "Deconnecte"}
                
                final_output.append(appliance_info)
            
            return final_output
            
        except requests.exceptions.Timeout:
            tomlogger.error("HomeConnect: Request timeout", module_name="homeconnect")
            return {"erreur": "Timeout lors de la connexion a l'API Home-Connect"}
        except Exception as e:
            tomlogger.error(f"HomeConnect: Error getting dishwasher status: {e}", module_name="homeconnect")
            return {"erreur": f"Erreur lors de la recuperation du statut: {str(e)}"}

    @property
    def systemContext(self):
        return """You are managing Home-Connect compatible dishwashers. You can:
- Check the status of dishwashers including current program, remaining time, and alerts
- Monitor dishwasher connection status
- Get detailed information about dishwasher settings and operation state

Always provide clear, actionable information about dishwasher status and any alerts that require user attention."""

    def __del__(self):
        """Clean up on module destruction"""
        pass