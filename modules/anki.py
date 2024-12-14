import requests
import json


################################################################################################
#                                                                                              #
#                                           Anki                                               #
#                                                                                              #
################################################################################################
class Anki:

  def __init__(self, config) -> None:
    self.url = config['url']

    self.decknames = None
    self.decks = None
    self.deckvalues = None

    self.update()

    self.tools = [
      {
        "type": "function",
        "function": {
            "name": "anki_status",
            "description": "Get the status of the Anki flashcards in all decks.",
            "parameters": {},
        },
      },
      {
        "type": "function",
        "function": {
          "name": "anki_add",
          "description": "Add a a flashcard in an Anki deck. Call this when you have to create or add a card in an Anki deck. For example when a user aks 'Add this card to my deck X', 'Create this flashcard to my deck X', 'Add this to anki deck'. Don't make assumptions about the deck name. Ask for clarification if a user request is ambiguous.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "front": {
                "type": "string",
                "description": "Front of the card, it's like the title of the card to add to. It could be a question a name or a sentence.",
              },
              "back": {
                "type": "string",
                "description": "Back of the card. It's like the response or the information I must know related to the front of the card.",
              },
              "deck": {
                "type": "string",
                "enum": self.decknames,
                "description": "Name of the Anki deck to add the flashcard to.",
              },
            },
            "required": ["front", "back", "deck"],
            "additionalProperties": False,
          },
        }
      },
    ]

    self.systemContext = "Anki is a flashcard program. It uses cards. It uses technics from cognitive science such as active recall testing and spaced repetition to help me in my memorization. I use Anki to train myself on memorizing and reinforcing my knowledge. If a user ask for Anki deck status, unless you are explicitly asked to, do not indicate decks with 0 cards to review"


  def ankiCall(self, call):

    # Make the POST request
    response = requests.post(self.url, headers={'Content-Type': 'application/json'}, data=json.dumps(call))

    # Check if the request was successful
    if response.status_code == 200:
        # Convert the JSON response to a dictionary
        response_dict = response.json()

        if response_dict['result'] == None:
          return False, f"Failure" 

        return True, response_dict['result']
    else:
        return False, f"Error: {response.status_code}"

  def update(self):
    self.ankiCall({"action": "sync", "version": 6})
    result, self.decknames = self.ankiCall({"action": "deckNames", "version": 6})
    result, self.decks = self.ankiCall({"action": "getDeckStats", "params": {"decks": self.decknames}, "version": 6})
    self.deckvalues = []
    for deck in self.decks:
      self.deckvalues.append({"deck_id": self.decks[deck]['deck_id'], "name": self.decks[deck]['name'], "to_review": self.decks[deck]['new_count'] + self.decks[deck]['learn_count'] + self.decks[deck]['review_count']})


  # List Anki decks
  def status(self):
    self.update()
    return True, self.deckvalues

  def add(self, deck, front, back):
    self.ankiCall({"action": "sync", "version": 6})
    action = {"action": "addNote", "version": 6, "params": { "note": {"deckName": deck, "modelName": "Basic", "fields": {"Front": front, "Back": back}}}}
    self.update()
    return self.ankiCall(action)



