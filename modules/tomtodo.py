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
#                                       CalDAV TODO                                            #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "todo",
  "class_name": "TomTodo",
  "description": "This module is used for managing TODO list."
}

class TomTodo:

  def __init__(self, config, tz=None) -> None:
  
    self.client = caldav.DAVClient(
      url = config['url'],
      username = config['user'],
      password = config['password'],
    )

    self.date_format = "%Y-%m-%d %H:%M:%S"

    if tz != None:
      self.tz = pytz.timezone(tz)
    else:
      self.tz = pytz.timezone('Europe/Paris')

    principal = self.client.principal()
    self.calendars = principal.calendars()

    for calendar in self.calendars:
      if calendar.get_properties() is not None:
        if '{urn:ietf:params:xml:ns:caldav}calendar-timezone' not in calendar.get_properties().keys():
          if calendar.get_properties([dav.DisplayName()])['{DAV:}displayname'] == config['list']:
            self.todoCal = calendar

    self.tasks = []

    self.update()



    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "todo_list_all",
          "description": "List all tasks in the todo list. For example when a user aks 'What is on my to-do list?', 'What do I have to do?'. ",
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
          "name": "todo_create_task",
          "description": "Create a task in a todo list. For example when a user aks 'Add this in my to-do list', 'Add this task to my X list'.",
          "parameters": {
            "type": "object",
            "properties": {
              "task_name": {
                "type": "string",
                "description": f"The title of the task or entry name to add in in the todo list.",
              },
              "priority": {
                "type": "integer",
                "description": f"Integer from 1 to 9. 1 is the highest priority level. Must only be defined when the user gives you enough information to define the task priority",
              },
              "due": {
                "type": "string",
                "description": f"Due date for a task. Must be in the form 'YYYY-MM-DD hh:mm:ss'. Must only be defined when the user gives you enough information to define the due date. If no information is provided about the year, consider it's the current year. If no information is provided about the hour, minutes nor seconds, set it to 0. So for example, user request like 'with a deadline on next monday' must give the next monday from today at 00:00:00 because no information about hour has been provided to you. Date format for this field is '%Y-%m-%d %H:%M:%S'",
              },
            },
            "required": ["task_name"],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "todo_close_task",
          "description": f"Close a task in the todo list. Call this when you have to remove, close or mark something in the todo list done. For example when a user aks 'Close this in my to-do list', 'Delete this task from my X list'. You must have the task ID that can be got using the todo_list_all function.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "id": {
                "type": "string",
                "description": f"The id of the task or entry name to remove or close in a list. Cannot be null",
              },
            },
            "required": ["id"],
            "additionalProperties": False,
          },
        }
      }


    ]

    self.systemContext = ""
    self.complexity = 0
    self.functions = {
      "todo_list_all": {
        "function": functools.partial(self.listTasks), 
        "responseContext": """Unless the user explicitly asks for it, name of the tasks (no priority or due date). Tasks must be ordered by due date and if multiple tasks have no due date or same due date, they must be ordered by priority level (the lower the priority value is, the higher the priority level is). The due value correspond the the deadline for closing a task. If a task still exists and has a due date in the past, it means it is an overdue task. Tasks without any due value cannot be overdue. 
       For example, your answer should be like "You have 4 tasks: create a new app, do the groceries, paint the wall and mow the lawn" or if the user asks for overdue tasks, your answer should be like "You have 2 overdue tasks: 'mow the lawn' that is 2 day late and 'paint the wall' that is 1 week late" """
      },
      "todo_create_task": {
        "function": functools.partial(self.create), 
        "responseContext": """Your answer must be consise like 'Task "mow the lawn" added'""" 
      },
      "todo_close_task": {
        "function": functools.partial(self.close), 
        "responseContext": """Your answer must be consise like 'Task "mow the lawn" closed'""" 
      },
    }



  def update(self):

    self.tasks = []

    for task in self.todoCal.todos():
      due = task.icalendar_component.get('due')
      if due != None:
        due = due.dt.strftime("%Y-%m-%d %H:%M:%S")

      self.tasks.append({"name": str(task.icalendar_component.get('summary')), "due": due, "priority": task.icalendar_component.get('priority'), "id": str(task.icalendar_component.get('uid'))})

     

  def listTasks(self):
    self.update()
    return self.tasks


  def close(self, id):

    task = self.todoCal.todo_by_uid(id)
    if not task:
        return False

    vtodo = task.instance.vtodo
    taskName = vtodo.contents.get('summary', ['No summary'])[0].value
    vtodo.add('status').value = 'COMPLETED'

    task.save()

    self.update()

    print(f"Task '{taskName}' has been closed.")

    return {"status": "success", "message": "Todo task removed"}



  def create(self, task_name, priority=None, due=None):

    # Create a new VTODO component
    task = Todo()
    task.add('summary', task_name)
    if priority is not None:
      task.add('priority', priority)
    if due is not None:
      task.add('due', datetime.strptime(due, self.date_format),)

    # Add the VTODO component to the calendar
    cal = iCalendar()
    cal.add_component(task)
    self.todoCal.save_event(cal.to_ical().decode('utf-8'))

    self.update()

    return {"status": "success", "message": "Todo task added"}



