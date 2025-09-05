#!/usr/bin/env python3
"""
Tom Chatbot Server - Refactored Version
Configuration-driven web server for Tom chatbot
"""

import cherrypy
import yaml
import os
import json
import sys
import sqlite3
import logging
import requests
from typing import Dict, Any, Optional

# Add lib directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))
from tomlogger import init_logger, logger, set_log_context
import tomlogger

# Global configuration storage
global_config: Dict[str, Any] = {}


def init_config(config_path: str = '/data/config.yml') -> Dict[str, Any]:
    """Load configuration from YAML file"""
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        print(f"ERROR: Configuration file not found: {config_path}")
        sys.exit(1)
    except yaml.YAMLError as exc:
        print(f"ERROR: Error parsing YAML configuration: {exc}")
        sys.exit(1)




class TomWebService:
    """Main web service class for Tom chatbot"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.users = {user['username']: user for user in config['users']}
        
    def _get_static_file(self, filename: str) -> str:
        """Helper to read static files"""
        try:
            filepath = os.path.join('static', filename)
            with open(filepath, 'r', encoding='utf-8') as file:
                return file.read()
        except FileNotFoundError:
            raise cherrypy.HTTPError(404, f"File not found: {filename}")
        except Exception as e:
            raise cherrypy.HTTPError(500, f"Error reading file: {str(e)}")

    def _check_auth(self) -> bool:
        """Check if current session is authenticated"""
        username = cherrypy.session.get('username')
        if username and username in self.users:
            return True
        return False

    def _validate_credentials(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Validate user credentials"""
        user = self.users.get(username)
        if user and user['password'] == password:
            return user
        return None

    def _proxy_request(self, endpoint: str) -> str:
        """Proxy request to user's backend container"""
        if not self._check_auth():
            raise cherrypy.HTTPError(401, "Authentication required")
            
        username = cherrypy.session['username']
        
        # Build target URL
        target_url = f"http://{username}:8080{endpoint}"
        
        # Get original request data
        method = cherrypy.request.method
        headers = dict(cherrypy.request.headers)
        query_string = cherrypy.request.query_string
        
        # Remove host-specific headers that shouldn't be forwarded
        headers_to_remove = ['host', 'content-length']
        for header in headers_to_remove:
            headers.pop(header, None)
        
        # Add query string if present
        if query_string:
            target_url += f"?{query_string}"
        
        try:
            # Get request body for POST/PUT requests
            body = None
            if method in ['POST', 'PUT', 'PATCH']:
                if hasattr(cherrypy.request, 'json') and cherrypy.request.json:
                    body = json.dumps(cherrypy.request.json)
                    headers['content-type'] = 'application/json'
                else:
                    # Handle form data or raw body
                    body = cherrypy.request.body.read()
                    if isinstance(body, bytes):
                        body = body.decode('utf-8')
            
            tomlogger.debug(f"Proxying {method} {endpoint} to {target_url}", username, "web", "proxy")
            
            # Make the proxy request
            response = requests.request(
                method=method,
                url=target_url,
                headers=headers,
                data=body,
                timeout=30,
                allow_redirects=False
            )
            
            # Set response headers
            for header_name, header_value in response.headers.items():
                # Skip headers that shouldn't be forwarded
                if header_name.lower() not in ['content-encoding', 'content-length', 'transfer-encoding']:
                    cherrypy.response.headers[header_name] = header_value
            
            # Set response status
            cherrypy.response.status = response.status_code
            
            tomlogger.debug(f"Proxy response: {response.status_code}", username, "web", "proxy")
            
            return response.content
            
        except requests.exceptions.ConnectionError:
            tomlogger.error(f"Backend connection failed for user {username}", username, "web", "proxy")
            raise cherrypy.HTTPError(503, f"Backend service unavailable for user {username}")
        except requests.exceptions.Timeout:
            tomlogger.error(f"Backend timeout for user {username}", username, "web", "proxy")
            raise cherrypy.HTTPError(504, f"Backend timeout for user {username}")
        except Exception as e:
            tomlogger.error(f"Proxy error for user {username}: {str(e)}", username, "web", "proxy")
            raise cherrypy.HTTPError(500, f"Proxy error: {str(e)}")

    def _proxy_memory_request(self, endpoint: str) -> str:
        """Proxy request to user's memory service container"""
        if not self._check_auth():
            raise cherrypy.HTTPError(401, "Authentication required")
            
        username = cherrypy.session['username']
        
        # Build target URL to memory service
        target_url = f"http://memory-{username}:8080{endpoint}"
        
        # Get original request data
        method = cherrypy.request.method
        headers = dict(cherrypy.request.headers)
        query_string = cherrypy.request.query_string
        
        # Remove host-specific headers that shouldn't be forwarded
        headers_to_remove = ['host', 'content-length']
        for header in headers_to_remove:
            headers.pop(header, None)
        
        # Add query string if present
        if query_string:
            target_url += f"?{query_string}"
        
        try:
            # Get request body for POST/PUT requests
            body = None
            content_length = int(cherrypy.request.headers.get('Content-Length', 0))
            
            if method in ['POST', 'PUT', 'PATCH'] or (method == 'DELETE' and content_length > 0):
                if hasattr(cherrypy.request, 'json') and cherrypy.request.json:
                    body = json.dumps(cherrypy.request.json)
                    headers['content-type'] = 'application/json'
                elif content_length > 0:
                    # Handle form data or raw body only if there is content
                    try:
                        body = cherrypy.request.body.read()
                    except TypeError:
                        # Handle different CherryPy versions
                        body = cherrypy.request.body.read(content_length)
                    if isinstance(body, bytes):
                        body = body.decode('utf-8')
            
            tomlogger.debug(f"Proxying {method} {endpoint} to memory service {target_url}", username, "web", "memory")
            
            # Make the proxy request
            response = requests.request(
                method=method,
                url=target_url,
                headers=headers,
                data=body,
                timeout=30,
                allow_redirects=False
            )
            
            # Set response headers
            for header_name, header_value in response.headers.items():
                # Skip headers that shouldn't be forwarded
                if header_name.lower() not in ['content-encoding', 'content-length', 'transfer-encoding']:
                    cherrypy.response.headers[header_name] = header_value
            
            # Set response status
            cherrypy.response.status = response.status_code
            
            tomlogger.debug(f"Memory proxy response: {response.status_code}", username, "web", "memory")
            
            return response.content
            
        except requests.exceptions.ConnectionError:
            tomlogger.error(f"Memory service connection failed for user {username}", username, "web", "memory")
            raise cherrypy.HTTPError(503, f"Memory service unavailable for user {username}")
        except requests.exceptions.Timeout:
            tomlogger.error(f"Memory service timeout for user {username}", username, "web", "memory")
            raise cherrypy.HTTPError(504, f"Memory service timeout for user {username}")
        except Exception as e:
            tomlogger.error(f"Memory proxy error for user {username}: {str(e)}", username, "web", "memory")
            raise cherrypy.HTTPError(500, f"Memory proxy error: {str(e)}")

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['GET'])
    def index(self):
        """Main index page"""
        if not self._check_auth():
            raise cherrypy.HTTPRedirect("/auth")
        
        return self._get_static_file('index.html')

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['GET', 'POST'])
    def auth(self):
        """Authentication page"""
        return self._get_static_file('auth.html')

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['GET', 'POST'])
    def login(self, username: str, password: str):
        """Handle login requests"""
        user = self._validate_credentials(username, password)
        
        if user:
            # Set session
            cherrypy.session['username'] = username
            
            tomlogger.info(f"🔐 Auth login: {username}", username, "web", "system")
            raise cherrypy.HTTPRedirect("/index")
        else:
            tomlogger.warning(f"🔒 Auth login failed: {username}", username, "web", "system")
            return "Invalid credentials. <a href='/auth'>Try again</a>"

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['GET', 'POST'])
    def logout(self):
        """Handle logout requests"""
        username = cherrypy.session.get('username', 'unknown')
        cherrypy.session.clear()
        tomlogger.info(f"🔐 Auth logout: {username}", username, "web", "system")
        raise cherrypy.HTTPRedirect("/auth")

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['GET'])
    @cherrypy.tools.json_out()
    def notificationconfig(self):
        """Get Firebase notification configuration"""
        if not self._check_auth():
            raise cherrypy.HTTPError(401, "Authentication required")
            
        firebase_config = self.config['global']['firebase']
        return {
            "firebaseConfig": {
                "apiKey": firebase_config['apiKey'],
                "authDomain": firebase_config['authDomain'],
                "projectId": firebase_config['projectId'],
                "storageBucket": firebase_config['storageBucket'],
                "messagingSenderId": firebase_config['messagingSenderId'],
                "appId": firebase_config['appId'],
            },
            "vapidKey": firebase_config['vapidkey']
        }

    @cherrypy.expose
    def firebase_messaging_sw_js(self):
        """Serve Firebase messaging service worker with dynamic config"""
        if not self._check_auth():
            raise cherrypy.HTTPError(401, "Authentication required")
            
        js_file_path = './static/firebase-messaging-sw.js'
        firebase_config = self.config['global']['firebase']
        
        config_js = f"""firebaseConfig={json.dumps({
            "apiKey": firebase_config['apiKey'],
            "authDomain": firebase_config['authDomain'],
            "projectId": firebase_config['projectId'],
            "storageBucket": firebase_config['storageBucket'],
            "messagingSenderId": firebase_config['messagingSenderId'],
            "appId": firebase_config['appId']
        })};"""
        
        try:
            with open(js_file_path, 'rb') as js_file:
                js_content = js_file.read().replace(
                    b'firebaseConfig = {};', 
                    config_js.encode('utf-8')
                )
            
            cherrypy.response.headers['Content-Type'] = 'application/javascript'
            return js_content
            
        except FileNotFoundError:
            raise cherrypy.HTTPError(404, "Service worker file not found")
        except Exception as e:
            raise cherrypy.HTTPError(500, f"Error serving service worker: {str(e)}")

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    @cherrypy.tools.json_in()
    def fcmtoken(self):
        """Handle FCM token registration"""
        if not self._check_auth():
            raise cherrypy.HTTPError(401, "Authentication required")
            
        input_json = cherrypy.request.json
        token = input_json.get('token')
        platform = input_json.get('platform', 'web')
        username = cherrypy.session['username']
        
        if not token:
            raise cherrypy.HTTPError(400, "Token is required")
        
        # Store FCM token in database
        db_path = "/data/mcp/notifications/"
        db_notifs = os.path.join(db_path, "notifications.sqlite")
        
        try:
            # Ensure directory exists
            os.makedirs(db_path, exist_ok=True)
            
            with sqlite3.connect(db_notifs) as conn:
                cursor = conn.cursor()
                
                # Create table if it doesn't exist
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS fcm_tokens (
                        token TEXT PRIMARY KEY,
                        username TEXT NOT NULL,
                        platform TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Remove old token if exists, then insert new one
                cursor.execute('DELETE FROM fcm_tokens WHERE token = ?', (token,))
                cursor.execute(
                    'INSERT INTO fcm_tokens (token, username, platform) VALUES (?, ?, ?)',
                    (token, username, platform)
                )
                
                conn.commit()
                
            tomlogger.info(f"FCM token registered for user {username} on {platform}", username, "web", "system")
            return {"status": "success"}
            
        except Exception as e:
            tomlogger.error(f"Error storing FCM token: {str(e)}", module_name="system")
            raise cherrypy.HTTPError(500, "Error storing FCM token")

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['GET', 'POST'])
    def notifications(self):
        """Proxy notifications requests to user backend"""
        return self._proxy_request("/notifications")

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    def reset(self):
        """Proxy reset requests to user backend"""
        return self._proxy_request("/reset")

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    def process(self):
        """Proxy process requests to user backend"""
        return self._proxy_request("/process")

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['GET'])
    def tasks(self):
        """Proxy tasks requests to user backend"""
        return self._proxy_request("/tasks")

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['GET'])
    def status(self):
        """Proxy status requests to user backend"""
        return self._proxy_request("/status")

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['GET', 'POST', 'PUT', 'DELETE'])
    def memory(self, *args, **kwargs):
        """Proxy memory requests to user memory service"""
        # Build the endpoint from the remaining path components
        # The memory service listens on root /, so we forward the sub-path directly
        if args:
            # Handle sub-paths: /memory/memories -> /memories, /memory/search -> /search
            endpoint = '/' + '/'.join(args)
        else:
            # /memory -> / (root of memory service)
            endpoint = '/'
        
        return self._proxy_memory_request(endpoint)

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    @cherrypy.tools.json_in()
    @cherrypy.tools.json_out()
    def health(self):
        """Receive Android Health Connect data"""
        if not self._check_auth():
            raise cherrypy.HTTPError(401, "Authentication required")
            
        username = cherrypy.session['username']
        input_json = cherrypy.request.json
        
        if not input_json:
            raise cherrypy.HTTPError(400, "JSON data is required")
        
        tomlogger.info(f"📱 Health data received from {username}: {json.dumps(input_json)}", username, "web", "health")
        
        return {"status": "success", "message": "Health data received"}


