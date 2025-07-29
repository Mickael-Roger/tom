import os
import functools
import firebase_admin
from firebase_admin import credentials, messaging
import threading
import time
import json
from datetime import datetime
import tomlogger

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

  def __init__(self, global_config, username, llm=None) -> None:
    self.tom_config = tom_config

    memory_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], username)
    os.makedirs(memory_path, exist_ok=True)

    self.memory_file = os.path.join(memory_path, "memory.md")
    self.username = username
    self.llm = llm

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
          "description": "Function to retrieve all the information that the is stored in the memory. Use this when the user asks about information that you could find in your memory, searches for specific information, or wants to know what you remember about them. For example: 'Where did I park my car?', 'Where are my keys?', 'What is my PIN code?', etc. This returns the complete memory content for you to analyze and respond to the user's query.",
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

     AUTOMATIC MEMORY STORAGE:
     - When a user provides factual information out of the blue (like "My PIN is 1234", "I live at 123 Main Street", "My favorite color is blue"), automatically store it using store_information and simply respond "OK" or acknowledge briefly.
     - DO NOT ask "Do you want me to remember this?" or similar confirmation questions.
     - The user providing the information implies they want it stored.

     INFORMATION TO STORE:
     - Personal facts: PIN codes, addresses, phone numbers, dates of birth, ages
     - Situational details: where objects are located, parking spots with GPS coordinates
     - Preferences: food preferences, habits, usual schedules
     - Important factual information the user shares

     INFORMATION NOT TO STORE (already managed by other modules):
     - Shopping list items (managed by shopping/todo modules)
     - Calendar events (managed by calendar module)
     - Reminders with specific dates/times (managed by reminder module)
     - Weather queries or temporary information

     GPS COORDINATES:
     When storing location information (like where they parked), save GPS coordinates along with descriptive details like parking spot number, street name, or nearby landmarks.
     GPS position must be stored in json format: `{"latitude": LATITUDE_VALUE, "longitude": LONGITUDE_VALUE}`

     Never directly provide GPS coordinates in your response. However, indicate that you have them if applicable and offer to guide the user.
     If the user explicitly requests GPS coordinates or guidance to retrieve an object, such as their car, the response should follow this format: `[open: https://www.google.com/maps/dir/?api=1&origin=Current+Location&destination=LATITUDE,LONGITUDE&travelmode=walking]`. This tag is interpreted by the frontend application to guide the user.

     FUNCTION USAGE:
     - Use store_information automatically when user provides factual information
     - Use list_stored_information function when the user asks what you remember or searches for specific information
     - Use delete_stored_information function when the user asks you to forget something specific
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
      
      # Check if this information already exists to avoid duplicates
      if f"- {information}" in content:
        return {"status": "success", "message": "Information already exists in memory"}
      
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
        new_section = f"\n\n{date_header}\n- {information}"
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


  def extract_user_visible_content(self, conversation_history):
    """Extract only user-visible content from conversation history (input/output text only)."""
    user_visible_content = []
    
    try:
      for message in conversation_history:
        role = message.get('role', '')
        content = message.get('content', '')
        
        # Only include user and assistant messages (not system, function calls, etc.)
        if role in ['user', 'assistant'] and content:
          user_visible_content.append({
            'role': role,
            'content': content
          })
      
      return user_visible_content
    except Exception as e:
      tomlogger.error(f"Error extracting user-visible content: {str(e)}", self.username)
      return []


  def store_session_insight(self, information):
    """Function to store insights extracted from session analysis."""
    try:
      result = self.remember_add(information)
      tomlogger.info(f"Auto-stored from session analysis: {information}", self.username)
      return {"status": "success", "message": f"Stored: {information}"}
    except Exception as e:
      tomlogger.error(f"Error storing session insight: {str(e)}", self.username)
      return {"status": "error", "message": f"Failed to store: {str(e)}"}

  def analyze_session_with_llm(self, conversation_history):
    """Analyze conversation history with Mistral LLM to extract important information."""
    if not self.llm:
      tomlogger.warning("No LLM available for session analysis", self.username)
      return
    
    # Debug: check the type and attributes of self.llm
    tomlogger.debug(f"LLM object type: {type(self.llm)}", self.username)
    if hasattr(self.llm, 'callLLM'):
      tomlogger.debug("LLM object has callLLM method", self.username)
    else:
      tomlogger.error(f"LLM object does not have callLLM method. Available attributes: {dir(self.llm)}", self.username)
      return

    if not conversation_history:
      tomlogger.debug("Empty conversation history, nothing to analyze", self.username)
      return

    # Get current memory content to avoid duplicates
    current_memory = self.remember_list()
    memory_content = current_memory.get('content', '') if current_memory.get('status') == 'success' else ''

    # Extract only user-visible content
    user_content = self.extract_user_visible_content(conversation_history)
    
    if not user_content:
      tomlogger.debug("No user-visible content to analyze", self.username)
      return

    # Prepare conversation content for analysis
    conversation_text = ""
    for msg in user_content:
      role_label = "Utilisateur" if msg['role'] == 'user' else "Assistant"
      conversation_text += f"{role_label}: {msg['content']}\n\n"

    # LLM prompt for memory analysis with function calling
    context = f"""Tu es un assistant qui analyse les conversations pour identifier les informations importantes à retenir en mémoire.

    Analyse la conversation suivante et identifie uniquement les informations qui devraient être retenues pour de futures interactions. Ne garde que ce qui est vraiment pertinent et utile.

    IMPORTANT: Voici le contenu actuel de la mémoire. Ne stocke PAS d'informations qui sont déjà présentes dans cette mémoire :

    === CONTENU ACTUEL DE LA MÉMOIRE ===
    {memory_content}
    === FIN DU CONTENU DE LA MÉMOIRE ===

    Types d'informations à retenir :
    - Informations personnelles importantes (codes, dates, préférences durables)
    - Détails situationnels utiles (localisation d'objets, informations de parking avec coordonnées GPS)
    - Préférences utilisateur (habitudes, goûts, configurations)
    - Informations factuelles importantes demandées explicitement

    Types d'informations à NE PAS retenir :
    - Conversations générales sans information factuelle
    - Questions ponctuelles sans suite
    - Informations temporaires ou éphémères
    - Discussions techniques sans impact personnel
    - Informations déjà présentes dans la mémoire (voir ci-dessus)

    Si tu identifies des informations pertinentes ET qu'elles ne sont pas déjà dans la mémoire, utilise la fonction store_session_insight pour chaque information importante à retenir.
    Si aucune information pertinente n'est identifiée ou si toutes les informations sont déjà en mémoire, ne fais aucun appel de fonction.

    Conversation à analyser :
    """

    # Define the tool for storing session insights
    session_analysis_tools = [
      {
        "type": "function",
        "function": {
          "name": "store_session_insight",
          "description": "Stocke une information importante extraite de l'analyse de session",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "information": {
                "type": "string",
                "description": "L'information importante à retenir en mémoire"
              }
            },
            "required": ["information"],
            "additionalProperties": False
          }
        }
      }
    ]

    llm_messages = [
      {"role": "system", "content": context},
      {"role": "user", "content": conversation_text}
    ]

    try:
      response = self.llm.callLLM(llm_messages, tools=session_analysis_tools, llm='mistral')
      
      if response and response.choices:
        choice = response.choices[0]
        
        # Check if there are tool calls (information to store)
        if hasattr(choice.message, 'tool_calls') and choice.message.tool_calls:
          for tool_call in choice.message.tool_calls:
            if tool_call.function.name == "store_session_insight":
              try:
                import json
                args = json.loads(tool_call.function.arguments)
                information = args.get("information", "")
                if information:
                  self.store_session_insight(information)
              except Exception as e:
                tomlogger.error(f"Error processing tool call: {str(e)}", self.username)
        else:
          tomlogger.debug("No relevant information found in session for memory storage", self.username)
      
    except Exception as e:
      tomlogger.error(f"Error during LLM session analysis: {str(e)}", self.username)


  def analyze_session_async(self, conversation_history):
    """Analyze session in a separate thread to avoid blocking the reset call."""
    def analysis_worker():
      try:
        self.analyze_session_with_llm(conversation_history)
      except Exception as e:
        tomlogger.error(f"Error in async session analysis: {str(e)}", self.username)
    
    # Start analysis in background thread
    analysis_thread = threading.Thread(target=analysis_worker)
    analysis_thread.daemon = True
    analysis_thread.start()
    
    tomlogger.debug("Started async session analysis", self.username)
