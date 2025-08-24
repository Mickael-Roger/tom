#!/usr/bin/env python3
"""
Notifications MCP Server
Provides notification functionality via MCP protocol
Based on the original tomcoremessage.py and tomcorereminder.py modules
"""

import json
import os
import sys
import sqlite3
import threading
import time
import functools
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import firebase_admin
from firebase_admin import credentials, messaging
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
    tomlogger.info(f"🚀 Notifications MCP Server starting with log level: {log_level}", module_name="notifications")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = """This module is used to send instant messages to family members via Firebase notifications and manage reminders. Use this when the user wants to send a message, notification, or alert to another family member immediately, or when they want to be reminded about something at a specific time. For example: 'Send a message to mom saying I'll be late', 'Tell Jennifer that dinner is ready', 'Remind me in 2 hours to take out the laundry', or 'Remind me tomorrow morning at 9 a.m. to buy bread'."""

# Initialize FastMCP server
server = FastMCP(name="notifications-server", stateless_http=True, host="0.0.0.0", port=80)


class NotificationService:
    """Notification service class combining message sending and reminder functionality"""
    
    _firebase_initialized = False
    _update_thread_started = False
    
    def __init__(self):
        # Configuration paths
        self.firebase_config_path = '/data/firebase.json'
        self.db_path = '/data/notifications.sqlite'
        
        # Create data directory if it doesn't exist
        os.makedirs('/data', exist_ok=True)
        
        # Load users from environment (simplified for MCP)
        # In real implementation, this would come from configuration
        self.users = os.environ.get('NOTIFICATION_USERS', 'alice,bob,charlie').split(',')
        
        if tomlogger:
            tomlogger.info(f"Notification service initialized with {len(self.users)} users: {', '.join(self.users)}", module_name="notifications")
        
        # Initialize database
        self._init_database()
        
        # Initialize Firebase
        self._init_firebase()
        
        # Start notification thread
        self._start_notification_thread()
    
    def _init_database(self):
        """Initialize SQLite database with required tables"""
        try:
            dbconn = sqlite3.connect(self.db_path)
            cursor = dbconn.cursor()
            
            # Create notifications table for reminders
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    datetime DATETIME DEFAULT CURRENT_TIMESTAMP,
                    notification DATETIME,
                    sender TEXT,
                    recipient TEXT,
                    sent BOOLEAN DEFAULT 0,
                    message TEXT,
                    recurrence TEXT DEFAULT NULL,
                    next_occurrence DATETIME DEFAULT NULL
                )
            ''')
            
            # Create FCM tokens table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fcm_tokens (
                    token TEXT PRIMARY KEY,
                    username TEXT,
                    platform TEXT,
                    last_update DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create message history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS message_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    datetime DATETIME DEFAULT CURRENT_TIMESTAMP,
                    sender TEXT,
                    recipient TEXT,
                    message TEXT,
                    status TEXT
                )
            ''')
            
            dbconn.commit()
            dbconn.close()
            
            if tomlogger:
                tomlogger.info("Database initialized successfully", module_name="notifications")
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Database initialization error: {e}", module_name="notifications")
            else:
                print(f"Database initialization error: {e}")
    
    def _init_firebase(self):
        """Initialize Firebase Admin SDK"""
        if NotificationService._firebase_initialized:
            return
            
        try:
            if os.path.exists(self.firebase_config_path):
                cred = credentials.Certificate(self.firebase_config_path)
                firebase_admin.initialize_app(cred)
                NotificationService._firebase_initialized = True
                
                if tomlogger:
                    tomlogger.info("Firebase initialized successfully", module_name="notifications")
            else:
                if tomlogger:
                    tomlogger.error(f"Firebase config file not found: {self.firebase_config_path}", module_name="notifications")
                    
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Firebase initialization error: {e}", module_name="notifications")
            else:
                print(f"Firebase initialization error: {e}")
    
    def _start_notification_thread(self):
        """Start background thread to check and send pending notifications"""
        if NotificationService._update_thread_started:
            return
            
        NotificationService._update_thread_started = True
        self.thread = threading.Thread(target=self._notification_worker)
        self.thread.daemon = True
        self.thread.start()
        
        if tomlogger:
            tomlogger.info("Notification background thread started", module_name="notifications")
    
    def _notification_worker(self):
        """Background worker to process pending notifications"""
        while True:
            try:
                if tomlogger:
                    tomlogger.debug("Checking for pending notifications", module_name="notifications")
                
                dbconn = sqlite3.connect(self.db_path)
                cursor = dbconn.cursor()
                
                # Get pending notifications
                cursor.execute("""
                    SELECT id, message, sender, recipient, recurrence, notification 
                    FROM notifications 
                    WHERE sent = 0 AND notification < datetime('now', 'localtime')
                """)
                notifications = cursor.fetchall()
                
                # Get FCM tokens
                cursor.execute("SELECT username, token FROM fcm_tokens WHERE platform LIKE 'android%'")
                tokens = cursor.fetchall()
                dbconn.close()
                
                # Build token dictionary
                token_list = {}
                for token in tokens:
                    username = token[0]
                    if username not in token_list:
                        token_list[username] = []
                    token_list[username].append(token[1])
                
                # Process notifications
                for notification in notifications:
                    notif_id, message, sender, recipient, recurrence, notif_datetime = notification
                    
                    # Send notification
                    success = self._send_firebase_notification(recipient, message, sender, token_list)
                    
                    if success:
                        # Handle recurrence
                        if recurrence:
                            next_occurrence = self._calculate_next_occurrence(notif_datetime, recurrence)
                            if next_occurrence:
                                # Update for next occurrence
                                dbconn = sqlite3.connect(self.db_path)
                                cursor = dbconn.cursor()
                                cursor.execute("""
                                    UPDATE notifications 
                                    SET notification = ?, sent = 0 
                                    WHERE id = ?
                                """, (next_occurrence, notif_id))
                                dbconn.commit()
                                dbconn.close()
                                
                                if tomlogger:
                                    tomlogger.info(f"Recurring reminder rescheduled for {next_occurrence}", module_name="notifications")
                            else:
                                # Mark as sent if no more occurrences
                                self._mark_notification_sent(notif_id)
                        else:
                            # Mark as sent for one-time notifications
                            self._mark_notification_sent(notif_id)
                            
            except Exception as e:
                if tomlogger:
                    tomlogger.error(f"Error in notification worker: {e}", module_name="notifications")
                else:
                    print(f"Error in notification worker: {e}")
            
            time.sleep(60)  # Check every minute
    
    def _calculate_next_occurrence(self, current_datetime: str, recurrence: str) -> Optional[str]:
        """Calculate next occurrence based on recurrence pattern"""
        try:
            current_dt = datetime.strptime(current_datetime, '%Y-%m-%d %H:%M:%S')
            
            if recurrence == 'daily':
                next_dt = current_dt + timedelta(days=1)
            elif recurrence == 'weekly':
                next_dt = current_dt + timedelta(weeks=1)
            elif recurrence == 'monthly':
                # Approximate monthly (30 days)
                next_dt = current_dt + timedelta(days=30)
            else:
                return None
                
            return next_dt.strftime('%Y-%m-%d %H:%M:%S')
            
        except Exception:
            return None
    
    def _mark_notification_sent(self, notification_id: int):
        """Mark notification as sent"""
        try:
            dbconn = sqlite3.connect(self.db_path)
            cursor = dbconn.cursor()
            cursor.execute("UPDATE notifications SET sent = 1 WHERE id = ?", (notification_id,))
            dbconn.commit()
            dbconn.close()
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error marking notification as sent: {e}", module_name="notifications")
    
    def _send_firebase_notification(self, recipient: str, message: str, sender: str, token_list: Dict[str, List[str]]) -> bool:
        """Send Firebase notification to recipient"""
        if not NotificationService._firebase_initialized:
            return False
            
        if recipient not in token_list:
            if tomlogger:
                tomlogger.error(f"No FCM tokens found for user {recipient}", module_name="notifications")
            return False
        
        success_count = 0
        for token in token_list[recipient]:
            try:
                title = f"Message from {sender}" if sender != recipient else "Tom Reminder"
                
                notif = messaging.Message(
                    data={
                        "title": title,
                        "body": message,
                    },
                    token=token,
                )
                
                response = messaging.send(notif)
                success_count += 1
                
                if tomlogger:
                    tomlogger.info(f"Notification sent to {recipient}: {message}", module_name="notifications")
                    
            except Exception as e:
                if tomlogger:
                    tomlogger.error(f"Failed to send notification to token {token}: {e}", module_name="notifications")
        
        return success_count > 0
    
    def send_instant_message(self, message_text: str, message_recipient: str, sender: str = "system") -> Dict[str, Any]:
        """Send an instant message to a user"""
        try:
            # Log message in history
            dbconn = sqlite3.connect(self.db_path)
            cursor = dbconn.cursor()
            cursor.execute("""
                INSERT INTO message_history (sender, recipient, message, status) 
                VALUES (?, ?, ?, 'pending')
            """, (sender, message_recipient, message_text))
            dbconn.commit()
            
            # Get FCM tokens
            cursor.execute("SELECT token FROM fcm_tokens WHERE username = ? AND platform LIKE 'android%'", (message_recipient,))
            tokens = cursor.fetchall()
            dbconn.close()
            
            if not tokens:
                return {"status": "failure", "message": f"No device tokens found for {message_recipient}"}
            
            # Send message to all devices
            sent_count = 0
            for token_row in tokens:
                token = token_row[0]
                
                try:
                    title = f"Message from {sender}"
                    
                    notif = messaging.Message(
                        data={
                            "title": title,
                            "body": message_text,
                        },
                        token=token,
                    )
                    
                    response = messaging.send(notif)
                    sent_count += 1
                    
                    if tomlogger:
                        tomlogger.info(f"Instant message sent to {message_recipient}: {message_text}", module_name="notifications")
                        
                except Exception as e:
                    if tomlogger:
                        tomlogger.error(f"Failed to send message to token {token}: {e}", module_name="notifications")
            
            status = "success" if sent_count > 0 else "failure"
            result_message = f"Message sent to {message_recipient}" if sent_count > 0 else f"Failed to send message to {message_recipient}"
            
            return {"status": status, "message": result_message}
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error in send_instant_message: {e}", module_name="notifications")
            return {"status": "failure", "message": "Could not send message"}
    
    def add_reminder(self, reminder_text: str, reminder_datetime: str, reminder_recipient: str, sender: str = "system", recurrence: str = None) -> Dict[str, Any]:
        """Add a reminder notification"""
        try:
            dbconn = sqlite3.connect(self.db_path)
            cursor = dbconn.cursor()
            cursor.execute("""
                INSERT INTO notifications (notification, message, recipient, sender, recurrence) 
                VALUES (?, ?, ?, ?, ?)
            """, (reminder_datetime, reminder_text, reminder_recipient, sender, recurrence))
            dbconn.commit()
            dbconn.close()
            
            if tomlogger:
                recurrence_info = f" (recurring {recurrence})" if recurrence else ""
                tomlogger.info(f"Reminder added for {reminder_recipient} at {reminder_datetime}{recurrence_info}: {reminder_text}", module_name="notifications")
            
            return {"status": "success", "message": "Reminder added"}
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error adding reminder: {e}", module_name="notifications")
            return {"status": "failure", "message": "Could not add reminder"}
    
    def list_reminders(self, username: str) -> List[Dict[str, Any]]:
        """List pending reminders for a user"""
        try:
            dbconn = sqlite3.connect(self.db_path)
            cursor = dbconn.cursor()
            cursor.execute("""
                SELECT id, notification, message, recurrence 
                FROM notifications 
                WHERE sent = 0 AND recipient = ?
                ORDER BY notification
            """, (username,))
            values = cursor.fetchall()
            dbconn.close()
            
            reminders = []
            for val in values:
                reminder_data = {
                    "id": val[0],
                    "reminder_datetime": val[1],
                    "reminder_message": val[2]
                }
                if val[3]:  # recurrence
                    reminder_data["recurrence"] = val[3]
                reminders.append(reminder_data)
            
            return reminders
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error listing reminders: {e}", module_name="notifications")
            return []
    
    def delete_reminder(self, reminder_id: str) -> Dict[str, Any]:
        """Delete a reminder by ID"""
        try:
            dbconn = sqlite3.connect(self.db_path)
            cursor = dbconn.cursor()
            cursor.execute("DELETE FROM notifications WHERE id = ?", (reminder_id,))
            affected_rows = cursor.rowcount
            dbconn.commit()
            dbconn.close()
            
            if affected_rows > 0:
                if tomlogger:
                    tomlogger.info(f"Reminder {reminder_id} deleted", module_name="notifications")
                return {"status": "success", "message": "Reminder deleted"}
            else:
                return {"status": "failure", "message": "Reminder not found"}
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error deleting reminder: {e}", module_name="notifications")
            return {"status": "failure", "message": "Could not delete reminder"}
    


