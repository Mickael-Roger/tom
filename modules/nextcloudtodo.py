# CalDav Calendar and TODO
import caldav
from icalendar import Todo, Calendar as iCalendar
import pytz
from caldav.elements import dav

import json
from datetime import datetime, timedelta

################################################################################################
#                                                                                              #
#                                       CalDAV TODO                                            #
#                                                                                              #
################################################################################################
class NextCloudTodo:

  def __init__(self, config, tz=None) -> None:
  
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



