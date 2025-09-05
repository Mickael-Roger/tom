#!/usr/bin/env python3
"""
Calendar MCP Server
Provides calendar management functionality via MCP protocol
Based on the original tomcalendar.py module
"""

import json
import os
import sys
import yaml
import functools
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List

import caldav
import pytz
from caldav.elements import dav
from icalendar import Todo, Calendar as iCalendar
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

# Initialize logging
log_level = os.environ.get('TOM_LOG_LEVEL', 'INFO')
if tomlogger:
    logger = init_logger(log_level)
    tomlogger.info(f"🚀 Calendar MCP Server starting with log level: {log_level}", module_name="calendar")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "This module is used to manage my personal and familial calendar events, meetings and appointments."

# Initialize FastMCP server
server = FastMCP(name="calendar-server", stateless_http=True, host="0.0.0.0", port=80)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file using TOM_USER environment variable"""
    tom_user = os.environ.get('TOM_USER', 'unknown')
    config_path = f'/data/{tom_user}/config.yml'
    
    if tomlogger:
        tomlogger.info(f"Loading configuration for user '{tom_user}' from {config_path}", module_name="calendar")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        if tomlogger:
            tomlogger.error(f"Configuration file not found: {config_path}", module_name="calendar")
        else:
            print(f"ERROR: Configuration file not found: {config_path}")
        return {}
    except yaml.YAMLError as exc:
        if tomlogger:
            tomlogger.error(f"Error parsing YAML configuration: {exc}", module_name="calendar")
        else:
            print(f"ERROR: Error parsing YAML configuration: {exc}")
        return {}


class CalendarService:
    """Calendar service class based on original TomCalendar"""
    
    def __init__(self, config: Dict[str, Any]):
        # Load calendar configuration from config
        calendar_config = config.get('calendar', {})
        
        # Validate required config fields
        required_fields = ['url', 'user', 'password', 'calendar_name']
        for field in required_fields:
            if field not in calendar_config:
                raise KeyError(f"Missing required calendar config field: {field}")
        
        self.config = calendar_config
        self.client = caldav.DAVClient(
            url=calendar_config['url'],
            username=calendar_config['user'],
            password=calendar_config['password'],
        )
        
        # Set timezone
        timezone = calendar_config.get('timezone', 'Europe/Paris')
        self.tz = pytz.timezone(timezone)
        
        try:
            principal = self.client.principal()
            self.calendars = principal.calendars()
            
            # Safely set default calendar
            self.defaultCalendar = None
            if self.calendars:
                self.defaultCalendar = self.calendars[0]  # Set first calendar as default
                
                # Look for configured calendar
                configured_calendar_name = calendar_config['calendar_name']
                for calendar in self.calendars:
                    try:
                        if calendar.get_properties() is not None:
                            calendar_name = calendar.get_properties([dav.DisplayName()])['{DAV:}displayname']
                            if calendar_name == configured_calendar_name:
                                self.defaultCalendar = calendar
                                break
                    except Exception as e:
                        if tomlogger:
                            tomlogger.error(f"Error getting calendar properties: {str(e)}", module_name="calendar")
                        continue
            
            if not self.defaultCalendar:
                raise Exception("No calendars found or accessible")
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error initializing calendar: {str(e)}", module_name="calendar")
            raise
        
        self.calendarsContent = []
        self.update()
        
        if tomlogger:
            tomlogger.info(f"✅ Calendar service initialized successfully", module_name="calendar")
    
    def update(self):
        """Update calendar content cache"""
        try:
            current_year = datetime.now().year
            start = datetime(current_year - 1, 1, 1).strftime('%Y-%m-%d %H:%M:%S')
            end = datetime(current_year + 1, 12, 31).strftime('%Y-%m-%d %H:%M:%S')

            self.calendarsContent = []
            for cal in self.calendars:
                try:
                    vals = self.listEvent(start=start, end=end, calendar=cal)
                    for val in vals:
                        self.calendarsContent.append(val)
                except Exception as e:
                    if tomlogger:
                        tomlogger.error(f"Error updating calendar content for calendar: {str(e)}", module_name="calendar")
                    continue
                    
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error during calendar update: {str(e)}", module_name="calendar")
            self.calendarsContent = []
    
    def search(self, period_from: str, period_to: str) -> str:
        """Search for events in a specific period"""
        try:
            self.update()

            events = []

            # Validate date format
            try:
                search_from = datetime.strptime(period_from, '%Y-%m-%d').replace(hour=0, minute=0, second=0)
                search_to = datetime.strptime(period_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            except ValueError as e:
                if tomlogger:
                    tomlogger.error(f"Invalid date format in search: {str(e)}", module_name="calendar")
                return json.dumps({"error": f"Invalid date format: {str(e)}"})

            for evt in self.calendarsContent:
                try:
                    evt_start = datetime.strptime(evt['start'], '%Y-%m-%d %H:%M:%S')
                    if search_from <= evt_start <= search_to:
                        events.append(evt)
                except (ValueError, KeyError) as e:
                    if tomlogger:
                        tomlogger.error(f"Error processing event in search: {str(e)}", module_name="calendar")
                    continue

            if tomlogger:
                tomlogger.info(f"Found {len(events)} events between {period_from} and {period_to}", module_name="calendar")
            return json.dumps(events, ensure_ascii=False)
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error during calendar search: {str(e)}", module_name="calendar")
            return json.dumps({"error": f"Search failed: {str(e)}"})
    
    def listEvent(self, start="1900-01-01 00:00:00", end="2040-01-01 00:00:00", calendar=None):
        """List events in one or many calendar(s) for a certain period of time"""
        if calendar is None:
            calendar = self.defaultCalendar
        
        if not calendar:
            if tomlogger:
                tomlogger.error("No calendar available for listing events", module_name="calendar")
            return []
      
        evts = []

        try:
            date_format = "%Y-%m-%d %H:%M:%S"

            # Validate and parse dates
            try:
                start_dt = self.tz.localize(datetime.strptime(start, date_format))
                end_dt = self.tz.localize(datetime.strptime(end, date_format))
            except ValueError as e:
                if tomlogger:
                    tomlogger.error(f"Invalid date format in listEvent: {str(e)}", module_name="calendar")
                return []

            events = calendar.search(
                start=start_dt,
                end=end_dt,
                event=True,
                expand=True,
            )

            for event in events:
                try:
                    for component in event.icalendar_instance.walk():

                        if component.name != "VEVENT":
                            continue

                        valarms = []

                        try:
                            alarms = [subcomp for subcomp in component.subcomponents if subcomp.name == "VALARM"]
                            if alarms:
                                for alarm in alarms:
                                    try:
                                        alarmdate = component.get("dtstart").dt + alarm.get('trigger').dt
                                        valarms.append(alarmdate.strftime("%Y-%m-%d %H:%M:%S"))
                                    except Exception as e:
                                        if tomlogger:
                                            tomlogger.error(f"Error processing alarm: {str(e)}", module_name="calendar")
                                        continue
                        except Exception as e:
                            if tomlogger:
                                tomlogger.error(f"Error processing alarms: {str(e)}", module_name="calendar")

                        # Safely extract event data
                        try:
                            event_id = str(component.get("uid", ""))
                            title = str(component.get("summary", "No title"))
                            description = str(component.get("description", ""))
                            
                            dtstart = component.get("dtstart")
                            dtend = component.get("dtend")
                            
                            if dtstart and dtend:
                                start_str = dtstart.dt.strftime("%Y-%m-%d %H:%M:%S")
                                end_str = dtend.dt.strftime("%Y-%m-%d %H:%M:%S")
                                
                                calevent = {
                                    "id": event_id,
                                    "title": title,
                                    "description": description,
                                    "start": start_str,
                                    "end": end_str,
                                    "alarms": valarms
                                }

                                evts.append(calevent)
                            else:
                                if tomlogger:
                                    tomlogger.error(f"Event missing start or end time: {event_id}", module_name="calendar")
                                
                        except Exception as e:
                            if tomlogger:
                                tomlogger.error(f"Error processing event component: {str(e)}", module_name="calendar")
                            continue
                            
                except Exception as e:
                    if tomlogger:
                        tomlogger.error(f"Error processing event: {str(e)}", module_name="calendar")
                    continue
      
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error listing events: {str(e)}", module_name="calendar")
            return []
        
        return evts
    
    def addEvent(self, title: str, start: str, end: str, description: Optional[str] = None, calendar=None) -> Dict[str, Any]:
        """Add a new event to the calendar"""
        if calendar is None:
            calendar = self.defaultCalendar
        
        if not calendar:
            if tomlogger:
                tomlogger.error("No calendar available for adding events", module_name="calendar")
            return {"status": "error", "message": "No calendar available"}
        
        try:
            # Try multiple date formats
            date_formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]

            # Validate and parse dates
            start_dt = None
            end_dt = None
            
            for date_format in date_formats:
                try:
                    start_dt = self.tz.localize(datetime.strptime(start, date_format))
                    end_dt = self.tz.localize(datetime.strptime(end, date_format))
                    break
                except ValueError:
                    continue
            
            if start_dt is None or end_dt is None:
                if tomlogger:
                    tomlogger.error(f"Invalid date format in addEvent. Expected formats: {date_formats}", module_name="calendar")
                return {"status": "error", "message": f"Invalid date format. Expected formats: {', '.join(date_formats)}"}
            
            # Validate that end is after start
            if end_dt <= start_dt:
                if tomlogger:
                    tomlogger.error(f"End time must be after start time", module_name="calendar")
                return {"status": "error", "message": "End time must be after start time"}

            calendar.save_event(
                dtstart=start_dt,
                dtend=end_dt,
                summary=title,
                description=description,
            )

            self.update()
            
            if tomlogger:
                tomlogger.info(f"Event '{title}' added from {start} to {end}", module_name="calendar")
            return {"status": "success", "message": "Event added"}
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error adding event '{title}': {str(e)}", module_name="calendar")
            return {"status": "error", "message": f"Failed to add event: {str(e)}"}
    
    def deleteEvent(self, event_id: str, calendar=None) -> Dict[str, Any]:
        """Delete an event from the calendar"""
        if calendar is None:
            calendar = self.defaultCalendar
        
        if not calendar:
            if tomlogger:
                tomlogger.error("No calendar available for deleting events", module_name="calendar")
            return {"status": "error", "message": "No calendar available"}
        
        try:
            # Search for the event first to verify it exists
            events = calendar.search(
                start=datetime(2020, 1, 1),
                end=datetime(2040, 12, 31),
                event=True,
                expand=True,
            )
            
            event_to_delete = None
            for event in events:
                try:
                    for component in event.icalendar_instance.walk():
                        if component.name == "VEVENT":
                            if str(component.get("uid", "")) == event_id:
                                event_to_delete = event
                                break
                    if event_to_delete:
                        break
                except Exception as e:
                    if tomlogger:
                        tomlogger.error(f"Error processing event during search: {str(e)}", module_name="calendar")
                    continue
            
            if not event_to_delete:
                if tomlogger:
                    tomlogger.error(f"Event with ID {event_id} not found", module_name="calendar")
                return {"status": "error", "message": "Event not found"}
            
            # Delete the event
            event_to_delete.delete()
            
            self.update()
            
            if tomlogger:
                tomlogger.info(f"Event with ID {event_id} deleted successfully", module_name="calendar")
            return {"status": "success", "message": "Event deleted"}
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error deleting event {event_id}: {str(e)}", module_name="calendar")
            return {"status": "error", "message": f"Failed to delete event: {str(e)}"}
    
    def updateEvent(self, event_id: str, title: Optional[str] = None, start: Optional[str] = None, 
                   end: Optional[str] = None, description: Optional[str] = None, calendar=None) -> Dict[str, Any]:
        """Update an existing event in the calendar"""
        if calendar is None:
            calendar = self.defaultCalendar
        
        if not calendar:
            if tomlogger:
                tomlogger.error("No calendar available for updating events", module_name="calendar")
            return {"status": "error", "message": "No calendar available"}
        
        try:
            # Search for the event first
            events = calendar.search(
                start=datetime(2020, 1, 1),
                end=datetime(2040, 12, 31),
                event=True,
                expand=True,
            )
            
            event_to_update = None
            event_component = None
            for event in events:
                try:
                    for component in event.icalendar_instance.walk():
                        if component.name == "VEVENT":
                            if str(component.get("uid", "")) == event_id:
                                event_to_update = event
                                event_component = component
                                break
                    if event_to_update:
                        break
                except Exception as e:
                    if tomlogger:
                        tomlogger.error(f"Error processing event during search: {str(e)}", module_name="calendar")
                    continue
            
            if not event_to_update or not event_component:
                if tomlogger:
                    tomlogger.error(f"Event with ID {event_id} not found", module_name="calendar")
                return {"status": "error", "message": "Event not found"}
            
            # Validate and parse new dates if provided
            new_start_dt = None
            new_end_dt = None
            date_formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]
            
            if start:
                for date_format in date_formats:
                    try:
                        new_start_dt = self.tz.localize(datetime.strptime(start, date_format))
                        break
                    except ValueError:
                        continue
                
                if new_start_dt is None:
                    if tomlogger:
                        tomlogger.error(f"Invalid start date format in updateEvent. Expected formats: {date_formats}", module_name="calendar")
                    return {"status": "error", "message": f"Invalid start date format. Expected formats: {', '.join(date_formats)}"}
            
            if end:
                for date_format in date_formats:
                    try:
                        new_end_dt = self.tz.localize(datetime.strptime(end, date_format))
                        break
                    except ValueError:
                        continue
                
                if new_end_dt is None:
                    if tomlogger:
                        tomlogger.error(f"Invalid end date format in updateEvent. Expected formats: {date_formats}", module_name="calendar")
                    return {"status": "error", "message": f"Invalid end date format. Expected formats: {', '.join(date_formats)}"}
            
            # If both start and end are provided, validate that end is after start
            if new_start_dt and new_end_dt and new_end_dt <= new_start_dt:
                if tomlogger:
                    tomlogger.error(f"End time must be after start time", module_name="calendar")
                return {"status": "error", "message": "End time must be after start time"}
            
            # If only one of start/end is provided, get the other from existing event
            if new_start_dt and not new_end_dt:
                current_end = event_component.get("dtend")
                if current_end:
                    new_end_dt = current_end.dt
                    if new_end_dt <= new_start_dt:
                        if tomlogger:
                            tomlogger.error(f"New start time conflicts with existing end time", module_name="calendar")
                        return {"status": "error", "message": "New start time must be before existing end time"}
            
            if new_end_dt and not new_start_dt:
                current_start = event_component.get("dtstart")
                if current_start:
                    new_start_dt = current_start.dt
                    if new_end_dt <= new_start_dt:
                        if tomlogger:
                            tomlogger.error(f"New end time conflicts with existing start time", module_name="calendar")
                        return {"status": "error", "message": "New end time must be after existing start time"}
            
            # Get current values for fields not being updated
            current_title = str(event_component.get("summary", ""))
            current_description = str(event_component.get("description", ""))
            current_start = event_component.get("dtstart")
            current_end = event_component.get("dtend")
            
            # Use provided values or fallback to current values
            final_title = title if title is not None else current_title
            final_description = description if description is not None else current_description
            final_start_dt = new_start_dt if new_start_dt else (current_start.dt if current_start else None)
            final_end_dt = new_end_dt if new_end_dt else (current_end.dt if current_end else None)
            
            # Delete the old event
            event_to_update.delete()
            
            # Create a new event with updated properties
            calendar.save_event(
                dtstart=final_start_dt,
                dtend=final_end_dt,
                summary=final_title,
                description=final_description,
            )
            
            self.update()
            
            changes = []
            if title is not None:
                changes.append(f"title to '{title}'")
            if start:
                changes.append(f"start time to {start}")
            if end:
                changes.append(f"end time to {end}")
            if description is not None:
                changes.append("description")
            
            changes_str = ", ".join(changes) if changes else "no changes"
            if tomlogger:
                tomlogger.info(f"Event {event_id} updated: {changes_str}", module_name="calendar")
            return {"status": "success", "message": "Event updated"}
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error updating event {event_id}: {str(e)}", module_name="calendar")
            return {"status": "error", "message": f"Failed to update event: {str(e)}"}


# Load configuration and initialize calendar service
config = load_config()
calendar_service = CalendarService(config)


@server.tool()
def calendar_search_event(period_from: str, period_to: str) -> str:
    """Search for events, appointments or meeting in calendars. For example when a user asks 'Do I have an appointment?', 'When is my next', 'When was my last', 'What is planned for'. This function does not add, remove or update any event in the calendar.
    
    Args:
        period_from: Must be in the form of '%Y-%m-%d'. Define the starting date to search for. Oldest starting date is '2020-01-01' and could be used when the user request are about events in the past with no more precision about the period like 'When was my last medical appointment?'.
        period_to: Must be in the form of '%Y-%m-%d'. Define the ending date to search for. Maximum ending date is today plus 5 years and could be used when the user request are about events in the future no more precision about the period like 'When will be my next medical appointment?'.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: calendar_search_event with period_from={period_from}, period_to={period_to}", module_name="calendar")
    
    result = calendar_service.search(period_from, period_to)
    return result