# Initialize notification service
notification_service = NotificationService()


@server.tool()
def send_instant_message(
    message_text: str,
    message_recipient: str
) -> str:
    """Send an instant message to a family member via mobile notification. This sends the message immediately, not at a scheduled time. Use this when the user wants to communicate with another family member right away. For example: 'Send a message to mom saying I'll be late', 'Tell Jennifer that dinner is ready', or 'Notify dad that I arrived safely'.
    
    Args:
        message_text: The text of the message to send
        message_recipient: Recipient of the message, must be one of the family members
    """
    if tomlogger:
        tomlogger.info(f"Tool call: send_instant_message to {message_recipient}", module_name="notifications")
    
    # Get sender from environment (would be set by the agent)
    sender = os.environ.get('TOM_USERNAME', 'system')
    
    result = notification_service.send_instant_message(message_text, message_recipient, sender)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def add_reminder(
    reminder_text: str,
    reminder_datetime: str,
    reminder_recipient: str,
    recurrence: str = None
) -> str:
    """Function to create a reminder. A reminder is a time-specific notification for the user. The purpose of this function is to prompt the user to perform a specific action at a given time. This is for tasks or events that need a one-time or time-sensitive follow-up. For example: 'Remind me to call my mom tomorrow.', 'Reminder Jennifer to go to school tomorrow at 9am' or 'Remind me at 8 PM to go to sports.' Can also handle recurring reminders like 'Remind me to take my medicine every day at 8am'.
    
    Args:
        reminder_text: The text of the reminder
        reminder_datetime: The datetime you need to remind about this reminder. Must be in the form of 'YYYY-MM-DD HH:MM:SS'
        reminder_recipient: Recipient of the reminder
        recurrence: Optional recurrence pattern ('daily', 'weekly', 'monthly')
    """
    if tomlogger:
        tomlogger.info(f"Tool call: add_reminder for {reminder_recipient} at {reminder_datetime}", module_name="notifications")
    
    # Get sender from environment
    sender = os.environ.get('TOM_USERNAME', 'system')
    
    result = notification_service.add_reminder(reminder_text, reminder_datetime, reminder_recipient, sender, recurrence)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def list_reminders(username: str) -> str:
    """A function to retrieve a list of all active or pending reminders previously set by the user. This function provides an overview of scheduled reminders and their corresponding times. For example: 'List all my reminders.' or 'What reminders do I have?'
    
    Args:
        username: Username to list reminders for
    """
    if tomlogger:
        tomlogger.info(f"Tool call: list_reminders for {username}", module_name="notifications")
    
    result = notification_service.list_reminders(username)
    return json.dumps(result, ensure_ascii=False)


@server.tool()
def delete_reminder(reminder_id: str) -> str:
    """A function to delete a specific reminder previously set by the user. The function allows the user to specify which reminder to remove by referencing its ID. This ensures users can manage their reminders efficiently by removing completed or outdated ones. For example: 'Delete reminder 123', 'Remove the reminder with ID 456'.
    
    Args:
        reminder_id: ID of the reminder to delete
    """
    if tomlogger:
        tomlogger.info(f"Tool call: delete_reminder with ID {reminder_id}", module_name="notifications")
    
    result = notification_service.delete_reminder(reminder_id)
    return json.dumps(result, ensure_ascii=False)


@server.resource("description://notifications")
def description() -> str:
    """Return server description."""
    return SERVER_DESCRIPTION




def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting Notifications MCP Server on port 80", module_name="notifications")
    else:
        print("Starting Notifications MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()