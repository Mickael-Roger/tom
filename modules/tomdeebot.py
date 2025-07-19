import functools
import json
import time
import asyncio
import threading

# Logging
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
from tomlogger import logger

# Check for required dependencies
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

# Deebot client imports
try:
    from deebot_client.api_client import ApiClient
    from deebot_client.authentication import Authenticator, create_rest_config
    from deebot_client.commands.json.clean import Clean, CleanAction
    from deebot_client.commands.json.charge import Charge
    from deebot_client.events import BatteryEvent, StateEvent, CleanLogEvent, ErrorEvent, StatsEvent
    from deebot_client.mqtt_client import MqttClient, create_mqtt_config
    from deebot_client.util import md5
    from deebot_client.device import Device
    DEEBOT_AVAILABLE = True
except ImportError as e:
    logger.error(f"Deebot client not available: {e}")
    DEEBOT_AVAILABLE = False

# Check if all dependencies are available
DEPENDENCIES_AVAILABLE = DEEBOT_AVAILABLE and AIOHTTP_AVAILABLE

tom_config = {
    "module_name": "deebot",
    "class_name": "TomDeebot",
    "description": "Module to manage Deebot robot vacuum - control, status and cleaning scheduling.",
    "type": "global"
}



class TomDeebot:
    def __init__(self, config, llm) -> None:
        self.config = config
        self.llm = llm
        
        if not DEPENDENCIES_AVAILABLE:
            if not AIOHTTP_AVAILABLE:
                logger.error("aiohttp library not available - required for Deebot module")
            if not DEEBOT_AVAILABLE:
                logger.error("Deebot client library not available")
            self.tools = []
            self.functions = {}
            self.systemContext = "Deebot module unavailable - missing dependencies (deebot-client and/or aiohttp)."
            self.complexity = 0
            return
        
        # Authentication configuration
        self.username = config.get('username')
        self.password = config.get('password')
        self.country = config.get('country', 'FR')
        
        if not self.username or not self.password:
            logger.error("Deebot username and password required in config")
            self.tools = []
            self.functions = {}
            self.systemContext = "Deebot module not configured - username and password required."
            self.complexity = 0
            return
        
        # Device and MQTT components
        self.device_id = md5(str(time.time()))
        self.account_id = self.username
        self.password_hash = md5(self.password)
        self.bot = None
        self.mqtt_client = None
        self.session = None
        
        # Background task management
        self.mqtt_task = None
        self.mqtt_loop = None
        self.mqtt_thread = None
        
        # Robot status
        self.battery_level = None
        self.robot_status = None
        self.last_clean_log = None
        
        # Robot data dict for real-time updates
        self.robot_data = {
            "battery_level": None,
            "status": None,
            "cleaning_mode": None,
            "position": None
        }
        
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "start_cleaning",
                    "description": "Start cleaning the house with the Deebot robot vacuum.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function", 
                "function": {
                    "name": "stop_cleaning",
                    "description": "Stop the current cleaning operation and pause the Deebot robot.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "return_to_base",
                    "description": "Send the Deebot robot back to its charging base.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_robot_status",
                    "description": "Get the current status of the Deebot robot including battery level and cleaning state.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_deebot_status",
                    "description": "Get real-time status data from the Deebot robot including battery level, status, cleaning mode and position.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
        ]
        
        self.systemContext = "This module allows control of a Deebot robot vacuum. It can get status, start/stop cleaning and return the robot to its base. The robot sends real-time status updates via MQTT."
        self.complexity = 0
        
        self.functions = {
            "start_cleaning": {"function": functools.partial(self.start_cleaning)},
            "stop_cleaning": {"function": functools.partial(self.stop_cleaning)},
            "return_to_base": {"function": functools.partial(self.return_to_base)},
            "get_robot_status": {"function": functools.partial(self.get_robot_status)},
            "get_deebot_status": {"function": functools.partial(self.get_deebot_status)},
        }
        
        # Start MQTT background task
        self._start_mqtt_background_task()
        
    def _get_status_label(self, status_code):
        """Convert numeric status code to human readable label"""
        status_map = {
            0: "unknown",
            1: "idle", 
            2: "cleaning",
            3: "paused",
            4: "returning",
            5: "charging",
            6: "error",
            7: "offline",
            8: "docked",
            9: "sleeping",
            10: "manual_cleaning",
            11: "spot_cleaning",
            12: "edge_cleaning",
            13: "zone_cleaning"
        }
        
        # Handle both numeric and string inputs
        if isinstance(status_code, str):
            try:
                status_code = int(status_code)
            except (ValueError, TypeError):
                return status_code  # Return as-is if not numeric
        
        return status_map.get(status_code, f"status_{status_code}")
        
    def _start_mqtt_background_task(self):
        """Start the MQTT background task in a separate thread"""
        def run_mqtt_loop():
            self.mqtt_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.mqtt_loop)
            try:
                self.mqtt_loop.run_until_complete(self._mqtt_main())
            except Exception as e:
                logger.error(f"MQTT background task error: {e}")
            finally:
                try:
                    # Cancel all running tasks
                    pending = asyncio.all_tasks(self.mqtt_loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        self.mqtt_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception as e:
                    logger.error(f"Error cleaning up MQTT loop: {e}")
                finally:
                    self.mqtt_loop.close()
        
        self.mqtt_thread = threading.Thread(target=run_mqtt_loop, daemon=True)
        self.mqtt_thread.start()
        logger.info("Deebot MQTT background task started")
    
    async def _mqtt_main(self):
        """Main MQTT connection and event handling"""
        session = None
        try:
            # Create persistent session
            session = aiohttp.ClientSession()
            self.session = session
            
            # Create REST config and authenticator
            rest_config = create_rest_config(
                session, 
                device_id=self.device_id, 
                alpha_2_country=self.country
            )
            
            authenticator = Authenticator(rest_config, self.account_id, self.password_hash)
            api_client = ApiClient(authenticator)
            
            # Get devices
            devices = await api_client.get_devices()
            
            if not devices or not hasattr(devices, 'mqtt') or not devices.mqtt:
                logger.error("No MQTT devices found")
                return
            
            # Initialize bot with first device
            self.bot = Device(devices.mqtt[0], authenticator)
            
            # Create MQTT client
            mqtt_config = create_mqtt_config(device_id=self.device_id, country=self.country)
            self.mqtt_client = MqttClient(mqtt_config, authenticator)
            
            # Initialize bot with MQTT
            await self.bot.initialize(self.mqtt_client)
            
            # Subscribe to events
            self.bot.events.subscribe(BatteryEvent, self._on_battery_event)
            self.bot.events.subscribe(StateEvent, self._on_state_event)
            self.bot.events.subscribe(CleanLogEvent, self._on_clean_log_event)
            self.bot.events.subscribe(ErrorEvent, self._on_error_event)
            self.bot.events.subscribe(StatsEvent, self._on_stats_event)
            
            # Get device name safely
            device_name = "Unknown"
            if hasattr(self.bot, 'device_info') and self.bot.device_info:
                if hasattr(self.bot.device_info, 'name'):
                    device_name = self.bot.device_info.name
                elif isinstance(self.bot.device_info, dict) and 'name' in self.bot.device_info:
                    device_name = self.bot.device_info['name']
            
            logger.info(f"Connected to Deebot {device_name}")
            
            # Keep the connection alive
            while True:
                await asyncio.sleep(30)
                
        except Exception as e:
            logger.error(f"MQTT connection error: {e}")
        finally:
            # Clean up session
            if session and not session.closed:
                await session.close()
            
    async def _on_battery_event(self, event):
        """Handle battery level updates"""
        self.battery_level = event.value
        self.robot_data["battery_level"] = event.value
        logger.debug(f"Battery level: {event.value}%")
        
    async def _on_state_event(self, event):
        """Handle robot state updates"""
        # Try different possible attributes for state events
        if hasattr(event, 'state'):
            raw_status = event.state
            self.robot_status = raw_status
            self.robot_data["status"] = self._get_status_label(raw_status)
            logger.debug(f"Robot state: {raw_status} -> {self.robot_data['status']}")
        elif hasattr(event, 'value'):
            raw_status = event.value
            self.robot_status = raw_status
            self.robot_data["status"] = self._get_status_label(raw_status)
            logger.debug(f"Robot state: {raw_status} -> {self.robot_data['status']}")
        else:
            raw_status = str(event)
            self.robot_status = raw_status
            self.robot_data["status"] = self._get_status_label(raw_status)
            logger.debug(f"Robot state: {raw_status}")
        
    async def _on_error_event(self, event):
        """Handle robot error events"""
        # Try different possible attributes for error events
        error_info = "Unknown error"
        if hasattr(event, 'error'):
            error_info = event.error
        elif hasattr(event, 'value'):
            error_info = event.value
        elif hasattr(event, 'code'):
            error_info = event.code
        elif hasattr(event, 'message'):
            error_info = event.message
        else:
            error_info = str(event)
        
        logger.warning(f"Robot error: {error_info}")
        
    async def _on_clean_log_event(self, event):
        """Handle cleaning log updates"""
        self.last_clean_log = event
        
        # Extract cleaning mode if available
        if hasattr(event, 'cleaning_mode'):
            self.robot_data["cleaning_mode"] = event.cleaning_mode
        elif hasattr(event, 'mode'):
            self.robot_data["cleaning_mode"] = event.mode
        elif hasattr(event, 'type'):
            self.robot_data["cleaning_mode"] = event.type
            
        logger.debug(f"Clean log: {event}")
    
    async def _on_stats_event(self, event):
        """Handle stats updates which may contain position info"""
        # Try to extract position information
        if hasattr(event, 'position'):
            self.robot_data["position"] = event.position
        elif hasattr(event, 'coordinates'):
            self.robot_data["position"] = event.coordinates
        elif hasattr(event, 'location'):
            self.robot_data["position"] = event.location
        elif hasattr(event, 'x') and hasattr(event, 'y'):
            self.robot_data["position"] = {"x": event.x, "y": event.y}
            
        logger.debug(f"Stats event: {event}")
    
    def _execute_command_sync(self, command):
        """Execute a command synchronously"""
        if not self.bot:
            return "Robot not connected. Please wait for initialization."
        
        if not self.mqtt_loop or self.mqtt_loop.is_closed():
            return "MQTT connection not available"
        
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.bot.execute_command(command), 
                self.mqtt_loop
            )
            result = future.result(timeout=15)
            return "Command executed successfully"
        except asyncio.TimeoutError:
            logger.error("Command execution timeout")
            return "Command execution timeout - robot may be offline"
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            if "Session is closed" in str(e):
                return "Connection lost to robot. Please restart the module."
            return f"Error executing command: {e}"
    
    def start_cleaning(self):
        """Start cleaning the house"""
        logger.info("Starting Deebot cleaning")
        return self._execute_command_sync(Clean(CleanAction.START))
    
    def stop_cleaning(self):
        """Stop current cleaning operation"""
        logger.info("Stopping Deebot cleaning")
        return self._execute_command_sync(Clean(CleanAction.STOP))
    
    def return_to_base(self):
        """Return robot to charging base"""
        logger.info("Returning Deebot to base")
        return self._execute_command_sync(Charge())
    
    def get_robot_status(self):
        """Get current robot status"""
        if not self.bot:
            return "Robot not connected. Please wait for initialization."
        
        # Get device name safely
        device_name = "Unknown"
        if hasattr(self.bot, 'device_info') and self.bot.device_info:
            if hasattr(self.bot.device_info, 'name'):
                device_name = self.bot.device_info.name
            elif isinstance(self.bot.device_info, dict) and 'name' in self.bot.device_info:
                device_name = self.bot.device_info['name']
        
        status_info = {
            "device_name": device_name,
            "battery_level": self.battery_level,
            "status": self.robot_status,
            "connected": self.bot is not None
        }
        
        return json.dumps(status_info, indent=2)
    
    def get_deebot_status(self):
        """Get real-time robot status from robot_data dict"""
        logger.debug("Getting Deebot real-time status")
        return json.dumps(self.robot_data, indent=2)
    
    

