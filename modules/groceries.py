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
    self.answerContext = {
      "grocery_list_content": """You should always answered in a consise way. Your answer must be in the form of a sentence and not a list that contains '-' or element number. For example, when a user ask "What are in my grocery list?", your answer should be like "You have 4 products: pears, milk, water and sugar" or if the user asks "Do I have milk in my grocery list?", your answer should be like "Yes, you have" """,
      "grocery_list_add": """You should always answered in a consise way: For example, when a user ask "Add milk to my grocery list?", your answer should be like "Milk added" """,
      "grocery_list_remove": """You should always answered in a consise way: For example, when a user ask "Remove milk from my grocery list", your answer should be like "Milk removed"
      """
    }




  def update(self):

    for product in self.groceryCal.todos():
      self.groceryList.append({"product": str(product.icalendar_component.get('summary')), "id": str(product.icalendar_component.get('uid'))})



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

    return True, f"{self.groceryList}.\n\nProduct '{product}' has been added to the grocery list."

  def remove(self, id):

    print(datetime.now())

    tasks = self.groceryCal.todos()

    for task in tasks:
      task_uid = task.icalendar_component.get('UID')
      if task_uid == id:
        productName = task.icalendar_component.get('SUMMARY')

        task.delete()
        print(f"Task with UID '{task_uid}' has been deleted.")
        return True, f"Task '{productName}' has been removed."

    return False, f"Product with ID '{id}' not found."







