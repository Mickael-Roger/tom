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

  _update_thread_started = False

  def __init__(self, global_config, username) -> None:

    db_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], "all")
    os.makedirs(db_path, exist_ok=True)

    self.db = os.path.join(db_path, "memory.sqlite")
    self.creds = global_config['global']['firebase']['sa_token_file']

    self.username = username

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('''
    create table if not exists notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datetime DATETIME default current_date,
        notification DATETIME,
        sender TEXT,
        recipient TEXT,
        sent BOOLEAN DEFAULT 0,
        message TEXT
    )
    ''')
    cursor.execute('''
    create table if not exists fcm_tokens (
        token TEXT PRIMARY KEY,
        username TEXT,
        platform TEXT,
        last_update DATETIME default current_date
    )
    ''')
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
          "name": "list_reminders",
          "description": "A function to retrieve a list of all active or pending reminders previously set by the user. This function provides an overview of scheduled reminders and their corresponding times. For example: 'List all my reminders.' or 'What reminders do I have?'",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "delete_reminder",
          "description": "A function to delete a specific reminder previously set by the user. The function allows the user to specify which reminder to remove by referencing its message, time, or both. This ensures users can manage their reminders efficiently by removing completed or outdated ones. For example: 'Delete the reminder to call my mom.', 'Remove the 8 PM sports reminder.' or 'Cancel the reminder set for tomorrow.'",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "reminder_id": {
                "type": "string",
                "description": f"ID of the reminder",
              },
            },
            "required": ["reminder_id"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "add_reminder",
          "description": "Function to create a reminder. A reminder is a time-specific notification for the user. The purpose of this function is to prompt the user to perform a specific action at a given time. This is for tasks or events that need a one-time or time-sensitive follow-up. For example: 'Remind me to call my mom tomorrow.', 'Reminder Jennifer to go to school tommorow at 9am' or 'Remind me at 8 PM to go to sports.'",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "reminder_text": {
                "type": "string",
                "description": f"The text of the reminder",
              },
              "reminder_recipient": {
                "type": "string",
                "enum": self.users,
                "description": f"Recipient of the reminder, could be the requester (me: {username}) or someone else.",
              },
              "reminder_datetime": {
                "type": "string",
                "description": f"The datetime you need to remind me this reminder. Must be in the form of 'YYYY-MM-DD hh:mm:ss'",
              },
            },
            "required": ["reminder_text", "reminder_datetime", "reminder_recipient"],
            "additionalProperties": False,
          },
        },
      },
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

    self.systemContext = """This module is used to manage everything related to your memory or the user's requests. Memory can take several forms:

     - Reminders: A reminder is an element, task, or action the user asks you to remind them about. It has a temporal aspect and will result in a notification being sent to the user at the appropriate time. For example, the user might say: "Remind me in 2 hours to take out the laundry," or "Remind me tomorrow morning at 9 a.m. to buy bread." A reminder is always associated with a specific deadline.

     - Permanent information: Permanent information is data provided by the user that might be useful to you or to them later. This information is relevant and needs to be stored indefinitely. It is unique to each user, so you cannot know it without being explicitly told. For example: "My PIN code is 1234," "X's date of birth is [date]," or "Mr. X is 45 years old." Typically, this information is shared voluntarily by the user, indicating they expect you to keep it in memory.

     - Temporary information: Temporary information is data that is only useful for a short time, either until a specific event occurs or within a short timeframe. This is helpful for storing temporary details, such as when a user says, "I left my keys on the table," or "I parked in this spot." Such information is meant to help the user retrieve their keys or locate their car but loses relevance once the task is completed. Examples include: "I just parked," "I put the keys under the flowerpot," etc.

     If the user's request is to remember where the car is parked, you must save the GPS location along with additional information such as the parking spot number, street name, a point of interest (POI), etc. If the user does not provide any additional information, ask if they have any.

     When the user asks for information about a temporary detail, remind them to let you know when the information is no longer needed so you can delete it from memory. For example, if the user asks where they parked, you should remind them to tell you once they've retrieved their car so you can erase the information from your memory.

     If the user tells you they've retrieved their car, found their keys, or similar, it means you should delete the temporary information related to that item from your memory.
     This only applies to temporary information. The deletion of permanent information must be explicitly requested by the user.

     This module must absolutely be used when the user ask explicit you to search in your memory.
    """

    self.complexity = 0

    self.functions = {
      "list_reminders": {
        "function": functools.partial(self.reminder_list), 
        "responseContext": "Your response must be concise and in the form of a single sentence. You must not reply in list form. For example: 'You have 3 reminders: One for tommorrow about the grocery, another one for next  monday about going to school and a last about calling your mom next month'" 
      },
      "delete_reminder": {
        "function": functools.partial(self.reminder_delete), 
        "responseContext": "" 
      },
      "add_reminder": {
        "function": functools.partial(self.reminder_add), 
        "responseContext": "" 
      },
      "list_stored_information": {
        "function": functools.partial(self.remember_list), 
        "responseContext": "" 
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

    if not TomMemory._update_thread_started:
      TomMemory._update_thread_started = True
      self.cred = credentials.Certificate(self.creds)
      firebase_admin.initialize_app(self.cred)
      self.thread = threading.Thread(target=self.notify)
      self.thread.daemon = True  # Allow the thread to exit when the main program exits
      self.thread.start()
    

  def notify(self):

    while True:
      print("Check for notifications")
      try:
        dbconn = sqlite3.connect(self.db)
        cursor = dbconn.cursor()
        cursor.execute("SELECT id, message, sender, recipient FROM notifications WHERE sent = 0 and notification < datetime('now')")
        notifications = cursor.fetchall()
        cursor.execute("SELECT username, token FROM fcm_tokens WHERE platform = 'android'")
        tokens = cursor.fetchall()
        dbconn.close()
  

        token_list = {}
        for token in tokens:
          username = token[0]
          if username not in token_list.keys():
            token_list[username] = []
          token_list[username].append(token[1])

        if notifications:
          for notification in notifications:
            id = notification[0]
            message = notification[1]
            sender = notification[2]
            recipient = notification[3]
  
            if sender != recipient:
              title = f"Tom Reminder from {sender}"
            else:
              title = f"Tom Reminder"
  
            for device in token_list[recipient]:
              notif = messaging.Message(
                data={
                  "title": title,
                  "body": message,
                },
                token=device,
              )
              response = messaging.send(notif)
  
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            cursor.execute("UPDATE notifications SET sent = 1 WHERE id = ?", (id,))
            dbconn.commit()
            dbconn.close()
  
            print(f"Successfully sent message: {message}")
  
      except Exception as e:
        print(f"Error in notify: {e}")

      time.sleep(60)



  def reminder_add(self, reminder_text, reminder_datetime, reminder_recipient):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("INSERT INTO notifications (notification, message, recipient, sender) VALUES (?, ?, ?, ?)", (reminder_datetime, reminder_text, reminder_recipient, self.username))
      dbconn.commit()
      dbconn.close()


      return {"status": "success", "message": "Reminder added"}

    except:
      return False


  def reminder_delete(self, reminder_id):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("DELETE FROM notifications WHERE id = ?", (reminder_id))
      dbconn.commit()
      dbconn.close()


      return {"status": "success", "message": "Reminder deleted"}

    except:
      return False



  def reminder_list(self):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("SELECT id, notification, message FROM notifications WHERE sent = 0 AND recipient = ?", (self.username,))
      values = cursor.fetchall()
      dbconn.close()

      reminders = []
      for val in values:
        reminders.append({"id": val[0], "reminder_datetime": val[1], "reminder_message": val[2]})

      return reminders

    except:
      return False





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

