import json
from anki.collection import Collection
from anki.sync import Syncer
#from anki.consts import SYNC_SERVER
from datetime import datetime

################################################################################################
#                                                                                              #
#                                           Anki                                               #
#                                                                                              #
################################################################################################
class TomAnki:

  def __init__(self, config) -> None:

    SYNC_SERVER = config['url']
    self.db_dir = config['db_dir']
    self.username = config['username']
    self.password = config['password']


    self.col = Collection(self.db_dir)
        
    self.syncer = Syncer(self.col)

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "anki_list_decks",
          "description": "List all Anki decks and their card status.",
          "parameters": {},
        },
      },
      {
        "type": "function",
        "function": {
          "name": "anki_list_due_cards",
          "description": "List Anki due cards of a deck.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "deck_name": {
                "type": "string",
                "description": "Name of the Anki deck.",
              },
            },
            "required": ["deck_name"],
            "additionalProperties": False,
          },
        }
      },
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
                "description": "Name of the Anki deck.",
              },
            },
            "required": ["deck_name"],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "anki_review_card",
          "description": "Change the status of a card after its review.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "card_id": {
                "type": "string",
                "description": "ID of the Anki card.",
              },
              "review_status": {
                "type": "string",
                "enum": ['again', 'hard', 'good', 'easy'],
                "description": "Status of the review of the card.",
              },
            },
            "required": ["card_id", "review_status"],
            "additionalProperties": False,
          },
        }
      },
      {
        "type": "function",
        "function": {
          "name": "anki_add_card",
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
              "deck_name": {
                "type": "string",
                "description": "Name of the Anki deck to add the flashcard to.",
              },
            },
            "required": ["front", "back", "deck_name"],
            "additionalProperties": False,
          },
        }
      },
    ]

    self.systemContext = "Anki is a flashcard program. It uses cards. It uses technics from cognitive science such as active recall testing and spaced repetition to help me in my memorization. I use Anki to train myself on memorizing and reinforcing my knowledge."

    self.answerContext =     self.answerContext = {
      "anki_list_decks": """You should always answered in a consise way. If a user ask for Anki deck status, unless you are explicitly asked to, do not indicate decks with 0 cards to review. For example, when a user ask "What is my anki decks status?", your answer should be like "You have 4 reviews in 'English', 3 reviews in 'Tech' and 2 reviews in 'Culture G'"
      """,
      "anki_list_due_cards": """You should always answered in a consise way: For example, your answer should be like "You have x cards to review in your 'deckname' deck." """,
      "anki_list_all_cards": """You should always answered in a consise way.""",
      "anki_review_card": "",
      "anki_add_card": """You should always answered in a consise way: For example, your answer should be like "Card 'front label of my card' with the back 'back sentence of my card' added to deck 'Tech'" """
    }



  def list_decks(self):

    decks_info = []

    for deck_id in self.col.decks.all():
      deck_name = self.col.decks.name(deck_id)
      total_cards = self.col.decks.count(deck_id)
      due_cards = self.col.decks.due(deck_id)
      
      decks_info.append({'deck_name': deck_name, 'total_cards': total_cards, 'due_cards': due_cards })
    
    return True, decks_info



  def sync(self):

    try:
      self.syncer.login(self.username, self.password)
      self.syncer.sync()
      return True, "Anki sync succedeed"

    except Exception as e:
      return False, f"Could not synchronise Anki: {e}"



  def add_card(self, deck_name, front, back):

    self.sync()

    try:
      deck_id = self.col.decks.id(deck_name)
      
      note = self.col.newNote()
      note.fields[0] = front
      note.fields[1] = back
      
      self.col.addNote(note)
      self.col.decks.select(deck_id)
      
      self.col.save()

      self.sync()

      return True, f"Card: '{front}' added into deck '{deck_name}'."

    except Exception as e:
      return False, f"Could not add card: '{front}' added into deck '{deck_name}': {e}."


  def due_cards(self, deck_name):

    self.sync()
    due_cards = []
    
    try:
      cards = self.col.findCards(f"deck:{deck_name} is:due")
      
      for card_id in cards:
        card = self.col.getCard(card_id)
        front = card.note().fields[0]
        back = card.note().fields[1]
        due_cards.append({ 'card_id': card.id, 'front': front, 'back': back })
        
      self.sync()
      
      return True, due_cards

    except Exception as e:
      return False, f"Error while getting due cards: {e}"



  def card_review(self, card_id, status):

    self.sync()

    try:
      status_map = {
          'again': 1,
          'hard': 2,
          'good': 3,
          'easy': 4
      }
      
      card = self.col.getCard(card_id)
      front = card.note().fields[0]
      
      card.interval = 1
      card.ease = status_map[status]
      
      self.col.save()

      self.sync()

      return True, f"Card '{front}' review updated."

    except Exception as e:
      return False, f"Erro while updating the card status: {e}"
  


  def list_cards(self, deck_name):

    self.sync()

    cards_info = []
    
    try:
      cards = self.col.findCards(f"deck:{deck_name}")
      
      for card_id in cards:
        card = self.col.getCard(card_id)
        front = card.note().fields[0]
        back = card.note().fields[1]
        due = True if card.due <= int(datetime.now().timestamp()) else False
        cards_info.append({ 'card_id': card.id, 'front': front, 'back': back, 'due': due })
          
      return True, cards_info

    except Exception as e:
      return False, f"Error while listing cards for deck '{deck_name}': {e}"

