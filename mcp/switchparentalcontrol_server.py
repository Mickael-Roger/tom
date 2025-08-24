#!/usr/bin/env python3
"""
Nintendo Switch Parental Control MCP Server
Provides Nintendo Switch parental control functionality via MCP protocol
Based on the original tomswitchparentalcontrol.py module
"""

import asyncio
import json
import os
import sys
import yaml
import functools
import concurrent.futures
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List

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

# Nintendo Switch specific imports
try:
    from pynintendoparental import Authenticator, NintendoParental
    from pynintendoparental.exceptions import InvalidSessionTokenException
except ImportError:
    if tomlogger:
        tomlogger.error("pynintendoparental not found. Please install with 'pip install pynintendoparental'", module_name="switchparentalcontrol")
    else:
        print("ERROR: pynintendoparental not found. Please install with 'pip install pynintendoparental'")
    raise

# Initialize logging
log_level = os.environ.get('TOM_LOG_LEVEL', 'INFO')
if tomlogger:
    logger = init_logger(log_level)
    tomlogger.info(f"🚀 Nintendo Switch Parental Control MCP Server starting with log level: {log_level}", module_name="switchparentalcontrol")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "This module is used to manage Nintendo Switch parental control: check daily usage time and add extra playing time"

# Initialize FastMCP server
server = FastMCP(name="switchparentalcontrol-server", stateless_http=True, host="0.0.0.0", port=80)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file"""
    config_path = '/data/config.yml'
    
    if tomlogger:
        tomlogger.info(f"Loading configuration from {config_path}", module_name="switchparentalcontrol")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        if tomlogger:
            tomlogger.error(f"Configuration file not found: {config_path}", module_name="switchparentalcontrol")
        else:
            print(f"ERROR: Configuration file not found: {config_path}")
        return {}
    except yaml.YAMLError as exc:
        if tomlogger:
            tomlogger.error(f"Error parsing YAML configuration: {exc}", module_name="switchparentalcontrol")
        else:
            print(f"ERROR: Error parsing YAML configuration: {exc}")
        return {}


class SwitchParentalControlService:
    """Nintendo Switch Parental Control service class based on original TomSwitchParentalControl"""
    
    def __init__(self, config: Dict[str, Any]):
        # Load nintendo session token from config
        nintendo_config = config.get('nintendo_switch', {})
        
        # Validate required config fields
        self.session_token = nintendo_config.get('nintendo_session_token')
        if not self.session_token:
            raise ValueError("Nintendo session token not found in configuration under nintendo_switch.nintendo_session_token")
        
        # Cache for storing authentication and device information
        data_dir = '/data'
        os.makedirs(data_dir, exist_ok=True)
        self.cache_file = os.path.join(data_dir, 'nintendo_switch_cache.json')
        self.cache = self._load_cache()
        
        # Nintendo authentication
        self.auth = None
        self.control = None
        self.devices = {}
        
        if tomlogger:
            tomlogger.info("✅ Nintendo Switch Parental Control service initialized successfully", module_name="switchparentalcontrol")
    
    def _load_cache(self):
        """Load cache from JSON file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            if tomlogger:
                tomlogger.warning(f"Failed to load Nintendo Switch cache: {e}", module_name="switchparentalcontrol")
        return {"devices": {}, "last_update": None}

    def _save_cache(self):
        """Save cache to JSON file"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except IOError as e:
            if tomlogger:
                tomlogger.warning(f"Failed to save Nintendo Switch cache: {e}", module_name="switchparentalcontrol")

    def _get_cache_summary(self):
        """Returns a cache summary for system context"""
        if not self.cache.get('devices'):
            return "No Nintendo Switch devices are currently cached."
        
        cache_summary = "Cached Nintendo Switch devices:\\n"
        for device_id, device_data in self.cache['devices'].items():
            cache_summary += f"- {device_data['name']} (ID: {device_id})\\n"
        
        return cache_summary

    def _async_wrapper(self, async_func, *args, **kwargs):
        """Wrapper to run async functions in sync context with proper aiohttp session management"""
        try:
            loop = asyncio.get_event_loop()
            
            if loop.is_running():
                # If a loop is already running, use a new thread with a new loop
                def run_in_new_loop():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        # Wrapper that executes the async function
                        async def safe_async_func(*args, **kwargs):
                            result = await async_func(*args, **kwargs)
                            # Wait a bit for HTTP connections to stabilize
                            await asyncio.sleep(0.1)
                            return result
                        
                        return new_loop.run_until_complete(safe_async_func(*args, **kwargs))
                    finally:
                        # Clean up remaining tasks before closing the loop
                        pending_tasks = asyncio.all_tasks(new_loop)
                        if pending_tasks:
                            for task in pending_tasks:
                                task.cancel()
                            # Wait for tasks to be cancelled
                            new_loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
                        
                        new_loop.close()
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_new_loop)
                    return future.result()
            else:
                return loop.run_until_complete(async_func(*args, **kwargs))
        except RuntimeError:
            # No existing loop, create a new one with proper session management
            async def safe_run(*args, **kwargs):
                result = await async_func(*args, **kwargs)
                # Wait a bit for HTTP connections to stabilize
                await asyncio.sleep(0.1)
                return result
            
            return asyncio.run(safe_run(*args, **kwargs))

    async def _ensure_authenticated(self):
        """Ensure we have valid authentication and device list - Always create fresh session"""
        try:
            # Always clean up old auth to avoid event loop problems
            if self.auth and hasattr(self.auth, 'client_session'):
                if self.auth.client_session and not self.auth.client_session.closed:
                    try:
                        await self.auth.client_session.close()
                    except Exception as e:
                        if tomlogger:
                            tomlogger.warning(f"Error closing old session: {e}", module_name="switchparentalcontrol")
            
            # Always create new authentication to avoid event loop problems
            self.auth = await Authenticator.complete_login(
                auth=None,
                response_token=self.session_token,
                is_session_token=True
            )
            
            self.control = await NintendoParental.create(self.auth)
            
            if self.control.devices:
                # Update cache with devices
                for device_id, device in self.control.devices.items():
                    self.cache['devices'][device_id] = {
                        'name': device.name,
                        'device_id': device.device_id
                    }
                self.cache['last_update'] = datetime.now().isoformat()
                self._save_cache()
                if tomlogger:
                    tomlogger.info(f"Found {len(self.control.devices)} Nintendo Switch devices", module_name="switchparentalcontrol")
            else:
                if tomlogger:
                    tomlogger.warning("No Nintendo Switch devices found", module_name="switchparentalcontrol")
                
        except InvalidSessionTokenException:
            if tomlogger:
                tomlogger.error("Invalid Nintendo session token", module_name="switchparentalcontrol")
            raise ValueError("Invalid Nintendo session token. Please update the token in configuration.")
        except Exception as e:
            error_msg = str(e).lower()
            if "event loop is closed" in error_msg or "connection" in error_msg or "network" in error_msg:
                if tomlogger:
                    tomlogger.warning(f"Nintendo Switch appears to be offline: {e}", module_name="switchparentalcontrol")
                raise ValueError("Nintendo Switch is not connected to the internet. Please connect the device and try again.")
            else:
                if tomlogger:
                    tomlogger.error(f"Failed to authenticate with Nintendo: {e}", module_name="switchparentalcontrol")
                raise

    async def get_daily_usage(self, device_id=None):
        """Get daily usage time for Nintendo Switch devices"""
        await self._ensure_authenticated()
        
        if not self.control.devices:
            return {"error": "No Nintendo Switch devices found"}
        
        usage_data = []
        
        if device_id:
            # Usage for a specific device
            device = self.control.devices.get(device_id)
            if not device:
                return {"error": f"Device with ID {device_id} not found"}
            
            await device.update()
            
            # Calculate total time available today (limit + extra time)
            daily_limit = device.limit_time if device.limit_time is not None else 0
            extra_time = 0
            total_time_available = daily_limit
            
            # Extract extra time if available
            if hasattr(device, 'extra') and device.extra and 'extraPlayingTime' in device.extra:
                extra_playing_time = device.extra.get('extraPlayingTime', {})
                # Handle case where extra_playing_time is None
                if extra_playing_time is None:
                    extra_playing_time = {}
                in_one_day = extra_playing_time.get('inOneDay', {})
                if in_one_day.get('isInfinity', False):
                    extra_time = "unlimited"
                    total_time_available = "unlimited"
                else:
                    extra_time = in_one_day.get('duration', 0)
                    total_time_available = daily_limit + extra_time
            
            # Calculate real remaining time
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
            # Usage for all devices
            for device in self.control.devices.values():
                await device.update()
                
                # Calculate total time available today (limit + extra time)
                daily_limit = device.limit_time if device.limit_time is not None else 0
                extra_time = 0
                total_time_available = daily_limit
                
                # Extract extra time if available
                if hasattr(device, 'extra') and device.extra and 'extraPlayingTime' in device.extra:
                    extra_playing_time = device.extra.get('extraPlayingTime', {})
                    # Handle case where extra_playing_time is None
                    if extra_playing_time is None:
                        extra_playing_time = {}
                    in_one_day = extra_playing_time.get('inOneDay', {})
                    if in_one_day.get('isInfinity', False):
                        extra_time = "unlimited"
                        total_time_available = "unlimited"
                    else:
                        extra_time = in_one_day.get('duration', 0)
                        total_time_available = daily_limit + extra_time
                
                # Calculate real remaining time
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
        """Add extra playing time for a specific device using direct API call
        
        The Nintendo API only supports adding 5, 15, or 30 minutes per call.
        This function handles any requested duration by making multiple API calls as needed.
        """
        try:
            await self._ensure_authenticated()
            
            device = self.control.devices.get(device_id)
            if not device:
                return {"error": f"Device with ID {device_id} not found"}
            
            await device.update()
            current_limit = device.limit_time
            current_playing_time = device.today_playing_time
            
            # Calculate how to break down the requested minutes into valid API calls
            total_minutes_to_add = minutes
            api_calls_made = []
            total_added = 0
            
            # Handle special cases
            if minutes < 5:
                # If less than 5 minutes requested, add 5 minutes (minimum)
                api_calls_to_make = [(5, "Minimum 5 minutes required by API")]
                total_minutes_to_add = 5
            else:
                # Break down the requested time into valid increments (30, 15, 5)
                api_calls_to_make = []
                remaining_minutes = minutes
                
                # First, use as many 30-minute blocks as possible
                while remaining_minutes >= 30:
                    api_calls_to_make.append((30, "30-minute block"))
                    remaining_minutes -= 30
                
                # Then, use 15-minute blocks
                while remaining_minutes >= 15:
                    api_calls_to_make.append((15, "15-minute block"))
                    remaining_minutes -= 15
                
                # Finally, handle remaining time with 5-minute blocks
                if remaining_minutes > 0:
                    # Round up to nearest 5 minutes
                    blocks_of_5 = (remaining_minutes + 4) // 5  # Round up division
                    for _ in range(blocks_of_5):
                        api_calls_to_make.append((5, "5-minute block"))
            
            # Execute all API calls
            for duration, description in api_calls_to_make:
                try:
                    api_result = await device._api.async_update_extra_playing_time(device_id, duration)
                    
                    api_status = api_result.get('status', 'unknown')
                    api_json = api_result.get('json', {})
                    
                    api_calls_made.append({
                        "duration": duration,
                        "description": description,
                        "status": api_status,
                        "response": api_json
                    })
                    total_added += duration
                    
                    if tomlogger:
                        tomlogger.info(f"Added {duration} minutes to device {device.name} ({description})", module_name="switchparentalcontrol")
                    
                    # Small delay between API calls to avoid rate limiting
                    if len(api_calls_to_make) > 1:
                        await asyncio.sleep(0.5)
                        
                except Exception as call_error:
                    if tomlogger:
                        tomlogger.error(f"Failed to add {duration} minutes: {call_error}", module_name="switchparentalcontrol")
                    api_calls_made.append({
                        "duration": duration,
                        "description": description,
                        "status": "error",
                        "error": str(call_error)
                    })
                    # Continue with remaining calls even if one fails
            
            # Update device info after all API calls
            await device.update()
            new_playing_time = device.today_playing_time
            
            # Determine success based on whether any calls succeeded
            successful_calls = [call for call in api_calls_made if call.get("status") != "error"]
            
            if successful_calls:
                if tomlogger:
                    tomlogger.info(f"Successfully extended play time for device {device.name}. Requested: {minutes} minutes, Actually added: {total_added} minutes via {len(successful_calls)} API calls", module_name="switchparentalcontrol")
                return {
                    "success": True,
                    "device_id": device_id,
                    "device_name": device.name,
                    "current_limit_minutes": current_limit,
                    "previous_playing_time": current_playing_time,
                    "new_playing_time": new_playing_time,
                    "requested_minutes": minutes,
                    "actual_minutes_added": sum(call["duration"] for call in successful_calls if call.get("status") != "error"),
                    "api_calls_made": len(api_calls_made),
                    "successful_calls": len(successful_calls),
                    "api_call_details": api_calls_made
                }
            else:
                if tomlogger:
                    tomlogger.error(f"All API calls failed for device {device.name}", module_name="switchparentalcontrol")
                return {
                    "error": "All API calls failed to extend play time",
                    "api_call_details": api_calls_made
                }
                
        except Exception as e:
            error_msg = str(e).lower()
            if "event loop is closed" in error_msg or "connection" in error_msg or "network" in error_msg:
                if tomlogger:
                    tomlogger.warning(f"Nintendo Switch appears to be offline: {e}", module_name="switchparentalcontrol")
                return {"error": "Nintendo Switch is not connected to the internet. Please connect the device and try again."}
            else:
                if tomlogger:
                    tomlogger.error(f"Error extending play time: {e}", module_name="switchparentalcontrol")
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


# Load configuration and initialize switch parental control service
config = load_config()
switch_service = SwitchParentalControlService(config)


@server.tool()
def get_switch_daily_usage(device_id: Optional[str] = None) -> str:
    """Get the daily usage time for Nintendo Switch devices. Shows how much time has been played today.
    
    Args:
        device_id: Optional device ID to get usage for a specific device. If not provided, returns usage for all devices.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: get_switch_daily_usage with device_id={device_id}", module_name="switchparentalcontrol")
    
    try:
        result = switch_service._async_wrapper(switch_service.get_daily_usage, device_id=device_id)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        if tomlogger:
            tomlogger.error(f"get_switch_daily_usage failed: {type(e).__name__}: {e}", module_name="switchparentalcontrol")
        return json.dumps({"error": f"Failed to get daily usage: {str(e)}"}, ensure_ascii=False)