def main():
    """Main application entry point"""
    # Get config file path from command line or use default
    config_file_path = sys.argv[1] if len(sys.argv) > 1 else '/data/config.yml'
    
    # Load configuration
    global global_config
    global_config = init_config(config_file_path)
    
    # Initialize logging
    log_level = global_config.get('global', {}).get('log_level', 'INFO')
    tom_logger = init_logger(log_level)
    tom_logger.startup(f"Starting Tom server with config: {config_file_path}")
    tom_logger.startup(f"Log level: {log_level}")
    
    # Log users found in configuration
    users = global_config.get('users', [])
    tom_logger.info(f"Found {len(users)} user(s) in configuration", module_name="system")
    for user in users:
        username = user.get('username', 'unknown')
        tom_logger.info(f"✅ User configured: {username}", module_name="system")
    
    # Create web service instance
    web_service = TomWebService(global_config)
    
    # Configure sessions directory
    sessions_dir = global_config['global']['sessions']
    os.makedirs(sessions_dir, exist_ok=True)
    
    # Configure CherryPy logging to use our tomlogger
    # Disable default CherryPy logging
    cherrypy.config.update({
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
    
    # Check for TLS certificates - REQUIRED
    tls_dir = '/data/tls'
    cert_file = os.path.join(tls_dir, 'cert.pem')
    key_file = os.path.join(tls_dir, 'key.pem')
    chain_file = os.path.join(tls_dir, 'chain.pem')
    
    # Verify TLS certificates exist
    if not os.path.exists(cert_file):
        tom_logger.error(f"TLS certificate not found: {cert_file}")
        sys.exit(1)
    
    if not os.path.exists(key_file):
        tom_logger.error(f"TLS private key not found: {key_file}")
        sys.exit(1)
    
    tom_logger.startup(f"TLS certificates found in {tls_dir}")
    tom_logger.startup(f"Certificate: {cert_file}")
    tom_logger.startup(f"Private key: {key_file}")
    
    # Configure HTTPS server
    server_config = {
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 443,
        'server.ssl_module': 'builtin',
        'server.ssl_certificate': cert_file,
        'server.ssl_private_key': key_file,
        'tools.sessions.on': True,
        'tools.sessions.timeout': 3600 * 24 * 30,  # 30 days
        'tools.sessions.storage_type': 'file',
        'tools.sessions.storage_path': sessions_dir
    }
    
    # Add certificate chain if available
    if os.path.exists(chain_file):
        server_config['server.ssl_certificate_chain'] = chain_file
        tom_logger.startup(f"Certificate chain: {chain_file}")
    
    tom_logger.startup("HTTPS mode enabled")
    
    # Configure CherryPy server
    cherrypy.config.update(server_config)
    
    # Static file configuration
    static_config = {
        '/static': {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': os.path.abspath('static')
        }
    }
    
    # Log server startup
    tom_logger.startup("Tom server starting on port 443 (HTTPS)...")
    
    try:
        cherrypy.quickstart(web_service, '/', config=static_config)
    except KeyboardInterrupt:
        tom_logger.shutdown("Server shutting down...")
    except Exception as e:
        tom_logger.error(f"Server error: {str(e)}", module_name="system")
        sys.exit(1)


if __name__ == "__main__":
    main()
