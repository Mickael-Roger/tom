import sqlite3
import os
import functools
import firebase_admin
from firebase_admin import credentials, messaging
import threading
import time
import json

################################################################################################
#                                                                                              #
#                                   Memory capability                                          #
#                                                                                              #
################################################################################################
class TomMemory:

  def __init__(self, global_config, username) -> None:

    db_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], username)
    os.makedirs(db_path, exist_ok=True)

    self.db = os.path.join(db_path, "memory.sqlite")

    self.username = username

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('''
    create table if not exists temporary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datetime DATETIME default current_date,
        information TEXT
    )
    ''')
    cursor.execute('''
    create table if not exists permanent (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datetime DATETIME default current_date,
        information TEXT
    )
    ''')
    dbconn.commit()
    dbconn.close()

    self.users = []
    for user in global_config['users']:
      self.users.append(user['username'])

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "list_stored_information",
          "description": "Function to retrieve all pieces of information that the user has previously asked the system to remember. This provides an overview of the stored facts, events, or data, helping the user recall and manage the remembered context effectively. For example: 'List everything you remember.', 'What have I told you to remember?', 'Do I ask you to remember something about my pin code?', 'Do you remember where I park my car?', 'Where are my keys?', 'What is my PIN code?', ... And more generally, any information specific to the user that you cannot know on your own. This is the way to retreive previously stored information. Must be called when you want to get previously stored information.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "information_type": {
                "type": "string",
                "enum": ["permanent", "temporary"],
                "description": f"Permanent information is data meant to be stored indefinitely, like birthdays or PIN codes, while temporary information is situational and only relevant for a short time, such as where the user parked their car.",
              },
            },
            "required": ["information_type"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "delete_stored_information",
          "description": "Function to remove specific information previously stored by the user. The function allows the user to specify which piece of remembered information to delete, ensuring that the stored context remains relevant and up-to-date.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "information_type": {
                "type": "string",
                "enum": ["permanent", "temporary"],
                "description": f"Permanent information is data meant to be stored indefinitely, like birthdays or PIN codes, while temporary information is situational and only relevant for a short time, such as where the user parked their car.",
              },
              "stored_information_id": {
                "type": "string",
                "description": f"ID of the stored information to remove. This 'stored_information_id' values must be retreived using 'tom_list_stored_information' function. Unless you already have the 'store_information_value', you must first run 'tom_list_stored_information' function to retreive this id.",
              },
            },
            "required": ["information_type", "stored_information_id"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "store_information",
          "description": "A function to store user-provided information permanently or indefinitely. The purpose of this function is to retain facts, data, or context provided by the user for future reference. This is not tied to any specific time but serves as a knowledge repository. For example: 'Remember that my PIN code is 1234.' or 'Remember today I lost my keys.'",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "information_type": {
                "type": "string",
                "enum": ["permanent", "temporary"],
                "description": f"Permanent information is data meant to be stored indefinitely, like birthdays or PIN codes, while temporary information is situational and only relevant for a short time, such as where the user parked their car.",
              },
              "information": {
                "type": "string",
                "description": f"The text of the information to remember",
              },
            },
            "required": ["information_type", "information"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = """Memory can take several forms:

     - Permanent information: Permanent information is data provided by the user that might be useful to you or to them later. This information is relevant and needs to be stored indefinitely. It is unique to each user, so you cannot know it without being explicitly told. For example: "My PIN code is 1234," "X's date of birth is [date]," or "Mr. X is 45 years old." Typically, this information is shared voluntarily by the user, indicating they expect you to keep it in memory.

     - Temporary information: Temporary information is data that is only useful for a short time, either until a specific event occurs or within a short timeframe. This is helpful for storing temporary details, such as when a user says, "I left my keys on the table," or "I parked in this spot." Such information is meant to help the user retrieve their keys or locate their car but loses relevance once the task is completed. Examples include: "I just parked," "I put the keys under the flowerpot," etc.

     If the user's request is to remember where the car is parked, you must save the GPS location along with additional information such as the parking spot number, street name, a point of interest (POI), etc. If the user does not provide any additional information, ask if they have any.
     GPS position must be stored in json format: `{"latitude": PLACE HERE THE LATITUDE VALUE, "longitude": PLACE HERE THE LONGITUDE VALUE}`

     When the user asks for information about a temporary detail, remind them to let you know when the information is no longer needed so you can delete it from memory. For example, if the user asks where they parked, you should remind them to tell you once they've retrieved their car so you can erase the information from your memory.

     If the user tells you they've retrieved their car, found their keys, or similar, it means you should delete the temporary information related to that item from your memory.
     This only applies to temporary information. The deletion of permanent information must be explicitly requested by the user.
    """

    self.complexity = 0

    self.functions = {
      "list_stored_information": {
        "function": functools.partial(self.remember_list), 
        "responseContext": """Your response will be read aloud via text-to-speech, so it should be concise and free from any markdown formatting or URLs.
        If the request involves retrieving information about where something is located (their car, keys, an object, etc.), at the end, remember to ask the user to confirm that they have retrieved their item, car, etc., so you can delete this entry from your memory.
        Never directly provide GPS coordinates in your response. However, indicate that you have them if applicable and offer to guide the user.
        If the user explicitly requests GPS coordinates or guidance to retrieve an object, such as their car, the response should follow this format: `[open: https://www.google.com/maps/dir/?api=1&origin=Current+Location&destination=PLACE HERE THE GPS LATITUDE,PLACE HERE THE GPS LONGITUDE&travelmode=walking]`. This tag is interpreted by the frontend application, so, in this way, the user will be guided by an external application to find its object.
        """
      },
      "delete_stored_information": {
        "function": functools.partial(self.remember_delete), 
        "responseContext": "" 
      },
      "store_information": {
        "function": functools.partial(self.remember_add), 
        "responseContext": "" 
      },
    }


  def remember_add(self, information, information_type):

    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      query = f"INSERT INTO {information_type} (information) VALUES (?)"
      cursor.execute(query, (information,))
      dbconn.commit()
      id = cursor.lastrowid
      dbconn.close()

      return {"status": "success", "message": "Added to memory"}

    except:
      return False


  def remember_delete(self, stored_information_id, information_type):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      query = f"DELETE FROM {information_type} WHERE id = ?"
      cursor.execute(query, (stored_information_id,))
      dbconn.commit()
      dbconn.close()

      return {"status": "success", "message": "Deleted from memory"}

    except:
      return False



  def remember_list(self, information_type):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute(f"SELECT id, datetime, information FROM {information_type}")
      values = cursor.fetchall()
      dbconn.close()

      remembers = []
      for val in values:
        remembers.append({"stored_information_id": val[0], "datetime": val[1], "information": val[2]})

      return remembers

    except:
      return False

