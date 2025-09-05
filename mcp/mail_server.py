#!/usr/bin/env python3
"""
Mail MCP Server
Provides email management functionality via MCP protocol
Handles IMAP and SMTP operations for email reading and sending
"""

import json
import os
import sys
import yaml
import imaplib
import smtplib
import email
import time
import threading
from datetime import datetime
from typing import Any, Dict, Optional, List
try:
    from email.mime.text import MIMEText as MimeText
    from email.mime.multipart import MIMEMultipart as MimeMultipart
except ImportError:
    from email.mime.text import MimeText
    from email.mime.multipart import MimeMultipart
from email.header import decode_header
import ssl

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

# Always import logging for log level control
import logging

# Initialize logging
log_level = os.environ.get('TOM_LOG_LEVEL', 'INFO')
if tomlogger:
    logger = init_logger(log_level)
    tomlogger.info(f"🚀 Mail MCP Server starting with log level: {log_level}", module_name="mail")
else:
    logger = logging.getLogger(__name__)

# Disable FastMCP and uvicorn logging
logging.getLogger("uvicorn").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("fastmcp").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)

# Server configuration and description
SERVER_DESCRIPTION = "This module is used for email management. It provides functionality to read emails, send emails, list new emails, and search through email content."

# Initialize FastMCP server
server = FastMCP(name="email", stateless_http=True, host="0.0.0.0", port=80)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file"""
    config_path = '/data/config.yml'
    
    if tomlogger:
        tomlogger.info(f"Loading configuration from {config_path}", module_name="mail")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        if tomlogger:
            tomlogger.error(f"Configuration file not found: {config_path}", module_name="mail")
        else:
            print(f"ERROR: Configuration file not found: {config_path}")
        return {}
    except yaml.YAMLError as exc:
        if tomlogger:
            tomlogger.error(f"Error parsing YAML configuration: {exc}", module_name="mail")
        else:
            print(f"ERROR: Error parsing YAML configuration: {exc}")
        return {}


class MailService:
    """Mail service class for handling IMAP and SMTP operations"""
    
    def __init__(self, config: Dict[str, Any]):
        # Load mail configuration from config
        mail_config = config.get('mail', {})
        
        # Validate required config fields
        required_smtp_fields = ['host', 'port', 'username', 'password', 'from']
        required_imap_fields = ['host', 'port', 'username', 'password']
        
        smtp_config = mail_config.get('smtp', {})
        imap_config = mail_config.get('imap', {})
        
        for field in required_smtp_fields:
            if field not in smtp_config:
                raise KeyError(f"Missing required SMTP config field: {field}")
        
        for field in required_imap_fields:
            if field not in imap_config:
                raise KeyError(f"Missing required IMAP config field: {field}")
        
        self.smtp_config = smtp_config
        self.imap_config = imap_config
        
        # Background status tracking
        self.background_status = {"ts": int(time.time()), "status": None}
        
        # Test connections
        self._test_connections()
        
        if tomlogger:
            tomlogger.info(f"✅ Mail service initialized successfully", module_name="mail")
    
    def _test_connections(self):
        """Test SMTP and IMAP connections"""
        try:
            # Test SMTP connection
            with smtplib.SMTP_SSL(self.smtp_config['host'], self.smtp_config['port']) as smtp:
                smtp.login(self.smtp_config['username'], self.smtp_config['password'])
            
            # Test IMAP connection
            with imaplib.IMAP4_SSL(self.imap_config['host'], self.imap_config['port']) as imap:
                imap.login(self.imap_config['username'], self.imap_config['password'])
                imap.select('INBOX')
            
            if tomlogger:
                tomlogger.info(f"✅ Mail connections tested successfully", module_name="mail")
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Mail connection test failed: {str(e)}", module_name="mail")
            raise
    
    def list_new_emails(self) -> str:
        """List new (unread) emails from INBOX"""
        try:
            with imaplib.IMAP4_SSL(self.imap_config['host'], self.imap_config['port']) as imap:
                imap.login(self.imap_config['username'], self.imap_config['password'])
                imap.select('INBOX')
                
                # Search for unseen emails
                status, messages = imap.search(None, 'UNSEEN')
                
                if status != 'OK':
                    return json.dumps({"error": "Failed to search for new emails"}, ensure_ascii=False)
                
                email_ids = messages[0].split()
                
                if not email_ids:
                    return json.dumps({"status": "success", "message": "No new emails", "emails": []}, ensure_ascii=False)
                
                emails = []
                for email_id in email_ids[-20:]:  # Get last 20 new emails
                    try:
                        status, msg_data = imap.fetch(email_id, '(BODY.PEEK[])')
                        if status == 'OK':
                            email_message = email.message_from_bytes(msg_data[0][1])
                            
                            # Decode subject
                            subject = email_message.get('Subject', '')
                            if subject:
                                decoded_subject = decode_header(subject)[0]
                                if isinstance(decoded_subject[0], bytes):
                                    subject = decoded_subject[0].decode(decoded_subject[1] or 'utf-8')
                                else:
                                    subject = decoded_subject[0]
                            
                            # Decode sender
                            sender = email_message.get('From', '')
                            if sender:
                                decoded_sender = decode_header(sender)[0]
                                if isinstance(decoded_sender[0], bytes):
                                    sender = decoded_sender[0].decode(decoded_sender[1] or 'utf-8')
                                else:
                                    sender = decoded_sender[0]
                            
                            emails.append({
                                "id": email_id.decode(),
                                "subject": subject,
                                "from": sender,
                                "date": email_message.get('Date', ''),
                                "size": len(msg_data[0][1])
                            })
                    except Exception as e:
                        if tomlogger:
                            tomlogger.error(f"Error processing email {email_id}: {str(e)}", module_name="mail")
                        continue
                
                result = {
                    "status": "success",
                    "count": len(emails),
                    "emails": emails
                }
                
                if tomlogger:
                    tomlogger.info(f"Retrieved {len(emails)} new emails", module_name="mail")
                
                return json.dumps(result, ensure_ascii=False)
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error listing new emails: {str(e)}", module_name="mail")
            return json.dumps({"error": f"Failed to list emails: {str(e)}"}, ensure_ascii=False)
    
    def get_email_content(self, email_id: str) -> str:
        """Get full content of a specific email"""
        try:
            with imaplib.IMAP4_SSL(self.imap_config['host'], self.imap_config['port']) as imap:
                imap.login(self.imap_config['username'], self.imap_config['password'])
                imap.select('INBOX')
                
                status, msg_data = imap.fetch(email_id.encode(), '(BODY.PEEK[])')
                if status != 'OK':
                    return json.dumps({"error": "Failed to fetch email"}, ensure_ascii=False)
                
                email_message = email.message_from_bytes(msg_data[0][1])
                
                # Extract email content
                content = {
                    "id": email_id,
                    "subject": "",
                    "from": "",
                    "to": "",
                    "date": "",
                    "body": ""
                }
                
                # Decode headers
                for header in ['Subject', 'From', 'To', 'Date']:
                    value = email_message.get(header, '')
                    if value:
                        try:
                            decoded_value = decode_header(value)[0]
                            if isinstance(decoded_value[0], bytes):
                                content[header.lower()] = decoded_value[0].decode(decoded_value[1] or 'utf-8')
                            else:
                                content[header.lower()] = decoded_value[0]
                        except:
                            content[header.lower()] = value
                
                # Extract body
                if email_message.is_multipart():
                    for part in email_message.walk():
                        content_type = part.get_content_type()
                        if content_type == "text/plain":
                            try:
                                body = part.get_payload(decode=True)
                                if isinstance(body, bytes):
                                    content["body"] = body.decode('utf-8')
                                else:
                                    content["body"] = body
                                break
                            except:
                                continue
                else:
                    try:
                        body = email_message.get_payload(decode=True)
                        if isinstance(body, bytes):
                            content["body"] = body.decode('utf-8')
                        else:
                            content["body"] = body
                    except:
                        content["body"] = email_message.get_payload()
                
                if tomlogger:
                    tomlogger.info(f"Retrieved content for email {email_id}", module_name="mail")
                
                return json.dumps(content, ensure_ascii=False)
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error getting email content {email_id}: {str(e)}", module_name="mail")
            return json.dumps({"error": f"Failed to get email content: {str(e)}"}, ensure_ascii=False)
    
    def send_email(self, to: str, subject: str, body: str, cc: str = "", bcc: str = "") -> str:
        """Send an email"""
        try:
            # Create message
            msg = MimeMultipart()
            msg['From'] = self.smtp_config['from']
            msg['To'] = to
            msg['Subject'] = subject
            
            if cc:
                msg['Cc'] = cc
            
            # Attach body
            msg.attach(MimeText(body, 'plain', 'utf-8'))
            
            # Prepare recipients list
            recipients = [to]
            if cc:
                recipients.extend([addr.strip() for addr in cc.split(',')])
            if bcc:
                recipients.extend([addr.strip() for addr in bcc.split(',')])
            
            # Send email
            with smtplib.SMTP_SSL(self.smtp_config['host'], self.smtp_config['port']) as smtp:
                smtp.login(self.smtp_config['username'], self.smtp_config['password'])
                smtp.send_message(msg, to_addrs=recipients)
            
            result = {
                "status": "success",
                "message": "Email sent successfully",
                "to": to,
                "subject": subject
            }
            
            if tomlogger:
                tomlogger.info(f"Email sent to {to} with subject '{subject}'", module_name="mail")
            
            return json.dumps(result, ensure_ascii=False)
            
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error sending email: {str(e)}", module_name="mail")
            return json.dumps({"error": f"Failed to send email: {str(e)}"}, ensure_ascii=False)
    
    def list_recent_emails(self, count: int = 10) -> str:
        """List the most recent emails (read and unread) from INBOX"""
        try:
            with imaplib.IMAP4_SSL(self.imap_config['host'], self.imap_config['port']) as imap:
                imap.login(self.imap_config['username'], self.imap_config['password'])
                imap.select('INBOX')
                
                # Search for all emails
                status, messages = imap.search(None, 'ALL')
                
                if status != 'OK':
                    return json.dumps({"error": "Failed to search for emails"}, ensure_ascii=False)
                
                email_ids = messages[0].split()
                
                if not email_ids:
                    return json.dumps({"status": "success", "message": "No emails found", "emails": []}, ensure_ascii=False)
                
                # Get the most recent emails (email IDs are usually in chronological order)
                recent_email_ids = email_ids[-count:]
                
                emails = []
                for email_id in reversed(recent_email_ids):  # Most recent first
                    try:
                        status, msg_data = imap.fetch(email_id, '(BODY.PEEK[])')
                        if status == 'OK':
                            email_message = email.message_from_bytes(msg_data[0][1])
                            
                            # Check if email is read or unread
                            status, flags = imap.fetch(email_id, '(FLAGS)')
                            is_read = b'\\Seen' in flags[0] if status == 'OK' else False
                            
                            # Decode subject
                            subject = email_message.get('Subject', '')
                            if subject:
                                decoded_subject = decode_header(subject)[0]
                                if isinstance(decoded_subject[0], bytes):
                                    subject = decoded_subject[0].decode(decoded_subject[1] or 'utf-8')
                                else:
                                    subject = decoded_subject[0]
                            
                            # Decode sender
                            sender = email_message.get('From', '')
                            if sender:
                                decoded_sender = decode_header(sender)[0]
                                if isinstance(decoded_sender[0], bytes):
                                    sender = decoded_sender[0].decode(decoded_sender[1] or 'utf-8')
                                else:
                                    sender = decoded_sender[0]
                            
                            emails.append({
                                "id": email_id.decode(),
                                "subject": subject,
                                "from": sender,
                                "date": email_message.get('Date', ''),
                                "read": is_read,
                                "size": len(msg_data[0][1])
                            })
                    except Exception as e:
                        if tomlogger:
                            tomlogger.error(f"Error processing email {email_id}: {str(e)}", module_name="mail")
                        continue
                
                result = {
                    "status": "success",
                    "count": len(emails),
                    "emails": emails
                }
                
                if tomlogger:
                    tomlogger.info(f"Retrieved {len(emails)} recent emails", module_name="mail")
                
                return json.dumps(result, ensure_ascii=False)
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error listing recent emails: {str(e)}", module_name="mail")
            return json.dumps({"error": f"Failed to list recent emails: {str(e)}"}, ensure_ascii=False)

    def search_emails(self, query: str, max_results: int = 10) -> str:
        """Search emails by subject or content"""
        try:
            with imaplib.IMAP4_SSL(self.imap_config['host'], self.imap_config['port']) as imap:
                imap.login(self.imap_config['username'], self.imap_config['password'])
                imap.select('INBOX')
                
                # Search by subject first
                status, messages = imap.search(None, f'SUBJECT "{query}"')
                email_ids = messages[0].split() if status == 'OK' else []
                
                # If not enough results, search in body (if server supports it)
                if len(email_ids) < max_results:
                    try:
                        status, body_messages = imap.search(None, f'BODY "{query}"')
                        if status == 'OK':
                            body_email_ids = body_messages[0].split()
                            # Combine and deduplicate
                            email_ids = list(set(email_ids + body_email_ids))
                    except:
                        pass  # Body search not supported by all servers
                
                if not email_ids:
                    return json.dumps({"status": "success", "message": "No emails found", "emails": []}, ensure_ascii=False)
                
                # Sort by most recent first and limit results
                email_ids = email_ids[-max_results:]
                
                emails = []
                for email_id in reversed(email_ids):  # Most recent first
                    try:
                        status, msg_data = imap.fetch(email_id, '(BODY.PEEK[])')
                        if status == 'OK':
                            email_message = email.message_from_bytes(msg_data[0][1])
                            
                            # Decode subject and sender
                            subject = email_message.get('Subject', '')
                            if subject:
                                try:
                                    decoded_subject = decode_header(subject)[0]
                                    if isinstance(decoded_subject[0], bytes):
                                        subject = decoded_subject[0].decode(decoded_subject[1] or 'utf-8')
                                    else:
                                        subject = decoded_subject[0]
                                except:
                                    pass
                            
                            sender = email_message.get('From', '')
                            if sender:
                                try:
                                    decoded_sender = decode_header(sender)[0]
                                    if isinstance(decoded_sender[0], bytes):
                                        sender = decoded_sender[0].decode(decoded_sender[1] or 'utf-8')
                                    else:
                                        sender = decoded_sender[0]
                                except:
                                    pass
                            
                            emails.append({
                                "id": email_id.decode(),
                                "subject": subject,
                                "from": sender,
                                "date": email_message.get('Date', '')
                            })
                    except Exception as e:
                        if tomlogger:
                            tomlogger.error(f"Error processing search result {email_id}: {str(e)}", module_name="mail")
                        continue
                
                result = {
                    "status": "success",
                    "query": query,
                    "count": len(emails),
                    "emails": emails
                }
                
                if tomlogger:
                    tomlogger.info(f"Search for '{query}' returned {len(emails)} emails", module_name="mail")
                
                return json.dumps(result, ensure_ascii=False)
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error searching emails: {str(e)}", module_name="mail")
            return json.dumps({"error": f"Failed to search emails: {str(e)}"}, ensure_ascii=False)
    
    def mark_email_as_read(self, email_id: str) -> str:
        """Mark an email as read"""
        try:
            with imaplib.IMAP4_SSL(self.imap_config['host'], self.imap_config['port']) as imap:
                imap.login(self.imap_config['username'], self.imap_config['password'])
                imap.select('INBOX')
                
                imap.store(email_id.encode(), '+FLAGS', '\\Seen')
                
                result = {
                    "status": "success",
                    "message": "Email marked as read",
                    "email_id": email_id
                }
                
                if tomlogger:
                    tomlogger.info(f"Marked email {email_id} as read", module_name="mail")
                
                return json.dumps(result, ensure_ascii=False)
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error marking email as read: {str(e)}", module_name="mail")
            return json.dumps({"error": f"Failed to mark email as read: {str(e)}"}, ensure_ascii=False)
    
    def mark_email_as_unread(self, email_id: str) -> str:
        """Mark an email as unread"""
        try:
            with imaplib.IMAP4_SSL(self.imap_config['host'], self.imap_config['port']) as imap:
                imap.login(self.imap_config['username'], self.imap_config['password'])
                imap.select('INBOX')
                
                imap.store(email_id.encode(), '-FLAGS', '\\Seen')
                
                result = {
                    "status": "success",
                    "message": "Email marked as unread",
                    "email_id": email_id
                }
                
                if tomlogger:
                    tomlogger.info(f"Marked email {email_id} as unread", module_name="mail")
                
                return json.dumps(result, ensure_ascii=False)
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error marking email as unread: {str(e)}", module_name="mail")
            return json.dumps({"error": f"Failed to mark email as unread: {str(e)}"}, ensure_ascii=False)
    
    def delete_email(self, email_id: str) -> str:
        """Delete an email (move to trash/deleted folder)"""
        try:
            with imaplib.IMAP4_SSL(self.imap_config['host'], self.imap_config['port']) as imap:
                imap.login(self.imap_config['username'], self.imap_config['password'])
                imap.select('INBOX')
                
                # Mark email as deleted
                imap.store(email_id.encode(), '+FLAGS', '\\Deleted')
                
                # Expunge to move to trash (some servers do this automatically)
                try:
                    imap.expunge()
                except:
                    # Some servers don't support expunge or handle it differently
                    pass
                
                result = {
                    "status": "success",
                    "message": "Email deleted (moved to trash)",
                    "email_id": email_id
                }
                
                if tomlogger:
                    tomlogger.info(f"Deleted email {email_id}", module_name="mail")
                
                return json.dumps(result, ensure_ascii=False)
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error deleting email: {str(e)}", module_name="mail")
            return json.dumps({"error": f"Failed to delete email: {str(e)}"}, ensure_ascii=False)
    
    def create_folder(self, folder_name: str) -> str:
        """Create a new folder/mailbox"""
        try:
            with imaplib.IMAP4_SSL(self.imap_config['host'], self.imap_config['port']) as imap:
                imap.login(self.imap_config['username'], self.imap_config['password'])
                
                # Create folder
                status, response = imap.create(folder_name)
                
                if status != 'OK':
                    return json.dumps({"error": f"Failed to create folder: {response[0].decode() if response else 'Unknown error'}"}, ensure_ascii=False)
                
                result = {
                    "status": "success",
                    "message": "Folder created successfully",
                    "folder_name": folder_name
                }
                
                if tomlogger:
                    tomlogger.info(f"Created folder '{folder_name}'", module_name="mail")
                
                return json.dumps(result, ensure_ascii=False)
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error creating folder: {str(e)}", module_name="mail")
            return json.dumps({"error": f"Failed to create folder: {str(e)}"}, ensure_ascii=False)
    
    def list_folders(self) -> str:
        """List all folders/mailboxes"""
        try:
            with imaplib.IMAP4_SSL(self.imap_config['host'], self.imap_config['port']) as imap:
                imap.login(self.imap_config['username'], self.imap_config['password'])
                
                # List all folders
                status, folders = imap.list()
                
                if status != 'OK':
                    return json.dumps({"error": "Failed to list folders"}, ensure_ascii=False)
                
                folder_list = []
                for folder in folders:
                    if folder:
                        folder_str = folder.decode()
                        # Extract folder name from IMAP LIST response
                        # Format is typically: (flags) "delimiter" "folder_name"
                        parts = folder_str.split('"')
                        if len(parts) >= 3:
                            folder_name = parts[-2]
                            # Get folder flags (first part)
                            flags = parts[0].strip('() ')
                            folder_list.append({
                                "name": folder_name,
                                "flags": flags
                            })
                
                result = {
                    "status": "success",
                    "count": len(folder_list),
                    "folders": folder_list
                }
                
                if tomlogger:
                    tomlogger.info(f"Listed {len(folder_list)} folders", module_name="mail")
                
                return json.dumps(result, ensure_ascii=False)
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error listing folders: {str(e)}", module_name="mail")
            return json.dumps({"error": f"Failed to list folders: {str(e)}"}, ensure_ascii=False)
    
    def move_email_to_folder(self, email_id: str, folder_name: str) -> str:
        """Move an email to a specific folder"""
        try:
            with imaplib.IMAP4_SSL(self.imap_config['host'], self.imap_config['port']) as imap:
                imap.login(self.imap_config['username'], self.imap_config['password'])
                imap.select('INBOX')
                
                # Check if target folder exists
                status, folders = imap.list()
                folder_exists = False
                if status == 'OK':
                    for folder in folders:
                        if folder:
                            folder_str = folder.decode()
                            if folder_name in folder_str:
                                folder_exists = True
                                break
                
                if not folder_exists:
                    return json.dumps({"error": f"Target folder '{folder_name}' does not exist"}, ensure_ascii=False)
                
                # Copy email to target folder
                copy_status, copy_response = imap.copy(email_id.encode(), folder_name)
                if copy_status != 'OK':
                    return json.dumps({"error": f"Failed to copy email to folder: {copy_response[0].decode() if copy_response else 'Unknown error'}"}, ensure_ascii=False)
                
                # Mark original email as deleted
                imap.store(email_id.encode(), '+FLAGS', '\\Deleted')
                
                # Expunge to remove from INBOX
                try:
                    imap.expunge()
                except:
                    # Some servers don't support expunge or handle it differently
                    pass
                
                result = {
                    "status": "success",
                    "message": f"Email moved to folder '{folder_name}'",
                    "email_id": email_id,
                    "folder_name": folder_name
                }
                
                if tomlogger:
                    tomlogger.info(f"Moved email {email_id} to folder '{folder_name}'", module_name="mail")
                
                return json.dumps(result, ensure_ascii=False)
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f"Error moving email to folder: {str(e)}", module_name="mail")
            return json.dumps({"error": f"Failed to move email to folder: {str(e)}"}, ensure_ascii=False)


# Load configuration and initialize mail service
config = load_config()
mail_service = MailService(config)


@server.tool()
def list_new_emails() -> str:
    """List all new (unread) emails from the inbox. Returns email ID, subject, sender, date and size for each new email."""
    if tomlogger:
        tomlogger.info("Tool call: list_new_emails", module_name="mail")
    
    return mail_service.list_new_emails()


@server.tool()
def get_email_content(email_id: str) -> str:
    """Get the full content of a specific email including headers and body.
    
    Args:
        email_id: ID of the email to retrieve (obtained from list_new_emails or search_emails)
    """
    if tomlogger:
        tomlogger.info(f"Tool call: get_email_content with email_id={email_id}", module_name="mail")
    
    return mail_service.get_email_content(email_id)


@server.tool()
def send_email(to: str, subject: str, body: str, cc: str = "", bcc: str = "") -> str:
    """Send an email to one or more recipients.
    
    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body content
        cc: Optional CC recipients (comma-separated)
        bcc: Optional BCC recipients (comma-separated)
    """
    if tomlogger:
        tomlogger.info(f"Tool call: send_email to={to} subject='{subject}'", module_name="mail")
    
    return mail_service.send_email(to, subject, body, cc, bcc)


@server.tool()
def list_recent_emails(count: int = 10) -> str:
    """List the most recent emails from the inbox, ordered from newest to oldest.
    
    Args:
        count: Number of recent emails to retrieve (default: 10)
    """
    if tomlogger:
        tomlogger.info(f"Tool call: list_recent_emails count={count}", module_name="mail")
    
    return mail_service.list_recent_emails(count)


@server.tool()
def search_emails(query: str, max_results: int = 10) -> str:
    """Search emails by subject or content.
    
    Args:
        query: Search term to look for in email subjects and content
        max_results: Maximum number of results to return (default: 10)
    """
    if tomlogger:
        tomlogger.info(f"Tool call: search_emails query='{query}' max_results={max_results}", module_name="mail")
    
    return mail_service.search_emails(query, max_results)


@server.tool()
def mark_email_as_read(email_id: str) -> str:
    """Mark a specific email as read.
    
    Args:
        email_id: ID of the email to mark as read
    """
    if tomlogger:
        tomlogger.info(f"Tool call: mark_email_as_read with email_id={email_id}", module_name="mail")
    
    return mail_service.mark_email_as_read(email_id)


@server.tool()
def mark_email_as_unread(email_id: str) -> str:
    """Mark a specific email as unread.
    
    Args:
        email_id: ID of the email to mark as unread
    """
    if tomlogger:
        tomlogger.info(f"Tool call: mark_email_as_unread with email_id={email_id}", module_name="mail")
    
    return mail_service.mark_email_as_unread(email_id)


@server.tool()
def delete_email(email_id: str) -> str:
    """Delete a specific email (move to trash/deleted folder).
    
    Args:
        email_id: ID of the email to delete
    """
    if tomlogger:
        tomlogger.info(f"Tool call: delete_email with email_id={email_id}", module_name="mail")
    
    return mail_service.delete_email(email_id)


@server.tool()
def create_folder(folder_name: str) -> str:
    """Create a new folder/mailbox.
    
    Args:
        folder_name: Name of the folder to create
    """
    if tomlogger:
        tomlogger.info(f"Tool call: create_folder with folder_name={folder_name}", module_name="mail")
    
    return mail_service.create_folder(folder_name)


@server.tool()
def list_folders() -> str:
    """List all available folders/mailboxes. Returns folder names and flags."""
    if tomlogger:
        tomlogger.info("Tool call: list_folders", module_name="mail")
    
    return mail_service.list_folders()


@server.tool()
def move_email_to_folder(email_id: str, folder_name: str) -> str:
    """Move an email to a specific folder.
    
    Args:
        email_id: ID of the email to move
        folder_name: Name of the target folder
    """
    if tomlogger:
        tomlogger.info(f"Tool call: move_email_to_folder with email_id={email_id} folder_name={folder_name}", module_name="mail")
    
    return mail_service.move_email_to_folder(email_id, folder_name)


@server.resource("description://mail")
def description() -> str:
    """Return the server description."""
    return SERVER_DESCRIPTION


@server.resource("description://tom_notification")
def notification_status() -> str:
    """Return current background notification status - number of unread emails."""
    try:
        # Get count of unread emails
        result = mail_service.list_new_emails()
        data = json.loads(result)
        
        if "count" in data and data["count"] > 0:
            return f"{data['count']} new emails"
        else:
            return ""  # No status to report when no unread emails
            
    except Exception as e:
        if tomlogger:
            tomlogger.error(f"Error getting notification status: {str(e)}", module_name="mail")
        return ""  # Return empty string on error to avoid breaking the system


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting Mail MCP Server on port 80", module_name="mail")
    else:
        print("Starting Mail MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
