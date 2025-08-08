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
from tomlogger import logger

################################################################################################
#                                                                                              #
#                                       CalDAV TODO                                            #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "todo",
  "class_name": "TomTodo",
  "description": "This module manages various types of task lists including TODO lists, grocery/shopping lists, and custom lists. It provides comprehensive list management capabilities for organizing different types of tasks and items.",
  "type": "personal",
  "complexity": 0,
  "configuration_parameters": {
    "url": {
      "type": "string",
      "description": "CalDAV server URL for accessing the TODO service.",
      "required": True
    },
    "user": {
      "type": "string",
      "description": "Username for CalDAV server authentication.",
      "required": True
    },
    "password": {
      "type": "string",
      "description": "Password for CalDAV server authentication.",
      "required": True
    },
    "todo_list": {
      "type": "string",
      "description": "Name of the default TODO list to use on the CalDAV server.",
      "required": True
    },
    "groceries_list": {
      "type": "string",
      "description": "Name of the default groceries/shopping list to use on the CalDAV server.",
      "required": True
    }
  }
}

class TomTodo:

  def __init__(self, config, llm, tz=None) -> None:
    
    self.date_format = "%Y-%m-%d %H:%M:%S"

    if tz != None:
      self.tz = pytz.timezone(tz)
    else:
      self.tz = pytz.timezone('Europe/Paris')

    self.defaultTodoListName = config['todo_list']
    self.defaultGroceriesListName = config['groceries_list']
    
    self.todoCalendars = {}
    self.todoCal = None

    try:
      self.client = caldav.DAVClient(
        url = config['url'],
        username = config['user'],
        password = config['password'],
      )

      principal = self.client.principal()
      self.calendars = principal.calendars()
      
      for calendar in self.calendars:
        if calendar.get_properties() is not None:
          if '{urn:ietf:params:xml:ns:caldav}calendar-timezone' not in calendar.get_properties().keys():
            display_name = calendar.get_properties([dav.DisplayName()])['{DAV:}displayname']
            self.todoCalendars[display_name] = calendar
            if display_name == self.defaultTodoListName:
              self.todoCal = calendar

      logger.info("CalDAV connection established successfully", module_name="todo")
      
    except Exception as e:
      logger.error(f"Failed to connect to CalDAV server: {str(e)}", module_name="todo")
      # Initialize with empty state so module can still load
      self.client = None
      self.calendars = []
      self.todoCalendars = {}
      self.todoCal = None



    self.tools = self._build_tools()

    self.systemContext = f"""You are managing a comprehensive list management system with these capabilities:

**Available Lists**:
- **TODO List**: "{self.defaultTodoListName}" - For tasks, deadlines, priorities, and general to-do items
- **Groceries List**: "{self.defaultGroceriesListName}" - For shopping items, products to buy, grocery items
- **Custom Lists**: Any other lists the user creates

**Usage Rules**:
1. **For TODO requests** (tasks, deadlines, "add to my to-do list", "what do I need to do"):
   → Use list_name="{self.defaultTodoListName}"
   → Can include priority (1-9) and due dates

2. **For GROCERY requests** (shopping, "add to grocery list", "what do I need to buy", products):
   → Use list_name="{self.defaultGroceriesListName}"
   → No priority or due dates needed

3. **For OTHER lists**: User must specify the list name explicitly

**Available Functions**:
- list_available_lists(): Show all lists
- create_list(list_name): Create new list
- add_to_list(item_name, list_name, [priority], [due]): Add item to any list
- list_items(list_name): Show items in a list
- remove_from_list(id, list_name): Remove/complete an item
- update_item_priority(id, list_name, priority): Update item priority (1=urgent, 5=medium, 9=low)

Always determine the correct list based on user intent - grocery/shopping requests go to "{self.defaultGroceriesListName}", task/todo requests go to "{self.defaultTodoListName}"."""
    self.complexity = tom_config.get("complexity", 0)
    self.functions = {
      "list_available_lists": {
        "function": functools.partial(self.listAvailableLists)
      },
      "create_list": {
        "function": functools.partial(self.createList)
      },
      "add_to_list": {
        "function": functools.partial(self.addToList)
      },
      "list_items": {
        "function": functools.partial(self.listItems)
      },
      "remove_from_list": {
        "function": functools.partial(self.removeFromList)
      },
      "update_item_priority": {
        "function": functools.partial(self.updateItemPriority)
      },
    }




  def _build_tools(self):
    available_lists = list(self.todoCalendars.keys()) if self.todoCalendars else [self.defaultTodoListName, self.defaultGroceriesListName]
    
    return [
      {
        "type": "function",
        "function": {
          "name": "list_available_lists",
          "description": "List all available lists. Use this when user asks about what lists they have.",
          "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "create_list",
          "description": "Create a new list. Use this when user wants to create a new list.",
          "parameters": {
            "type": "object",
            "properties": {
              "list_name": {
                "type": "string",
                "description": "Name of the new list to create.",
              }
            },
            "required": ["list_name"],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "add_to_list",
          "description": "Add an item to a list. Use this for adding tasks, products, or any items to lists.",
          "parameters": {
            "type": "object",
            "properties": {
              "item_name": {
                "type": "string",
                "description": "The name/title of the item to add to the list.",
              },
              "list_name": {
                "type": "string",
                "description": "Name of the list to add the item to. REQUIRED parameter.",
                "enum": available_lists
              },
              "priority": {
                "type": "integer",
                "description": "Priority from 1-9 (1 is highest). Only for TODO tasks, not for grocery items.",
              },
              "due": {
                "type": "string",
                "description": "Due date in 'YYYY-MM-DD HH:MM:SS' format. Only for TODO tasks, not for grocery items.",
              }
            },
            "required": ["item_name", "list_name"],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "list_items",
          "description": "List all items in a specific list. Use this to show contents of any list.",
          "parameters": {
            "type": "object",
            "properties": {
              "list_name": {
                "type": "string",
                "description": "Name of the list to show items from. REQUIRED parameter.",
                "enum": available_lists
              }
            },
            "required": ["list_name"],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "remove_from_list",
          "description": "Remove/close an item from a list. Use this to remove items, mark tasks as done, etc.",
          "parameters": {
            "type": "object",
            "properties": {
              "id": {
                "type": "string",
                "description": "The ID of the item to remove. Get this from list_items function.",
              },
              "list_name": {
                "type": "string",
                "description": "Name of the list containing the item. REQUIRED parameter.",
                "enum": available_lists
              }
            },
            "required": ["id", "list_name"],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "update_item_priority",
          "description": "Update the priority of an item in a list. Use this to change task priority (1-9, where 1 is highest priority).",
          "parameters": {
            "type": "object",
            "properties": {
              "id": {
                "type": "string",
                "description": "The ID of the item to update. Get this from list_items function.",
              },
              "list_name": {
                "type": "string",
                "description": "Name of the list containing the item. REQUIRED parameter.",
                "enum": available_lists
              },
              "priority": {
                "type": "integer",
                "description": "New priority: 1 (highest/urgent), 5 (medium), 9 (lowest).",
              }
            },
            "required": ["id", "list_name", "priority"],
            "additionalProperties": False,
          },
        }
      }
    ]

  def getCalendarByName(self, list_name=None):
    if self.client is None:
      return None
      
    if list_name is None:
      return self.todoCal
    
    if list_name in self.todoCalendars:
      return self.todoCalendars[list_name]
    
    return None

  def listAvailableLists(self):
    if self.client is None:
      return {"status": "error", "message": "CalDAV connection not available"}
    
    # Rafraîchir la liste des calendriers depuis le serveur
    try:
      principal = self.client.principal()
      calendars = principal.calendars()
      
      self.todoCalendars = {}
      for calendar in calendars:
        if calendar.get_properties() is not None:
          if '{urn:ietf:params:xml:ns:caldav}calendar-timezone' not in calendar.get_properties().keys():
            display_name = calendar.get_properties([dav.DisplayName()])['{DAV:}displayname']
            self.todoCalendars[display_name] = calendar
            if display_name == self.defaultTodoListName:
              self.todoCal = calendar
      
      # Mise à jour dynamique des outils avec les listes rafraîchies
      self.tools = self._build_tools()
      
    except Exception as e:
      logger.error(f"Error refreshing calendar list: {str(e)}", module_name="todo")
    
    return {"status": "success", "lists": list(self.todoCalendars.keys())}

  def createList(self, list_name):
    if self.client is None:
      return {"status": "error", "message": "CalDAV connection not available"}
    
    try:
      principal = self.client.principal()
      
      new_calendar = principal.make_calendar(name=list_name)
      new_calendar.set_properties([dav.DisplayName(list_name)])
      
      self.todoCalendars[list_name] = new_calendar
      
      # Mise à jour dynamique des outils avec la nouvelle liste
      self.tools = self._build_tools()
      
      logger.info(f"New todo list '{list_name}' created successfully.", module_name="todo")
      return {"status": "success", "message": f"Todo list '{list_name}' created"}
      
    except Exception as e:
      logger.error(f"Error creating todo list '{list_name}': {str(e)}", module_name="todo")
      return {"status": "error", "message": f"Failed to create todo list '{list_name}'"}

  def listItems(self, list_name):
    calendar = self.getCalendarByName(list_name)
    if calendar is None:
      return {"status": "error", "message": f"List '{list_name}' not found"}
    
    items = []
    try:
      for item in calendar.todos():
        due = item.icalendar_component.get('due')
        if due is not None:
          due = due.dt.strftime("%Y-%m-%d %H:%M:%S")

        items.append({
          "name": str(item.icalendar_component.get('summary')), 
          "due": due,
          "priority": item.icalendar_component.get('priority'),
          "id": str(item.icalendar_component.get('uid'))
        })
    except Exception as e:
      logger.error(f"Error retrieving list '{list_name}': {str(e)}", module_name="todo")
      return {"status": "error", "message": f"Failed to retrieve list '{list_name}'"}
    
    return items


  def addToList(self, item_name, list_name, priority=None, due=None):
    calendar = self.getCalendarByName(list_name)
    if calendar is None:
      return {"status": "error", "message": f"List '{list_name}' not found"}

    try:
      task = Todo()
      task.add('summary', item_name)
      if priority is not None:
        task.add('priority', priority)
      if due is not None:
        task.add('due', datetime.strptime(due, self.date_format))

      cal = iCalendar()
      cal.add_component(task)
      calendar.save_event(cal.to_ical().decode('utf-8'))

      logger.info(f"Item '{item_name}' added to list '{list_name}'", module_name="todo")
      return {"status": "success", "message": f"Item added to {list_name}"}
      
    except Exception as e:
      logger.error(f"Error adding item '{item_name}' to '{list_name}': {str(e)}", module_name="todo")
      return {"status": "error", "message": f"Failed to add item: {str(e)}"}


  def removeFromList(self, id, list_name):
    calendar = self.getCalendarByName(list_name)
    if calendar is None:
      return {"status": "error", "message": f"List '{list_name}' not found"}

    try:
      task = calendar.todo_by_uid(id)
      if not task:
        return {"status": "error", "message": "Item not found"}

      # Get item name for logging
      if hasattr(task, 'vobject_instance') and task.vobject_instance:
        vtodo = task.vobject_instance.vtodo
        itemName = vtodo.summary.value if hasattr(vtodo, 'summary') else 'No summary'
        vtodo.add('status').value = 'COMPLETED'
        task.save()
      elif hasattr(task, 'icalendar_instance') and task.icalendar_instance:
        itemName = str(task.icalendar_component.get('summary', 'No summary'))
        task.icalendar_component['status'] = 'COMPLETED'
        task.save()
      else:
        try:
          vtodo = task.instance.vtodo
          itemName = vtodo.contents.get('summary', ['No summary'])[0].value
          vtodo.add('status').value = 'COMPLETED'
          task.save()
        except AttributeError:
          itemName = str(task.icalendar_component.get('summary', 'No summary'))
          task.delete()

      logger.info(f"Item '{itemName}' removed from list '{list_name}'", module_name="todo")
      return {"status": "success", "message": f"Item removed from {list_name}"}
      
    except Exception as e:
      logger.error(f"Error removing item {id} from '{list_name}': {str(e)}", module_name="todo")
      return {"status": "error", "message": f"Failed to remove item: {str(e)}"}


  def updateItemPriority(self, id, list_name, priority):
    calendar = self.getCalendarByName(list_name)
    if calendar is None:
      return {"status": "error", "message": f"List '{list_name}' not found"}

    try:
      task = calendar.todo_by_uid(id)
      if not task:
        return {"status": "error", "message": "Item not found"}

      # Get item name for logging
      itemName = "Unknown item"
      
      # Handle different CalDAV API versions
      if hasattr(task, 'vobject_instance') and task.vobject_instance:
        vtodo = task.vobject_instance.vtodo
        itemName = vtodo.summary.value if hasattr(vtodo, 'summary') else 'No summary'
        
        # Set or update priority
        if hasattr(vtodo, 'priority'):
          vtodo.priority.value = priority
        else:
          vtodo.add('priority').value = priority
            
        task.save()
        
      elif hasattr(task, 'icalendar_instance') and task.icalendar_instance:
        # Use icalendar API
        itemName = str(task.icalendar_component.get('summary', 'No summary'))
        
        # Set priority in icalendar component
        task.icalendar_component['priority'] = priority
          
        task.save()
        
      else:
        # Fallback to legacy API
        try:
          vtodo = task.instance.vtodo
          itemName = vtodo.contents.get('summary', ['No summary'])[0].value
          
          # Set priority
          if 'priority' in vtodo.contents:
            vtodo.contents['priority'][0].value = priority
          else:
            vtodo.add('priority').value = priority
              
          task.save()
          
        except AttributeError:
          # Last resort: try icalendar component
          itemName = str(task.icalendar_component.get('summary', 'No summary'))
          
          task.icalendar_component['priority'] = priority
            
          task.save()

      logger.info(f"Priority updated to {priority} for item '{itemName}' in list '{list_name}'", module_name="todo")
      return {"status": "success", "message": f"Priority updated to {priority} for item in {list_name}"}
      
    except Exception as e:
      logger.error(f"Error updating priority for item {id} in '{list_name}': {str(e)}", module_name="todo")
      return {"status": "error", "message": f"Failed to update priority: {str(e)}"}
