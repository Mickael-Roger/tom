import functools
import asyncio
import json
import aiohttp
import time
from deebot_client.api_client import ApiClient
from deebot_client.authentication import Authenticator, create_rest_config
from deebot_client.mqtt_client import MqttClient, create_mqtt_config
from deebot_client.device import Device
from deebot_client.util import md5

# Logging
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
from tomlogger import logger

tom_config = {
    "module_name": "deebot",
    "class_name": "TomDeebot",
    "description": "Module to manage Deebot robot vacuum - control, status and cleaning scheduling.",
    "type": "global"
}


class CustomEncoder(json.JSONEncoder):
    def default(self, o):
        return o.__dict__


class TomDeebot:
    def __init__(self, config, llm) -> None:
        self.config = config
        self.llm = llm
        
        # Authentication configuration
        self.username = config.get('username')
        self.password = config.get('password')
        self.country = 'FR'
        
        # Initialize authentication and API client
        self.authenticator = None
        self.api_client = None
        self.mqtt_client = None
        self.device = None
        self.session = None
        
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_deebot_status",
                    "description": "Gets the current status of the Deebot robot vacuum (battery, cleaning state, etc.)",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False
                    }
                }
            }
        ]
        
        self.systemContext = "This module allows control of a Deebot robot vacuum. It can get status, start/stop cleaning and return the robot to its base."
        self.complexity = 0
        
        self.functions = {
            "get_deebot_status": {
                "function": functools.partial(self.get_status)
            }
        }
        
        # Initialize authentication flag
        self._initialized = False
    
    async def _initialize_deebot(self):
        """Initialize Deebot authentication and connection"""
        try:
            # Create aiohttp session
            self.session = aiohttp.ClientSession()
            
            # Generate device ID and hash password
            device_id = md5(str(time.time()))
            password_hash = md5(self.password)
            
            # Create REST configuration
            rest_config = create_rest_config(
                self.session, 
                device_id=device_id, 
                alpha_2_country=self.country
            )
            
            # Create authenticator
            self.authenticator = Authenticator(rest_config, self.username, password_hash)
            
            # Create API client
            self.api_client = ApiClient(self.authenticator)
            
            # Get devices
            devices = await self.api_client.get_devices()
            if devices and hasattr(devices, 'mqtt') and devices.mqtt:
                device_info = devices.mqtt[0]
                self.device = Device(device_info, self.authenticator)
                
                # Create MQTT configuration
                mqtt_config = create_mqtt_config(
                    device_id=device_id,
                    country=self.country
                )
                
                # Initialize MQTT client
                self.mqtt_client = MqttClient(mqtt_config, self.authenticator)
                await self.device.initialize(self.mqtt_client)
                
                self._initialized = True
                device_name = getattr(self.device, 'name', getattr(device_info, 'name', 'Unknown'))
                logger.info(f"Deebot initialized successfully: {device_name}")





                
            else:
                logger.warning("No MQTT devices found")
                logger.info(f"Available devices: {devices}")
                self._initialized = False
                
        except Exception as e:
            logger.error(f"Error initializing Deebot: {e}")
            self._initialized = False
    
    def get_status(self):
        """Gets the current status of the Deebot robot vacuum"""
        # Check if we need to initialize first
        if not self._initialized and self.username and self.password:
            try:
                # Run initialization synchronously
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self._initialize_deebot())
                finally:
                    # Properly close the loop and cleanup
                    if not loop.is_closed():
                        loop.run_until_complete(self._cleanup())
                    loop.close()
            except Exception as e:
                return {"error": f"Failed to initialize: {str(e)}"}
        
        if not self.device:
            return {"error": "Device not initialized"}
        
        try:
            # Get device status using asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self._get_status_async())
                return result
            finally:
                if not loop.is_closed():
                    loop.close()
        except Exception as e:
            return {"error": f"Failed to get status: {str(e)}"}
    
    async def _cleanup(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
    
    async def _get_status_async(self):
        """Async helper to get device status"""
        try:
            # Get device basic info
            device_info = getattr(self.device, 'device_info', {})
            
            status_info = {
                "device_name": device_info.get('name', 'Unknown'),
                "model": device_info.get('model', 'Unknown')
            }
            
            # Get current state
            current_state = getattr(self.device, '_state', None)
            if current_state:
                status_info["current_state"] = str(current_state)


            # Get events and their last values - focus on equipment status
            if hasattr(self.device, 'events'):
                event_bus = self.device.events
                logger.debug("##################################")
                logger.debug(json.dumps(self.device, indent=4, cls=CustomEncoder))
                logger.debug("##################################")

                if hasattr(event_bus, '_event_processing_data'):
                    for event_type, processing_data in event_bus._event_processing_data.items():
                        if hasattr(processing_data, 'last_event') and processing_data.last_event:
                            event_name = event_type.__name__
                            event_value = processing_data.last_event
                            
                            # Extract meaningful status info
                            if event_name == 'BatteryEvent':
                                status_info["battery_level"] = getattr(event_value, 'value', 'Unknown')
                            
                            elif event_name == 'StateEvent':
                                status_info["robot_state"] = str(getattr(event_value, 'value', 'Unknown'))
                            
                            elif event_name == 'FanSpeedEvent':
                                status_info["fan_speed"] = str(getattr(event_value, 'value', 'Unknown'))
                            
                            elif event_name == 'WaterAmountEvent':
                                status_info["water_level"] = str(getattr(event_value, 'value', 'Unknown'))
                            
                            elif event_name == 'MopAttachedEvent':
                                status_info["mop_attached"] = getattr(event_value, 'value', 'Unknown')
                            
                            elif event_name == 'AvailabilityEvent':
                                status_info["online"] = getattr(event_value, 'value', 'Unknown')
                            
                            elif event_name == 'NetworkInfoEvent':
                                network_info = getattr(event_value, 'value', None)
                                if network_info:
                                    status_info["network_signal"] = getattr(network_info, 'signal', 'Unknown')
                            
                            elif event_name == 'PositionsEvent':
                                position = getattr(event_value, 'value', None)
                                if position:
                                    status_info["position"] = {
                                        "x": getattr(position, 'x', 'Unknown'),
                                        "y": getattr(position, 'y', 'Unknown')
                                    }
                            
                            elif event_name == 'LifeSpanEvent':
                                lifespan = getattr(event_value, 'value', None)
                                if lifespan:
                                    status_info["equipment_lifespan"] = {
                                        "component": str(getattr(lifespan, 'type', 'Unknown')),
                                        "remaining": getattr(lifespan, 'remaining', 'Unknown')
                                    }
                            
                            elif event_name == 'ErrorEvent':
                                error = getattr(event_value, 'value', None)
                                if error:
                                    status_info["error"] = {
                                        "code": getattr(error, 'code', 'Unknown'),
                                        "description": getattr(error, 'description', 'Unknown')
                                    }
                            
                            elif event_name == 'StatsEvent':
                                stats = getattr(event_value, 'value', None)
                                if stats:
                                    status_info["cleaning_stats"] = {
                                        "area": getattr(stats, 'area', 'Unknown'),
                                        "time": getattr(stats, 'time', 'Unknown')
                                    }
                            
                            elif event_name == 'WorkModeEvent':
                                status_info["work_mode"] = str(getattr(event_value, 'value', 'Unknown'))
                            
                            elif event_name == 'CleanLogEvent':
                                logs = getattr(event_value, 'value', None)
                                if logs and len(logs) > 0:
                                    last_clean = logs[0]
                                    status_info["last_cleaning"] = {
                                        "timestamp": getattr(last_clean, 'timestamp', 'Unknown'),
                                        "duration": getattr(last_clean, 'duration', 'Unknown'),
                                        "area": getattr(last_clean, 'area', 'Unknown')
                                    }
            
            return status_info
            
        except Exception as e:
            return {"error": f"Failed to get async status: {str(e)}"}



