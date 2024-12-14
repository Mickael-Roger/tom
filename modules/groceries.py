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
class Groceries:

  def __init__(self, config, tz=None) -> None:
  
    self.client = caldav.DAVClient(
      url = config['url'],
      username = config['user'],
      password = config['password'],
    )

    self.date_format = "%Y-%m-%d %H:%M:%S"


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
            "required": ["prodcut"],
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


  def update(self):

    for product in self.groceryCal.todos():
      self.groceryList.append({"product": str(product.icalendar_instance.subcomponents[0].get("summary")), "id": str(product.icalendar_instance.subcomponents[0].get("uid"))})


  def listProducts(self):
    self.update()
    return True, self.groceryList


  def add(self, product):

    # Create a new VTODO component
    task = Todo()
    task.add('summary', product)

    # Add the VTODO component to the calendar
    cal = iCalendar()
    cal.add_component(task)
    self.groceryCal.save_event(cal.to_ical().decode('utf-8'))

    self.update()

    return True, f"Product '{product}' has been added."

  def remove(self, id):

    task = self.groceryCal.todo_by_uid(id)
    if not task:
        return False, (f"Product with ID '{id}' not found.")

    vtodo = task.instance.vtodo
    productName = vtodo.contents.get('summary', ['No summary'])[0].value
    vtodo.add('status').value = 'COMPLETED'

    task.save()

    self.update()

    print(f"Product '{productName}' has been removed.")
    return True, f"Task '{productName}' has been removed."





