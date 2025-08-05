# Morning Reminder Module
import yaml
import os
import sys
import functools
import threading
import time
from datetime import datetime, time as time_obj

# Logging
import tomlogger

################################################################################################
#                                                                                              #
#                                    Morning Reminder                                          #
#                                                                                              #
################################################################################################

tom_config = {
    "module_name": "coremorningreminder",
    "class_name": "TomCoreMorningReminder",
    "description": "Core module that manages morning briefing prompts. Stores LLM prompts that will be executed during the user's morning routine to provide daily information and reminders.",
    "type": "core",
    "complexity": 0,
    "configuration_parameters": {}
}

class TomCoreMorningReminder:

    def __init__(self, global_config, username) -> None:
        
        # Store username for logging
        self.username = username
        
        # Store references for processing requests
        self.global_config = global_config
        self.llm = None  # Will be set later by server.py
        
        # Set up personal data directory based on global config
        user_datadir = global_config.get('global', {}).get('user_datadir', './data/users/')
        user_dir = os.path.join(user_datadir, username)
        
        # Ensure user directory exists
        if not os.path.exists(user_dir):
            os.makedirs(user_dir, exist_ok=True)
        
        # Set up YAML file path
        self.config_file = os.path.join(user_dir, 'morning_reminder.yml')
        self.briefing_file = os.path.join(user_dir, 'daily_briefing.yml')
        
        # Initialize with default configuration if file doesn't exist
        self._ensure_config_file()
        
        # Load current configuration
        self.load_config()
        
        # Add tom_config for core module compatibility
        self.tom_config = tom_config
        
        # Start the scheduling thread
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()

        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "morning_reminder_get_instructions",
                    "description": "Get the morning briefing prompts that will be executed during the user's daily briefing routine.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "morning_reminder_add_instruction",
                    "description": "Add a new LLM prompt to the morning briefing routine. The prompt should be formulated as a question or request that will be executed by the LLM during the morning briefing (e.g., 'What's the weather forecast for today?', 'What are my appointments today?', 'Summarize my tasks for today').",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "instruction": {
                                "type": "string",
                                "description": "The LLM prompt to add to the morning briefing routine. Should be written as a question or request that the LLM will execute (e.g., 'What's the weather like today in Paris?', 'What meetings do I have scheduled?').",
                            },
                        },
                        "required": ["instruction"],
                        "additionalProperties": False,
                    },
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "morning_reminder_remove_instruction",
                    "description": "Remove an LLM prompt from the morning briefing routine.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "index": {
                                "type": "integer",
                                "description": "The index (0-based) of the prompt to remove from the morning briefing routine.",
                            },
                        },
                        "required": ["index"],
                        "additionalProperties": False,
                    },
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "morning_reminder_list_instructions",
                    "description": "List all current LLM prompts configured for the morning briefing routine with their indices.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "morning_reminder_get_daily_briefing",
                    "description": "Get the latest generated daily briefing summary from the morning routine.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "morning_reminder_generate_briefing_now",
                    "description": "Generate the daily briefing immediately by executing all configured morning prompts and creating a synthesis.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                }
            }
        ]

        self.systemContext = "This module manages morning briefing prompts that are executed during the user's daily routine. When adding instructions, formulate them as LLM prompts (questions or requests) that will be executed to provide the user with daily information. Examples: 'What's the weather forecast for today?', 'What appointments do I have today?', 'What are my priority tasks for today?'"
        self.complexity = tom_config.get("complexity", 0)
        
        self.functions = {
            "morning_reminder_get_instructions": {
                "function": functools.partial(self.get_instructions)
            },
            "morning_reminder_add_instruction": {
                "function": functools.partial(self.add_instruction)
            },
            "morning_reminder_remove_instruction": {
                "function": functools.partial(self.remove_instruction)
            },
            "morning_reminder_list_instructions": {
                "function": functools.partial(self.list_instructions)
            },
            "morning_reminder_get_daily_briefing": {
                "function": functools.partial(self.get_daily_briefing)
            },
            "morning_reminder_generate_briefing_now": {
                "function": functools.partial(self.generate_briefing_now)
            },
        }

    def _ensure_config_file(self):
        """Ensure the configuration file exists with empty instructions list."""
        if not os.path.exists(self.config_file):
            default_config = {
                'instructions': []
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
            
            tomlogger.info(f"Created empty morning reminder configuration at {self.config_file}", self.username)

    def load_config(self):
        """Load configuration from YAML file."""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f) or {}
            
            # Ensure instructions key exists
            if 'instructions' not in self.config:
                self.config['instructions'] = []
                self.save_config()
                
        except Exception as e:
            tomlogger.error(f"Error loading morning reminder config: {str(e)}", self.username)
            self.config = {'instructions': []}

    def save_config(self):
        """Save configuration to YAML file."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            
        except Exception as e:
            tomlogger.error(f"Error saving morning reminder config: {str(e)}", self.username)

    def get_instructions(self):
        """Get all morning reminder instructions."""
        self.load_config()
        instructions = self.config.get('instructions', []) if self.config.get('instructions') is not None else []
        return {"instructions": instructions}

    def add_instruction(self, instruction):
        """Add a new instruction to the list."""
        try:
            self.load_config()
            
            if 'instructions' not in self.config or self.config['instructions'] is None:
                self.config['instructions'] = []
            
            self.config['instructions'].append(instruction)
            self.save_config()
            
            tomlogger.info(f"Added morning briefing prompt: {instruction}", self.username)
            return {"status": "success", "message": "Morning briefing prompt added successfully"}
            
        except Exception as e:
            tomlogger.error(f"Error adding morning briefing prompt: {str(e)}", self.username)
            return {"status": "error", "message": f"Failed to add morning briefing prompt: {str(e)}"}

    def remove_instruction(self, index):
        """Remove an instruction by index."""
        try:
            self.load_config()
            
            instructions = self.config.get('instructions', []) if self.config.get('instructions') is not None else []
            
            if index < 0 or index >= len(instructions):
                return {"status": "error", "message": "Invalid prompt index"}
            
            removed_instruction = instructions.pop(index)
            self.save_config()
            
            tomlogger.info(f"Removed morning briefing prompt: {removed_instruction}", self.username)
            return {"status": "success", "message": f"Morning briefing prompt '{removed_instruction}' removed successfully"}
            
        except Exception as e:
            tomlogger.error(f"Error removing morning briefing prompt: {str(e)}", self.username)
            return {"status": "error", "message": f"Failed to remove morning briefing prompt: {str(e)}"}

    def list_instructions(self):
        """List all morning briefing prompts with their indices."""
        self.load_config()
        instructions = self.config.get('instructions', []) if self.config.get('instructions') is not None else []
        
        indexed_instructions = []
        for i, instruction in enumerate(instructions):
            indexed_instructions.append({"index": i, "instruction": instruction})
        
        return {"instructions": indexed_instructions}

    def get_daily_briefing(self):
        """Get the latest generated daily briefing."""
        try:
            if os.path.exists(self.briefing_file):
                with open(self.briefing_file, 'r', encoding='utf-8') as f:
                    briefing_data = yaml.safe_load(f) or {}
                    return {
                        "briefing": briefing_data.get('content', 'No briefing available'),
                        "generated_at": briefing_data.get('generated_at', 'Unknown'),
                        "date": briefing_data.get('date', 'Unknown')
                    }
            else:
                return {"briefing": "No daily briefing available yet", "generated_at": None, "date": None}
        except Exception as e:
            tomlogger.error(f"Error reading daily briefing: {str(e)}", self.username)
            return {"briefing": "Error reading daily briefing", "generated_at": None, "date": None}

    def generate_briefing_now(self):
        """Manually trigger briefing generation for testing."""
        try:
            result = self._generate_daily_briefing()
            return {"status": "success", "message": "Daily briefing generated successfully", "briefing": result}
        except Exception as e:
            tomlogger.error(f"Error generating briefing manually: {str(e)}", self.username)
            return {"status": "error", "message": f"Failed to generate briefing: {str(e)}"}

    def _run_scheduler(self):
        """Background scheduler that runs the daily briefing at 2 AM."""
        while True:
            try:
                now = datetime.now()
                target_time = now.replace(hour=2, minute=0, second=0, microsecond=0)
                
                # If it's past 2 AM today, schedule for tomorrow
                if now.time() > time_obj(2, 0):
                    target_time = target_time.replace(day=target_time.day + 1)
                
                # Calculate seconds until next execution
                time_diff = (target_time - now).total_seconds()
                
                tomlogger.info(f"Morning briefing scheduled in {time_diff/3600:.1f} hours at {target_time}", self.username)
                
                # Sleep until target time
                time.sleep(time_diff)
                
                # Generate the briefing
                tomlogger.info("Generating scheduled morning briefing", self.username)
                self._generate_daily_briefing()
                
            except Exception as e:
                tomlogger.error(f"Error in morning briefing scheduler: {str(e)}", self.username)
                # Sleep for 1 hour before retrying
                time.sleep(3600)

    def _generate_daily_briefing(self):
        """Generate the daily briefing by executing all configured prompts."""
        try:
            if not self.llm:
                tomlogger.error("LLM not available for briefing generation", self.username)
                return "Error: LLM not available"
            
            self.load_config()
            instructions = self.config.get('instructions', []) if self.config.get('instructions') is not None else []
            
            if not instructions:
                tomlogger.info("No instructions configured for morning briefing", self.username)
                return "No instructions configured for morning briefing"
            
            tomlogger.info(f"Generating daily briefing with {len(instructions)} prompts", self.username)
            
            # Execute each instruction as if it came from the user
            responses = []
            for i, instruction in enumerate(instructions):
                try:
                    tomlogger.debug(f"Executing prompt {i+1}/{len(instructions)}: {instruction}", self.username)
                    
                    # Execute the prompt through the normal processing pipeline
                    response = self.llm.processRequest(
                        input=instruction,
                        lang="fr",  # Default to French, could be configurable
                        position=None,
                        client_type="background"
                    )
                    
                    if response:
                        responses.append({
                            "prompt": instruction,
                            "response": response
                        })
                        tomlogger.debug(f"Prompt {i+1} executed successfully", self.username)
                    else:
                        tomlogger.warning(f"No response for prompt {i+1}: {instruction}", self.username)
                        responses.append({
                            "prompt": instruction,
                            "response": "Aucune réponse disponible"
                        })
                        
                except Exception as e:
                    tomlogger.error(f"Error executing prompt {i+1} '{instruction}': {str(e)}", self.username)
                    responses.append({
                        "prompt": instruction,
                        "response": f"Erreur lors de l'exécution: {str(e)}"
                    })
            
            # Create synthesis prompt
            responses_text = "\n\n".join([f"Question: {r['prompt']}\nRéponse: {r['response']}" for r in responses])
            
            synthesis_prompt = f"""Voici les informations collectées pour le briefing matinal de {datetime.now().strftime('%A %d %B %Y')} :

