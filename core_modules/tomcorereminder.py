import sqlite3
import os
import functools
import firebase_admin
from firebase_admin import credentials, messaging
import threading
import time

################################################################################################
#                                                                                              #
#                               Notification capability                                        #
#                                                                                              #
################################################################################################
class TomReminder:

  _update_thread_started = False

  def __init__(self, global_config, username) -> None:

    db_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], "all")
    os.makedirs(db_path, exist_ok=True)

    self.db = os.path.join(db_path, "reminders.sqlite")
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
    dbconn.commit()
    dbconn.close()

    self.users = []
    for user in global_config['users']:
      self.users.append(user['username'])

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "tom_list_reminders",
          "description": "A function to retrieve a list of all active or pending reminders previously set by the user. This function provides an overview of scheduled reminders and their corresponding times. For example: 'List all my reminders.' or 'What reminders do I have?'",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_delete_reminder",
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
          "name": "tom_add_reminder",
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
    ]

    self.systemContext = "Reminder functions are tied to a specific time, designed to prompt an action"

    self.functions = {
      "tom_list_reminders": {
        "function": functools.partial(self.reminder_list), 
        "responseContext": "Your response must be concise and in the form of a single sentence. You must not reply in list form. For example: 'You have 3 reminders: One for tommorrow about the grocery, another one for next  monday about going to school and a last about calling your mom next month'" 
      },
      "tom_delete_reminder": {
        "function": functools.partial(self.reminder_delete), 
        "responseContext": "" 
      },
      "tom_add_reminder": {
        "function": functools.partial(self.reminder_add), 
        "responseContext": "" 
      },
    }

    if not TomReminder._update_thread_started:
      TomReminder._update_thread_started = True
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

      return True, f"Reminder {reminder_text} added"

    except:
      return False, "Cannot add reminder"


  def reminder_delete(self, reminder_id):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("DELETE FROM notifications WHERE id = ?", (reminder_id))
      dbconn.commit()
      dbconn.close()

      return True, "Reminder removed"

    except:
      return False, "Cannot remove reminder"



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

      return True, reminders

    except:
      return False, "Could not list reminders"




