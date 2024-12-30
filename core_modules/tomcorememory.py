import os
import sqlite3
import json
import functools


################################################################################################
#                                                                                              #
#                                 Memorization capability                                      #
#                                                                                              #
################################################################################################
class TomMemory:

  def __init__(self, global_config, username) -> None:

    db_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], username)
    os.makedirs(db_path, exist_ok=True)

    self.db = os.path.join(db_path, "memory.sqlite")

    self.llm = None

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('''
    create table if not exists conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datetime DATETIME default current_date,
        summary TEXT,
        conversation BLOB
    )
    ''')
    dbconn.commit()
    dbconn.close()

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "tom_archive_conversation",
          "description": "Function use to save the current conversation between me and you for future reference. The archived conversation can be retrieved or reviewed later to preserve context, decisions, or information exchanged during the interaction. For example: 'Archive this conversation' or 'Save our discussion'",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_list_archived_conversations",
          "description": "List all archived conversation we previously had. For example when a user aks 'Do we have already talked about something?', 'We already talked about that, could you remember?'. Will return, the conversation ID, the datetime of the conversation and a summary of it.",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_retreive_archived_conversation_content",
          "description": "Retreive the content of an archived conversation we previously had.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "conversation_id": {
                "type": "string",
                "description": f"ID of the conversation",
              },
            },
            "required": ["conversation_id"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_delete_archived_conversation_content",
          "description": "Delete from your memory an archived conversation we previously had.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "conversation_id": {
                "type": "string",
                "description": f"ID of the conversation",
              },
            },
            "required": ["conversation_id"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = ""
    self.complexity = 0

    self.functions = {
      "tom_archive_conversation": {
        "function": functools.partial(self.history_keep), 
        "responseContext": "" 
      },
      "tom_list_archived_conversations": {
        "function": functools.partial(self.history_list), 
        "responseContext": "" 
      },
      "tom_retreive_archived_conversation_content": {
        "function": functools.partial(self.history_get), 
        "responseContext": "" 
      },
      "tom_delete_archived_conversation_content": {
        "function": functools.partial(self.history_delete), 
        "responseContext": "" 
      },
    }



  def history_get(self, conversation_id):

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('SELECT id, datetime, conversation FROM conversations WHERE id = ?', (conversation_id,))
    val = cursor.fetchone()
    dbconn.close()


    return {"id": val[0], "datetime": val[1], "conversation": val[2]}


  def history_delete(self, conversation_id):

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('DELETE FROM conversations WHERE id = ?', (conversation_id,))
    dbconn.commit()
    dbconn.close()


    return True


  def history_list(self):

    history = []

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('SELECT id, datetime, summary FROM conversations')
    values = cursor.fetchall()
    dbconn.close()

    for val in values:
      history.append({"id": val[0], "datetime": val[1], "conversation_summary": val[2]})

    return history



  def history_keep(self, history):

    conversation = []

    # Parse conversation
    for message in history:
      if isinstance(message, dict):     
        if "role" in message.keys():
          if message['role'] in ["assistant", "user"]:
            conversation.append(message)

    # Then make a summary and extract keywords
    systemContext = """The user input will be a conversation between you and me. You will need to respond with a brief summary of this conversation."""

    conversation = json.dumps(conversation)
    messages = [{"role": "system", "content": systemContext},{"role": "user", "content": conversation}]

    response = self.llm(messages, None)

    if response != False:
      db = self.db

      if response.choices is not None:
        if response.choices[0].message.content is not None:

          summary = str(response.choices[0].message.content)

          dbconn = sqlite3.connect(db)
          cursor = dbconn.cursor()
          cursor.execute('INSERT INTO conversations (summary, conversation) VALUES (?, ?)', (summary, conversation))
          dbconn.commit()
          dbconn.close()

          response = json.dumps({"history_added": [{"summary": summary}]})

          return True

    return False


