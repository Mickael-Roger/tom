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
from deebot_client.commands.json.clean import Clean, CleanAction, CleanArea
from deebot_client.commands.json.charge import Charge
from deebot_client.commands.json.work_mode import SetWorkMode
from deebot_client.commands.json.battery import GetBattery
from deebot_client.commands.json.stats import GetStats
from deebot_client.commands.json.clean_logs import GetCleanLogs
from deebot_client.commands.json.charge_state import GetChargeState
from deebot_client.commands.json.pos import GetPos
from deebot_client.commands.json.network import GetNetInfo
from deebot_client.commands.json.error import GetError
from deebot_client.commands.json.water_info import GetWaterInfo
from deebot_client.commands.json.station_state import GetStationState
from deebot_client.events import BatteryEvent, StateEvent, CleanLogEvent, ErrorEvent, StatsEvent, RoomsEvent, VolumeEvent, AvailabilityEvent, WorkMode
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
            "volume": None,
            "availability": None,
            "water_info": None,
            "station_state": None,
            "last_error": None,
            "error_history": []
        }
        
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_vacuum_robot_status",
                    "description": "Get comprehensive status of the vacuum robot combining real-time MQTT data with detailed REST API information including battery, position, cleaning status, errors, and device information.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "stop_vacuum_robot",
                    "description": "Stop the vacuum robot from cleaning and pause its current operation.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "go_to_base_station",
                    "description": "Send the vacuum robot back to its charging base station to recharge.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "start_vacuum_robot_cleaning",
                    "description": "Start a cleaning session on the vacuum robot with configurable cleaning type and optional room specification.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "cleaning_type": {
                                "type": "string",
                                "enum": ["vacuum_only", "mop_only", "vacuum_then_mop", "vacuum_and_mop"],
                                "description": "Type of cleaning to perform: vacuum_only (vaccum only), mop_only (mop only), vacuum_then_mop (vaccum then mop), vacuum_and_mop (vaccum and mop at the same time)"
                            },
                            "room_name": {
                                "type": "string",
                                "enum": ["Salon", "Cuisine", "Entree"],
                                "description": "Optional name of the specific room to clean. If not provided, will clean all rooms. Available rooms will be validated against the robot's room mapping."
                            }
                        },
                        "required": ["cleaning_type"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_vacuum_robot_rooms",
                    "description": "Get the list of available rooms that the vacuum robot can clean individually.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
        ]
        
        self.systemContext = "This module provides comprehensive status monitoring and control of a Deebot robot vacuum. It combines real-time MQTT data with detailed REST API information to give complete device status and allows control commands including starting cleaning with different modes (vacuum only, mop only, vacuum then mop, vacuum and mop simultaneously), stopping cleaning, and returning to base station. It supports both full house cleaning and room-specific cleaning."
        self.complexity = 0
        
        self.functions = {
            "get_vacuum_robot_status": {"function": functools.partial(self.get_vacuum_robot_status)},
            "stop_vacuum_robot": {"function": functools.partial(self.stop_vacuum_robot)},
            "go_to_base_station": {"function": functools.partial(self.go_to_base_station)},
            "start_vacuum_robot_cleaning": {"function": functools.partial(self.start_vacuum_robot_cleaning)},
            "get_vacuum_robot_rooms": {"function": functools.partial(self.get_vacuum_robot_rooms)},
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
    
    def _parse_lifespan_event(self, lifespan_str):
        """Parse LifeSpanEvent string into readable format"""
        import re
        try:
            # Example: LifeSpanEvent(type=<LifeSpan.FILTER: 'heap'>, percent=75.42, remaining=5430)
            
            # Extract component type
            type_match = re.search(r"type=<LifeSpan\.(\w+): '(\w+)'", lifespan_str)
            component_type = type_match.group(1).lower() if type_match else "unknown"
            component_name = type_match.group(2) if type_match else "unknown"
            
            # Extract percent
            percent_match = re.search(r"percent=([\d.]+)", lifespan_str)
            percent = float(percent_match.group(1)) if percent_match else None
            
            # Extract remaining
            remaining_match = re.search(r"remaining=(\d+)", lifespan_str)
            remaining = int(remaining_match.group(1)) if remaining_match else None
            
            return {
                "component": component_type,
                "name": component_name,
                "percent_remaining": percent,
                "remaining_time": remaining,
                "status": "good" if percent and percent > 20 else "low" if percent and percent > 5 else "replace"
            }
        except Exception as e:
            logger.debug(f"Error parsing lifespan event: {e}")
            return None

    def _make_json_serializable(self, obj, _seen=None):
        """Convert objects to JSON serializable format"""
        if _seen is None:
            _seen = set()
        
        # Prevent infinite recursion
        if id(obj) in _seen:
            return str(obj)
        
        if obj is None:
            return None
        elif isinstance(obj, (str, int, float, bool)):
            return obj
        elif isinstance(obj, dict):
            _seen.add(id(obj))
            try:
                # Create a snapshot of dict items to avoid "dictionary changed size during iteration"
                items = list(obj.items())
                result = {k: self._make_json_serializable(v, _seen) for k, v in items}
            except (RuntimeError, AttributeError):
                # Fallback for problematic objects (like MagicMock)
                result = str(obj)
            _seen.remove(id(obj))
            return result
        elif isinstance(obj, (list, tuple)):
            _seen.add(id(obj))
            try:
                result = [self._make_json_serializable(item, _seen) for item in obj]
            except (RuntimeError, AttributeError):
                result = str(obj)
            _seen.remove(id(obj))
            return result
        elif hasattr(obj, '__dict__'):
            _seen.add(id(obj))
            try:
                # Convert object to dict representation
                obj_dict = obj.__dict__
                if isinstance(obj_dict, dict):
                    items = list(obj_dict.items())
                    result = {k: self._make_json_serializable(v, _seen) for k, v in items}
                else:
                    result = str(obj)
            except (RuntimeError, AttributeError):
                result = str(obj)
            _seen.remove(id(obj))
            return result
        else:
            # Fallback to string representation
            return str(obj)
    
    def _get_available_rooms(self):
        """Get list of available room names"""
        rooms = self.robot_data.get("rooms", [])
        room_names = []
        if isinstance(rooms, list):
            for room in rooms:
                if isinstance(room, dict) and room.get("name"):
                    room_names.append(room.get("name"))
        
        # Return sorted list with default rooms if none are detected yet
        if not room_names:
            # Default room names commonly found in homes
            return ["salon", "cuisine", "chambre", "salle_de_bain", "bureau", "entree"]
        
        return sorted(room_names)
        
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
    
    def get_vacuum_robot_status(self):
        """Get comprehensive status combining MQTT real-time data with REST API detailed information"""
        logger.info("Getting comprehensive vacuum robot status (MQTT + REST)")
        
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
            ("water_info", GetWaterInfo()),
            ("station_state", GetStationState()),
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
        
        # Extract and prioritize information (REST over MQTT)
        
        # Battery level (REST priority)
        battery_level = None
        if "battery" in rest_results and isinstance(rest_results["battery"], dict):
            battery_data = rest_results["battery"].get("resp", {}).get("body", {}).get("data", {})
            battery_level = battery_data.get("value")
        if battery_level is None:
            battery_level = self.robot_data.get("battery_level")
        
        # Robot status (MQTT)
        robot_status = self.robot_data.get("status")
        
        # Position (REST priority)
        position = None
        if "position" in rest_results and isinstance(rest_results["position"], dict):
            pos_data = rest_results["position"].get("resp", {}).get("body", {}).get("data", {})
            deebot_pos = pos_data.get("deebotPos", {})
            if deebot_pos.get("invalid") == 0:  # Valid position
                position = {
                    "x": deebot_pos.get("x"),
                    "y": deebot_pos.get("y"),
                    "angle": deebot_pos.get("a")
                }
        if position is None:
            position = self.robot_data.get("position")
        
        # Rooms (simplified - name and id only)
        rooms = []
        mqtt_rooms = self.robot_data.get("rooms", [])
        if isinstance(mqtt_rooms, list):
            for room in mqtt_rooms:
                if isinstance(room, dict):
                    rooms.append({
                        "id": room.get("id"),
                        "name": room.get("name")
                    })
        
        # Volume (MQTT)
        volume = self.robot_data.get("volume")
        
        # Availability (MQTT)
        availability = self.robot_data.get("availability")
        
        # Water info (REST priority)
        water_info = None
        if "water_info" in rest_results and isinstance(rest_results["water_info"], dict):
            water_data = rest_results["water_info"].get("resp", {}).get("body", {}).get("data", {})
            if water_data:
                water_info = water_data
        if water_info is None:
            water_info = self.robot_data.get("water_info")
        
        # Station state (REST priority)
        station_state = None
        if "station_state" in rest_results and isinstance(rest_results["station_state"], dict):
            station_data = rest_results["station_state"].get("resp", {}).get("body", {}).get("data", {})
            if station_data:
                station_state = station_data
        if station_state is None:
            station_state = self.robot_data.get("station_state")
        
        # Current errors
        current_errors = []
        last_error = self.robot_data.get("last_error")
        if last_error and last_error.get("code") != 0:  # Only non-zero error codes
            current_errors.append({
                "code": last_error.get("code"),
                "message": last_error.get("message"),
                "timestamp": last_error.get("formatted_time", self._format_timestamp(last_error.get("timestamp", 0)))
            })
        
        # Is charging (REST priority)
        is_charging = None
        if "charge_state" in rest_results and isinstance(rest_results["charge_state"], dict):
            charge_data = rest_results["charge_state"].get("resp", {}).get("body", {}).get("data", {})
            is_charging = bool(charge_data.get("isCharging", 0))
        
        # Build clean response
        clean_status = {
            "battery_level": battery_level,
            "robot_status": robot_status,
            "position": position,
            "rooms": rooms,
            "volume": volume,
            "availability": availability,
            "water_info": water_info,
            "station_state": station_state,
            "current_errors": current_errors,
            "is_charging": is_charging,
            "device_name": device_name,
            "connected": self.bot is not None
        }
        
        # Make everything JSON serializable
        serializable_status = self._make_json_serializable(clean_status)
        
        return json.dumps(serializable_status, indent=2)
    
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
    
    def stop_vacuum_robot(self):
        """Stop the vacuum robot from cleaning"""
        logger.info("Stopping vacuum robot cleaning")
        return self._execute_command_sync(Clean(CleanAction.PAUSE))
    
    def go_to_base_station(self):
        """Send the vacuum robot back to its charging base station"""
        logger.info("Sending vacuum robot back to base station")
        return self._execute_command_sync(Charge())
    
    def start_vacuum_robot_cleaning(self, cleaning_type, room_name=None):
        """Start cleaning with specified type and optional room"""
        logger.info(f"Starting vacuum robot cleaning: {cleaning_type}" + (f" in room {room_name}" if room_name else " (all rooms)"))
        
        if not self.bot:
            return "Robot not connected. Please wait for initialization."
        
        if not self.mqtt_loop or self.mqtt_loop.is_closed():
            return "MQTT connection not available"
        
        try:
            # Find room ID if room name is specified
            room_id = None
            if room_name:
                rooms = self.robot_data.get("rooms", [])
                available_room_names = []
                
                if isinstance(rooms, list):
                    for room in rooms:
                        if isinstance(room, dict) and room.get("name"):
                            available_room_names.append(room.get("name"))
                            # Check for exact match (case insensitive)
                            if room.get("name").lower() == room_name.lower():
                                room_id = room.get("id")
                                break
                    
                    # If no exact match found, try fuzzy matching
                    if room_id is None:
                        for room in rooms:
                            if isinstance(room, dict) and room.get("name"):
                                # Check if room_name is contained in the detected room name or vice versa
                                detected_name = room.get("name").lower()
                                search_name = room_name.lower()
                                if search_name in detected_name or detected_name in search_name:
                                    room_id = room.get("id")
                                    logger.info(f"Fuzzy match found: '{room_name}' matched with '{room.get('name')}'")
                                    break
                
                if room_id is None:
                    if available_room_names:
                        return f"Room '{room_name}' not found. Available rooms from robot: {available_room_names}"
                    else:
                        return f"Room '{room_name}' specified but no rooms detected by robot yet. Try using room names from predefined list or wait for room detection."
            
            # Configure cleaning based on type using WorkMode
            commands_to_execute = []
            logger.info(f"Requested cleaning type: {cleaning_type}")
            
            # Set the appropriate work mode first
            if cleaning_type == "vacuum_only":
                commands_to_execute.append(SetWorkMode(WorkMode.VACUUM))
                
            elif cleaning_type == "mop_only":
                commands_to_execute.append(SetWorkMode(WorkMode.MOP))
                
            elif cleaning_type == "vacuum_then_mop":
                commands_to_execute.append(SetWorkMode(WorkMode.MOP_AFTER_VACUUM))
                
            elif cleaning_type == "vacuum_and_mop":
                commands_to_execute.append(SetWorkMode(WorkMode.VACUUM_AND_MOP))
            
            else:
                return f"Invalid cleaning type: {cleaning_type}"
            
            # Add the cleaning command
            if room_id:
                # Clean specific area/room
                commands_to_execute.append(CleanArea(area=str(room_id)))
                logger.info(f"Starting room cleaning for room ID: {room_id}")
            else:
                # Clean all areas
                commands_to_execute.append(Clean(CleanAction.START))
                logger.info("Starting full house cleaning")
            
            # Execute all commands in sequence
            results = []
            for i, command in enumerate(commands_to_execute):
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self.bot.execute_command(command), 
                        self.mqtt_loop
                    )
                    result = future.result(timeout=15)
                    results.append(f"Command {i+1} executed successfully")
                    logger.debug(f"Cleaning command {i+1} executed: {type(command).__name__}")
                except asyncio.TimeoutError:
                    error_msg = f"Command {i+1} timeout"
                    logger.error(error_msg)
                    results.append(error_msg)
                except Exception as e:
                    error_msg = f"Command {i+1} error: {e}"
                    logger.error(error_msg)
                    results.append(error_msg)
            
            # Check results
            success_count = sum(1 for r in results if "successfully" in r)
            if success_count == len(commands_to_execute):
                success_msg = f"Cleaning started successfully with {cleaning_type}" + (f" in room {room_name}" if room_name else " for all rooms")
                logger.info(success_msg)
                return success_msg
            else:
                return f"Cleaning started with some issues: {'; '.join(results)}"
                
        except Exception as e:
            logger.error(f"Error starting cleaning: {e}")
            return f"Error starting cleaning: {e}"
    
    def get_vacuum_robot_rooms(self):
        """Get the list of available rooms for cleaning"""
        logger.info("Getting list of available rooms for vacuum robot")
        
        available_rooms = self._get_available_rooms()
        
        # Get actual rooms detected by the robot
        rooms = self.robot_data.get("rooms", [])
        detected_rooms = []
        if isinstance(rooms, list):
            for room in rooms:
                if isinstance(room, dict) and room.get("name"):
                    detected_rooms.append({
                        "id": room.get("id"),
                        "name": room.get("name")
                    })
        
        result = {
            "predefined_rooms": available_rooms,
            "detected_rooms": detected_rooms,
            "total_available": len(available_rooms),
            "total_detected": len(detected_rooms)
        }
        
        return json.dumps(result, indent=2)
    
    

