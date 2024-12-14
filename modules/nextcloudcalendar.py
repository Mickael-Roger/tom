# CalDav Calendar and TODO
import caldav
from icalendar import Todo, Calendar as iCalendar
import pytz
from caldav.elements import dav
import json
from datetime import datetime, timedelta



################################################################################################
#                                                                                              #
#                                    CalDAV Calendar                                           #
#                                                                                              #
################################################################################################
class NextCloudCalendar:

  def __init__(self, config, tz=None) -> None:
  
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

    self.calendarsContent = []

    self.update()

    self.systemContext = "When a user ask for a appointment, an event or any information from it's calendar, you must give him information about the weekday, the date and the hour of the event an the title of the event"
    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "calendar_search",
          "description": f"Search for events, appointments or meeting in calendars. For example when a user aks 'Do I have an appointment?', 'When is my next', 'When was my last', 'What is planned for'. This function does not add, remove or update any event in the calendar.",
          "parameters": {
            "type": "object",
            "properties": {
              "period": {
                "type": "string",
                "enum": ["futur", "past"],
                "description": f"Determine if the searched event is in the past or the futur. The tense used in the user input must be used to determine this. Questions like 'When will be my next', 'When will I see' or 'Do I have' are in the futur. Questions like 'When was' or 'Do I had' are in the past",
              },
            },
            "required": [],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "calendar_add",
          "description": "Add an appointment, meeting or event in my calendar. For example when a user aks 'Add this to my calendar', 'Add this appoitment', 'Add this meeting', 'create this appoitnment'",
          "parameters": {
            "type": "object",
            "properties": {
              "title": {
                "type": "string",
                "description": f"The title of the event, appointment or meeting to add to the calendar",
              },
              "start": {
                "type": "string",
                "description": f"Start date and time of the event. Must be in the form of '%Y-%m-%d %H:%M:%S'. If no information is provided about the day of the event, must be set to today. If no information is provided about the hour of the event, time must be set to 9am.",
              },
              "end": {
                "type": "string",
                "description": f"End date and time of the event. Must be in the form of '%Y-%m-%d %H:%M:%S'. By default and if no information is provided, event, appoitnment or meeting are 1h of duration. If no information is provided about the end of the event, the end value must be set to the start value plus one hour",
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


  def update(self):
    current_year = datetime.now().year
    start = datetime(current_year - 1, 1, 1).strftime('%Y-%m-%d %H:%M:%S')
    end = datetime(current_year + 1, 12, 31).strftime('%Y-%m-%d %H:%M:%S')

    self.calendarsContent = []
    for cal in self.calendars:
      ret, vals = self.listEvent(start=start, end=end, calendar=cal)
      for val in vals:
        self.calendarsContent.append(val)



  def search(self, period=None):
    self.update()

    events = []

    for evt in self.calendarsContent:
      if period == "futur":
        if datetime.strptime(evt['start'], '%Y-%m-%d %H:%M:%S') > datetime.now():
          events.append(evt)
      elif period == "past":
        if datetime.strptime(evt['start'], '%Y-%m-%d %H:%M:%S') < datetime.now():
          events.append(evt)
      else:
        events.append(evt)

    calendarsContentJson = json.dumps(events)
    
    return True, calendarsContentJson
    



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
  
    return True, evts

  def deleteEvents(self, ids=[], calendar=None):
    
    if calendar == None:
      calendar = self.defaultCalendar
  
    # Find the event by its ID
    events = calendar.events()
    event = None

    deleteTitles = []


    if len(ids) > 2:
      return False, "For protection reason, I cannot delete more than 2 event"

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
          return False, f"Event with ID '{elem}' not found."

      # Delete the event
      event.delete()
      
      print("Delete event: " + str(deleteTitles))

      self.update()

    return True, str(deleteTitles) 

                 
  def addEvent(self, title, start, end, description=None, calendar=None):
    
    if calendar == None:
      calendar = self.defaultCalendar
  
    date_format = "%Y-%m-%d %H:%M:%S"

    calendar.save_event(
        dtstart = self.tz.localize(datetime.strptime(start, date_format)),
        dtend = self.tz.localize(datetime.strptime(end, date_format)),
        summary = title,
        description = description,
        # TODO: Add Alarms
    )

    self.update()

    return True, f"I just added an event in your calendar named {title}, that is planned from {start} to {end}" 



