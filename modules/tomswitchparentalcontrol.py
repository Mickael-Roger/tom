import asyncio
import functools
import json
import os
from datetime import datetime, timedelta
from tomlogger import logger

try:
    from pynintendoparental import Authenticator, NintendoParental
    from pynintendoparental.exceptions import InvalidSessionTokenException
except ImportError:
    logger.error("pynintendoparental not found. Please install with 'pip install pynintendoparental'")
    raise


################################################################################################
#                                                                                              #
#                                Nintendo Switch Parental Control                             #
#                                                                                              #
################################################################################################

tom_config = {
    "module_name": "switchparentalcontrol",
    "class_name": "TomSwitchParentalControl",
    "description": "Module to manage Nintendo Switch parental control: check daily usage time, extend or reduce play time",
    "type": "global",
    "complexity": 1,
    "configuration_parameters": {
        "nintendo_session_token": {
            "type": "string",
            "description": "Nintendo session token obtained from authentication process",
            "required": True
        }
    }
}

class TomSwitchParentalControl:

    def __init__(self, config, llm) -> None:
        self.config = config
        self.llm = llm
        
        # Récupération du token de session depuis la configuration
        self.session_token = config.get('nintendo_session_token')
        if not self.session_token:
            logger.error("Nintendo session token not found in configuration")
            raise ValueError("Nintendo session token is required")
        
        # Cache pour stocker l'authentification et les informations des appareils
        all_datadir = config.get('all_datadir', './data/all/')
        os.makedirs(all_datadir, exist_ok=True)
        self.cache_file = os.path.join(all_datadir, 'nintendo_switch_cache.json')
        self.cache = self._load_cache()
        
        # Authentification Nintendo
        self.auth = None
        self.control = None
        self.devices = {}
        
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_switch_daily_usage",
                    "description": "Get the daily usage time for Nintendo Switch devices. Shows how much time has been played today.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string",
                                "description": "Optional device ID to get usage for a specific device. If not provided, returns usage for all devices."
                            }
                        },
                        "additionalProperties": False
                    }
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "extend_switch_playtime",
                    "description": "Extend the daily play time limit for a Nintendo Switch device by a specified number of minutes.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string",
                                "description": "Device ID to extend play time for"
                            },
                            "minutes": {
                                "type": "integer",
                                "description": "Number of minutes to extend the play time (positive number)",
                                "minimum": 1,
                                "maximum": 480
                            }
                        },
                        "required": ["device_id", "minutes"],
                        "additionalProperties": False
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "reduce_switch_playtime", 
                    "description": "Reduce the daily play time limit for a Nintendo Switch device by a specified number of minutes.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string", 
                                "description": "Device ID to reduce play time for"
                            },
                            "minutes": {
                                "type": "integer",
                                "description": "Number of minutes to reduce the play time (positive number)",
                                "minimum": 1,
                                "maximum": 480
                            }
                        },
                        "required": ["device_id", "minutes"],
                        "additionalProperties": False
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_switch_devices",
                    "description": "List all Nintendo Switch devices associated with the account.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False
                    }
                }
            }
        ]

        self.complexity = tom_config.get("complexity", 1)
        self.functions = {
            "get_switch_daily_usage": {
                "function": functools.partial(self._async_wrapper, self.get_daily_usage)
            },
            "extend_switch_playtime": {
                "function": functools.partial(self._async_wrapper, self.extend_playtime)
            },
            "reduce_switch_playtime": {
                "function": functools.partial(self._async_wrapper, self.reduce_playtime)
            },
            "list_switch_devices": {
                "function": functools.partial(self._async_wrapper, self.list_devices)
            }
        }

    def _load_cache(self):
        """Charge le cache depuis le fichier JSON"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load Nintendo Switch cache: {e}")
        return {"devices": {}, "last_update": None}

    def _save_cache(self):
        """Sauvegarde le cache dans le fichier JSON"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.warning(f"Failed to save Nintendo Switch cache: {e}")

    def _get_cache_summary(self):
        """Returns a cache summary for system context"""
        if not self.cache.get('devices'):
            return "No Nintendo Switch devices are currently cached."
        
        cache_summary = "Cached Nintendo Switch devices:\n"
        for device_id, device_data in self.cache['devices'].items():
            cache_summary += f"- {device_data['name']} (ID: {device_id})\n"
        
        return cache_summary

    @property
    def systemContext(self):
        """Dynamic system context that includes up-to-date cache information"""
        return f"""You have access to Nintendo Switch parental control functionality.

{self._get_cache_summary()}

You can:
- Check daily usage time for Switch devices
- Extend or reduce daily play time limits
- List all registered devices

IMPORTANT: When interpreting daily time limits:
- If daily_limit_minutes is 0: This means NO play time allowed (blocked/restricted), not unlimited
- If daily_limit_minutes is null/None: This means unlimited play time
- If daily_limit_minutes is a positive number: This is the maximum minutes allowed per day

Use the appropriate functions to help users manage their Nintendo Switch parental controls."""

    def _async_wrapper(self, async_func, *args, **kwargs):
        """Wrapper to run async functions in sync context"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Si une boucle est déjà en cours, créer une nouvelle tâche
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, async_func(*args, **kwargs))
                    return future.result()
            else:
                return loop.run_until_complete(async_func(*args, **kwargs))
        except RuntimeError:
            # Pas de boucle existante, créer une nouvelle
            return asyncio.run(async_func(*args, **kwargs))

    async def _ensure_authenticated(self):
        """Ensure we have valid authentication and device list"""
        if self.auth is None or self.control is None:
            try:
                logger.info("Authenticating with Nintendo...")
                self.auth = await Authenticator.complete_login(
                    auth=None,
                    response_token=self.session_token,
                    is_session_token=True
                )
                
                self.control = await NintendoParental.create(self.auth)
                
                if self.control.devices:
                    # Mettre à jour le cache avec les appareils
                    for device_id, device in self.control.devices.items():
                        self.cache['devices'][device_id] = {
                            'name': device.name,
                            'device_id': device.device_id
                        }
                    self.cache['last_update'] = datetime.now().isoformat()
                    self._save_cache()
                    logger.info(f"Found {len(self.control.devices)} Nintendo Switch devices")
                else:
                    logger.warning("No Nintendo Switch devices found")
                    
            except InvalidSessionTokenException:
                logger.error("Invalid Nintendo session token")
                raise ValueError("Invalid Nintendo session token. Please update the token in configuration.")
            except Exception as e:
                error_msg = str(e).lower()
                if "event loop is closed" in error_msg or "connection" in error_msg or "network" in error_msg:
                    logger.warning(f"Nintendo Switch appears to be offline: {e}")
                    raise ValueError("Nintendo Switch is not connected to the internet. Please connect the device and try again.")
                else:
                    logger.error(f"Failed to authenticate with Nintendo: {e}")
                    raise

    async def get_daily_usage(self, device_id=None):
        """Get daily usage time for Nintendo Switch devices"""
        await self._ensure_authenticated()
        
        if not self.control.devices:
            return {"error": "No Nintendo Switch devices found"}
        
        usage_data = []
        
        if device_id:
            # Usage pour un appareil spécifique
            device = self.control.devices.get(device_id)
            if not device:
                return {"error": f"Device with ID {device_id} not found"}
            
            await device.update()
            usage_data.append({
                "device_id": device.device_id,
                "device_name": device.name,
                "today_playing_time_minutes": device.today_playing_time,
                "daily_limit_minutes": device.limit_time,
                "remaining_time_minutes": max(0, device.limit_time - device.today_playing_time) if device.limit_time is not None and device.limit_time > 0 else ("unlimited" if device.limit_time is None else "blocked")
            })
        else:
            # Usage pour tous les appareils
            for device in self.control.devices.values():
                await device.update()
                usage_data.append({
                    "device_id": device.device_id,
                    "device_name": device.name,
                    "today_playing_time_minutes": device.today_playing_time,
                    "daily_limit_minutes": device.limit_time,
                    "remaining_time_minutes": max(0, device.limit_time - device.today_playing_time) if device.limit_time is not None and device.limit_time > 0 else ("unlimited" if device.limit_time is None else "blocked")
                })
        
        return {"devices_usage": usage_data}

    async def extend_playtime(self, device_id, minutes):
        """Extend play time for a specific device"""
        await self._ensure_authenticated()
        
        device = self.control.devices.get(device_id)
        if not device:
            return {"error": f"Device with ID {device_id} not found"}
        
        try:
            await device.update()
            current_limit = device.limit_time
            new_limit = current_limit + minutes
            
            # Note: La méthode exacte pour modifier la limite peut varier selon l'API
            # Il faudra peut-être utiliser une autre méthode selon la documentation de pynintendoparental
            success = await device.set_limit_time(new_limit)
            
            if success:
                logger.info(f"Extended play time for device {device.name} by {minutes} minutes")
                return {
                    "success": True,
                    "device_id": device_id,
                    "device_name": device.name,
                    "previous_limit_minutes": current_limit,
                    "new_limit_minutes": new_limit,
                    "extended_by_minutes": minutes
                }
            else:
                return {"error": "Failed to extend play time"}
                
        except Exception as e:
            error_msg = str(e).lower()
            if "event loop is closed" in error_msg or "connection" in error_msg or "network" in error_msg:
                logger.warning(f"Nintendo Switch appears to be offline: {e}")
                return {"error": "Nintendo Switch is not connected to the internet. Please connect the device and try again."}
            else:
                logger.error(f"Error extending play time: {e}")
                return {"error": f"Failed to extend play time: {str(e)}"}

    async def reduce_playtime(self, device_id, minutes):
        """Reduce play time for a specific device"""
        await self._ensure_authenticated()
        
        device = self.control.devices.get(device_id)
        if not device:
            return {"error": f"Device with ID {device_id} not found"}
        
        try:
            await device.update()
            current_limit = device.limit_time
            new_limit = max(0, current_limit - minutes)
            
            success = await device.set_limit_time(new_limit)
            
            if success:
                logger.info(f"Reduced play time for device {device.name} by {minutes} minutes")
                return {
                    "success": True,
                    "device_id": device_id,
                    "device_name": device.name,
                    "previous_limit_minutes": current_limit,
                    "new_limit_minutes": new_limit,
                    "reduced_by_minutes": minutes
                }
            else:
                return {"error": "Failed to reduce play time"}
                
        except Exception as e:
            error_msg = str(e).lower()
            if "event loop is closed" in error_msg or "connection" in error_msg or "network" in error_msg:
                logger.warning(f"Nintendo Switch appears to be offline: {e}")
                return {"error": "Nintendo Switch is not connected to the internet. Please connect the device and try again."}
            else:
                logger.error(f"Error reducing play time: {e}")
                return {"error": f"Failed to reduce play time: {str(e)}"}

    async def list_devices(self):
        """List all Nintendo Switch devices"""
        await self._ensure_authenticated()
        
        if not self.control.devices:
            return {"devices": [], "message": "No Nintendo Switch devices found"}
        
        devices_list = []
        for device in self.control.devices.values():
            await device.update()
            devices_list.append({
                "device_id": device.device_id,
                "device_name": device.name,
                "today_playing_time_minutes": device.today_playing_time,
                "daily_limit_minutes": device.limit_time,
                "remaining_time_minutes": max(0, device.limit_time - device.today_playing_time) if device.limit_time is not None and device.limit_time > 0 else ("unlimited" if device.limit_time is None else "blocked")
            })
        
        return {"devices": devices_list}