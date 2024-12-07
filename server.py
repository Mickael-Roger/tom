# Core
import cherrypy
import uuid
import yaml
import os
import json
import time
from datetime import datetime, timedelta


# CalDav Calendar and TODO
import caldav
from icalendar import Todo, Calendar as iCalendar
import pytz
from caldav.elements import dav

# Anki
import requests

# OpenAI
from openai import OpenAI

# Mistral
from mistralai import Mistral
import functools


################################################################################################
#                                                                                              #
#                          JarMick configuration management                                    #
#                                                                                              #
################################################################################################
config = {}

def initConf():
  # Load config
  with open('config.yml', 'r') as file:
    try:
      conf = yaml.safe_load(file)
    except yaml.YAMLError as exc:
      print(f"Error reading YAML file: {exc}")
      exit(1)

  return conf


################################################################################################
#                                                                                              #
#                                           Anki                                               #
#                                                                                              #
################################################################################################
class Anki:

  def __init__(self) -> None:
    self.url = config['anki']['url']

    self.decknames = None
    self.decks = None
    self.deckvalues = None

    self.update()

    self.tools = [
      {
        "type": "function",
        "description": "Get the status of the Anki flashcards in all decks.",
        "function": {
            "name": "anki_status",
            "parameters": {
            },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "anki_add",
          "description": "Add a a flashcard in an Anki deck. Call this when you have to create or add a card in an Anki deck. For example when a user aks 'Add this card to my deck X', 'Create this flashcard to my deck X', 'Add this to anki deck'",
          "parameters": {
            "type": "object",
            "properties": {
              "front": {
                "type": "string",
                "description": f"Front of the card, it's like the title of the card to add to. It could be a question a name or a sentence.",
              },
              "priority": {
                "type": "string",
                "description": f"Back of the card. It's like the response or the information I must know related to the front of the card.",
              },
              "deck": {
                "type": "string",
                "enum": self.decknames,
                "description": f"Name of the Anki deck to add the flashcard to",
              },
            },
            "required": ["front", "back", "deck"],
            "additionalProperties": False,
          },
        }
      },
    ]

    self.systemContext = "Anki is a flashcard program. It uses cards. It uses technics from cognitive science such as active recall testing and spaced repetition to help me in my memorization. I use Anki to train myself on memorizing and reinforcing my knowledge."


  def ankiCall(self, call):

    # Make the POST request
    response = requests.post(self.url, headers={'Content-Type': 'application/json'}, data=json.dumps(call))

    # Check if the request was successful
    if response.status_code == 200:
        # Convert the JSON response to a dictionary
        response_dict = response.json()
        return True, response_dict['result']
    else:
        return False, f"Error: {response.status_code}"

  def update(self):
    self.ankiCall({"action": "sync", "version": 6})
    result, self.decknames = self.ankiCall({"action": "deckNames", "version": 6})
    result, self.decks = self.ankiCall({"action": "getDeckStats", "params": {"decks": self.decknames}, "version": 6})
    self.deckvalues = []
    for deck in self.decks:
      self.deckvalues.append(self.decks[deck])


  # List Anki decks
  def status(self):
    self.update()
    print(self.decknames)
    return True, self.deckvalues

  def add(self, deck, front, back):
    self.ankiCall({"action": "sync", "version": 6})
    action = {"action": "addNote", "version": 6, "params": { "note": {"deckName": deck, "modelName": "Basic", "fields": {"Front": front, "Back": back}}}}
    self.update()
    return self.ankiCall(action)




