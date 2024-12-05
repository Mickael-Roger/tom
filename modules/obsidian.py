import os
from mistralai import Mistral
import time
import json
from datetime import datetime


class JarMick():

  def __init__(self, config, callLLM) -> None:

    self.triage = {
      "name": "obsidian",
      "description": "Obsidian is a note taking application. I use it to note important stuff of even small event I'd like to remember.",
      "consigne": 'If the request is about obsidian or any note taking request like taking a note, searching for notes, take a note about something, write something to remember, ..., the "service" field is set to "obsidian". User prompt that ak you to "take a note about ...", "note that ...", ... are concerned'
    }

    self.conf = config
    self.callLLM = callLLM


  def addToNote(self, note, content):
    try:
      if not os.path.exists(note):
        with open(note, 'w') as file:
          file.write(content)  # Create an empty file
        return {"response": f"{note} created with the content: {content}"} 
      else:
        return {"response": f"{content} added to the note {note}"} 
    except Exception as e:
      return {"response": f"Could not create note {note}: {e}"} 






  def request(self, user):
  # First triage this calendar request: Search for an event or an information about an event; Create an event; Update an event; Delete an event
    systemPrompt = f"""
      The user prompt is a about information that is containt in the note taking application called obsidian.
      You must answer a json that contain only one value: "action". 
      According to the user prompt, you must set the "action" value to one of the appropriate values: "search", "add", "create", "find"
      - The "search" value is used for any user prompt that request information that can be containt in a note like what note contains information about somthing
      - The "add" value is used for any user prompt that is about adding text to an existing note, taking a note about something, write something down to remember, creating a new note
      - The "find" value is used for any user prompt that is about finding a note, finding if a note about a topic or with a specific title exist, listing existing notes
    """
   
    response = self.callLLM("mistral-medium-latest", systemPrompt, user, self.conf)

    match response['action']:
      case 'search':
        result = {"response": f"Search"} 
      case 'add':
        result = {"response": f"Add"} 
      case 'find':
        result = {"response": f"Find"} 
      case _:
        # TODO: Try to use a biger model to determine the Calendar triage, otherwise we don't understand for real
        result = {"response": f"Sorry, I could not understand your Obsidian request"} 

    return result



