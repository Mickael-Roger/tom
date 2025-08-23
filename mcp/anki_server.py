#!/usr/bin/env python3
"""
Anki MCP Server
Provides Anki flashcard management functionality via MCP protocol
Based on the original tomanki.py module
"""

import json
import os
import sys
from typing import Any, Dict, List

import requests
from mcp.server.fastmcp import FastMCP
from mcp.types import Tool, TextContent

# Add lib directory to path for imports
sys.path.insert(0, '/app/lib')
try:
    from tomlogger import init_logger
    import tomlogger
except ImportError:
    # Fallback if tomlogger is not available
    import logging
    logging.basicConfig(level=logging.INFO)
    tomlogger = None

# Initialize logging
log_level = os.environ.get('TOM_LOG_LEVEL', 'INFO')
if tomlogger:
    logger = init_logger(log_level)
    tomlogger.info(f"🚀 Anki MCP Server starting with log level: {log_level}", module_name="anki")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "This module is used to manage Anki. Anki is a flashcard program. It uses cards. It uses technics from cognitive science such as active recall testing and spaced repetition to help me in my memorization. I use Anki to train myself on memorizing and reinforcing my knowledge."

# Initialize FastMCP server
server = FastMCP(name="anki-server", stateless_http=True, host="0.0.0.0", port=80)


class AnkiService:
    """Anki service class based on original TomAnki"""
    
    def __init__(self):
        # Configuration from environment variables
        self.url = os.environ.get('ANKI_URL', 'http://localhost:8765')
        self.profile_name = os.environ.get('ANKI_PROFILE', 'User 1')
        
        # Cache for deck names
        self.decks = []
        
        if tomlogger:
            tomlogger.info(f"Anki service initialized with URL: {self.url}, Profile: {self.profile_name}", module_name="anki")
    
    def anki_request(self, action: str, params: Dict[str, Any] = None) -> Any:
        """Make a request to AnkiConnect API"""
        if params is None:
            params = {}
        
        try:
            # First, load the profile
            payload = json.dumps({
                "action": "loadProfile", 
                "version": 6, 
                "params": {"name": self.profile_name}
            })
            response = requests.post(self.url, data=payload, timeout=10)
            
            # Then make the actual request
            payload = json.dumps({
                "action": action, 
                "version": 6, 
                "params": params
            })
            response = requests.post(self.url, data=payload, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("error"):
                    if tomlogger:
                        tomlogger.error(f"Anki API error: {result['error']}", module_name="anki")
                    return None
                return result.get("result")
            else:
                if tomlogger:
                    tomlogger.error(f"Anki request error {response.status_code}: {response.text}", module_name="anki")
                return None
                
        except requests.RequestException as e:
            if tomlogger:
                tomlogger.error(f"Anki connection error: {e}", module_name="anki")
            return None
    
    def sync(self) -> bool:
        """Synchronize Anki collection"""
        result = self.anki_request("sync")
        return result is not None
    
    def list_decks(self) -> List[Dict[str, Any]]:
        """List all Anki decks with their statistics"""
        decks = self.anki_request("deckNames")
        
        decks_info = []
        if decks:
            stats = self.anki_request("getDeckStats", {"decks": decks})
            
            if stats:
                for deck in stats:
                    deck_info = stats[deck]
                    if deck_info["name"] not in self.decks:
                        self.decks.append(deck_info["name"])
                    
                    decks_info.append({
                        "deck_name": deck_info["name"],
                        "total_cards": deck_info["total_in_deck"],
                        "due_cards": deck_info["review_count"] + deck_info["new_count"] + deck_info["learn_count"]
                    })
        
        return decks_info
    
    def list_cards(self, deck_name: str) -> List[Dict[str, str]]:
        """List all cards in a specific deck"""
        self.sync()
        
        cards_list = []
        
        # Find cards in the deck
        cards_ids = self.anki_request("findCards", {"query": f"deck:{deck_name}"})
        
        if not cards_ids:
            return cards_list
        
        # Get card information
        cards_info = self.anki_request("cardsInfo", {"cards": cards_ids})
        
        if cards_info:
            for card in cards_info:
                if "fields" in card and "Front" in card["fields"] and "Back" in card["fields"]:
                    cards_list.append({
                        "front": card["fields"]["Front"]["value"],
                        "back": card["fields"]["Back"]["value"]
                    })
        
        return cards_list
    
    def add_card(self, deck_name: str, front: str, back: str) -> bool:
        """Add a new card to the specified deck"""
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


# Initialize Anki service
anki_service = AnkiService()


@server.tool()
def anki_list_decks() -> str:
    """List all Anki decks and their card status. Use this to see available decks and how many cards need review.
    
    Returns a JSON string with deck information including total cards and due cards for each deck.
    """
    if tomlogger:
        tomlogger.info("Tool call: anki_list_decks", module_name="anki")
    
    result = anki_service.list_decks()
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def anki_list_all_cards(deck_name: str) -> str:
    """List all Anki cards of a specific deck. Use this to see all flashcards in a deck.
    
    Args:
        deck_name: Name of the Anki deck to list cards from
    
    Returns a JSON string with all cards (front and back) in the specified deck.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: anki_list_all_cards with deck={deck_name}", module_name="anki")
    
    result = anki_service.list_cards(deck_name)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def anki_add_card(front: str, back: str, deck_name: str) -> str:
    """Add a flashcard to an Anki deck. The front should be very short (a few words or a question). The back should ideally be one line, two lines maximum.
    
    Args:
        front: Front of the card (question, term, or prompt) - keep it short
        back: Back of the card (answer or explanation) - ideally one line
        deck_name: Name of the Anki deck to add the flashcard to
    
    Returns a JSON string indicating success or failure of the card addition.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: anki_add_card with deck={deck_name}, front='{front[:50]}...', back='{back[:50]}...'", module_name="anki")
    
    success = anki_service.add_card(deck_name, front, back)
    
    if success:
        result = {
            "status": "success",
            "message": f"Card added successfully to deck '{deck_name}'",
            "front": front,
            "back": back
        }
    else:
        result = {
            "status": "error",
            "message": f"Failed to add card to deck '{deck_name}'"
        }
    
    return json.dumps(result, ensure_ascii=False)


@server.resource("description://anki")
def description() -> str:
    """Return the server description."""
    return SERVER_DESCRIPTION


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting Anki MCP Server on port 80", module_name="anki")
    else:
        print("Starting Anki MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