################################################################################################
#                                                                                              #
#                                       CalDAV TODO                                            #
#                                                                                              #
################################################################################################
class NextCloudTodo:

  def __init__(self, tz=None) -> None:
  
    self.client = caldav.DAVClient(
      url = config['nextcloud']['todo']['url'],
      username = config['nextcloud']['todo']['user'],
      password = config['nextcloud']['todo']['password'],
    )

    self.date_format = "%Y-%m-%d %H:%M:%S"

    if tz != None:
      self.tz = pytz.timezone(tz)
    else:
      self.tz = pytz.timezone('Europe/Paris')

    self.todoLists = []

    principal = self.client.principal()
    self.calendars = principal.calendars()

    self.todoLists = []

    self.defaultTodoList = None

    self.listNames = []

    self.inventory = None
    self.inventoryJson = None

    self.updateData()



    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "todo_listAll",
          "description": "List all tasks in a todo list or in any list like groceries list. Call this whenever you need to know if there is something to do or to buy. For example when a user aks 'What are my grocery list', 'What do I have in my shopping list', 'What is on my to-do list?', 'What do I have to do?'. ",
          "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "todo_createTask",
          "description": "Create a task in a todo list or in any list like groceries list. Call this when you have to add something in a list. For example when a user aks 'Add this to my grocery list', 'Add this to my shopping list', 'Add this in my to-do list', 'Add this task to my X list'",
          "parameters": {
            "type": "object",
            "properties": {
              "summary": {
                "type": "string",
                "description": f"The title of the task or entry name to add in a list. For example, it could be like a name of product to buy to add in the grocery list or a string that define a task to do",
              },
              "priority": {
                "type": "integer",
                "description": f"Integer from 1 to 9. 1 is the highest priority level. Must only be defined when the user gives you enough information to define the task priority",
              },
              "due": {
                "type": "string",
                "description": f"Due date for a task. Must be in the form 'YYYY-MM-DD hh:mm:ss'. Must only be defined when the user gives you enough information to define the due date. If no information is provided about the year, consider it's the current year. If no information is provided about the hour, minutes nor seconds, set it to 0. So for example, user request like 'with a deadline on next monday' must give the next monday from today at 00:00:00 because no information about hour has been provided to you. Date format for this field is '%Y-%m-%d %H:%M:%S'",
              },
              "todo": {
                "type": "string",
                "enum": self.listNames,
                "description": f"Must only be defined when the user gives you enough information to define the appropriate list",
              },
            },
            "required": ["summary"],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "todo_closeTask",
          "description": f"Close a task in a todo list or in any list like groceries list. Call this when you have to remove, close or mark something in a list done. For example when a user aks 'Remove this to my grocery list', 'Remove this to my shopping list', 'Close this in my to-do list', 'Delete this task from my X list'. \n Tasks for each list are: {self.inventoryJson}",
          "parameters": {
            "type": "object",
            "properties": {
              "id": {
                "type": "string",
                "description": f"The id of the task or entry name to remove or close in a list.",
              },
              "todo": {
                "type": "string",
                "enum": self.listNames,
                "description": f"The list name the task to be closed belongs to",
              },
            },
            "required": ["id", "todo"],
            "additionalProperties": False,
          },
        }
      }


    ]

    self.systemContext = "Unless the user explicitly asks for it, if the user is asking for a list content, do not return any other information except the name of the tasks (no priority or due date). Tasks must be ordered by due date and if multiple tasks have no due date or same due date, they must be ordered by priority level (the lower the priority value is, the higher the priority level is). The due value correspond the the deadline for closing a task. If a task still exists and has a due date in the past, it means it is an overdue task. Tasks without any due value cannot be overdue."


  def updateData(self):

    for calendar in self.calendars:
      if calendar.get_properties() is not None:
        if '{urn:ietf:params:xml:ns:caldav}calendar-timezone' not in calendar.get_properties().keys():
          self.todoLists.append(calendar)

    self.defaultTodoList = self.todoLists[0]

    self.listNames = []
    for name in self.todoLists:
      self.listNames.append(name.get_properties([dav.DisplayName()])['{DAV:}displayname'])

    # Inventory dict
    self.inventory = {"list": []}
    for todo in self.todoLists:
      res, tasks = self.listTasks(todolist=todo.get_properties([dav.DisplayName()])['{DAV:}displayname'])
      self.inventory['list'].append({"name": todo.get_properties([dav.DisplayName()])['{DAV:}displayname'], "tasks": tasks})

    self.inventoryJson = json.dumps(self.inventory)
      







  def findListByName(self, name):
    for todoList in self.todoLists:
      if todoList.get_properties([dav.DisplayName()])['{DAV:}displayname'] == name:
        return todoList

    return None



  def listAll(self):
    self.updateData()

    return True, self.inventoryJson




  # List event in one or many calendar(s) for a certain period of time
  def listTasks(self, todolist=None):

    if todolist == None:
      todolist = self.defaultTodoList
    else:
      todolist = self.findListByName(todolist)
      if todolist == None:
        return False, f"Could not find todo list: {todolist}"

    tasks = []

    for task in todolist.todos():
      due = task.icalendar_instance.subcomponents[0].get("due")
      if due != None:
        due = task.icalendar_instance.subcomponents[0].get("due").dt.strftime("%Y-%m-%d %H:%M:%S")

      tasks.append({"name": str(task.icalendar_instance.subcomponents[0].get("summary")), "due": due, "priority": task.icalendar_instance.subcomponents[0].get("priority"), "id": str(task.icalendar_instance.subcomponents[0].get("uid"))})

    return True, tasks


  def closeTask(self, id, todo=None):

    if todo == None:
      todolist = self.defaultTodoList
    else:
      todolist = self.findListByName(name=todo)
      if todolist == None:
        return False, f"Could not find TODO List {todo}"


    task = todolist.todo_by_uid(id)
    if not task:
        return False, (f"Task with ID '{id}' not found.")

    vtodo = task.instance.vtodo
    taskName = vtodo.contents.get('summary', ['No summary'])[0].value
    vtodo.add('status').value = 'COMPLETED'

    task.save()

    self.updateData()

    print(f"Task '{taskName}' has been closed.")
    return True, f"Task '{taskName}' has been closed."


  def updateTask(self, id, values, todolist=None):

    self.updateData()

    return "todo"

  def createTask(self, summary, priority=None, due=None, todo=None):


    if todo == None:
      todolist = self.defaultTodoList
    else:
      todolist = self.findListByName(name=todo)
      if todolist == None:
        return False, f"Could not find TODO List {todo}"

    # Create a new VTODO component
    task = Todo()
    task.add('summary', summary)
    if priority is not None:
      task.add('priority', priority)
    if due is not None:
      task.add('due', datetime.strptime(due, self.date_format),)

    # Add the VTODO component to the calendar
    cal = iCalendar()
    cal.add_component(task)
    todolist.save_event(cal.to_ical().decode('utf-8'))

    self.updateData()

    return True, f"Task '{summary}' has been created."






