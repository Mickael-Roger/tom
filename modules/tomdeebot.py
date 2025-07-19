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

# Required dependencies
import aiohttp

# Deebot client imports
from deebot_client.api_client import ApiClient
from deebot_client.authentication import Authenticator, create_rest_config
from deebot_client.commands.json.clean import Clean, CleanAction
from deebot_client.commands.json.charge import Charge
from deebot_client.commands.json.battery import GetBattery
from deebot_client.commands.json.stats import GetStats
from deebot_client.commands.json.clean_logs import GetCleanLogs
from deebot_client.commands.json.charge_state import GetChargeState
from deebot_client.commands.json.pos import GetPos
from deebot_client.commands.json.network import GetNetInfo
from deebot_client.commands.json.error import GetError
from deebot_client.events import BatteryEvent, StateEvent, CleanLogEvent, ErrorEvent, StatsEvent, RoomsEvent, LifeSpanEvent, VolumeEvent, AvailabilityEvent
from deebot_client.mqtt_client import MqttClient, create_mqtt_config
from deebot_client.util import md5
from deebot_client.device import Device

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
            "position": None,
            "rooms": None,
            "component_lifespan": None,
            "volume": None,
            "availability": None,
            "last_error": None,
            "error_history": []
        }
        
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_deebot_status",
                    "description": "Get comprehensive status of the Deebot robot combining real-time MQTT data with detailed REST API information including battery, position, cleaning status, errors, and device information.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
        ]
        
        self.systemContext = "This module provides comprehensive status monitoring of a Deebot robot vacuum. It combines real-time MQTT data with detailed REST API information to give complete device status including battery, position, cleaning state, errors, and component information."
        self.complexity = 0
        
        self.functions = {
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
    
    def _format_timestamp(self, timestamp):
        """Format timestamp to human readable string"""
        import datetime
        return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    
    def _make_json_serializable(self, obj):
        """Convert objects to JSON serializable format"""
        if obj is None:
            return None
        elif isinstance(obj, (str, int, float, bool)):
            return obj
        elif isinstance(obj, dict):
            return {k: self._make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._make_json_serializable(item) for item in obj]
        elif hasattr(obj, '__dict__'):
            # Convert object to dict representation
            return self._make_json_serializable(obj.__dict__)
        else:
            # Fallback to string representation
            return str(obj)
        
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
            self.bot.events.subscribe(RoomsEvent, self._on_rooms_event)
            self.bot.events.subscribe(LifeSpanEvent, self._on_lifespan_event)
            self.bot.events.subscribe(VolumeEvent, self._on_volume_event)
            self.bot.events.subscribe(AvailabilityEvent, self._on_availability_event)
            
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
        error_code = None
        error_message = None
        
        if hasattr(event, 'error'):
            error_info = event.error
        elif hasattr(event, 'value'):
            error_info = event.value
        elif hasattr(event, 'code'):
            error_code = event.code
            error_info = f"Error code: {event.code}"
        elif hasattr(event, 'message'):
            error_message = event.message
            error_info = event.message
        else:
            error_info = str(event)
        
        # Try to get both code and message if available
        if hasattr(event, 'code') and hasattr(event, 'message'):
            error_code = event.code
            error_message = event.message
            error_info = f"Code {event.code}: {event.message}"
        elif hasattr(event, 'error_code') and hasattr(event, 'error_message'):
            error_code = event.error_code
            error_message = event.error_message
            error_info = f"Code {event.error_code}: {event.error_message}"
        
        # Create error object with timestamp
        import time
        error_object = {
            "timestamp": time.time(),
            "error": error_info,
            "code": error_code,
            "message": error_message,
            "raw_event": str(event)
        }
        
        # Update robot data
        self.robot_data["last_error"] = error_object
        
        # Add to error history (keep last 10 errors)
        if self.robot_data["error_history"] is None:
            self.robot_data["error_history"] = []
        
        self.robot_data["error_history"].append(error_object)
        
        # Keep only last 10 errors
        if len(self.robot_data["error_history"]) > 10:
            self.robot_data["error_history"] = self.robot_data["error_history"][-10:]
        
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
    
    async def _on_rooms_event(self, event):
        """Handle rooms information updates"""
        # Try to extract rooms information
        if hasattr(event, 'rooms'):
            self.robot_data["rooms"] = event.rooms
        elif hasattr(event, 'value'):
            self.robot_data["rooms"] = event.value
        elif hasattr(event, 'data'):
            self.robot_data["rooms"] = event.data
        else:
            self.robot_data["rooms"] = str(event)
            
        logger.debug(f"Rooms event: {event}")
    
    async def _on_lifespan_event(self, event):
        """Handle component lifespan updates"""
        # Try to extract lifespan information
        lifespan_data = {}
        
        if hasattr(event, 'component') and hasattr(event, 'lifespan'):
            lifespan_data[event.component] = event.lifespan
        elif hasattr(event, 'value'):
            lifespan_data = event.value
        elif hasattr(event, 'data'):
            lifespan_data = event.data
        else:
            lifespan_data = str(event)
        
        # Update or create lifespan dict
        if self.robot_data["component_lifespan"] is None:
            self.robot_data["component_lifespan"] = {}
        
        if isinstance(lifespan_data, dict):
            self.robot_data["component_lifespan"].update(lifespan_data)
        else:
            self.robot_data["component_lifespan"] = lifespan_data
            
        logger.debug(f"Lifespan event: {event}")
    
    async def _on_volume_event(self, event):
        """Handle volume level updates"""
        # Try to extract volume information
        if hasattr(event, 'volume'):
            self.robot_data["volume"] = event.volume
        elif hasattr(event, 'value'):
            self.robot_data["volume"] = event.value
        elif hasattr(event, 'level'):
            self.robot_data["volume"] = event.level
        else:
            self.robot_data["volume"] = str(event)
            
        logger.debug(f"Volume event: {event}")
    
    async def _on_availability_event(self, event):
        """Handle robot availability updates"""
        # Try to extract availability information
        if hasattr(event, 'available'):
            self.robot_data["availability"] = event.available
        elif hasattr(event, 'value'):
            self.robot_data["availability"] = event.value
        elif hasattr(event, 'online'):
            self.robot_data["availability"] = event.online
        else:
            self.robot_data["availability"] = str(event)
            
        logger.debug(f"Availability event: {event}")
    
    def get_deebot_status(self):
        """Get comprehensive status combining MQTT real-time data with REST API detailed information"""
        logger.info("Getting comprehensive Deebot status (MQTT + REST)")
        
        if not self.bot:
            return "Robot not connected. Please wait for initialization."
        
        if not self.mqtt_loop or self.mqtt_loop.is_closed():
            return "MQTT connection not available"
        
        # Create list of REST commands to execute
        rest_commands = [
            ("battery", GetBattery()),
            ("stats", GetStats()),
            ("clean_logs", GetCleanLogs()),
            ("charge_state", GetChargeState()),
        ]
        
        # Add additional commands
        rest_commands.extend([
            ("position", GetPos()),
            ("network_info", GetNetInfo()),
            ("error_info", GetError()),
        ])
        
        # Execute all REST commands
        rest_results = {}
        
        for command_name, command in rest_commands:
            try:
                logger.debug(f"Executing REST command: {command_name}")
                future = asyncio.run_coroutine_threadsafe(
                    self.bot.execute_command(command), 
                    self.mqtt_loop
                )
                result = future.result(timeout=10)
                rest_results[command_name] = result
                logger.debug(f"REST command {command_name} completed successfully")
            except asyncio.TimeoutError:
                logger.warning(f"REST command {command_name} timeout")
                rest_results[command_name] = {"error": "timeout"}
            except Exception as e:
                logger.error(f"REST command {command_name} error: {e}")
                rest_results[command_name] = {"error": str(e)}
        
        # Get device name safely
        device_name = "Unknown"
        if hasattr(self.bot, 'device_info') and self.bot.device_info:
            if hasattr(self.bot.device_info, 'name'):
                device_name = self.bot.device_info.name
            elif isinstance(self.bot.device_info, dict) and 'name' in self.bot.device_info:
                device_name = self.bot.device_info['name']
        
        # Combine MQTT data with REST results
        complete_status = self.robot_data.copy()
        
        # Add REST data to the main status
        complete_status.update({
            "timestamp": time.time(),
            "formatted_time": self._format_timestamp(time.time()),
            "device_name": device_name,
            "connected": self.bot is not None,
            "rest_data": rest_results
        })
        
        # Make everything JSON serializable
        serializable_status = self._make_json_serializable(complete_status)
        
        return json.dumps(serializable_status, indent=2)
    
    

