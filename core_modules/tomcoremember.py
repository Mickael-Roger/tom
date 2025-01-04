import sqlite3
import os
import functools
import json

################################################################################################
#                                                                                              #
#                               Notification capability                                        #
#                                                                                              #
################################################################################################
class TomRemember:

  def __init__(self, global_config, username) -> None:

    db_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], username)
    os.makedirs(db_path, exist_ok=True)

    self.db = os.path.join(db_path, "remember.sqlite")

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('''
    create table if not exists remembers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datetime DATETIME default current_date,
        information TEXT
    )
    ''')
    dbconn.commit()
    dbconn.close()

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "tom_list_stored_information",
          "description": "Function to retrieve all pieces of information that the user has previously asked the system to remember. This provides an overview of the stored facts, events, or data, helping the user recall and manage the remembered context effectively. For example: 'List everything you remember.', 'What have I told you to remember?', 'Do I ask you to remember something about my pin code?', 'Do you remember where I park my car?', 'Where are my keys?', 'What is my PIN code?', ...",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_delete_stored_information",
          "description": "Function to remove specific information previously stored by the user. The function allows the user to specify which piece of remembered information to delete, ensuring that the stored context remains relevant and up-to-date.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "stored_information_id": {
                "type": "string",
                "description": f"ID of the stored information to remove. This 'stored_information_id' values must be retreived using 'tom_list_stored_information' function. Unless you already have the 'store_information_value', you must first run 'tom_list_stored_information' function to retreive this id.",
              },
            },
            "required": ["stored_information_id"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_store_information",
          "description": "A function to store user-provided information permanently or indefinitely. The purpose of this function is to retain facts, data, or context provided by the user for future reference. This is not tied to any specific time but serves as a knowledge repository. For example: 'Remember that my PIN code is 1234.' or 'Remember today I lost my keys.'",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "information": {
                "type": "string",
                "description": f"The text of the information to remember",
              },
            },
            "required": ["information"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = """Remember functions are meant to manage user-provided information permanently, indefinitely or temporary. The purpose of remember functions is to retain facts, data, or context provided by the user for future reference. This is not tied to any specific time but serves as a knowledge repository. You may use these functions to store both permanent information, such as a credit card code, and temporary information that will be useful to the user later, such as remembering where the car was parked or where the keys were placed.
     If the user's request is to remember where the car is parked, you must save the GPS location along with additional information such as the parking spot number, street name, a point of interest (POI), etc. If the user does not provide any additional information, ask if they have any. If not, just sore the GPS position.
     When the user asks you to remember where something is (their keys, car, etc.), you must absolutely record at least the GPS location of the said item.
    """
    self.complexity = 1

    self.functions = {
      "tom_list_stored_information": {
        "function": functools.partial(self.remember_list), 
        "responseContext": """Your response will be read aloud via text-to-speech, so it should be concise and free from any markdown formatting or URLs.
        If the request involves retrieving information about where something is located (their car, keys, an object, etc.), at the end, remember to ask the user to confirm that they have retrieved their item, car, etc., so you can delete this entry from your memory.
        Never directly provide GPS coordinates in your response. However, indicate that you have them if applicable and offer to guide the user.
        If the user explicitly requests GPS coordinates or guidance to retrieve an object, such as their car, the response should follow this format: `[open: https://www.google.com/maps/dir/?api=1&origin=Current+Location&destination=PLACE HERE THE GPS LATITUDE,PLACE HERE THE GPS LONGITUDE&travelmode=walking]`. This tag is interpreted by the frontend application, so, in this way, the user will be guided by an external application to find its object.
        """
      },
      "tom_delete_stored_information": {
        "function": functools.partial(self.remember_delete), 
        "responseContext": "" 
      },
      "tom_store_information": {
        "function": functools.partial(self.remember_add), 
        "responseContext": """
        """

      },
    }



  def remember_add(self, information):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("INSERT INTO remembers (information) VALUES (?)", (information,))
      dbconn.commit()
      id = cursor.lastrowid
      dbconn.close()

      return f"Added with id: {id}"

    except:
      return False


  def remember_delete(self, stored_information_id):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("DELETE FROM remembers WHERE id = ?", (stored_information_id,))
      dbconn.commit()
      dbconn.close()

      return True

    except:
      return False



  def remember_list(self):
    try:
      dbconn = sqlite3.connect(self.db)
      cursor = dbconn.cursor()
      cursor.execute("SELECT id, datetime, information FROM remembers")
      values = cursor.fetchall()
      dbconn.close()

      remembers = []
      for val in values:
        remembers.append({"stored_information_id": val[0], "datetime": val[1], "information": val[2]})

      return remembers

    except:
      return False