@server.tool()
def calendar_add_event(title: str, start: str, end: str, description: Optional[str] = None) -> str:
    """Add an appointment, meeting or event in my calendar. For example when a user asks 'Add this to my calendar', 'Add this appointment', 'Add this meeting', 'create this appointment'
    
    Args:
        title: The title of the event, appointment or meeting to add to the calendar
        start: Start date and time of the event. Must be in the form of '%Y-%m-%d %H:%M' or '%Y-%m-%d %H:%M:%S'. If no information is provided about the day of the event, must be set to today. If no information is provided about the hour of the event, you must ask the user for it.
        end: End date and time of the event. Must be in the form of '%Y-%m-%d %H:%M' or '%Y-%m-%d %H:%M:%S'. By default and if no information is provided, event, appointment or meeting are 1h of duration.
        description: Optional description of the event
    """
    if tomlogger:
        tomlogger.info(f"Tool call: calendar_add_event with title={title}, start={start}, end={end}", module_name="calendar")
    
    result = calendar_service.addEvent(title, start, end, description)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def calendar_delete_event(event_id: str) -> str:
    """Delete an event, appointment or meeting from my calendar. For example when a user asks 'Delete this appointment', 'Remove this meeting', 'Cancel this event'
    
    Args:
        event_id: The unique identifier of the event to delete. This should be obtained from a calendar search first.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: calendar_delete_event with event_id={event_id}", module_name="calendar")
    
    result = calendar_service.deleteEvent(event_id)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def calendar_update_event(event_id: str, title: Optional[str] = None, start: Optional[str] = None, 
                         end: Optional[str] = None, description: Optional[str] = None) -> str:
    """Update an existing event, appointment or meeting in my calendar. For example when a user asks 'Change this appointment time', 'Update this meeting', 'Modify this event'
    
    Args:
        event_id: The unique identifier of the event to update. This should be obtained from a calendar search first.
        title: The new title of the event, appointment or meeting. If not provided, the current title will be kept.
        start: New start date and time of the event. Must be in the form of '%Y-%m-%d %H:%M' or '%Y-%m-%d %H:%M:%S'. If not provided, the current start time will be kept.
        end: New end date and time of the event. Must be in the form of '%Y-%m-%d %H:%M' or '%Y-%m-%d %H:%M:%S'. If not provided, the current end time will be kept.
        description: New description of the event. If not provided, the current description will be kept.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: calendar_update_event with event_id={event_id}", module_name="calendar")
    
    result = calendar_service.updateEvent(event_id, title, start, end, description)
    return json.dumps(result, ensure_ascii=False)


@server.resource("description://calendar")
def description() -> str:
    """Return the server description."""
    return SERVER_DESCRIPTION


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting Calendar MCP Server on port 80", module_name="calendar")
    else:
        print("Starting Calendar MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()