# CalDav Calendar and TODO
import caldav
from icalendar import Todo, Calendar as iCalendar
import pytz
from caldav.elements import dav
import json
from datetime import datetime, timedelta
import functools



################################################################################################
#                                                                                              #
#                                    CalDAV Calendar                                           #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "calendar",
  "class_name": "TomCalendar",
  "description": "This module is used to manage my personal and familial calendar events, meetings and appointments."
}

class TomCalendar:

  def __init__(self, config, llm, tz=None) -> None:
  
    self.client = caldav.DAVClient(
      url = config['url'],
      username = config['user'],
      password = config['password'],
    )

    if tz != None:
      self.tz = pytz.timezone(tz)
    else:
      self.tz = pytz.timezone('Europe/Paris')

    principal = self.client.principal()
    self.calendars = principal.calendars()
    self.defaultCalendar = self.calendars[0]
    for calendar in self.calendars:
      if calendar.get_properties() is not None:
        if '{urn:ietf:params:xml:ns:caldav}calendar-timezone' in calendar.get_properties().keys():
          if calendar.get_properties([dav.DisplayName()])['{DAV:}displayname'] == config['calendar_name']:
            self.defaultCalendar = calendar

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
#      {
#        "type": "function",
#        "function": {
#          "name": "calendar_remove",
#          "description": f"Remove or delete an appointment, meeting or event in my calendar. For example when a user aks 'Delete from my calendar', 'Remove this appoitment', 'Remove this meeting', 'Delete my appointment'. Calendar content is: {self.calendarsContent}",
#          "parameters": {
#            "type": "object",
#            "properties": {
#              "ids": {
#                "type": "string",
#                "description": f"List of the events id that must be removed from my calendar",
#              },
#            },
#            "required": ["ids"],
#            "additionalProperties": False,
#          },
#        }
#      },
    ]

    self.systemContext = ""
    self.complexity = 0

    self.functions = {
      "calendar_search": {
        "function": functools.partial(self.search), 
        "responseContext": """When a user ask for a appointment, an event or any information from it's calendar, you must give him information about the weekday, the date and the hour of the event an the title of the event
       For example, if the user asks "What appointments do I have tommorrow?", your answer must be like "Tommorrow, saturday december the 2nd, you have 2 appointments: 'Doctor' at 9am and 'Meeting with John at 4pm'". If the user asks "What appointments do I have next week?" your answer should be like "Next week, you will have 3 appointments: 'Doctor' on monday morning, 'Meeting with John' on monday afternoon and 'Playing chess' on wednesday afternoon"
      """ 
      },
      "calendar_add": {
        "function": functools.partial(self.addEvent), 
        "responseContext": """Your answer must be consise like 'Appointment 'Doctor' on monday december the 15th added to your calendar""" 
      },
    }

    


  def update(self):
    current_year = datetime.now().year
    start = datetime(current_year - 1, 1, 1).strftime('%Y-%m-%d %H:%M:%S')
    end = datetime(current_year + 1, 12, 31).strftime('%Y-%m-%d %H:%M:%S')

    self.calendarsContent = []
    for cal in self.calendars:
      vals = self.listEvent(start=start, end=end, calendar=cal)
      for val in vals:
        self.calendarsContent.append(val)



  def search(self, period_from, period_to):
    self.update()

    events = []

    search_from = datetime.strptime(period_from, '%Y-%m-%d').replace(hour=0, minute=0, second=0)
    search_to = datetime.strptime(period_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)

    for evt in self.calendarsContent:
      if datetime.strptime(evt['start'], '%Y-%m-%d %H:%M:%S') >= search_from and datetime.strptime(evt['start'], '%Y-%m-%d %H:%M:%S') <= search_to:
        events.append(evt)

    calendarsContentJson = json.dumps(events)
    
    return calendarsContentJson
    



  # List event in one or many calendar(s) for a certain period of time
  def listEvent(self, start="1900-01-01 00:00:00", end="2040-01-01 00:00:00", calendar=None):

    if calendar == None:
      calendar = self.defaultCalendar
  
    evts = []

    date_format = "%Y-%m-%d %H:%M:%S"

    events = calendar.search(
      start = self.tz.localize(datetime.strptime(start, date_format)),
      end = self.tz.localize(datetime.strptime(end, date_format)),
      event=True,
      expand=True,
    )


    for event in events:
      for component in event.icalendar_instance.walk():

        if component.name != "VEVENT":
          continue

        valarms = []

        alarms = [subcomp for subcomp in component.subcomponents if subcomp.name == "VALARM"]
        if alarms:
          for alarm in alarms:
            alarmdate = component.get("dtstart").dt + alarm.get('trigger').dt
            valarms.append(alarmdate.strftime("%Y-%m-%d %H:%M:%S"))

        calevent = {"id": component.get("uid"),
          "title": component.get("summary"),
          "description": component.get("description"),
          "start": component.get("dtstart").dt.strftime("%Y-%m-%d %H:%M:%S"),
          "end": component.get("dtend").dt.strftime("%Y-%m-%d %H:%M:%S"),
          "alarms": valarms}

        evts.append(calevent) 
  
    return evts


  def deleteEvents(self, ids=[], calendar=None):
    
    if calendar == None:
      calendar = self.defaultCalendar
  
    # Find the event by its ID
    events = calendar.events()
    event = None

    deleteTitles = []


    if len(ids) > 2:
      return False

    if len(ids) == 0:
      return "No event is corresponding to your request" 

    for elem in ids:
      events = calendar.events()
      for e in events:
        for component in e.icalendar_instance.walk():
          if component.name != "VEVENT":
            continue

          if component.get("uid") == elem:
            event = e
            deleteTitles.append(str(component.get("dtstart").dt.strftime("%Y-%m-%d %H:%M:%S")) + " " + str(component.get("summary")))
            break

      if event is None:
          return False

      # Delete the event
      event.delete()
      

      self.update()

      print("Delete event: " + str(deleteTitles))

    return {"status": "success", "message": "Event deleted"}


                 
  def addEvent(self, title, start, end, description=None, calendar=None):
    
    if calendar == None:
      calendar = self.defaultCalendar
  
    date_format = "%Y-%m-%d %H:%M"

    calendar.save_event(
        dtstart = self.tz.localize(datetime.strptime(start, date_format)),
        dtend = self.tz.localize(datetime.strptime(end, date_format)),
        summary = title,
        description = description,
        # TODO: Add Alarms
    )

    self.update()

    return {"status": "success", "message": "Event added"}



