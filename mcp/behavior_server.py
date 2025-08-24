#!/usr/bin/env python3
"""
Behavior MCP Server
Provides behavior tuning functionality via MCP protocol
Manages behavioral adjustments and prompts for modules
"""

import json
import os
import sys
from datetime import datetime
from typing import Any, Optional, Dict

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
    tomlogger.info(f"🚀 Behavior MCP Server starting with log level: {log_level}", module_name="behavior")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "This module is used for managing behavioral tuning and prompt adjustments for all modules, including global behavioral changes."

# Initialize FastMCP server
server = FastMCP(name="behavior-server", stateless_http=True, host="0.0.0.0", port=80)


class BehaviorService:
    """Behavior service class for managing module behavioral adjustments"""
    
    def __init__(self):
        # Get username from environment variable
        username = os.environ.get('TOM_USER', 'unknown')
        
        # Data storage directory - user-specific
        user_data_dir = f'/data/{username}'
        os.makedirs(user_data_dir, exist_ok=True)
        self.behavior_file = os.path.join(user_data_dir, 'behavior_config.json')
        
        # Load existing behavioral configuration
        self.behavior_config = self._load_behavior_config()
        
        if tomlogger:
            tomlogger.info(f"Behavior service initialized for user '{username}' with config file: {self.behavior_file}", module_name="behavior")
            tomlogger.info(f"Behavior config loaded with {len(self.behavior_config)} modules", module_name="behavior")
    
    def _load_behavior_config(self) -> Dict[str, str]:
        """Load behavioral configuration from JSON file"""
        try:
            if os.path.exists(self.behavior_file):
                with open(self.behavior_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    if isinstance(config, dict):
                        return config
                    else:
                        if tomlogger:
                            tomlogger.warning(f"Invalid behavior config format, using empty config", module_name="behavior")
                        return {}
        except (json.JSONDecodeError, IOError) as e:
            if tomlogger:
                tomlogger.warning(f"Failed to load behavior config: {e}", module_name="behavior")
        
        return {}
    
    def _save_behavior_config(self) -> bool:
        """Save behavioral configuration to JSON file"""
        try:
            # Create backup of existing file
            if os.path.exists(self.behavior_file):
                backup_file = f"{self.behavior_file}.backup"
                with open(self.behavior_file, 'r', encoding='utf-8') as src, \
                     open(backup_file, 'w', encoding='utf-8') as dst:
                    dst.write(src.read())
            
            # Save new configuration
            with open(self.behavior_file, 'w', encoding='utf-8') as f:
                json.dump(self.behavior_config, f, ensure_ascii=False, indent=2)
            
            if tomlogger:
                tomlogger.info(f"Behavior config saved successfully", module_name="behavior")
            return True
            
        except IOError as e:
            if tomlogger:
                tomlogger.error(f"Failed to save behavior config: {e}", module_name="behavior")
            return False
    
    def get_behavior_prompt(self, module_name: Optional[str] = None) -> str:
        """Get behavior prompt for a specific module or all modules"""
        if module_name:
            # Return prompt for specific module
            return self.behavior_config.get(module_name, "")
        else:
            # Return all behavior prompts formatted
            if not self.behavior_config:
                return ""
            
            formatted_prompts = []
            # Always put global first if it exists
            if "global" in self.behavior_config and self.behavior_config["global"]:
                formatted_prompts.append(f"GLOBAL BEHAVIOR ADJUSTMENTS:\n{self.behavior_config['global']}")
            
            # Add other module-specific prompts
            for mod_name, prompt in self.behavior_config.items():
                if mod_name != "global" and prompt:
                    formatted_prompts.append(f"MODULE '{mod_name}' BEHAVIOR ADJUSTMENTS:\n{prompt}")
            
            return "\n\n".join(formatted_prompts)
    
    def update_behavior_prompt(self, module_name: str, prompt: str) -> Dict[str, Any]:
        """Update behavior prompt for a specific module"""
        if not isinstance(module_name, str) or not module_name.strip():
            return {
                "success": False,
                "error": "Module name must be a non-empty string"
            }
        
        module_name = module_name.strip()
        
        # Validate prompt
        if not isinstance(prompt, str):
            return {
                "success": False,
                "error": "Prompt must be a string"
            }
        
        # Clean and validate prompt
        clean_prompt = prompt.strip()
        
        if clean_prompt:
            # Update or add the behavior prompt
            self.behavior_config[module_name] = clean_prompt
            if tomlogger:
                tomlogger.info(f"Updated behavior prompt for module '{module_name}'", module_name="behavior")
        else:
            # Remove empty prompts
            if module_name in self.behavior_config:
                del self.behavior_config[module_name]
                if tomlogger:
                    tomlogger.info(f"Removed empty behavior prompt for module '{module_name}'", module_name="behavior")
        
        # Save configuration
        if self._save_behavior_config():
            return {
                "success": True,
                "message": f"Behavior prompt for module '{module_name}' updated successfully",
                "module": module_name,
                "prompt_length": len(clean_prompt)
            }
        else:
            return {
                "success": False,
                "error": "Failed to save behavior configuration"
            }
    
    def get_all_modules(self) -> list:
        """Get list of all modules with behavior prompts"""
        return list(self.behavior_config.keys())


# Initialize behavior service
behavior_service = BehaviorService()


@server.tool()
def get_behavior_prompt_for_module(module_name: str) -> str:
    """Get the behavioral adjustment prompt for a specific module. Use 'global' for global behavioral changes that apply to all modules.
    
    Args:
        module_name: Name of the module to get behavior prompt for. Use 'global' for global behavioral changes.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: get_behavior_prompt_for_module with module={module_name}", module_name="behavior")
    
    result = behavior_service.get_behavior_prompt(module_name)
    return result


@server.tool()
def update_behavior_prompt_for_module(module_name: str, behavior_prompt: str) -> str:
    """Update the behavioral adjustment prompt for a specific module. Use 'global' for global behavioral changes that apply to all modules.
    
    Args:
        module_name: Name of the module to update behavior prompt for. Use 'global' for global behavioral changes.
        behavior_prompt: The behavioral adjustment prompt/instruction to set for this module. Use empty string to remove.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: update_behavior_prompt_for_module with module={module_name}, prompt_length={len(behavior_prompt)}", module_name="behavior")
    
    result = behavior_service.update_behavior_prompt(module_name, behavior_prompt)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def list_all_behavior_modules() -> str:
    """List all modules that currently have behavioral adjustment prompts configured.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: list_all_behavior_modules", module_name="behavior")
    
    modules = behavior_service.get_all_modules()
    result = {
        "modules": modules,
        "count": len(modules)
    }
    return json.dumps(result, ensure_ascii=False)


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting Behavior MCP Server on port 80", module_name="behavior")
    else:
        print("Starting Behavior MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


@server.resource("description://behavior")
def description() -> str:
    """Return server description."""
    return SERVER_DESCRIPTION


@server.resource("description://behavior_prompts")
def get_all_behavior_prompts() -> str:
    """Return all behavioral adjustment prompts for all modules."""
    if tomlogger:
        tomlogger.debug(f"Resource call: description://behavior_prompts", module_name="behavior")
    
    return behavior_service.get_behavior_prompt()


@server.resource("description://tom_notification")
def get_notification_status() -> str:
    """Return current background notification status for behavior tuning system."""
    # Count how many modules have behavior prompts
    module_count = len(behavior_service.get_all_modules())
    
    if module_count == 0:
        return "No behavior adjustments configured"
    elif module_count == 1:
        return f"1 behavior adjustment configured"
    else:
        return f"{module_count} behavior adjustments configured"


if __name__ == "__main__":
    main()