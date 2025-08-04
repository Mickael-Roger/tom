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
    "description": "Module to manage Nintendo Switch parental control: check daily usage time and add extra playing time",
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
                    "description": "Add extra playing time to a Nintendo Switch device for today. This does NOT modify the daily limit but adds bonus time on top of it.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string",
                                "description": "Device ID to add extra time for"
                            },
                            "minutes": {
                                "type": "integer",
                                "description": "Number of minutes to add as extra playing time (positive number)",
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
                "function": functools.partial(self._debug_wrapper, "get_switch_daily_usage", self.get_daily_usage)
            },
            "extend_switch_playtime": {
                "function": functools.partial(self._debug_wrapper, "extend_switch_playtime", self.extend_playtime)
            },
            "list_switch_devices": {
                "function": functools.partial(self._debug_wrapper, "list_switch_devices", self.list_devices)
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
- Add extra playing time for today (bonus time on top of daily limit)
- List all registered devices

IMPORTANT: When interpreting time limits:
- daily_limit_minutes: The base daily limit (0 = blocked, null = unlimited, positive number = limit in minutes)
- extra_time_minutes: Additional time granted for today only (0 = no extra time, positive number = extra minutes, "unlimited" = infinite extra time)
- total_time_available_minutes: Total time available today (daily_limit + extra_time)
- remaining_time_minutes: Time left to play today based on total_time_available - today_playing_time

Note about extending play time:
- extend_switch_playtime: Adds extra time for today only without changing the daily limit (using async_update_extra_playing_time API)

Use the appropriate functions to help users manage their Nintendo Switch parental controls."""

    def _debug_wrapper(self, function_name, async_func, *args, **kwargs):
        """Wrapper for async functions"""
        try:
            result = self._async_wrapper(async_func, *args, **kwargs)
            if 'error' in str(result):
                logger.warning(f"{function_name} returned error: {result.get('error', 'Unknown error')}")
            return result
        except Exception as e:
            logger.error(f"{function_name} failed: {type(e).__name__}: {e}")
            raise

    def _async_wrapper(self, async_func, *args, **kwargs):
        """Wrapper to run async functions in sync context with proper aiohttp session management"""
        try:
            loop = asyncio.get_event_loop()
            
            if loop.is_running():
                # Si une boucle est déjà en cours, utiliser un nouveau thread avec une nouvelle boucle
                import concurrent.futures
                
                def run_in_new_loop():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        # Wrapper qui exécute la fonction async
                        async def safe_async_func(*args, **kwargs):
                            result = await async_func(*args, **kwargs)
                            # Attendre un peu pour que les connexions HTTP se stabilisent
                            await asyncio.sleep(0.1)
                            return result
                        
                        return new_loop.run_until_complete(safe_async_func(*args, **kwargs))
                    finally:
                        # Nettoyer les tâches restantes avant de fermer la loop
                        pending_tasks = asyncio.all_tasks(new_loop)
                        if pending_tasks:
                            for task in pending_tasks:
                                task.cancel()
                            # Attendre que les tâches soient annulées
                            new_loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
                        
                        new_loop.close()
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_new_loop)
                    return future.result()
            else:
                return loop.run_until_complete(async_func(*args, **kwargs))
        except RuntimeError:
            # Pas de boucle existante, créer une nouvelle avec gestion propre des sessions
            async def safe_run(*args, **kwargs):
                result = await async_func(*args, **kwargs)
                # Attendre un peu pour que les connexions HTTP se stabilisent
                await asyncio.sleep(0.1)
                return result
            
            return asyncio.run(safe_run(*args, **kwargs))

    async def _ensure_authenticated(self):
        """Ensure we have valid authentication and device list - Always create fresh session"""
        try:
            # Toujours nettoyer l'ancienne auth pour éviter les problèmes d'event loop
            if self.auth and hasattr(self.auth, 'client_session'):
                if self.auth.client_session and not self.auth.client_session.closed:
                    try:
                        await self.auth.client_session.close()
                    except Exception as e:
                        logger.warning(f"Error closing old session: {e}")
            
            # Toujours créer une nouvelle authentification pour éviter les problèmes d'event loop
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
            
            # Calculer le temps total disponible aujourd'hui (limite + extra time)
            daily_limit = device.limit_time if device.limit_time is not None else 0
            extra_time = 0
            total_time_available = daily_limit
            
            # Extraire le temps extra si disponible
            if hasattr(device, 'extra') and device.extra and 'extraPlayingTime' in device.extra:
                extra_playing_time = device.extra.get('extraPlayingTime', {})
                # Gérer le cas où extra_playing_time est None
                if extra_playing_time is None:
                    extra_playing_time = {}
                in_one_day = extra_playing_time.get('inOneDay', {})
                if in_one_day.get('isInfinity', False):
                    extra_time = "unlimited"
                    total_time_available = "unlimited"
                else:
                    extra_time = in_one_day.get('duration', 0)
                    total_time_available = daily_limit + extra_time
            
            # Calculer le temps restant réel
            playing_time = device.today_playing_time
            if total_time_available == "unlimited":
                remaining_time = "unlimited"
            elif daily_limit is None:
                remaining_time = "unlimited"
            elif daily_limit == 0 and extra_time == 0:
                remaining_time = "blocked"
            else:
                remaining_time = max(0, total_time_available - playing_time)
            
            usage_data.append({
                "device_id": device.device_id,
                "device_name": device.name,
                "today_playing_time_minutes": playing_time,
                "daily_limit_minutes": daily_limit,
                "extra_time_minutes": extra_time,
                "total_time_available_minutes": total_time_available,
                "remaining_time_minutes": remaining_time
            })
        else:
            # Usage pour tous les appareils
            for device in self.control.devices.values():
                await device.update()
                
                # Calculer le temps total disponible aujourd'hui (limite + extra time)
                daily_limit = device.limit_time if device.limit_time is not None else 0
                extra_time = 0
                total_time_available = daily_limit
                
                # Extraire le temps extra si disponible
                if hasattr(device, 'extra') and device.extra and 'extraPlayingTime' in device.extra:
                    extra_playing_time = device.extra.get('extraPlayingTime', {})
                    # Gérer le cas où extra_playing_time est None
                    if extra_playing_time is None:
                        extra_playing_time = {}
                    in_one_day = extra_playing_time.get('inOneDay', {})
                    if in_one_day.get('isInfinity', False):
                        extra_time = "unlimited"
                        total_time_available = "unlimited"
                    else:
                        extra_time = in_one_day.get('duration', 0)
                        total_time_available = daily_limit + extra_time
                
                # Calculer le temps restant réel
                playing_time = device.today_playing_time
                if total_time_available == "unlimited":
                    remaining_time = "unlimited"
                elif daily_limit is None:
                    remaining_time = "unlimited"
                elif daily_limit == 0 and extra_time == 0:
                    remaining_time = "blocked"
                else:
                    remaining_time = max(0, total_time_available - playing_time)
                
                usage_data.append({
                    "device_id": device.device_id,
                    "device_name": device.name,
                    "today_playing_time_minutes": playing_time,
                    "daily_limit_minutes": daily_limit,
                    "extra_time_minutes": extra_time,
                    "total_time_available_minutes": total_time_available,
                    "remaining_time_minutes": remaining_time
                })
        
        return {"devices_usage": usage_data}

    async def extend_playtime(self, device_id, minutes):
        """Add extra playing time for a specific device using direct API call"""
        try:
            await self._ensure_authenticated()
            
            device = self.control.devices.get(device_id)
            if not device:
                return {"error": f"Device with ID {device_id} not found"}
            
            await device.update()
            current_limit = device.limit_time
            current_playing_time = device.today_playing_time
            
            # Utiliser directement l'API async_update_extra_playing_time
            api_result = await device._api.async_update_extra_playing_time(device_id, minutes)
            
            # Extraire seulement les données JSON sérialisables de la réponse
            api_status = api_result.get('status', 'unknown')
            api_json = api_result.get('json', {})
            
            # Mettre à jour les informations après l'ajout d'extra time
            await device.update()
            new_playing_time = device.today_playing_time
            
            logger.info(f"Extended play time for device {device.name} by {minutes} minutes")
            return {
                "success": True,
                "device_id": device_id,
                "device_name": device.name,
                "current_limit_minutes": current_limit,
                "previous_playing_time": current_playing_time,
                "new_playing_time": new_playing_time,
                "extra_time_added_minutes": minutes,
                "api_status": api_status,
                "api_response": api_json
            }
                
        except Exception as e:
            error_msg = str(e).lower()
            if "event loop is closed" in error_msg or "connection" in error_msg or "network" in error_msg:
                logger.warning(f"Nintendo Switch appears to be offline: {e}")
                return {"error": "Nintendo Switch is not connected to the internet. Please connect the device and try again."}
            else:
                logger.error(f"Error extending play time: {e}")
                return {"error": f"Failed to extend play time: {str(e)}"}


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