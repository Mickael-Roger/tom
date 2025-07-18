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
  "module_name": "groceries",
  "class_name": "TomGroceries",
  "description": "This module is used to manage groceries list.",
  "type": "personal",
  "complexity": 0
}

class TomGroceries:

  def __init__(self, config, llm, tz=None) -> None:
  
    self.client = caldav.DAVClient(
      url = config['url'],
      username = config.get('user', ''),  # Handle missing user field gracefully
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
            self.groceryCal = calendar

    self.groceryList = []

    self.update()



    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "grocery_list_content",
          "description": "List all product in the groceries list. Call this whenever you need to know if there is something to buy. For example when a user aks 'What are my grocery list', 'What do I have in my shopping list'.",
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
          "name": "grocery_list_add",
          "description": "Add a product in the groceries list. For example when a user aks 'Add this to my grocery list', 'Add this to my shopping list'.",
          "parameters": {
            "type": "object",
            "properties": {
              "product": {
                "type": "string",
                "description": f"The name of the product to add in the grocery list.",
              },
            },
            "required": ["product"],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "grocery_list_remove",
          "description": f"Remove a product from the groceries list. For example when a user aks 'Remove this to my grocery list', 'Remove this to my shopping list'. You must have the task ID that can be got using the todo_list_all function.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "id": {
                "type": "string",
                "description": f"The id of the task or entry name to remove or close in a list.",
              },
            },
            "required": ["id"],
            "additionalProperties": False,
          },
        }
      }


    ]

    self.systemContext = ""
    self.complexity = tom_config.get("complexity", 0)

    self.functions = {
      "grocery_list_content": {
        "function": functools.partial(self.listProducts)
      },
      "grocery_list_add": {
        "function": functools.partial(self.add)
      },
      "grocery_list_remove": {
        "function": functools.partial(self.remove)
      },
    }




  def update(self):

    try:
        self.groceryList = []

        for product in self.groceryCal.todos():
            self.groceryList.append({"product": str(product.icalendar_component.get('summary')), "id": str(product.icalendar_component.get('uid'))})
            
    except Exception as e:
        logger.error(f"Error updating grocery list: {str(e)}", module_name="groceries")
        self.groceryList = []



  def listProducts(self):
    self.update()
    return self.groceryList


  def add(self, product):

    try:
        # Create a new VTODO component
        task = Todo()
        task.add('summary', product)

        # Add the VTODO component to the calendar
        cal = iCalendar()
        cal.add_component(task)
        self.groceryCal.save_event(cal.to_ical().decode('utf-8'))

        self.update()
        
        logger.info(f"Product '{product}' has been added to grocery list.", module_name="groceries")

        return {"status": "success", "message": "product added."}
        
    except Exception as e:
        logger.error(f"Error adding product '{product}': {str(e)}", module_name="groceries")
        return {"status": "error", "message": f"Failed to add product: {str(e)}"}


  def remove(self, id):

    try:
        task = self.groceryCal.todo_by_uid(id)
        if not task:
            return False

        # Handle both old and new CalDAV API for getting product name
        if hasattr(task, 'vobject_instance') and task.vobject_instance:
            vtodo = task.vobject_instance.vtodo
            productName = vtodo.summary.value if hasattr(vtodo, 'summary') else 'No summary'
        elif hasattr(task, 'icalendar_instance') and task.icalendar_instance:
            # Use icalendar API
            productName = str(task.icalendar_component.get('summary', 'No summary'))
        else:
            # Fallback to legacy API with deprecation handling
            try:
                vtodo = task.instance.vtodo
                productName = vtodo.contents.get('summary', ['No summary'])[0].value
            except AttributeError:
                # If instance.vtodo doesn't work, try to get product name
                productName = str(task.icalendar_component.get('summary', 'No summary'))

        task.delete()
        
        self.update()
        
        logger.info(f"Product '{productName}' has been removed from grocery list.", module_name="groceries")
        
        return {"status": "success", "message": "product removed."}
        
    except Exception as e:
        # Handle CalDAV exceptions (like NotFoundError)
        logger.error(f"Error removing product {id}: {str(e)}", module_name="groceries")
        return False
