#!/usr/bin/env python3
"""
Contacts MCP Server
Provides contact management functionality via MCP protocol
Based on the original tomcontacts.py module
"""

import json
import os
import sys
from typing import Any, Dict, List

import yaml
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
    tomlogger.info(f"🚀 Contacts MCP Server starting with log level: {log_level}", module_name="contacts")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "This module manages a contact list that can contains information like adress, phone number, email addresses."

# Initialize FastMCP server
server = FastMCP(name="contacts-server", stateless_http=True, host="0.0.0.0", port=80)


class ContactsService:
    """Contacts service class based on original TomContacts"""
    
    def __init__(self):
        # Store contacts file in /data directory as specified
        self.contacts_file = '/data/contacts.yml'
        
        # Initialize contacts file
        self._init_contacts_file()
        
        if tomlogger:
            tomlogger.info(f"Contacts service initialized with file: {self.contacts_file}", module_name="contacts")
    
    def _init_contacts_file(self):
        """Initialize the YAML contacts file if it doesn't exist."""
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.contacts_file), exist_ok=True)
        
        if not os.path.exists(self.contacts_file):
            initial_data = {"contacts": []}
            with open(self.contacts_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(initial_data, f, default_flow_style=False, allow_unicode=True, indent=2)
            
            if tomlogger:
                tomlogger.info(f"Initialized new contacts file: {self.contacts_file}", module_name="contacts")
    
    def add_contact(self, **kwargs) -> Dict[str, Any]:
        """Add a new contact to the YAML file with flexible structure."""
        try:
            # Load existing contacts
            with open(self.contacts_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {"contacts": []}
            
            # Validate that we have at least a name
            if 'name' not in kwargs or not kwargs['name']:
                return {
                    "success": False,
                    "message": "Le nom du contact est requis"
                }
            
            # Create contact dictionary from all provided parameters
            contact_dict = {}
            for key, value in kwargs.items():
                if value:  # Only add non-empty values
                    contact_dict[key] = value
            
            # Add to contacts list
            if "contacts" not in data:
                data["contacts"] = []
            data["contacts"].append(contact_dict)
            
            # Save back to file
            with open(self.contacts_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, indent=2)
            
            if tomlogger:
                tomlogger.info(f"Contact added successfully: {contact_dict['name']}", module_name="contacts")
            
            return {
                "success": True,
                "message": f"Contact ajouté avec succès : {contact_dict['name']}"
            }
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error adding contact: {str(e)}", module_name="contacts")
            return {
                "success": False,
                "message": f"Erreur lors de l'ajout du contact : {str(e)}"
            }
    
    def get_contacts(self) -> Dict[str, Any]:
        """Get the complete list of contacts from the YAML file."""
        try:
            # Load contacts data
            with open(self.contacts_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if not content.strip():
                return {
                    "success": True,
                    "contacts": "contacts: []",
                    "message": "Le carnet d'adresses est vide."
                }
            
            if tomlogger:
                tomlogger.debug("Contacts list retrieved successfully", module_name="contacts")
            
            return {
                "success": True,
                "contacts": content,
                "message": "Liste des contacts récupérée avec succès."
            }
        except FileNotFoundError:
            return {
                "success": True,
                "contacts": "contacts: []",
                "message": "Le carnet d'adresses n'existe pas encore."
            }
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error retrieving contacts: {str(e)}", module_name="contacts")
            return {
                "success": False,
                "message": f"Erreur lors de la récupération des contacts : {str(e)}"
            }
    
    def delete_contact(self, contact_identifier: str) -> Dict[str, Any]:
        """Delete a contact by removing it from the YAML file."""
        try:
            # Load contacts data
            with open(self.contacts_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {"contacts": []}
            
            if not data.get("contacts"):
                return {
                    "success": False,
                    "message": "Aucun contact trouvé dans le carnet d'adresses."
                }
            
            # Search for contacts to delete
            original_count = len(data["contacts"])
            deleted_contacts = []
            
            # Keep contacts that don't match the identifier
            remaining_contacts = []
            for contact in data["contacts"]:
                contact_str = yaml.safe_dump(contact, default_flow_style=False, allow_unicode=True)
                if contact_identifier.lower() in contact_str.lower():
                    deleted_contacts.append(contact.get("name", str(contact)))
                else:
                    remaining_contacts.append(contact)
            
            if not deleted_contacts:
                return {
                    "success": False,
                    "message": f"Aucun contact trouvé correspondant à '{contact_identifier}'"
                }
            
            # Update the data
            data["contacts"] = remaining_contacts
            
            # Save back to file
            with open(self.contacts_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, indent=2)
            
            if tomlogger:
                if len(deleted_contacts) == 1:
                    tomlogger.info(f"Contact deleted successfully: {deleted_contacts[0]}", module_name="contacts")
                else:
                    tomlogger.info(f"{len(deleted_contacts)} contacts deleted successfully: {', '.join(deleted_contacts)}", module_name="contacts")
            
            if len(deleted_contacts) == 1:
                return {
                    "success": True,
                    "message": f"Contact supprimé avec succès : {deleted_contacts[0]}"
                }
            else:
                return {
                    "success": True,
                    "message": f"{len(deleted_contacts)} contacts supprimés avec succès : {', '.join(deleted_contacts)}"
                }
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error deleting contact: {str(e)}", module_name="contacts")
            return {
                "success": False,
                "message": f"Erreur lors de la suppression : {str(e)}"
            }


# Initialize contacts service
contacts_service = ContactsService()


@server.tool()
def add_contact(name: str, **kwargs) -> str:
    """Add a new contact to the address book. Extract and structure the contact information from user input, then call this function with the structured data. Be flexible with field names based on the information provided.
    
    Args:
        name: Full name of the contact (required)
        **kwargs: Additional contact information (phone, email, address, etc.)
    
    Returns a JSON string indicating success or failure of the contact addition.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: add_contact with name='{name}' and additional fields: {list(kwargs.keys())}", module_name="contacts")
    
    # Include name in kwargs for the service call
    contact_data = {"name": name, **kwargs}
    result = contacts_service.add_contact(**contact_data)
    
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def get_contacts() -> str:
    """Get the complete list of contacts from the address book. Use this when the user asks about contacts, wants to search for someone, or needs contact information (email adress, address, phone number, ...).
    
    Returns a JSON string with the complete contacts list in YAML format.
    """
    if tomlogger:
        tomlogger.info("Tool call: get_contacts", module_name="contacts")
    
    result = contacts_service.get_contacts()
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def delete_contact(contact_identifier: str) -> str:
    """Delete a contact from the address book by removing the entry from the YAML file.
    
    Args:
        contact_identifier: Identifier to find the contact to delete (name, phone, email, or any unique information about the contact)
    
    Returns a JSON string indicating success or failure of the contact deletion.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: delete_contact with identifier='{contact_identifier}'", module_name="contacts")
    
    result = contacts_service.delete_contact(contact_identifier)
    return json.dumps(result, ensure_ascii=False)


@server.resource("description://contacts")
def description() -> str:
    """Return the server description."""
    return SERVER_DESCRIPTION


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting Contacts MCP Server on port 80", module_name="contacts")
    else:
        print("Starting Contacts MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()