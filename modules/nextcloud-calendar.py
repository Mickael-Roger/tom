import caldav
from datetime import datetime
import pytz

import json

from requests.api import delete


class JarMick():

  def __init__(self, config, callLLM) -> None:
  
    self.client = caldav.DAVClient(
      url = config['nextcloud']['calendar']['url'],
      username = config['nextcloud']['calendar']['user'],
      password = config['nextcloud']['calendar']['password'],
    )

    self.conf = config
    self.callLLM = callLLM

    principal = self.client.principal()
    self.calendars = principal.calendars()

    self.triage = {
      "name": "calendar",
      "description": "",
      "consigne": 'If the request is about a past or futur appointment, a date of an event, a meeting, a question about seeing someone or doing something or any information you could normally find in a calendar the "service" field is set to "calendar".'
    }

  
  def listEvent(self, start, end):
  
    evts = []

    date_format = "%Y-%m-%d %H:%M:%S"
  
    local_tz = pytz.timezone('Europe/Paris')

    for calendar in self.calendars:
      events = calendar.search(
        start = local_tz.localize(datetime.strptime(start, date_format)),
        end = local_tz.localize(datetime.strptime(end, date_format)),
        event=True,
        expand=True,
      )
      for event in events:
        for component in event.icalendar_instance.walk():
          if component.name != "VEVENT":
            continue
          myevent= {"id": component.get("uid"),
            "title": component.get("summary"),
            "description": component.get("description"),
            "start": component.get("dtstart").dt.strftime("%d/%m/%Y %H:%M"),
            "end": component.get("dtend").dt.strftime("%d/%m/%Y %H:%M")}
          evts.append(myevent) 
  
    return json.dumps(evts)

  def deleteFromCalendar(self, response):
    
    #self.calendars[0].delete_event(
    #    dtstart = datetime.strptime(start, date_format),
    #    dtend = datetime.strptime(end, date_format),
    #    summary = title,
    #    description = description,
    #)
 
    
    # Find the event by its ID
    events = self.calendars[0].events()
    event = None

    deleteTitles = []


    if len(response) > 2:
      return {"response": f"For protection reason, I cannot delete more than 2 event"} 

    if len(response) == 0:
      return {"response": f"No event is corresponding to your request"} 

    for elem in response:
      for calendar in self.calendars:
        events = calendar.events()
        for e in events:
          for component in e.icalendar_instance.walk():
            if component.name != "VEVENT":
              continue

            if component.get("uid") == elem['id']:
              event = e
              break

      if event is None:
          raise ValueError(f"Event with ID '{elem['id']}' not found.")

      # Delete the event
      event.delete()
      deleteTitles.append(str(elem['start']) + " " + str(elem['title']))

    return {"response": f"I've just deleted these events from your calendar: " + str(deleteTitles)} 

                 
  def addToCalendar(self, title, description, start, end):
    
    date_format = "%Y-%m-%d %H:%M:%S"

    local_tz = pytz.timezone('Europe/Paris')

    self.calendars[0].save_event(
        dtstart = local_tz.localize(datetime.strptime(start, date_format)),
        dtend = local_tz.localize(datetime.strptime(end, date_format)),
        summary = title,
        description = description,
    )

    return {"response": f"I just added an event in your calendar named {title}, that is planned from {start} to {end}"} 

  def searchEvent(self, user):

    today= datetime.now().strftime("%A %d %B %Y %H:%M:%S")

    # First we need to define the Searching range
    systemPrompt = f"""
      The user prompt is a about information that is containt in its calendar.
      Today is {today}.
      A week starts on monday and ends on sunday.
      You must answer a json that contains two values: "start" and "end". 
      The json "start" values and "end" values must correspond to the starting and ending date that must be used to answer the user request.
      If you have no information that you can use to define the period of search, the default period of search will be one year.
      If you do not have any information about the starting date and or ending date, you can use the tense of the user request to guess the starting and ending date. A request about something in the past could not have starting and ending date after {today}. A request about a coming or futur event cannot have a starting date before {today}
      If the request is about information from the past, the "end" value is {today}.
      Returned date must be in the form: 'YYYY-MM-DD HH:MM:SS'
    """
    response = self.callLLM("mistral-medium-latest", systemPrompt, user, self.conf)

    # Then search for Events in that range
    events = self.listEvent(response['start'], response['end'])
    systemPrompt = f"""
      {self.conf['personalContext']}
      The user prompt is a about information that is containt in its calendar.
      Today is {today}.
      A week starts on monday and ends on sunday.
      You must only return a json that only contains one field called 'response' and that contains your answer to the user prompt
      The following lines are a json version of the content of the calendar. It contains a list of event. Each event is composed of different fields: "id", "title", "description", "start" and "end"
      The "id" field is the id of the event
      The "title" field is the title of the event
      The "description" field could contain a description of the event
      The "start" field contains the starting date of the event
      The "end" field contains the ending date of the event
      Your user response must also indicate the exact title of the event
      ```json
      {events}
      ```
    """
    response = self.callLLM("mistral-large-latest", systemPrompt, user, self.conf)

    return response

  def addEvent(self, user):

    today= datetime.now().strftime("%A %d %B %Y %H:%M:%S")

    systemPrompt = f"""
      {self.conf['personalContext']}
      The user prompt is a about information that must be added in its calendar.
      Today is {today}.
      A week starts on monday and ends on sunday.
      You must only return a json that only contains for fields: "title", "description", "start" and "end"
      The "title" field is the title of the event. The "title" field is mandatory.
      The "description" field could contain a description of the event. The "description" field can be empty if the user does not provide enough information
      The "start" field contains the starting date of the event in the form "YYYY-mm-dd hh:mm:ss". If the user does not provide any information about the starting time set the time to "00:00:00". The start field is mandatory.
      The "end" field contains the ending date of the eventin the form "YYYY-mm-dd hh:mm:ss". If the user does not provide any information about the duration of the event or the end of the event. Consider it's a one hour event. The end field is mandatory.
      If you are able to determine the name of the one who has the appointment, you must indicate this name in the title of the event
    """
    response = self.callLLM("mistral-large-latest", systemPrompt, user, self.conf)

    result = self.addToCalendar(response['title'], response['description'], response['start'], response['end'])

    return result

  def deleteEvent(self, user):

    today= datetime.now().strftime("%A %d %B %Y %H:%M:%S")

    # First we need to define the Searching range
    systemPrompt = f"""
      The user prompt is a about information that that must be removed from its calendar.
      Today is {today}.
      A week starts on monday and ends on sunday.
      You must answer a json that contains two values: "start" and "end". 
      The json "start" values and "end" values must correspond to the starting and ending date that must be used to answer the user request.
      If you have no information that you can use to define the period of search, the default period of search will be one year.
      If you do not have any information about the starting date and or ending date, you can use the tense of the user request to guess the starting and ending date. A request about something in the past could not have starting and ending date after {today}. A request about a coming or futur event cannot have a starting date before {today}
      If the request is about information from the past, the "end" value is {today}.
      Returned date must be in the form: 'YYYY-MM-DD HH:MM:SS'
    """
    response = self.callLLM("mistral-medium-latest", systemPrompt, user, self.conf)

    # Then search for Events in that range
    events = self.listEvent(response['start'], response['end'])
    systemPrompt = f"""
      {self.conf['personalContext']}
      The user prompt is a about information that must be removed from its calendar.
      Today is {today}.
      A week starts on monday and ends on sunday.
      You must only return a json that only contains a list of object that must be removed from the user calendar. Each of these object is composed of three fields called 'id', 'title' and 'start' that contains the event id to remove, its title and it's starting date. You must determine the event(s) ID(s) to remove accoding to the user prompt. If no event correspond to the user prompt, the returned json is an empty array.
      The following lines are a json version of the content of the calendar. It contains a list of event. Each event is composed of different fields: "id", "title", "description", "start" and "end"
      The "id" field is the id of the event
      The "title" field is the title of the event. The "title" field is mandatory.
      The "description" field could contain a description of the event. The "description" field can be empty if the user does not provide enough information
      The "start" field contains the starting date of the event in the form "YYYY-mm-dd hh:mm:ss". If the user does not provide any information about the starting time set the time to "00:00:00". The start field is mandatory.
      The "end" field contains the ending date of the event. If the user does not provide any information about the duration of the event or the end of the event. Consider it's a one hour event. The end field is mandatory.
      ```json
      {events}
      ```
    """
    response = self.callLLM("mistral-large-latest", systemPrompt, user, self.conf)

    result = self.deleteFromCalendar(response)

    return result

  def updateEvent(self, user):
    return

  def request(self, user):
  # First triage this calendar request: Search for an event or an information about an event; Create an event; Update an event; Delete an event
    systemPrompt = f"""
      The user prompt is a about information that is containt in its calendar.
      You must answer a json that contain only one value: "action". 
      According to the user prompt, you must set the "action" value to one of the appropriate values: "search", "add", "update", "delete"
      - The "search" value is used for any user request that request information about an event in the calendar
      - The "add" value is used for any user request that request the creation of a new event in the calendar
      - The "update" value is used for any user request that request the update of an existing event in the calendar
      - The "delete" value is used for any user request that request the deletion of an existing event in the calendar
    """
   
    response = self.callLLM("mistral-small-latest", systemPrompt, user, self.conf)

    match response['action']:
      case 'search':
        result = self.searchEvent(user)
      case 'add':
        result = self.addEvent(user)
      case 'update':
        result = self.updateEvent(user)
      case 'delete':
        result = self.deleteEvent(user)
      case _:
        # TODO: Try to use a biger model to determine the Calendar triage, otherwise we don't understand for real
        result = {"response": f"Sorry, I could not understand you Calendar request"} 

    return result


