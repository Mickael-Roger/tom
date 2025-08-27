#!/usr/bin/env python3
"""
Kwyk MCP Server
Provides Kwyk platform integration functionality via MCP protocol
Based on the original tomkwyk.py module
"""

import json
import os
import sys
import yaml
import sqlite3
import threading
import random
import time
import requests
from datetime import datetime, timedelta, date
from typing import Any, Dict, Optional, List
from bs4 import BeautifulSoup

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
    tomlogger.info(f"🚀 Kwyk MCP Server starting with log level: {log_level}", module_name="kwyk")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "This module is used to get information from Kwyk. Kwyk is an online platform for math and French exercises. Note: Kwyk may sometimes be misspelled as 'Quick' or similar variations in user queries."

# Initialize FastMCP server
server = FastMCP(name="kwyk-server", stateless_http=True, host="0.0.0.0", port=80)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file"""
    config_path = '/data/config.yml'
    
    if tomlogger:
        tomlogger.info(f"Loading configuration from {config_path}", module_name="kwyk")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        if tomlogger:
            tomlogger.error(f"Configuration file not found: {config_path}", module_name="kwyk")
        else:
            print(f"ERROR: Configuration file not found: {config_path}")
        return {}
    except yaml.YAMLError as exc:
        if tomlogger:
            tomlogger.error(f"Error parsing YAML configuration: {exc}", module_name="kwyk")
        else:
            print(f"ERROR: Error parsing YAML configuration: {exc}")
        return {}


class KwykService:
    """Kwyk service class based on original TomKwyk"""
    
    _update_thread_started = False
    
    def __init__(self, config: Dict[str, Any]):
        # Load kwyk configuration from config
        kwyk_config = config.get('kwyk', {})
        
        # Validate required config fields
        required_fields = ['username', 'password', 'id']
        for field in required_fields:
            if field not in kwyk_config:
                raise KeyError(f"Missing required kwyk config field: {field}")
        
        self.username = kwyk_config['username']
        self.password = kwyk_config['password']
        self.id = kwyk_config['id']
        self.url = "https://www.kwyk.fr/"
        
        # Store database in /data/ directory
        data_dir = '/data'
        os.makedirs(data_dir, exist_ok=True)
        self.db = os.path.join(data_dir, 'kwyk.sqlite')
        
        self.lastUpdate = datetime.now() - timedelta(hours=24)
        
        # Initialize database
        self._init_database()
        
        # Start update thread
        if not KwykService._update_thread_started:
            KwykService._update_thread_started = True
            self.thread = threading.Thread(target=self.run_update)
            self.thread.daemon = True  # Allow the thread to exit when the main program exits
            self.thread.start()
            
            if tomlogger:
                tomlogger.info("✅ Kwyk service initialized successfully", module_name="kwyk")
    
    def _init_database(self):
        """Initialize the SQLite database"""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            # create the table `autonomous` if it does not exist
            cursor.execute('''
            create table if not exists autonomous (
                date date default current_date,
                daycorrect integer,
                daymcq integer,
                dayincorrect integer,
                daytotal integer,
                fullcorrect integer,
                fullmcq integer,
                fullincorrect integer,
                fulltotal integer
            )
            ''')
            dbconn.commit()
            dbconn.close()
            
            if tomlogger:
                tomlogger.info("Database initialized successfully", module_name="kwyk")
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error initializing database: {str(e)}", module_name="kwyk")
            raise
    
    def run_update(self):
        """Run automatic updates in background"""
        while True:
            time.sleep(random.randint(3, 10) * 3600)
            if tomlogger:
                tomlogger.info("Kwyk: Run auto update", module_name="kwyk")
            self.update()
    
    def update(self):
        """Update Kwyk data from the website"""
        try:
            session = requests.Session()
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0', 
                'Accept': '*/*', 
                'Accept-Language': 'en-US,en;q=0.5', 
                'Accept-Encoding': 'gzip, deflate, br, zstd', 
                'Referer': 'https://www.kwyk.fr/', 
                'Origin': 'https://www.kwyk.fr', 
                'X-Requested-With': 'XMLHttpRequest', 
                'DNT': '1', 
                'Sec-GPC': '1', 
                'Sec-Fetch-Dest': 'empty', 
                'Sec-Fetch-Mode': 'cors', 
                'Sec-Fetch-Site': 'same-origin', 
                'TE': 'trailers'
            }
            
            response = session.get('https://www.kwyk.fr/')
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            csrf_token_input = soup.find('input', {'name': 'csrfmiddlewaretoken'})
            if not csrf_token_input:
                raise Exception("CSRF token not found")
            csrf_token = csrf_token_input.get('value')
            
            data = {
                'csrfmiddlewaretoken': csrf_token, 
                'login': self.username, 
                'password': self.password
            }
            
            headers['Referer'] = f'https://www.kwyk.fr/bilan/{self.id}/onglets/autonomie/student/'
            response2 = session.post('https://www.kwyk.fr/accounts/login/', data=data, headers=headers, allow_redirects=False)
            
            if response2.status_code == 200:
                autonomousStatus = session.get(
                    f'https://www.kwyk.fr/bilan/{self.id}/onglets/autonomie/student/', 
                    headers=headers, 
                    allow_redirects=False
                )
                
                if autonomousStatus.status_code == 200:
                    # Convert the JSON response to a dictionary
                    data = autonomousStatus.json()
                    correct = data['instances_done_autonomous']['correct']
                    mcq = data['instances_done_autonomous']['mcq']
                    incorrect = data['instances_done_autonomous']['incorrect']
                    total = data['instances_done_autonomous']['total']
                    
                    dbconn = sqlite3.connect(self.db)
                    cursor = dbconn.cursor()
                    
                    today = date.today().isoformat()
                    
                    cursor.execute('''
                    DELETE FROM autonomous WHERE date = ? 
                    ''', (today,))
                    
                    dbconn.commit()
                    
                    cursor = dbconn.cursor()
                    cursor.execute("SELECT fullcorrect, fullmcq, fullincorrect, fulltotal FROM autonomous WHERE date < DATE('now') ORDER BY date DESC LIMIT 1")
                    lastValues = cursor.fetchone()
                    
                    if lastValues:
                        daycorrect = correct - lastValues[0]
                        daymcq = mcq - lastValues[1]
                        dayincorrect = incorrect - lastValues[2]
                        daytotal = total - lastValues[3]
                    else:
                        daycorrect = correct
                        daymcq = mcq
                        dayincorrect = incorrect
                        daytotal = total
                    
                    cursor.execute('''
                    INSERT INTO autonomous (fullcorrect, fullmcq, fullincorrect, fulltotal, daycorrect, daymcq, dayincorrect, daytotal) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (correct, mcq, incorrect, total, daycorrect, daymcq, dayincorrect, daytotal))
                    
                    dbconn.commit()
                    
                    self.lastUpdate = datetime.now()
                    if tomlogger:
                        tomlogger.info("Kwyk DB Updated", module_name="kwyk")
                    
                    dbconn.close()
                else:
                    raise Exception(f"Failed to get autonomous status: HTTP {autonomousStatus.status_code}")
            else:
                raise Exception(f"Failed to login: HTTP {response2.status_code}")
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error updating Kwyk data: {str(e)}", module_name="kwyk")
            raise
    
    def get(self, period_from: str, period_to: str) -> Dict[str, Any]:
        """Get Kwyk statistics for a specific period"""
        try:
            # Validate date format
            try:
                datetime.strptime(period_from, '%Y-%m-%d')
                datetime.strptime(period_to, '%Y-%m-%d')
            except ValueError as e:
                if tomlogger:
                    tomlogger.error(f"Invalid date format in get: {str(e)}", module_name="kwyk")
                return {"error": f"Invalid date format: {str(e)}"}
            
            # Update data before querying
            self.update()
            
            dbconn = sqlite3.connect(self.db)
            entries = dbconn.execute(
                'SELECT date, daycorrect, daymcq, dayincorrect, daytotal FROM autonomous WHERE date BETWEEN ? AND ? ORDER BY date ASC', 
                (period_from, period_to)
            )
            
            # Initialize sums for each exercise type
            total_correct = 0
            total_mcq = 0
            total_incorrect = 0
            total_exercises = 0
            
            for entry in entries:
                total_correct += entry[1]
                total_mcq += entry[2] 
                total_incorrect += entry[3]
                total_exercises += entry[4]
            
            dbconn.close()
            
            # Create aggregated response
            data = {
                "period": {
                    "start_date": period_from,
                    "end_date": period_to,
                },
                "math": {
                    "correct_exercises": total_correct,
                    "mcq_exercises": total_mcq,
                    "incorrect_exercises": total_incorrect,
                    "total_exercises": total_exercises
                }
            }
            
            if tomlogger:
                tomlogger.info(f"Retrieved Kwyk data for period {period_from} to {period_to}: {total_exercises} total exercises", module_name="kwyk")
            return data
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error getting Kwyk data: {str(e)}", module_name="kwyk")
            return {"error": f"Failed to get Kwyk data: {str(e)}"}


# Load configuration and initialize kwyk service
config = load_config()
kwyk_service = KwykService(config)


@server.tool()
def kwyk_get(period_from: str, period_to: str) -> str:
    """Get the Kwyk status. For example when a user asks 'How many kwyk exercises has been done today', 'What is the kwyk status', 'How many math exercise has been done today'
    
    Args:
        period_from: Must be in the form of '%Y-%m-%d'. Define the starting date to search for. Oldest starting date is '2020-01-01'.
        period_to: Must be in the form of '%Y-%m-%d'. Define the ending date to search for. Maximum ending date is today.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: kwyk_get with period_from={period_from}, period_to={period_to}", module_name="kwyk")
    
    result = kwyk_service.get(period_from, period_to)
    return json.dumps(result, ensure_ascii=False)


@server.resource("description://kwyk")
def description() -> str:
    """Return the server description."""
    return SERVER_DESCRIPTION


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting Kwyk MCP Server on port 80", module_name="kwyk")
    else:
        print("Starting Kwyk MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()