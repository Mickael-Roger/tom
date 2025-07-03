import json
import requests
import threading
import time
from datetime import datetime, timedelta, date
import functools

################################################################################################
#                                                                                              #
#                                           Anki                                               #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "anki",
  "class_name": "TomAnki",
  "description": "This module is used to manage Anki. Anki is a flashcard program. It uses cards. It uses technics from cognitive science such as active recall testing and spaced repetition to help me in my memorization. I use Anki to train myself on memorizing and reinforcing my knowledge."
}

class TomAnki:

  def __init__(self, config, llm) -> None:

    self.url = config['url']
    self.profile_name = config['profile']

    self.lastUpdate = datetime.now() - timedelta(hours=48)

    self.background_status = {"ts": int(time.time()), "status": None}

    self.decks = []


    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "anki_list_decks",
          "description": "List all Anki decks and their card status.",
          "parameters": {},
        },
      },
      #{
      #  "type": "function",
      #  "function": {
      #    "name": "anki_list_due_cards",
      #    "description": "List Anki due cards of a deck.",
      #    "strict": True,
      #    "parameters": {
      #      "type": "object",
      #      "properties": {
      #        "deck_name": {
      #          "type": "string",
      #          "description": "Name of the Anki deck.",
      #        },
      #      },
      #      "required": ["deck_name"],
      #      "additionalProperties": False,
      #    },
      #  }
      #},
      {
        "type": "function",
        "function": {
          "name": "anki_list_all_cards",
          "description": "List all Anki cards of a deck.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "deck_name": {
                "type": "string",
                "enum": self.decks,
                "description": "Name of the Anki deck.",
              },
            },
            "required": ["deck_name"],
            "additionalProperties": False,
          },
        }
      },
      #{
      #  "type": "function",
      #  "function": {
      #    "name": "anki_review_card",
      #    "description": "Change the status of a card after its review.",
      #    "strict": True,
      #    "parameters": {
      #      "type": "object",
      #      "properties": {
      #        "card_id": {
      #          "type": "string",
      #          "description": "ID of the Anki card.",
      #        },
      #        "review_status": {
      #          "type": "string",
      #          "enum": ['again', 'hard', 'good', 'easy'],
      #          "description": "Status of the review of the card.",
      #        },
      #      },
      #      "required": ["card_id", "review_status"],
      #      "additionalProperties": False,
      #    },
      #  }
      #},
      {
        "type": "function",
        "function": {
          "name": "anki_add_card",
          "description": """Adding a flashcard to an Anki deck. You must explicitly ask the user which deck this card should go into. Before adding the card to a deck, you must validate with the user the content of the front, back, and the destination deck. The front of the Anki flashcard should be very short: a few words or a question. The back, on the other hand, should ideally be one line. Ttwo lines is an acceptable maximum.""",
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
              "deck_name": {
                "type": "string",
                "enum": self.decks,
                "description": "Name of the Anki deck to add the flashcard to.",
              },
            },
            "required": ["front", "back", "deck_name"],
            "additionalProperties": False,
          },
        }
      },
    ]

    self.systemContext = ""
    self.complexity = 1

    self.functions = {
      "anki_list_decks": {
        "function": functools.partial(self.list_decks)
      },
      #"anki_list_due_cards": {
      #  "function": functools.partial(self.due_cards)
      #},
      "anki_list_all_cards": {
        "function": functools.partial(self.list_cards)
      },
      #"anki_review_card": {
      #  "function": functools.partial(self.card_review)
      #},
      "anki_add_card": {
        "function": functools.partial(self.add_card)
      },
    }

    self.thread = threading.Thread(target=self.run_update)
    self.thread.daemon = True  # Allow the thread to exit when the main program exits
    self.thread.start()
    

  def run_update(self):
    while True:
      print("Anki: Run auto update")
      time_diff = datetime.now() - self.lastUpdate
      if time_diff > timedelta(minutes=15):
        self.update()
      time.sleep(300)


  def update(self):
    self.sync()

    decks = self.list_decks()

    due_cards=0

    for deck in decks:
      due_cards = due_cards + deck['due_cards']

    if due_cards == 0:
      self.background_status['status'] = ""
    else:
      self.background_status['status'] = f"{due_cards} cards to review"

    self.lastUpdate = datetime.now()


  def anki_request(self, action, params={}):

    payload = json.dumps({"action": "loadProfile", "version": 6, "params": {"name": self.profile_name}})
    response = requests.post(self.url, data=payload)

    payload = json.dumps({"action": action, "version": 6, "params": params})
    response = requests.post(self.url, data=payload)
    
    if response.status_code == 200:
        return response.json().get("result")
    else:
        print(f"Anki sync error {response.status_code}: {response.text}")
        return None


  def list_decks(self):

    decks = self.anki_request("deckNames")

    decks_info = []
    if decks:
      stats = self.anki_request("getDeckStats", {"decks": decks})

      if stats:
        for deck in stats:
          if stats[deck]["name"] not in self.decks:
            self.decks.append(stats[deck]["name"])
          decks_info.append({
              "deck_name": stats[deck]["name"],
              "total_cards": stats[deck]["total_in_deck"],
              "due_cards": stats[deck]["review_count"] + stats[deck]["new_count"] + stats[deck]["learn_count"]
          })
      else:
        return False
    
    return decks_info



  def sync(self):
    if self.anki_request("sync"):
      return True
    else:
      return False




  def add_card(self, deck_name, front, back):

    self.sync()
    card = {
        "deckName": deck_name,
        "modelName": "Basic",
        "fields": {"Front": front, "Back": back},
        "options": {"allowDuplicate": False}
    }

    result = self.anki_request("addNote", {"note": card})
    if result:
      self.sync()
      return True
    else:
      return False


  def list_cards(self, deck_name):

    self.sync()

    cards_list = []

    cards_ids = self.anki_request("findCards", {"query": f"deck:{deck_name}"})
    print("==================")
    print(cards_ids)
    print("==================")
    if not cards_ids:
        return cards_list
    
    cards_info = self.anki_request("cardsInfo", {"cards": cards_ids})
    print("==================")
    print(cards_info)
    print("==================")
    
    if cards_info:
      for card in cards_info:
          cards_list.append({
              "front": card["fields"]["Front"]["value"],
              "back": card["fields"]["Back"]["value"]
          })
          
    return cards_list



#####################################################################

  #def due_cards(self, deck_name):

  #  self.sync()
  #  due_cards = []
  #  
  #  try:
  #    cards = self.col.findCards(f"deck:{deck_name} is:due")
  #    
  #    for card_id in cards:
  #      card = self.col.getCard(card_id)
  #      front = card.note().fields[0]
  #      back = card.note().fields[1]
  #      due_cards.append({ 'card_id': card.id, 'front': front, 'back': back })
  #      
  #    self.sync()
  #    
  #    return due_cards

  #  except Exception:
  #    return False



  #def card_review(self, card_id, status):

  #  self.sync()

  #  try:
  #    status_map = {
  #        'again': 1,
  #        'hard': 2,
  #        'good': 3,
  #        'easy': 4
  #    }
  #    
  #    card = self.col.getCard(card_id)
  #    front = card.note().fields[0]
  #    
  #    card.interval = 1
  #    card.ease = status_map[status]
  #    
  #    self.col.save()

  #    self.sync()

  #    return True, f"Card '{front}' review updated."

  #  except Exception as e:
  #    return False, f"Erro while updating the card status: {e}"
  