{responses_text}

Peux-tu créer une synthèse claire et structurée de ces informations pour présenter un briefing matinal complet ? Organise les informations par thèmes (météo, agenda, tâches, etc.) et présente-les de manière concise et utile pour bien commencer la journée."""

            try:
                # Generate synthesis
                tomlogger.debug("Generating synthesis of morning briefing", self.username)
                synthesis = self.llm.processRequest(
                    input=synthesis_prompt,
                    lang="fr",
                    position=None,
                    client_type="background"
                )
                
                if synthesis:
                    briefing_content = synthesis
                else:
                    # Fallback: simple concatenation
                    briefing_content = f"Briefing matinal du {datetime.now().strftime('%A %d %B %Y')}:\n\n" + responses_text
                
            except Exception as e:
                tomlogger.error(f"Error generating synthesis: {str(e)}", self.username)
                # Fallback: simple concatenation
                briefing_content = f"Briefing matinal du {datetime.now().strftime('%A %d %B %Y')}:\n\n" + responses_text
            
            # Save the briefing
            briefing_data = {
                'content': briefing_content,
                'generated_at': datetime.now().isoformat(),
                'date': datetime.now().strftime('%Y-%m-%d'),
                'prompts_executed': len(instructions),
                'raw_responses': responses
            }
            
            with open(self.briefing_file, 'w', encoding='utf-8') as f:
                yaml.dump(briefing_data, f, default_flow_style=False, allow_unicode=True)
            
            tomlogger.info(f"Daily briefing generated and saved with {len(instructions)} prompts", self.username)
            return briefing_content
            
        except Exception as e:
            tomlogger.error(f"Error generating daily briefing: {str(e)}", self.username)
            return f"Error generating daily briefing: {str(e)}"