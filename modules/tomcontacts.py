import os
from datetime import datetime
import functools
import yaml


################################################################################################
#                                                                                              #
#                                        Contacts                                              #
#                                                                                              #
################################################################################################

tom_config = {
    "module_name": "contacts",
    "class_name": "TomContacts", 
    "description": "This module manages a flexible contact list in YAML format with functions to add, search, and delete contacts.",
    "type": "global",
    "complexity": 0,
    "configuration_parameters": {}
}

class TomContacts:
    
    def __init__(self, config, llm) -> None:
        all_datadir = config.get('all_datadir', './data/all/')
        self.contacts_file = os.path.join(all_datadir, 'contacts.yml')
        self.llm = llm
        
        # Initialize contacts file
        self._init_contacts_file()
        
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "add_contact",
                    "description": "Add a new contact to the address book. Extract and structure the contact information from user input, then call this function with the structured data. Be flexible with field names based on the information provided.",
                    "strict": False,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Full name of the contact (required)"
                            }
                        },
                        "required": ["name"],
                        "additionalProperties": True
                    }
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "get_contacts",
                    "description": "Get the complete list of contacts from the address book. Use this when the user asks about contacts, wants to search for someone, or needs contact information.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_contact", 
                    "description": "Delete a contact from the address book by removing the entry from the YAML file.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "contact_identifier": {
                                "type": "string",
                                "description": "Identifier to find the contact to delete (name, phone, email, or any unique information about the contact)"
                            }
                        },
                        "required": ["contact_identifier"],
                        "additionalProperties": False
                    }
                }
            }
        ]
        
        self.systemContext = "You have access to a flexible contacts list in YAML format where you can add, search and delete contacts with any type of information."
        self.complexity = tom_config.get("complexity", 0)
        self.functions = {
            "add_contact": {
                "function": functools.partial(self.add_contact)
            },
            "get_contacts": {
                "function": functools.partial(self.get_contacts)
            },
            "delete_contact": {
                "function": functools.partial(self.delete_contact)
            }
        }
    
    def _init_contacts_file(self):
        """Initialize the YAML contacts file if it doesn't exist."""
        os.makedirs(os.path.dirname(self.contacts_file), exist_ok=True)
        
        if not os.path.exists(self.contacts_file):
            initial_data = {"contacts": []}
            with open(self.contacts_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(initial_data, f, default_flow_style=False, allow_unicode=True, indent=2)
    
    def add_contact(self, **kwargs):
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
            
            return {
                "success": True,
                "message": f"Contact ajouté avec succès : {contact_dict['name']}"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Erreur lors de l'ajout du contact : {str(e)}"
            }
    
    def get_contacts(self):
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
            return {
                "success": False,
                "message": f"Erreur lors de la récupération des contacts : {str(e)}"
            }
    
    def delete_contact(self, contact_identifier):
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
            return {
                "success": False,
                "message": f"Erreur lors de la suppression : {str(e)}"
            }