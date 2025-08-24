#!/usr/bin/env python3
"""
Cafetaria MCP Server
Provides school cafeteria management functionality via MCP protocol
Based on the original tomcafetaria.py module
"""

import json
import os
import sys
import yaml
import sqlite3
import threading
import time
import re
import functools
from urllib.parse import urlparse, parse_qs, quote
from datetime import datetime, timedelta, date
from typing import Any, Dict, Optional, List

import requests
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP
from mcp.types import Tool, TextContent

# Add lib directory to path for imports
sys.path.insert(0, '/app/lib')
try:
    from tomlogger import init_logger
    import tomlogger
    from tomhttphelper import TomHttpHelper
except ImportError:
    # Fallback if tomlogger is not available
    import logging
    logging.basicConfig(level=logging.INFO)
    tomlogger = None

# Initialize logging
log_level = os.environ.get('TOM_LOG_LEVEL', 'INFO')
if tomlogger:
    logger = init_logger(log_level)
    tomlogger.info(f"🚀 Cafetaria MCP Server starting with log level: {log_level}", module_name="cafetaria")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "This module is used to manage the use of the school cafeteria, such as reserving or canceling a cafeteria meal or checking the remaining credit."

# Initialize FastMCP server
server = FastMCP(name="cafetaria-server", stateless_http=True, host="0.0.0.0", port=80)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file"""
    config_path = '/data/config.yml'
    
    if tomlogger:
        tomlogger.info(f"Loading configuration from {config_path}", module_name="cafetaria")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        if tomlogger:
            tomlogger.error(f"Configuration file not found: {config_path}", module_name="cafetaria")
        else:
            print(f"ERROR: Configuration file not found: {config_path}")
        return {}
    except yaml.YAMLError as exc:
        if tomlogger:
            tomlogger.error(f"Error parsing YAML configuration: {exc}", module_name="cafetaria")
        else:
            print(f"ERROR: Error parsing YAML configuration: {exc}")
        return {}


class CafetariaService:
    """Cafetaria service class based on original TomCafetaria"""
    
    _update_thread_started = False
    
    def __init__(self, config: Dict[str, Any]):
        # Load cafetaria configuration from config
        cafetaria_config = config.get('cafetaria', {})
        
        # Validate required config fields
        required_fields = ['username', 'password']
        for field in required_fields:
            if field not in cafetaria_config:
                raise KeyError(f"Missing required cafetaria config field: {field}")
        
        self.username = cafetaria_config['username']
        self.password = cafetaria_config['password']
        self.url = 'https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152'
        
        # Store database directly in /data/cafetaria.sqlite
        self.db = '/data/cafetaria.sqlite'
        
        self.lastUpdate = datetime.now() - timedelta(hours=48)
        self.background_status = {"ts": int(time.time()), "status": None}
        
        # Initialize database
        self._init_database()
        
        # Start update thread
        if not CafetariaService._update_thread_started:
            CafetariaService._update_thread_started = True
            self.thread = threading.Thread(target=self.run_update)
            self.thread.daemon = True  # Allow the thread to exit when the main program exits
            self.thread.start()
            
            if tomlogger:
                tomlogger.info("✅ Cafetaria service initialized successfully", module_name="cafetaria")
    
    def _init_database(self):
        """Initialize the SQLite database"""
        try:
            dbconn = sqlite3.connect(self.db)
            cursor = dbconn.cursor()
            # create the table `cafetaria` if it does not exist
            cursor.execute('''
            create table if not exists cafetaria (
                date DATETIME PRIMARY KEY,
                id TEXT,
                is_reserved BOOLEAN
            )
            ''')
            cursor.execute('''
            create table if not exists solde (
                solde TEXT
            )
            ''')
            dbconn.commit()
            dbconn.close()
            
            if tomlogger:
                tomlogger.info("Database initialized successfully", module_name="cafetaria")
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error initializing database: {str(e)}", module_name="cafetaria")
            raise
    
    def run_update(self):
        """Run automatic updates in background"""
        while True:
            time.sleep(3600)  # Wait 1 hour
            if tomlogger:
                tomlogger.info("Cafetaria: Run auto update", module_name="cafetaria")
            time_diff = datetime.now() - self.lastUpdate
            if time_diff > timedelta(hours=48):
                try:
                    self.update()
                except Exception as e:
                    if tomlogger:
                        tomlogger.error(f"Auto update failed: {str(e)}", module_name="cafetaria")
    
    def update(self):
        """Update cafetaria data from the website"""
        data = {
            "txtLogin": self.username,
            "txtMdp": self.password,
            "y": "19"
        }

        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0', 
            'Accept': '*/*', 
            'Accept-Language': 'en-US,en;q=0.5', 
            'Accept-Encoding': 'gzip, deflate, br, zstd', 
            'Referer': 'https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152', 
            'Origin': 'https://webparent.paiementdp.com'
        }

        session = requests.Session()
        try:
            # Login and get balance
            session.get('https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152')
            resp_main = session.post('https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152', 
                                   data=data, headers=headers)

            if resp_main.status_code == 200:
                soup = BeautifulSoup(resp_main.text, 'html.parser')
                solde_element = soup.find('label', {'for': 'CLI_ID'})
                if solde_element:
                    solde = solde_element.get_text()

                    # Store balance in database
                    dbconn = sqlite3.connect(self.db)
                    dbconn.execute("DELETE FROM solde")
                    dbconn.execute("INSERT INTO solde (solde) VALUES (?)", (solde,))
                    dbconn.commit()
                    dbconn.close()

                    # Check if balance is low
                    pattern = r"(\d+,\d+)"
                    match = re.search(pattern, solde)
                    if match:
                        amount_str = match.group(1)
                        amount = float(amount_str.replace(',', '.'))

                        if amount < 10.0:
                            status = f"Only {amount} euros left on cafetaria credit"
                        else:
                            status = None

                        if status != self.background_status['status']:
                            self.background_status['ts'] = int(time.time())
                            self.background_status['status'] = status

                    else:
                        if tomlogger:
                            tomlogger.error("Could not extract cafetaria credit", module_name="cafetaria")

            # Get reservations
            resp_res_main = session.get('https://webparent.paiementdp.com/aliReservation.php')

            soup2 = BeautifulSoup(resp_res_main.text, 'html.parser')

            pattern = re.compile(r'^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$')

            tds = soup2.find_all('td', id=pattern)

            resas = []

            for td in tds:
                day = td.get('id')
                links = td.find_all('a')
                if links:
                    link = links[0].get('href')
                    parsed_url = urlparse(link)
                    query_params = parse_qs(parsed_url.query)

                    id = query_params.get('date', [None])[0]
                    path = parsed_url.path

                    if path == "aliReservationCancel.php":
                        reserved = True
                    elif path == "aliReservationDetail.php":
                        reserved = False
                    else:
                        reserved = None

                    if reserved is not None:
                        resas.append({"day": day, "id": id, "is_reserved": reserved})

            # Store reservations in database
            for resa in resas:
                dbconn = sqlite3.connect(self.db)
                dbconn.execute("""
                    INSERT OR REPLACE INTO cafetaria (date, id, is_reserved) VALUES (?, ?, ?)
                    """, (resa['day'], resa['id'].rstrip(), resa['is_reserved']))
                dbconn.commit()
                dbconn.close()

            session.get('https://webparent.paiementdp.com/aliDeconnexion.php')

            self.lastUpdate = datetime.now()
            if tomlogger:
                tomlogger.info("Cafetaria updated successfully", module_name="cafetaria")
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Failed to update cafetaria data: {str(e)}", module_name="cafetaria")
            raise

    def change_reservation(self, action: str, id: str) -> bool:
        """Change reservation status (add or cancel)"""
        id = quote(id)
        
        data = {
            "txtLogin": self.username,
            "txtMdp": self.password,
            "y": "19"
        }

        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0', 
            'Accept': '*/*', 
            'Accept-Language': 'en-US,en;q=0.5', 
            'Accept-Encoding': 'gzip, deflate, br, zstd', 
            'Referer': 'https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152', 
            'Origin': 'https://webparent.paiementdp.com'
        }

        session = requests.Session()
        try:
            session.get('https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152')
            session.post('https://webparent.paiementdp.com/aliAuthentification.php?site=aes00152', 
                        data=data, headers=headers)

            if action == "cancel":
                cancel_page = session.get(f"https://webparent.paiementdp.com/aliReservationCancel.php?date={id}", 
                                        headers=headers)

                if cancel_page.status_code != 200:
                    return False

                headers['Referer'] = f"https://webparent.paiementdp.com/aliReservationCancel.php?date={id}"

                values = {
                    "ref": "cancel",
                    "btnOK.x": 42,
                    "btnOK.y": 25,
                    "valide_form": 1
                }

                cancel = session.post('https://webparent.paiementdp.com/aliReservationCancel.php', 
                                    headers=headers, data=values)

                if cancel.status_code != 200:
                    return False

                self.update()
                return True

            if action == "add":
                add_page = session.get(f"https://webparent.paiementdp.com/aliReservationDetail.php?date={id}", 
                                     headers=headers)

                if add_page.status_code != 200:
                    return False

                headers['Referer'] = f"https://webparent.paiementdp.com/aliReservationDetail.php?date={id}"

                values = {
                    "CONS_QUANTITE": 1,
                    "restaurant": 1,
                    "btnOK.x": 69,
                    "btnOK.y": 19,
                    "valide_form": 1
                }

                add = session.post('https://webparent.paiementdp.com/aliReservationDetail.php', 
                                 headers=headers, data=values)

                if add.status_code != 200:
                    return False

                session.get('https://webparent.paiementdp.com/aliDeconnexion.php')
                
                self.update()
                return True
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Failed to change reservation: {str(e)}", module_name="cafetaria")
            return False

    def find_date(self, date_str: str) -> List:
        """Find reservation data for a specific date"""
        dbconn = sqlite3.connect(self.db)
        cursor = dbconn.cursor()
        cursor.execute("SELECT id, is_reserved FROM cafetaria WHERE date = ?", (date_str,))
        entries = cursor.fetchall()
        dbconn.close()
        return entries

    def add_reservation(self, date_str: str) -> Dict[str, str]:
        """Add a cafetaria reservation"""
        self.update()

        resa = self.find_date(date_str)

        if resa:
            res = resa[0]
            id = res[0]
            is_reserved = res[1]

            if is_reserved:
                return {"status": "success", "message": "Reservation was already done"}
            else:
                ret = self.change_reservation(action="add", id=id)
                if ret:
                    return {"status": "success", "message": "Reservation done"}
                else:
                    return {"status": "failure", "message": "Could not make the reservation"}
        else:
            return {"status": "failure", "message": "Date not available for reservation"}

    def cancel_reservation(self, date_str: str) -> Dict[str, str]:
        """Cancel a cafetaria reservation"""
        self.update()

        resa = self.find_date(date_str)

        if resa:
            res = resa[0]
            id = res[0]
            is_reserved = res[1]

            if is_reserved:
                ret = self.change_reservation(action="cancel", id=id)
                if ret:
                    return {"status": "success", "message": "Reservation canceled"}
                else:
                    return {"status": "failure", "message": "Could not cancel the reservation"}
            else:
                return {"status": "success", "message": "Reservation was already canceled"}
        else:
            return {"status": "failure", "message": "Date not found"}

    def list_reservations(self) -> List[Dict[str, Any]]:
        """List cafetaria reservations"""
        if datetime.now() > (self.lastUpdate + timedelta(hours=12)):
            self.update()

        resas = []
        today = date.today().strftime("%Y-%m-%d")

        dbconn = sqlite3.connect(self.db)
        cursor = dbconn.cursor()
        cursor.execute("SELECT date, id, is_reserved FROM cafetaria WHERE date >= ?", (today,))
        entries = cursor.fetchall()
        dbconn.close()

        for entry in entries:
            resas.append({"date": entry[0], "id": entry[1], "is_reserved": entry[2]})

        return resas

    def get_credit(self) -> Optional[str]:
        """Get cafetaria credit balance"""
        if datetime.now() > (self.lastUpdate + timedelta(days=1)):
            self.update()
        
        dbconn = sqlite3.connect(self.db)
        res = dbconn.execute("SELECT solde FROM solde").fetchone()
        dbconn.commit()
        dbconn.close()

        if res:
            return res[0]
        
        return None
    
    def get_notification_status(self) -> str:
        """Get current background notification status"""
        try:
            status = self.background_status.get('status', '')
            return status if status else ""
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error getting notification status: {str(e)}", module_name="cafetaria")
            return ""


# Load configuration and initialize cafetaria service
config = load_config()
cafetaria_service = CafetariaService(config)


@server.tool()
def get_cafetaria_credit() -> str:
    """Get the high school cafetaria credit. For example when a user asks 'How much cafeteria credit do I have?'"""
    if tomlogger:
        tomlogger.info("Tool call: get_cafetaria_credit", module_name="cafetaria")
    
    result = cafetaria_service.get_credit()
    if result:
        return result
    else:
        return "Could not retrieve cafetaria credit"


@server.tool()
def list_cafetaria_reservations() -> str:
    """List the high school cafetaria reservations. For example when a user asks 'Is the cafetaria reserved for this day?'. This function provides high school cafetaria reservations information."""
    if tomlogger:
        tomlogger.info("Tool call: list_cafetaria_reservations", module_name="cafetaria")
    
    result = cafetaria_service.list_reservations()
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def make_a_cafetaria_reservation(date: str) -> str:
    """Make a reservation for high school cafetaria. For example when a user asks 'Book the high school cafetaria for tomorrow'. This function does not provide any reservation information. Must only be used when the user explicitly ask for making a new reservation.
    
    Args:
        date: Day you want to make a cafetaria reservation. Must be in the form of '%Y-%m-%d'. Date is always in the future.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: make_a_cafetaria_reservation with date={date}", module_name="cafetaria")
    
    result = cafetaria_service.add_reservation(date)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def cancel_a_cafetaria_reservation(date: str) -> str:
    """Cancel a reservation for high school cafetaria. For example when a user asks 'Cancel the high school cafetaria reservation for tomorrow'. This function does not provide any reservation information.
    
    Args:
        date: Day you want to cancel the cafetaria reservation. Must be in the form of '%Y-%m-%d'. Date is always in the future.
    """
    if tomlogger:
        tomlogger.info(f"Tool call: cancel_a_cafetaria_reservation with date={date}", module_name="cafetaria")
    
    result = cafetaria_service.cancel_reservation(date)
    return json.dumps(result, ensure_ascii=False)


@server.resource("description://cafetaria")
def description() -> str:
    """Return the server description."""
    return SERVER_DESCRIPTION


@server.resource("description://tom_notification")
def notification_status() -> str:
    """Return current background notification status - cafetaria credit status."""
    return cafetaria_service.get_notification_status()


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting Cafetaria MCP Server on port 80", module_name="cafetaria")
    else:
        print("Starting Cafetaria MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()