################################################################################################
#                                                                                              #
#                                    CalDAV Calendar                                           #
#                                                                                              #
################################################################################################
class NextCloudCalendar:

  def __init__(self, tz=None) -> None:
  
    self.client = caldav.DAVClient(
      url = config['nextcloud']['calendar']['url'],
      username = config['nextcloud']['calendar']['user'],
      password = config['nextcloud']['calendar']['password'],
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





################################################################################################
#                                                                                              #
#                                    CherryPy API endpoint                                     #
#                                                                                              #
################################################################################################
class MyWebService:

  def __init__(self):
    self.sessions = {}


  @cherrypy.expose
  @cherrypy.tools.allow(methods=['GET'])
  def index(self):

#    session_id = self.get_session_id()
#    if session_id not in self.sessions:
#      self.sessions[session_id] = {"history": ""}
    
    with open(os.path.join('static', 'index.html'), 'r') as file:
      return file.read()


  @cherrypy.expose
  @cherrypy.tools.allow(methods=['POST'])
  @cherrypy.tools.json_in()
  @cherrypy.tools.json_out()
  def process(self):

#    session_id = self.get_session_id()
#    if session_id not in self.sessions:
#      self.sessions[session_id] = {"history": ""}
#    
    input_json = cherrypy.request.json
    
    user = input_json.get('request')

    response = processRequest(input=user)

    return {"response": response}


#  def get_session_id(self):
#
#    session_id = cherrypy.request.cookie.get('session_id')
#    
#    if session_id.value:
#      session_id = session_id.value
#    else:
#      session_id = str(uuid.uuid4())
#      cherrypy.response.cookie['session_id'] = session_id
#      cherrypy.response.cookie['session_id']['path'] = '/'
#      cherrypy.response.cookie['session_id']['max-age'] = 86400
#    
#    return session_id


def processRequest(input):

  today= datetime.now().strftime("%A %d %B %Y %H:%M:%S")
  systemContext = f"Today is {today}" + "\n" + config['personalContext'] + "\n" + calendar.systemContext + "\n" + todo.systemContext + "\n" + anki.systemContext

  messages = [
    {
      "role": "system",
      "content": systemContext
    },
    {
      "role": "user",
      "content": input,
    }
  ]

  functions = {
    'anki_status': functools.partial(anki.status),
    'anki_add': functools.partial(anki.add),
    'calendar_add': functools.partial(calendar.addEvent),
#    'calendar_remove': functools.partial(calendar.deleteEvents),
    'calendar_search': functools.partial(calendar.search),
    'todo_listAll': functools.partial(todo.listAll),
    'todo_closeTask': functools.partial(todo.closeTask),
    'todo_createTask': functools.partial(todo.createTask),
  }

  model = "mistral-large-latest"
  
  response = mistralClient.chat.complete(
    model = model,
    messages = messages,
    tools = tools,
    tool_choice = "auto",
  )

  messages.append(response.choices[0].message)


  if response is not None:
    if response.choices is not None:

      print(response.choices[0].message)

      tool_call = response.choices[0].message.tool_calls[0]
      function_name = tool_call.function.name
      function_params = json.loads(tool_call.function.arguments)

      print(function_name)
      print(function_params)

      res, function_result = functions[function_name](**function_params)



      messages.append({"role":"tool", "name":function_name, "content": json.dumps(function_result), "tool_call_id":tool_call.id})

      time.sleep(1.5)

      response = mistralClient.chat.complete(
        model = model, 
        messages = messages
      )

      print(response)

      return response.choices[0].message.content



################################################################################################
#                                                                                              #
#                                         Main                                                 #
#                                                                                              #
################################################################################################

config = initConf()
calendar = NextCloudCalendar()
todo = NextCloudTodo()
anki = Anki()

tools = calendar.tools + todo.tools + anki.tools

mistralClient = Mistral(api_key=config["mistral"]["api"])

if __name__ == "__main__":    

  cherrypy.config.update({'server.socket_host': '0.0.0.0', 'server.socket_port': 8444})
  cherrypy.quickstart(MyWebService(), '/', config={
      '/static': {
          'tools.staticdir.on': True,
          'tools.staticdir.dir': os.path.abspath('static')
      }
  })

