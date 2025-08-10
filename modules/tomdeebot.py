import time
import asyncio
import threading
import sqlite3
import os

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
from deebot_client.events import BatteryEvent, StateEvent, CleanLogEvent, ErrorEvent, StatsEvent, RoomsEvent, VolumeEvent, AvailabilityEvent
from deebot_client.mqtt_client import MqttClient, create_mqtt_config
from deebot_client.util import md5
from deebot_client.device import Device

tom_config = {
    "module_name": "deebot",
    "class_name": "TomDeebot",
    "description": "Module to manage Deebot robot vacuum - control, status and cleaning scheduling.",
    "type": "global",
    "configuration_parameters": {
        "username": {
            "type": "string",
            "description": "Deebot account username/email for authentication",
            "required": True
        },
        "password": {
            "type": "string", 
            "description": "Deebot account password for authentication",
            "required": True
        },
        "country": {
            "type": "string",
            "description": "Country code for Deebot API region (e.g., 'FR', 'US')",
            "required": False,
            "default": "FR"
        }
    }
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
        
        # Database setup
        all_datadir = config.get('all_datadir', './data/all/')
        if not os.path.exists(all_datadir):
            os.makedirs(all_datadir, exist_ok=True)
        self.db_path = os.path.join(all_datadir, 'deebot_cleaning_history.sqlite')
        self._init_database()
        
        # Robot state structure with raw and labeled values
        self.robot_state = {
            "battery": {
                "level": None,
                "label": None
            },
            "status": {
                "raw": None,
                "label": None
            },
            "cleaning_mode": {
                "raw": None,
                "label": None
            },
            "position": {
                "raw": None,
                "x": None,
                "y": None,
                "angle": None
            },
            "rooms": {
                "raw": None,
                "list": [],
                "count": 0
            },
            "volume": {
                "raw": None,
                "level": None
            },
            "availability": {
                "raw": None,
                "label": None,
                "online": None
            },
            "water_info": {
                "raw": None,
                "level": None
            },
            "station_state": {
                "raw": None,
                "label": None
            },
            "last_error": {
                "timestamp": None,
                "raw_event": None,
                "description": None
            },
            "error_history": [],
            "connection": {
                "last_event_timestamp": None,
                "last_event_type": None,
                "device_name": None
            },
            "current_cleaning_session": {
                "session_id": None,
                "is_cleaning": False,
                "start_time": None
            }
        }
        
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_deebot_status",
                    "description": "Get the current status and state of the Deebot robot vacuum including battery level, cleaning status, position, rooms, and connection information.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_deebot_cleaning_history",
                    "description": "Get the cleaning history of the Deebot robot vacuum including past cleaning sessions with dates, durations, cleaning types, and battery levels.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of cleaning sessions to return (default: 20, max: 100)",
                                "minimum": 1,
                                "maximum": 100
                            },
                            "status": {
                                "type": "string",
                                "enum": ["all", "completed", "interrupted", "started"],
                                "description": "Filter sessions by status (default: all)"
                            }
                        },
                        "additionalProperties": False
                    },
                },
            },
        ]
        
        self.systemContext = "This module monitors Deebot robot vacuum status via MQTT connection and provides status information."
        self.complexity = 0
        
        self.functions = {
            "get_deebot_status": {"function": self.get_deebot_status},
            "get_deebot_cleaning_history": {"function": self.get_deebot_cleaning_history},
        }
        
        # Start MQTT background task
        self._start_mqtt_background_task()
        
    def _update_event_timestamp(self, event_type):
        """Update timestamp when an event is received"""
        self.robot_state["connection"]["last_event_timestamp"] = time.time()
        self.robot_state["connection"]["last_event_type"] = event_type
    
    def _get_status_label(self, status_code):
        """Convert numeric status code to human readable label"""
        status_map = {
            0: "Unknown",
            1: "Idle", 
            2: "Cleaning",
            3: "Paused",
            4: "Returning to dock",
            5: "Charging",
            6: "Error",
            7: "Offline",
            8: "Docked",
            9: "Sleeping",
            10: "Manual cleaning",
            11: "Spot cleaning",
            12: "Edge cleaning",
            13: "Zone cleaning"
        }
        
        if isinstance(status_code, str):
            try:
                status_code = int(status_code)
            except (ValueError, TypeError):
                return status_code
        
        return status_map.get(status_code, f"Status {status_code}")
    
    def _get_cleaning_mode_label(self, mode):
        """Convert cleaning mode to human readable label"""
        mode_map = {
            "vacuum": "Aspiration",
            "mop": "Serpillière",
            "vacuum_and_mop": "Aspiration + Serpillière",
            "sweep": "Balayage",
            "auto": "Mode automatique",
            "spot": "Nettoyage localisé",
            "edge": "Nettoyage des bords",
            "single_room": "Pièce unique"
        }
        
        if isinstance(mode, str):
            return mode_map.get(mode.lower(), mode)
        return mode
        
        
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
            
            # Subscribe to MQTT client events for ping monitoring
            if hasattr(self.mqtt_client, 'on_ping_request'):
                self.mqtt_client.on_ping_request = self._on_ping_request
            if hasattr(self.mqtt_client, 'on_ping_response'):
                self.mqtt_client.on_ping_response = self._on_ping_response
            
            # Get device name safely
            device_name = "Unknown"
            if hasattr(self.bot, 'device_info') and self.bot.device_info:
                if hasattr(self.bot.device_info, 'name'):
                    device_name = self.bot.device_info.name
                elif isinstance(self.bot.device_info, dict) and 'name' in self.bot.device_info:
                    device_name = self.bot.device_info['name']
            
            # Store device name in robot state
            self.robot_state["connection"]["device_name"] = device_name
            logger.info(f"Connected to Deebot {device_name}")
            
            # Keep the connection alive
            await asyncio.sleep(99999999999)  # Wait indefinitely
                
        except Exception as e:
            logger.error(f"MQTT connection error: {e}")
        finally:
            # Clean up session
            if session and not session.closed:
                await session.close()
            
    async def _on_battery_event(self, event):
        """Handle battery level updates"""
        self._update_event_timestamp("battery")
        if hasattr(event, 'value'):
            level = event.value
            self.robot_state["battery"]["level"] = level
            self.robot_state["battery"]["label"] = f"{level}%" if level is not None else "Unknown"
        logger.info(f"Deebot MQTT Event - Battery: {event} (Level: {self.robot_state['battery']['label']})")
        
    async def _on_state_event(self, event):
        """Handle robot state updates"""
        self._update_event_timestamp("state")
        raw_status = None
        if hasattr(event, 'state'):
            raw_status = event.state
        elif hasattr(event, 'value'):
            raw_status = event.value
        
        if raw_status is not None:
            old_status = self.robot_state["status"]["raw"]
            self.robot_state["status"]["raw"] = raw_status
            self.robot_state["status"]["label"] = self._get_status_label(raw_status)
            
            # Track cleaning state changes
            self._handle_cleaning_state_change(old_status, raw_status)
        
        status_label = self.robot_state["status"]["label"] or "Unknown"
        logger.info(f"Deebot MQTT Event - State: {status_label} (raw: {raw_status})")
        
    async def _on_error_event(self, event):
        """Handle robot error events"""
        self._update_event_timestamp("error")
        
        error_description = "Unknown error"
        if hasattr(event, 'error'):
            error_description = str(event.error)
        elif hasattr(event, 'message'):
            error_description = str(event.message)
        elif hasattr(event, 'code'):
            error_description = f"Error code: {event.code}"
        else:
            error_description = str(event)
        
        error_object = {
            "timestamp": time.time(),
            "raw_event": str(event),
            "description": error_description
        }
        
        # Update last error
        self.robot_state["last_error"] = error_object
        
        # Add to error history
        if self.robot_state["error_history"] is None:
            self.robot_state["error_history"] = []
        self.robot_state["error_history"].append(error_object)
        
        # Keep only last 10 errors
        if len(self.robot_state["error_history"]) > 10:
            self.robot_state["error_history"] = self.robot_state["error_history"][-10:]
            
        logger.info(f"Deebot MQTT Event - Error: {error_description}")
        
    async def _on_clean_log_event(self, event):
        """Handle cleaning log updates"""
        self._update_event_timestamp("clean_log")
        raw_mode = None
        if hasattr(event, 'cleaning_mode'):
            raw_mode = event.cleaning_mode
        elif hasattr(event, 'mode'):
            raw_mode = event.mode
        elif hasattr(event, 'type'):
            raw_mode = event.type
        
        if raw_mode is not None:
            self.robot_state["cleaning_mode"]["raw"] = raw_mode
            self.robot_state["cleaning_mode"]["label"] = self._get_cleaning_mode_label(raw_mode)
            
            # If we're currently cleaning, update the session with cleaning mode
            if self.robot_state["current_cleaning_session"]["is_cleaning"]:
                self._update_cleaning_session_mode(raw_mode, self._get_cleaning_mode_label(raw_mode))
        
        mode_label = self.robot_state["cleaning_mode"]["label"] or "Unknown"
        logger.info(f"Deebot MQTT Event - Clean Log: {mode_label} (raw: {raw_mode})")
    
    async def _on_stats_event(self, event):
        """Handle stats updates which may contain position info"""
        self._update_event_timestamp("stats")
        
        # Handle position data
        if hasattr(event, 'position'):
            self.robot_state["position"]["raw"] = event.position
            if hasattr(event.position, 'x'):
                self.robot_state["position"]["x"] = event.position.x
            if hasattr(event.position, 'y'):
                self.robot_state["position"]["y"] = event.position.y
            if hasattr(event.position, 'angle'):
                self.robot_state["position"]["angle"] = event.position.angle
        elif hasattr(event, 'coordinates'):
            self.robot_state["position"]["raw"] = event.coordinates
        elif hasattr(event, 'location'):
            self.robot_state["position"]["raw"] = event.location
        elif hasattr(event, 'x') and hasattr(event, 'y'):
            self.robot_state["position"]["x"] = event.x
            self.robot_state["position"]["y"] = event.y
            self.robot_state["position"]["raw"] = {"x": event.x, "y": event.y}
            
        logger.info(f"Deebot MQTT Event - Stats: {event}")
    
    async def _on_rooms_event(self, event):
        """Handle rooms information updates"""
        self._update_event_timestamp("rooms")
        
        rooms_data = None
        if hasattr(event, 'rooms'):
            rooms_data = event.rooms
        elif hasattr(event, 'value'):
            rooms_data = event.value
        elif hasattr(event, 'data'):
            rooms_data = event.data
            
        if rooms_data is not None:
            self.robot_state["rooms"]["raw"] = rooms_data
            # Extract room list if it's a list of room objects
            if isinstance(rooms_data, list):
                room_list = []
                for room in rooms_data:
                    if isinstance(room, dict):
                        room_info = {
                            "id": room.get("id"),
                            "name": room.get("name", "Unknown"),
                            "area": room.get("area")
                        }
                        room_list.append(room_info)
                self.robot_state["rooms"]["list"] = room_list
                self.robot_state["rooms"]["count"] = len(room_list)
            
        logger.info(f"Deebot MQTT Event - Rooms: {event}")
    
    async def _on_volume_event(self, event):
        """Handle volume level updates"""
        self._update_event_timestamp("volume")
        
        volume_value = None
        if hasattr(event, 'volume'):
            volume_value = event.volume
        elif hasattr(event, 'value'):
            volume_value = event.value
        elif hasattr(event, 'level'):
            volume_value = event.level
            
        if volume_value is not None:
            self.robot_state["volume"]["raw"] = volume_value
            self.robot_state["volume"]["level"] = volume_value
            
        logger.info(f"Deebot MQTT Event - Volume: {event}")
    
    async def _on_availability_event(self, event):
        """Handle robot availability updates"""
        self._update_event_timestamp("availability")
        available = None
        if hasattr(event, 'available'):
            available = event.available
        elif hasattr(event, 'value'):
            available = event.value
        elif hasattr(event, 'online'):
            available = event.online
            
        if available is not None:
            self.robot_state["availability"]["raw"] = available
            self.robot_state["availability"]["online"] = bool(available)
            self.robot_state["availability"]["label"] = "En ligne" if available else "Hors ligne"
        
        availability_label = self.robot_state["availability"]["label"] or "Unknown"
        logger.info(f"Deebot MQTT Event - Availability: {availability_label} (raw: {available})")
    
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
    
    def get_deebot_status(self, **kwargs):
        """Get the current status of the Deebot robot"""
        import json
        import datetime
        
        logger.info("Getting Deebot robot status")
        
        # Create a copy of robot_state with formatted timestamps and JSON-safe objects
        status_copy = {}
        for key, value in self.robot_state.items():
            if key == "connection" and isinstance(value, dict) and value.get("last_event_timestamp"):
                status_copy[key] = self._make_json_serializable(value)
                # Add human readable timestamp
                timestamp = value["last_event_timestamp"]
                status_copy[key]["last_event_time"] = datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                status_copy[key]["seconds_since_last_event"] = int(time.time() - timestamp)
            elif key == "last_error" and isinstance(value, dict) and value.get("timestamp"):
                status_copy[key] = self._make_json_serializable(value)
                # Add human readable timestamp for last error
                timestamp = value["timestamp"]
                status_copy[key]["error_time"] = datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
            elif key == "error_history" and isinstance(value, list):
                status_copy[key] = []
                for error in value:
                    error_serializable = self._make_json_serializable(error)
                    if isinstance(error, dict) and error.get("timestamp"):
                        error_serializable["error_time"] = datetime.datetime.fromtimestamp(error["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
                    status_copy[key].append(error_serializable)
            else:
                status_copy[key] = self._make_json_serializable(value)
        
        return json.dumps(status_copy, indent=2, ensure_ascii=False)
    
    def _init_database(self):
        """Initialize SQLite database for cleaning history"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create cleaning_sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cleaning_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_datetime TEXT NOT NULL,
                    end_datetime TEXT,
                    cleaning_type TEXT NOT NULL,
                    cleaning_mode_raw TEXT,
                    cleaning_mode_label TEXT,
                    rooms_cleaned TEXT,
                    duration_seconds INTEGER,
                    battery_start INTEGER,
                    battery_end INTEGER,
                    status TEXT DEFAULT 'started',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info(f"Deebot cleaning history database initialized: {self.db_path}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Deebot database: {e}")
    
    def _record_cleaning_start(self, cleaning_type, cleaning_mode_raw, cleaning_mode_label, rooms=None):
        """Record the start of a cleaning session"""
        try:
            import datetime
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            start_datetime = datetime.datetime.now().isoformat()
            battery_level = self.robot_state.get('battery', {}).get('level')
            
            # Convert rooms list to string if provided
            rooms_str = None
            if rooms and isinstance(rooms, list):
                rooms_str = ', '.join([room.get('name', 'Unknown') for room in rooms if isinstance(room, dict)])
            
            cursor.execute('''
                INSERT INTO cleaning_sessions 
                (start_datetime, cleaning_type, cleaning_mode_raw, cleaning_mode_label, rooms_cleaned, battery_start, status)
                VALUES (?, ?, ?, ?, ?, ?, 'started')
            ''', (start_datetime, cleaning_type, cleaning_mode_raw, cleaning_mode_label, rooms_str, battery_level))
            
            session_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            logger.info(f"Recorded cleaning session start: ID={session_id}, Type={cleaning_type}, Mode={cleaning_mode_label}")
            return session_id
            
        except Exception as e:
            logger.error(f"Failed to record cleaning start: {e}")
            return None
    
    def _record_cleaning_end(self, status='completed'):
        """Record the end of the most recent cleaning session"""
        try:
            import datetime
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Find the most recent started session
            cursor.execute('''
                SELECT id, start_datetime FROM cleaning_sessions 
                WHERE status = 'started' 
                ORDER BY start_datetime DESC 
                LIMIT 1
            ''')
            
            result = cursor.fetchone()
            if result:
                session_id, start_datetime = result
                end_datetime = datetime.datetime.now().isoformat()
                battery_level = self.robot_state.get('battery', {}).get('level')
                
                # Calculate duration
                start_dt = datetime.datetime.fromisoformat(start_datetime)
                end_dt = datetime.datetime.now()
                duration_seconds = int((end_dt - start_dt).total_seconds())
                
                cursor.execute('''
                    UPDATE cleaning_sessions 
                    SET end_datetime = ?, duration_seconds = ?, battery_end = ?, status = ?
                    WHERE id = ?
                ''', (end_datetime, duration_seconds, battery_level, status, session_id))
                
                conn.commit()
                logger.info(f"Recorded cleaning session end: ID={session_id}, Duration={duration_seconds}s, Status={status}")
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to record cleaning end: {e}")
    
    def _handle_cleaning_state_change(self, old_status, new_status):
        """Handle cleaning state transitions and record cleaning sessions"""
        # Define cleaning states
        cleaning_states = [2, 10, 11, 12, 13]  # cleaning, manual_cleaning, spot_cleaning, edge_cleaning, zone_cleaning
        
        old_is_cleaning = old_status in cleaning_states if old_status is not None else False
        new_is_cleaning = new_status in cleaning_states if new_status is not None else False
        
        # Starting cleaning
        if not old_is_cleaning and new_is_cleaning:
            cleaning_type = self._determine_cleaning_type(new_status)
            cleaning_mode_raw = self.robot_state["cleaning_mode"]["raw"]
            cleaning_mode_label = self.robot_state["cleaning_mode"]["label"]
            rooms = self.robot_state["rooms"]["list"]
            
            session_id = self._record_cleaning_start(
                cleaning_type, 
                cleaning_mode_raw, 
                cleaning_mode_label,
                rooms
            )
            
            if session_id:
                self.robot_state["current_cleaning_session"]["session_id"] = session_id
                self.robot_state["current_cleaning_session"]["is_cleaning"] = True
                self.robot_state["current_cleaning_session"]["start_time"] = time.time()
                
        # Ending cleaning (going to idle, charging, docked, returning)
        elif old_is_cleaning and not new_is_cleaning:
            if self.robot_state["current_cleaning_session"]["is_cleaning"]:
                # Determine if completed or interrupted
                status = "completed" if new_status in [1, 4, 5, 8] else "interrupted"  # idle, returning, charging, docked
                self._record_cleaning_end(status)
                
                self.robot_state["current_cleaning_session"]["session_id"] = None
                self.robot_state["current_cleaning_session"]["is_cleaning"] = False
                self.robot_state["current_cleaning_session"]["start_time"] = None
    
    def _determine_cleaning_type(self, status_code):
        """Determine cleaning type based on status code"""
        type_map = {
            2: "general_cleaning",
            10: "manual_cleaning", 
            11: "spot_cleaning",
            12: "edge_cleaning",
            13: "zone_cleaning"
        }
        return type_map.get(status_code, "unknown_cleaning")
    
    def _update_cleaning_session_mode(self, raw_mode, mode_label):
        """Update the current cleaning session with cleaning mode info"""
        if not self.robot_state["current_cleaning_session"]["session_id"]:
            return
            
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE cleaning_sessions 
                SET cleaning_mode_raw = ?, cleaning_mode_label = ?
                WHERE id = ? AND status = 'started'
            ''', (raw_mode, mode_label, self.robot_state["current_cleaning_session"]["session_id"]))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to update cleaning session mode: {e}")
    
    def get_deebot_cleaning_history(self, limit=20, status="all", **kwargs):
        """Get the cleaning history of the Deebot robot"""
        import json
        import datetime
        
        logger.info(f"Getting Deebot cleaning history (limit: {limit}, status: {status})")
        
        # Validate parameters
        limit = min(max(limit, 1), 100)  # Clamp between 1 and 100
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Build query based on status filter
            if status == "all":
                query = '''
                    SELECT id, start_datetime, end_datetime, cleaning_type, 
                           cleaning_mode_raw, cleaning_mode_label, rooms_cleaned,
                           duration_seconds, battery_start, battery_end, status, created_at
                    FROM cleaning_sessions 
                    ORDER BY start_datetime DESC 
                    LIMIT ?
                '''
                params = (limit,)
            else:
                query = '''
                    SELECT id, start_datetime, end_datetime, cleaning_type, 
                           cleaning_mode_raw, cleaning_mode_label, rooms_cleaned,
                           duration_seconds, battery_start, battery_end, status, created_at
                    FROM cleaning_sessions 
                    WHERE status = ?
                    ORDER BY start_datetime DESC 
                    LIMIT ?
                '''
                params = (status, limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()
            
            # Format results
            sessions = []
            for row in rows:
                session = {
                    "id": row[0],
                    "start_datetime": row[1],
                    "end_datetime": row[2],
                    "cleaning_type": row[3],
                    "cleaning_mode": {
                        "raw": row[4],
                        "label": row[5]
                    },
                    "rooms_cleaned": row[6],
                    "duration_seconds": row[7],
                    "battery": {
                        "start": row[8],
                        "end": row[9],
                        "used": row[8] - row[9] if row[8] and row[9] else None
                    },
                    "status": row[10],
                    "created_at": row[11]
                }
                
                # Add formatted datetime and duration
                if session["start_datetime"]:
                    try:
                        start_dt = datetime.datetime.fromisoformat(session["start_datetime"])
                        session["start_date_formatted"] = start_dt.strftime("%d/%m/%Y")
                        session["start_time_formatted"] = start_dt.strftime("%H:%M:%S")
                        session["start_datetime_formatted"] = start_dt.strftime("%d/%m/%Y à %H:%M:%S")
                    except:
                        pass
                        
                if session["end_datetime"]:
                    try:
                        end_dt = datetime.datetime.fromisoformat(session["end_datetime"])
                        session["end_datetime_formatted"] = end_dt.strftime("%d/%m/%Y à %H:%M:%S")
                    except:
                        pass
                
                # Format duration
                if session["duration_seconds"]:
                    duration = session["duration_seconds"]
                    hours = duration // 3600
                    minutes = (duration % 3600) // 60
                    seconds = duration % 60
                    
                    if hours > 0:
                        session["duration_formatted"] = f"{hours}h {minutes:02d}m {seconds:02d}s"
                    elif minutes > 0:
                        session["duration_formatted"] = f"{minutes}m {seconds:02d}s"
                    else:
                        session["duration_formatted"] = f"{seconds}s"
                
                # Translate cleaning type
                type_labels = {
                    "general_cleaning": "Nettoyage général",
                    "manual_cleaning": "Nettoyage manuel",
                    "spot_cleaning": "Nettoyage localisé",
                    "edge_cleaning": "Nettoyage des bords",
                    "zone_cleaning": "Nettoyage par zone",
                    "unknown_cleaning": "Nettoyage inconnu"
                }
                session["cleaning_type_label"] = type_labels.get(session["cleaning_type"], session["cleaning_type"])
                
                # Translate status
                status_labels = {
                    "started": "En cours",
                    "completed": "Terminé",
                    "interrupted": "Interrompu"
                }
                session["status_label"] = status_labels.get(session["status"], session["status"])
                
                sessions.append(session)
            
            # Summary statistics
            summary = {
                "total_sessions": len(sessions),
                "completed_sessions": len([s for s in sessions if s["status"] == "completed"]),
                "interrupted_sessions": len([s for s in sessions if s["status"] == "interrupted"]),
                "in_progress_sessions": len([s for s in sessions if s["status"] == "started"]),
                "total_cleaning_time": sum([s["duration_seconds"] or 0 for s in sessions]),
                "average_battery_usage": None
            }
            
            # Calculate average battery usage
            battery_usages = [s["battery"]["used"] for s in sessions if s["battery"]["used"] is not None]
            if battery_usages:
                summary["average_battery_usage"] = round(sum(battery_usages) / len(battery_usages), 1)
            
            # Format total cleaning time
            total_seconds = summary["total_cleaning_time"]
            if total_seconds > 0:
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                if hours > 0:
                    summary["total_cleaning_time_formatted"] = f"{hours}h {minutes:02d}m"
                else:
                    summary["total_cleaning_time_formatted"] = f"{minutes}m"
            
            result = {
                "summary": summary,
                "sessions": sessions,
                "filter": {
                    "limit": limit,
                    "status": status
                }
            }
            
            return json.dumps(result, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Failed to get cleaning history: {e}")
            return json.dumps({
                "error": f"Failed to retrieve cleaning history: {str(e)}",
                "sessions": [],
                "summary": {}
            }, ensure_ascii=False)
        
    async def _on_ping_request(self):
        """Handle MQTT PINGREQ events"""
        self._update_event_timestamp("ping_request")
        logger.debug(f"Deebot MQTT Event - PINGREQ")
        
    async def _on_ping_response(self):
        """Handle MQTT PINGRESP events"""
        self._update_event_timestamp("ping_response")
        logger.debug(f"Deebot MQTT Event - PINGRESP")