import caldav
from datetime import datetime

import json


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
      "consigne": 'If the request is about an appointment, a date of an event or any information you could normally find in a calendar the "service" field is set to "calendar".'
    }

  
  def listEvent(self, start, end):
  
    evts = []
  
    for calendar in self.calendars:
      events = calendar.search(
        start = start,
        end = end,
        event=True,
        expand=True,
      )
      for event in events:
        for component in event.icalendar_instance.walk():
          if component.name != "VEVENT":
            continue
          myevent= {"summary": component.get("summary"),
            "description": component.get("description"),
            "start": component.get("dtstart").dt.strftime("%d/%m/%Y %H:%M"),
            "end": component.get("dtend").dt.strftime("%d/%m/%Y %H:%M")}
          evts.append(myevent) 
  
    return json.dumps(evts)
                  

  def searchEvent(self, user):

    today= datetime.now().strftime("%A %d %B %Y %H:%M:%S")
#"mistral-large-latest"
    systemPrompt = f"""
      The user prompt is a about information that is containt in its calendar.
      Today is {today}.
      A week starts on monday and ends on sunday.
      You must answer a json that contains three values: "action" "start" and "end". 
      The json "start" values and "end" values must correspond to the starting and ending date that must be used to answer the user request.
      If you have no information that you can use to define the period of search, the default period of search will be one year.
      If the request is about information from the past, the "end" value is today.
      Returned date must be in the form: YYYY-MM-DD HH:MM:SS
    """

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

    print(response)


