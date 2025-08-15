#!/usr/bin/env python3
"""
Tom Agent Server
Backend service for individual user agents
"""

import cherrypy
import json
import os
import sys
import yaml
import logging
from typing import Dict, Any, Optional

# Add lib directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from tomlogger import init_logger
import tomlogger


def init_config(config_path: str = '/data/config.yml') -> Dict[str, Any]:
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        print(f"ERROR: Configuration file not found: {config_path}")
        # Use default config if file not found
        return {'global': {'log_level': 'INFO'}}
    except yaml.YAMLError as exc:
        print(f"ERROR: Error parsing YAML configuration: {exc}")
        return {'global': {'log_level': 'INFO'}}


class TomAgent:
    """Individual Tom agent service"""
    
    def __init__(self, username: str):
        self.username = username
        
    @cherrypy.expose
    @cherrypy.tools.allow(methods=['GET'])
    @cherrypy.tools.json_out()
    def notifications(self):
        """Handle notifications requests"""
        tomlogger.info("GET /notifications", self.username, "api", "agent")
        return {"status": "OK", "message": "Notifications endpoint"}
    
    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    @cherrypy.tools.json_out()
    def reset(self):
        """Handle reset requests"""
        tomlogger.info("POST /reset", self.username, "api", "agent")
        return {"status": "OK"}
    
    @cherrypy.expose
    @cherrypy.tools.allow(methods=['GET'])
    @cherrypy.tools.json_out()
    def tasks(self):
        """Handle tasks requests"""
        tomlogger.info("GET /tasks", self.username, "api", "agent")
        return {
            "status": "OK", 
            "message": "Tasks endpoint",
            "background_tasks": [],
            "id": 0
        }
    
    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def process(self):
        """Handle process requests"""
        # Echo back the received data for POST requests
        request_data = getattr(cherrypy.request, 'json', None)
        tomlogger.info(f"POST /process with data: {request_data}", self.username, "api", "agent")
        return {
            "status": "OK",
            "message": "Process endpoint", 
            "received_data": request_data,
            "response": "This is a test response from the agent"
        }


def main():
    """Main application entry point"""
    # Get username from environment variable
    username = os.environ.get('TOM_USERNAME', 'unknown')
    
    # Load configuration
    config = init_config('/data/config.yml')
    
    # Initialize logging
    log_level = config.get('global', {}).get('log_level', 'INFO')
    tom_logger = init_logger(log_level)
    tom_logger.startup(f"Starting Tom Agent for user: {username}")
    tom_logger.startup(f"Log level: {log_level}")
    
    # Configure CherryPy logging to use our tomlogger
    # Disable default CherryPy logging
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8080,
        'log.screen': False,  # Disable default screen logging
        'log.access_file': '',  # Disable access log file
        'log.error_file': '',   # Disable error log file
    })
    
    # Replace CherryPy's loggers with our tomlogger
    cherrypy.log.access_log.handlers.clear()
    cherrypy.log.error_log.handlers.clear()
    
    # Add our handler to CherryPy logs
    tom_handler = tom_logger.logger.handlers[0]  # Get our console handler
    cherrypy.log.access_log.addHandler(tom_handler)
    cherrypy.log.error_log.addHandler(tom_handler)
    
    # Set CherryPy logs to INFO level (will be handled by our formatter)
    cherrypy.log.access_log.setLevel(logging.INFO)
    cherrypy.log.error_log.setLevel(logging.INFO)
    
    # Create agent instance
    agent = TomAgent(username)
    
    tom_logger.startup(f"Tom Agent server starting on port 8080 for user {username}...")
    
    try:
        cherrypy.quickstart(agent, '/')
    except KeyboardInterrupt:
        tom_logger.shutdown("Agent shutting down...")
    except Exception as e:
        tom_logger.error(f"Agent error: {str(e)}", module_name="system")
        sys.exit(1)


if __name__ == "__main__":
    main()