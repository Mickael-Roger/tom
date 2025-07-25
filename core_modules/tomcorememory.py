import os
import functools
import firebase_admin
from firebase_admin import credentials, messaging
import threading
import time
import json
from datetime import datetime

################################################################################################
#                                                                                              #
#                                   Memory capability                                          #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "memory",
  "class_name": "TomMemory",
  "description": """This module is used to manage everything related to your memory. It stores information that the user asks you to remember, such as personal details, preferences, or situational information.

     Examples of information to remember:
     - Personal facts: "My PIN code is 1234," "X's date of birth is [date]," "Mr. X is 45 years old"
     - Situational details: "I left my keys on the table," "I parked in spot B12," "The Wi-Fi password is abc123"
     - Preferences: "I prefer coffee without sugar," "I usually take the 8:15 train"

     If the user asks to remember where something is parked or located, save GPS coordinates along with additional context like parking spot number, street name, or nearby landmarks.

     This module must absolutely be used when the user explicitly asks you to search in your memory.
    """,
  "type": "core",
  "complexity": 0
}

class TomMemory:

  def __init__(self, global_config, username) -> None:
    self.tom_config = tom_config

    memory_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], username)
    os.makedirs(memory_path, exist_ok=True)

    self.memory_file = os.path.join(memory_path, "memory.md")
    self.username = username

    # Initialize memory file if it doesn't exist
    self._init_memory_file()

    self.users = []
    for user in global_config['users']:
      self.users.append(user['username'])

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "list_stored_information",
          "description": "Function to retrieve all pieces of information that the user has previously asked the system to remember. Use this when the user asks about their memory, searches for specific information, or wants to know what you remember about them. For example: 'List everything you remember.', 'What have I told you to remember?', 'Do you remember my pin code?', 'Where did I park my car?', 'Where are my keys?', 'What is my PIN code?', etc. This returns the complete memory content for you to analyze and respond to the user's query.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
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
              "information_text": {
                "type": "string",
                "description": "The text content of the information to delete. This should match exactly the information you want to remove from memory.",
              },
            },
            "required": ["information_text"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "store_information",
          "description": "A function to store user-provided information. The purpose of this function is to retain facts, data, or context provided by the user for future reference. This serves as a knowledge repository. For example: 'Remember that my PIN code is 1234.' or 'Remember I parked in spot B12.' or 'Remember I prefer coffee without sugar.'",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "information": {
                "type": "string",
                "description": "The text of the information to remember",
              },
            },
            "required": ["information"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = """You have access to a personal memory system where you can store and retrieve information that the user asks you to remember.

     When the user asks to remember location information (like where they parked), save GPS coordinates along with descriptive details like parking spot number, street name, or nearby landmarks.
     GPS position must be stored in json format: `{"latitude": LATITUDE_VALUE, "longitude": LONGITUDE_VALUE}`

     Never directly provide GPS coordinates in your response. However, indicate that you have them if applicable and offer to guide the user.
     If the user explicitly requests GPS coordinates or guidance to retrieve an object, such as their car, the response should follow this format: `[open: https://www.google.com/maps/dir/?api=1&origin=Current+Location&destination=LATITUDE,LONGITUDE&travelmode=walking]`. This tag is interpreted by the frontend application to guide the user.

     Use the store_information function when the user explicitly asks you to remember something.
     Use the list_stored_information function when the user asks what you remember or searches for specific information.
     Use the delete_stored_information function when the user asks you to forget something specific.
    """

    self.complexity = tom_config.get("complexity", 0)

    self.functions = {
      "list_stored_information": {
        "function": functools.partial(self.remember_list)
      },
      "delete_stored_information": {
        "function": functools.partial(self.remember_delete)
      },
      "store_information": {
        "function": functools.partial(self.remember_add)
      },
    }

  def _init_memory_file(self):
    """Initialize the markdown memory file if it doesn't exist."""
    if not os.path.exists(self.memory_file):
      with open(self.memory_file, 'w', encoding='utf-8') as f:
        f.write("# Mémoire personnelle\n\n")
        f.write("Ce fichier contient toutes les informations que vous avez demandé de retenir.\n\n")


  def remember_add(self, information):
    """Add information to memory with current date as heading."""
    try:
      current_date = datetime.now().strftime("%Y-%m-%d")
      
      # Read existing content
      with open(self.memory_file, 'r', encoding='utf-8') as f:
        content = f.read()
      
      # Check if today's date section already exists
      date_header = f"# {current_date}"
      
      if date_header in content:
        # Add to existing date section
        lines = content.split('\n')
        insert_index = -1
        
        for i, line in enumerate(lines):
          if line.startswith(date_header):
            # Find the end of this date section (next # or end of file)
            for j in range(i + 1, len(lines)):
              if lines[j].startswith('# ') and j != i:
                insert_index = j
                break
            if insert_index == -1:
              insert_index = len(lines)
            break
        
        # Insert the new information
        new_entry = f"- {information}"
        lines.insert(insert_index, new_entry)
        content = '\n'.join(lines)
      else:
        # Create new date section
        new_section = f"\n{date_header}\n\n- {information}\n"
        content += new_section
      
      # Write back to file
      with open(self.memory_file, 'w', encoding='utf-8') as f:
        f.write(content)
      
      return {"status": "success", "message": "Added to memory"}
    
    except Exception as e:
      return {"status": "error", "message": f"Failed to add to memory: {str(e)}"}


  def remember_delete(self, information_text):
    """Delete information from memory by matching text content."""
    try:
      # Read existing content
      with open(self.memory_file, 'r', encoding='utf-8') as f:
        content = f.read()
      
      lines = content.split('\n')
      new_lines = []
      found = False
      
      for line in lines:
        # Check if this line contains the information to delete
        if information_text.lower() in line.lower() and line.strip().startswith('- '):
          found = True
          continue  # Skip this line (delete it)
        new_lines.append(line)
      
      if not found:
        return {"status": "error", "message": "Information not found in memory"}
      
      # Write back to file
      with open(self.memory_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))
      
      return {"status": "success", "message": "Deleted from memory"}
    
    except Exception as e:
      return {"status": "error", "message": f"Failed to delete from memory: {str(e)}"}



  def remember_list(self):
    """Get all stored information from memory file for LLM to analyze."""
    try:
      # Read the memory file
      with open(self.memory_file, 'r', encoding='utf-8') as f:
        content = f.read()
      
      if not content.strip():
        return {"status": "success", "content": "", "message": "Aucune information n'est stockée en mémoire."}
      
      return {"status": "success", "content": content, "message": "Contenu de la mémoire récupéré avec succès."}
    
    except FileNotFoundError:
      return {"status": "success", "content": "", "message": "Aucun fichier de mémoire trouvé. Aucune information n'est stockée."}
    except Exception as e:
      return {"status": "error", "message": f"Erreur lors de la récupération des souvenirs : {str(e)}"}