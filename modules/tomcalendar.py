# CalDav Calendar and TODO
import caldav
from icalendar import Todo, Calendar as iCalendar
import pytz
from caldav.elements import dav
import json
from datetime import datetime, timedelta
import functools
import os
import sys

# Logging
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
try:
    from tomlogger import logger
except ImportError:
    # Fallback logger for testing
    import logging
    logger = logging.getLogger('tomcalendar')

# Ensure logger is not None (can happen in tests)
if logger is None:
    import logging
    logger = logging.getLogger('tomcalendar')
    logger.setLevel(logging.INFO)

# Create a wrapper function to handle both tomlogger and standard logger
def log_message(level, message, module_name=None):
    """Wrapper function to handle both tomlogger and standard logger"""
    global logger
    try:
        # First check if logger is a mock (for unit tests)
        if hasattr(logger, '_mock_name'):
            # This is a mock object, use it directly
            getattr(logger, level)(message, module_name=module_name)
        elif hasattr(logger, 'info') and hasattr(logger.info, '__code__') and 'module_name' in logger.info.__code__.co_varnames:
            # tomlogger supports module_name parameter
            getattr(logger, level)(message, module_name=module_name)
        else:
            # Standard logger doesn't support module_name
            if module_name:
                message = f"[{module_name}] {message}"
            getattr(logger, level)(message)
    except (AttributeError, TypeError):
        # Fallback to basic logging
        if module_name:
            message = f"[{module_name}] {message}"
        getattr(logger, level)(message)



################################################################################################
#                                                                                              #
#                                    CalDAV Calendar                                           #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "calendar",
  "class_name": "TomCalendar",
  "description": "This module is used to manage my personal and familial calendar events, meetings and appointments.",
  "type": "personal",
  "complexity": 0
}

