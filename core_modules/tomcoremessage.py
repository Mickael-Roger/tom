import sqlite3
import os
import functools
import firebase_admin
from firebase_admin import credentials, messaging
import tomlogger

################################################################################################
#                                                                                              #
#                               Message sending capability                                     #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "message",
  "class_name": "TomMessage",
  "description": """This module is used to send instant messages to family members via Firebase notifications. Use this when the user wants to send a message, notification, or alert to another family member immediately. For example: 'Send a message to mom saying I'll be late', 'Tell Jennifer that dinner is ready', or 'Notify everyone that I'm leaving now'.""",
  "type": "core",
  "complexity": 0
}

class TomMessage:

  _firebase_initialized = False

  def __init__(self, global_config, username) -> None:
    self.tom_config = tom_config

    self.creds = global_config['global']['firebase']['sa_token_file']
    self.username = username

    # Get FCM tokens database path from reminders module
    db_path = global_config['global']['all_datadir']
    self.db = os.path.join(db_path, "reminders.sqlite")

    self.users = []
    for user in global_config['users']:
      self.users.append(user['username'])

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "tom_send_message",
          "description": "Function to send an instant message to a family member via mobile notification. This sends the message immediately, not at a scheduled time. Use this when the user wants to communicate with another family member right away. For example: 'Send a message to mom saying I'll be late', 'Tell Jennifer that dinner is ready', or 'Notify dad that I arrived safely'.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "message_text": {
                "type": "string",
                "description": "The text of the message to send",
              },
              "message_recipient": {
                "type": "string",
                "enum": self.users,
                "description": f"Recipient of the message, must be one of the family members: {', '.join(self.users)}",
              },
            },
            "required": ["message_text", "message_recipient"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = """This module allows sending instant messages to family members via mobile notifications. Use this when the user wants to send a message, notification, or alert to another family member immediately. This is for real-time communication, not scheduled reminders."""
    self.complexity = tom_config.get("complexity", 0)

    self.functions = {
      "tom_send_message": {
        "function": functools.partial(self.send_message)
      },
    }

    # Firebase is already initialized by TomReminder, no need to initialize again
    # Just store credentials reference for potential future use
    self.cred = credentials.Certificate(self.creds)

  def send_message(self, message_text, message_recipient):
    try:
      # Get FCM tokens for the recipient
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("SELECT token FROM fcm_tokens WHERE username = ? AND platform LIKE 'android%'", (message_recipient,))
      tokens = cursor.fetchall()
      dbconn.close()

      if not tokens:
        tomlogger.error(f"No FCM tokens found for user {message_recipient}", self.username, module_name="message")
        return {"status": "failure", "message": f"No device tokens found for {message_recipient}"}

      # Send message to all devices of the recipient
      sent_count = 0
      for token_row in tokens:
        token = token_row[0]
        
        title = f"Message from {self.username}"
        
        notif = messaging.Message(
          data={
            "title": title,
            "body": message_text,
          },
          token=token,
        )
        
        try:
          response = messaging.send(notif)
          sent_count += 1
          tomlogger.info(f"Message sent to {message_recipient}: {message_text}", self.username, module_name="message")
        except Exception as e:
          tomlogger.error(f"Failed to send message to token {token}: {e}", self.username, module_name="message")

      if sent_count > 0:
        return {"status": "success", "message": f"Message sent to {message_recipient}"}
      else:
        return {"status": "failure", "message": f"Failed to send message to {message_recipient}"}

    except Exception as e:
      tomlogger.error(f"Error in send_message: {e}", self.username, module_name="message")
      return {"status": "failure", "message": "Could not send message"}