@server.tool()
def extend_switch_playtime(device_id: str, minutes: int) -> str:
    """Add extra playing time to a Nintendo Switch device for today. This does NOT modify the daily limit but adds bonus time on top of it.
    
    Args:
        device_id: Device ID to add extra time for
        minutes: Number of minutes to add as extra playing time (positive number, minimum 1, maximum 480)
    """
    if tomlogger:
        tomlogger.info(f"Tool call: extend_switch_playtime with device_id={device_id}, minutes={minutes}", module_name="switchparentalcontrol")
    
    # Validate parameters
    if not isinstance(minutes, int) or minutes < 1 or minutes > 480:
        error_msg = "Minutes must be an integer between 1 and 480"
        if tomlogger:
            tomlogger.error(f"extend_switch_playtime parameter error: {error_msg}", module_name="switchparentalcontrol")
        return json.dumps({"error": error_msg}, ensure_ascii=False)
    
    try:
        result = switch_service._async_wrapper(switch_service.extend_playtime, device_id=device_id, minutes=minutes)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        if tomlogger:
            tomlogger.error(f"extend_switch_playtime failed: {type(e).__name__}: {e}", module_name="switchparentalcontrol")
        return json.dumps({"error": f"Failed to extend play time: {str(e)}"}, ensure_ascii=False)


@server.tool()
def list_switch_devices() -> str:
    """List all Nintendo Switch devices associated with the account.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: list_switch_devices", module_name="switchparentalcontrol")
    
    try:
        result = switch_service._async_wrapper(switch_service.list_devices)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        if tomlogger:
            tomlogger.error(f"list_switch_devices failed: {type(e).__name__}: {e}", module_name="switchparentalcontrol")
        return json.dumps({"error": f"Failed to list devices: {str(e)}"}, ensure_ascii=False)


@server.resource("description://switchparentalcontrol")
def description() -> str:
    """Return the server description."""
    return SERVER_DESCRIPTION


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting Nintendo Switch Parental Control MCP Server on port 80", module_name="switchparentalcontrol")
    else:
        print("Starting Nintendo Switch Parental Control MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()