import os
import sqlite3
import functools
import json


################################################################################################
#                                                                                              #
#                                   Behavior capability                                        #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "behavior",
  "class_name": "TomBehavior",
  "description": "This module is used to manage your instructions and behaviors. It can be used to add or remove an instruction, modify your behaviors, or list your current instructions and behaviors. Use this module only if the user explicitly requests it, such as with phrases like: 'What instructions have I given you?', 'Remove this instruction' or 'From now on, I want you to'",
  "type": "core",
  "complexity": 0
}

class TomBehavior:

  def __init__(self, global_config, username) -> None:
    self.tom_config = tom_config

    db_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], username)
    os.makedirs(db_path, exist_ok=True)

    self.db = os.path.join(db_path, "behavior.sqlite")

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('''
    create table if not exists behaviors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datetime DATETIME default current_date,
        date_from DATETIME DEFAULT '2020-01-01',
        date_to DATETIME DEFAULT '2030-01-01',
        behavior TEXT
    )
    ''')
    dbconn.commit()
    dbconn.close()

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "tom_list_behaviors",
          "description": "List all the behaviors and instructions that have been given to you. For example when a user aks 'What are your specific behavior?', 'Do I ask you to behave like that?', 'What are you specific consignes?'. Will return, the behaviour ID, the application datetime from and to and the behavior description.",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_delete_behavior",
          "description": "Remove a behavior or instruction that have been given to you. For example when a user aks 'Stop behaving like that', 'Remove this consigne'",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "behavior_id": {
                "type": "string",
                "description": f"ID of the behavior",
              },
            },
            "required": ["behavior_id"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_add_behavior",
          "description": "Add a new behavior or instruction. For example when a user aks 'I want you to change you behavior', 'Add this consigne' or 'Behave like that'",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "behavior_consigne": {
                "type": "string",
                "description": f"The new behavior consigne",
              },
            },
            "required": ["behavior_consigne"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = ""
    self.complexity = tom_config.get("complexity", 0)

    self.functions = {
      "tom_list_behaviors": {
        "function": functools.partial(self.behavior_list)
      },
      "tom_add_behavior": {
        "function": functools.partial(self.behavior_add)
      },
      "tom_delete_behavior": {
        "function": functools.partial(self.behavior_delete)
      },
    }


  def behavior_get(self):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("SELECT behavior FROM behaviors WHERE datetime('now', 'localtime') > date_from AND datetime('now', 'localtime') < date_to")
      values = cursor.fetchall()
      dbconn.close()

      behavior = ""
      for val in values:
        behavior = behavior + "From now on, you have a new instruction: '" + val[0] + "'. If this instruction conflicts with a previous one, this one takes priority.\n"

      return behavior

    except:
      return False


  def behavior_add(self, behavior_consigne, date_from='2020-01-01', date_to='2030-01-01'):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("INSERT INTO behaviors (date_from, date_to, behavior) VALUES (?, ?, ?)", (date_from, date_to, behavior_consigne))
      dbconn.commit()
      dbconn.close()

      return {"status": "success", "message": "Behavior added"}

    except:
      return False


  def behavior_delete(self, behavior_id):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("DELETE FROM behaviors WHERE id = ?", (behavior_id))
      dbconn.commit()
      dbconn.close()

      return {"status": "success", "message": "Behavior deleted"}

    except:
      return False



  def behavior_list(self):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("SELECT id, date_from, date_to, behavior FROM behaviors")
      values = cursor.fetchall()
      dbconn.close()

      behaviors = []
      for val in values:
        behaviors.append({"id": val[0], "date_from": val[1], "date_to": val[2], "behavior": val[3]})

      return behaviors

    except:
      return False