class TomCalendar:

  def __init__(self, config, llm, tz=None) -> None:
  
    # Validate required config fields
    required_fields = ['url', 'user', 'password', 'calendar_name']
    for field in required_fields:
        if field not in config:
            raise KeyError(f"Missing required config field: {field}")
  
    self.client = caldav.DAVClient(
      url = config['url'],
      username = config['user'],
      password = config['password'],
    )

    if tz != None:
      self.tz = pytz.timezone(tz)
    else:
      self.tz = pytz.timezone('Europe/Paris')

    try:
        principal = self.client.principal()
        self.calendars = principal.calendars()
        
        # Safely set default calendar
        self.defaultCalendar = None
        if self.calendars:
            self.defaultCalendar = self.calendars[0]  # Set first calendar as default
            
            # Look for configured calendar
            configured_calendar_name = config['calendar_name']
            for calendar in self.calendars:
                try:
                    if calendar.get_properties() is not None:
                        calendar_name = calendar.get_properties([dav.DisplayName()])['{DAV:}displayname']
                        if calendar_name == configured_calendar_name:
                            self.defaultCalendar = calendar
                            break
                except Exception as e:
                    log_message('error', f"Error getting calendar properties: {str(e)}", module_name="calendar")
                    continue
        
        if not self.defaultCalendar:
            raise Exception("No calendars found or accessible")
            
    except Exception as e:
        log_message('error', f"Error initializing calendar: {str(e)}", module_name="calendar")
        raise


    self.calendarsContent = []

    self.update()

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "calendar_search",
          "description": f"Search for events, appointments or meeting in calendars. For example when a user aks 'Do I have an appointment?', 'When is my next', 'When was my last', 'What is planned for'. This function does not add, remove or update any event in the calendar.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "period_from": {
                "type": "string",
                "description": f"Must be in the form of '%Y-%m-%d'. Define the starting date to search for. Oldest starting date is '2020-01-01' and could be used when the user request are about events in the past with no more precision about the period like 'When was my last medical appointment?'.",
              },
              "period_to": {
                "type": "string",
                "description": f"Must be in the form of '%Y-%m-%d'. Define the ending date to search for. Maximum ending date is today plus 5 years and could be used when the user request are about events in the futur no more precision about the period like 'When will be my next medial appointment?'.",
              },
            },
            "required": ["period_from", "period_to"],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "calendar_add",
          "description": "Add an appointment, meeting or event in my calendar. For example when a user aks 'Add this to my calendar', 'Add this appoitment', 'Add this meeting', 'create this appoitnment'",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "title": {
                "type": "string",
                "description": f"The title of the event, appointment or meeting to add to the calendar",
              },
              "start": {
                "type": "string",
                "description": f"Start date and time of the event. Must be in the form of '%Y-%m-%d %H:%M'. If no information is provided about the day of the event, must be set to today. If no information is provided about the hour of the event, you must ask the user for it.",
              },
              "end": {
                "type": "string",
                "description": f"End date and time of the event. Must be in the form of '%Y-%m-%d %H:%M'. By default and if no information is provided, event, appointment or meeting are 1h of duration.",
              },
            },
            "required": ["title", "start", "end"],
            "additionalProperties": False,
          },
        }
      },
    ]

    self.systemContext = ""
    self.complexity = tom_config.get("complexity", 0)

    self.functions = {
      "calendar_search": {
        "function": functools.partial(self.search)
      },
      "calendar_add": {
        "function": functools.partial(self.addEvent)
      },
    }


  def update(self):
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
                log_message('error', f"Error updating calendar content for calendar: {str(e)}", module_name="calendar")
                continue
                
    except Exception as e:
        log_message('error', f"Error during calendar update: {str(e)}", module_name="calendar")
        self.calendarsContent = []



  def search(self, period_from, period_to):
    try:
        self.update()

        events = []

        # Validate date format
        try:
            search_from = datetime.strptime(period_from, '%Y-%m-%d').replace(hour=0, minute=0, second=0)
            search_to = datetime.strptime(period_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError as e:
            log_message('error', f"Invalid date format in search: {str(e)}", module_name="calendar")
            return json.dumps([])

        for evt in self.calendarsContent:
            try:
                evt_start = datetime.strptime(evt['start'], '%Y-%m-%d %H:%M:%S')
                if search_from <= evt_start <= search_to:
                    events.append(evt)
            except (ValueError, KeyError) as e:
                log_message('error', f"Error processing event in search: {str(e)}", module_name="calendar")
                continue

        calendarsContentJson = json.dumps(events)
        
        log_message('info', f"Found {len(events)} events between {period_from} and {period_to}", module_name="calendar")
        return calendarsContentJson
        
    except Exception as e:
        log_message('error', f"Error during calendar search: {str(e)}", module_name="calendar")
        return json.dumps([])
    



  # List event in one or many calendar(s) for a certain period of time
  def listEvent(self, start="1900-01-01 00:00:00", end="2040-01-01 00:00:00", calendar=None):

    if calendar is None:
        calendar = self.defaultCalendar
    
    if not calendar:
        log_message('error', "No calendar available for listing events", module_name="calendar")
        return []
  
    evts = []

    try:
        date_format = "%Y-%m-%d %H:%M:%S"

        # Validate and parse dates
        try:
            start_dt = self.tz.localize(datetime.strptime(start, date_format))
            end_dt = self.tz.localize(datetime.strptime(end, date_format))
        except ValueError as e:
            log_message('error', f"Invalid date format in listEvent: {str(e)}", module_name="calendar")
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
                                    log_message('error', f"Error processing alarm: {str(e)}", module_name="calendar")
                                    continue
                    except Exception as e:
                        log_message('error', f"Error processing alarms: {str(e)}", module_name="calendar")

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
                            log_message('error', f"Event missing start or end time: {event_id}", module_name="calendar")
                            
                    except Exception as e:
                        log_message('error', f"Error processing event component: {str(e)}", module_name="calendar")
                        continue
                        
            except Exception as e:
                log_message('error', f"Error processing event: {str(e)}", module_name="calendar")
                continue
  
    except Exception as e:
        log_message('error', f"Error listing events: {str(e)}", module_name="calendar")
        return []
    
    return evts



                 
  def addEvent(self, title, start, end, description=None, calendar=None):
    
    if calendar is None:
        calendar = self.defaultCalendar
    
    if not calendar:
        log_message('error', "No calendar available for adding events", module_name="calendar")
        return {"status": "error", "message": "No calendar available"}
    
    try:
        date_format = "%Y-%m-%d %H:%M"

        # Validate and parse dates
        try:
            start_dt = self.tz.localize(datetime.strptime(start, date_format))
            end_dt = self.tz.localize(datetime.strptime(end, date_format))
        except ValueError as e:
            log_message('error', f"Invalid date format in addEvent: {str(e)}", module_name="calendar")
            return {"status": "error", "message": f"Invalid date format: {str(e)}"}
        
        # Validate that end is after start
        if end_dt <= start_dt:
            log_message('error', f"End time must be after start time", module_name="calendar")
            return {"status": "error", "message": "End time must be after start time"}

        calendar.save_event(
            dtstart=start_dt,
            dtend=end_dt,
            summary=title,
            description=description,
            # TODO: Add Alarms
        )

        self.update()
        
        log_message('info', f"Event '{title}' added from {start} to {end}", module_name="calendar")
        return {"status": "success", "message": "Event added"}
        
    except Exception as e:
        log_message('error', f"Error adding event '{title}': {str(e)}", module_name="calendar")
        return {"status": "error", "message": f"Failed to add event: {str(e)}"}

  

