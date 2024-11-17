import caldav
from datetime import datetime

import json


class JarMick():

  def __init__(self, config, callLLM) -> None:
  
    self.client = caldav.DAVClient(
      url = config['nextcloud']['todo']['url'],
      username = config['nextcloud']['todo']['user'],
      password = config['nextcloud']['todo']['password'],
    )

    self.conf = config
    self.callLLM = callLLM

    principal = self.client.principal()
    self.calendars = principal.calendars()

    self.triage = {
      "name": "todo",
      "description": "",
      "consigne": 'If the request is about a task todo, todo list or any related items that could be related to a todo list, "service" firls must be set to "todo".'
    }

  
  def listTasks(self, start, end):
  
    evts = []

    date_format = "%Y-%m-%d %H:%M:%S"
  
    for calendar in self.calendars:
      events = calendar.search(
        start = datetime.strptime(start, date_format),
        end = datetime.strptime(end, date_format),
        event=True,
        expand=True,
      )
      for event in events:
        for component in event.icalendar_instance.walk():
          if component.name != "VEVENT":
            continue
          myevent= {"title": component.get("summary"),
            "start": component.get("dtstart").dt.strftime("%d/%m/%Y %H:%M"),
            "end": component.get("dtend").dt.strftime("%d/%m/%Y %H:%M")}
          evts.append(myevent) 
  
    return json.dumps(evts)
                  
  def addTask(self, title, todolist, due):
    
    date_format = "%Y-%m-%d %H:%M:%S"

    self.calendars[0].save_event(
        dtstart = datetime.strptime(start, date_format),
        dtend = datetime.strptime(end, date_format),
        summary = title,
        description = description,
    )

    return {"response": f"I just added an event in your calendar named {title}, that is planned from {start} to {end}"} 

  def searchTask(self, user):

    today= datetime.now().strftime("%A %d %B %Y %H:%M:%S")

    # First we need to define the Searching range
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
    response = self.callLLM("mistral-medium-latest", systemPrompt, user, self.conf)

    # Then search for Events in that range
    events = self.listTask(response['start'], response['end'])
    systemPrompt = f"""
      {self.conf['personalContext']}
      The user prompt is a about information that is containt in its calendar.
      Today is {today}.
      A week starts on monday and ends on sunday.
      You must only return a json that only contains one field called 'response' and that contains your answer to the user prompt
      The following lines are a json version of the content of the calendar. It contains a list of event. Each event is composed of different fields: "title", "description", "start" and "end"
      The "title" field is the title of the event
      The "description" field could contain a description of the event
      The "start" field contains the starting date of the event
      The "end" field contains the ending date of the event
      ```json
      {events}
      ```
    """
    response = self.callLLM("mistral-large-latest", systemPrompt, user, self.conf)

    return response

  def add(self, user):

    today= datetime.now().strftime("%A %d %B %Y %H:%M:%S")

    systemPrompt = f"""
      {self.conf['personalContext']}
      The user prompt is a about information that must be added in its todo list.
      Today is {today}.
      A week starts on monday and ends on sunday.
      You must only return a json that only contains for fields: "title", "list", "due"
      The "title" field is the title of the event. The "title" field is mandatory.
      The "list" field could contain the name of the todo list (like courses, famille, ...). The "list" field can be empty if the user does not provide enough information
      The "due" field contains the due date of the task in the form "YYYY-mm-dd hh:mm:ss". If the user does not provide any information about the due date time set the time to "00:00:00". The due date field can also be empty if the user does not provide any information about it.
    """
    response = self.callLLM("mistral-large-latest", systemPrompt, user, self.conf)

    result = self.addTask(response['title'], response['list'], response['due'])

    return result

  def closeTask(self, user):
    return

  def updateTask(self, user):
    return

  def request(self, user):

    systemPrompt = f"""
      The user prompt is a about information that is containt in its todo list.
      You must answer a json that contain only one value: "action". 
      According to the user prompt, you must set the "action" value to one of the appropriate values: "search", "add", "update", "close"
      - The "search" value is used for any user request that request information about a task in its todo list
      - The "add" value is used for any user request that request the creation of a new task in its todo list
      - The "update" value is used for any user request that request the update of an existing task in its todo list
      - The "close" value is used for any user request that request to mark at completed a certain task in its todo list
    """
   
    #response = self.callLLM("mistral-small-latest", systemPrompt, user, self.conf)

    #match response['action']:
    #  case 'search':
    #    result = self.search(user)
    #  case 'add':
    #    result = self.add(user)
    #  case 'update':
    #    result = self.update(user)
    #  case 'close':
    #    result = self.close(user)
    #  case _:
    #    # TODO: Try to use a biger model to determine the Calendar triage, otherwise we don't understand for real
    #    result = {"response": f"Sorry, I could not understand you Calendar request"} 

    #return result
    return "OK"


