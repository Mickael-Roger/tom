import os
import sqlite3
import functools
import json


################################################################################################
#                                                                                              #
#                                    Morning capability                                        #
#                                                                                              #
################################################################################################
class TomMorning:

  def __init__(self, global_config, username) -> None:

    db_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], username)
    os.makedirs(db_path, exist_ok=True)

    self.db = os.path.join(db_path, "morning.sqlite")

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('''
    create table if not exists routines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datetime DATETIME default current_date,
        routine TEXT
    )
    ''')
    dbconn.commit()
    dbconn.close()

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "tom_morning_routine",
          "description": "This is the prompt you have to execute when the user ask for its morning routine execution",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_list_routines",
          "description": "List all morning routines in the global morning routine.",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_delete_routine",
          "description": "Delete a morning routine",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "routine_id": {
                "type": "string",
                "description": f"ID of the routine you want to remove.",
              },
            },
            "required": ["routine_id"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_add_routine",
          "description": "Add a new routine to the morning routines.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "routine_consigne": {
                "type": "string",
                "description": f"The new routine consigne to add",
              },
            },
            "required": ["routine_consigne"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = "A morning routine is a set of instructions given to you that must be carried out every morning when the user requests their morning routine."
    self.complexity = 0

    self.functions = {
      "tom_morning_routine": {
        "function": functools.partial(self.morning_routine_prompt), 
        "responseContext": "" 
      },
      "tom_list_routines": {
        "function": functools.partial(self.routine_list), 
        "responseContext": "" 
      },
      "tom_add_routine": {
        "function": functools.partial(self.routine_add), 
        "responseContext": "" 
      },
      "tom_delete_routine": {
        "function": functools.partial(self.routine_delete), 
        "responseContext": "" 
      },
    }


  def routine_get(self):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("SELECT routine FROM routines")
      values = cursor.fetchall()
      dbconn.close()

      routine = ""
      for val in values:
        routine = routine + "From now on, you have a new instruction: '" + val[0] + "'. If this instruction conflicts with a previous one, this one takes priority.\n"

      return "\n" + routine

    except:
      return False


  def routine_add(self, routine_consigne):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("INSERT INTO routines (routine) VALUES (?)", (routine_consigne))
      dbconn.commit()
      dbconn.close()

      return True

    except:
      return False


  def routine_delete(self, routine_id):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("DELETE FROM routines WHERE id = ?", (routine_id))
      dbconn.commit()
      dbconn.close()

      return True

    except:
      return False



  def routine_list(self):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("SELECT id, routine FROM routines")
      values = cursor.fetchall()
      dbconn.close()

      routines = []
      for val in values:
        routines.append({"id": val[0], "routine_consigne": val[1]})

      return routines

    except:
      return False

  def morning_routine_prompt(self,):

    routine_prompt = ""

    routines = self.routine_list()

    if routines:
      routine_prompt = """You must address the following requests:\n"""
      for routine in routines:
        routine_prompt = routine_prompt + routine['routine_consigne'] + '\n'

    return routine_prompt




