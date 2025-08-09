# gPodder.net integration module
import mygpoclient.api
import json
import os
import sys
import functools
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
from tomlogger import logger

tom_config = {
    "module_name": "gpodder",
    "class_name": "TomGpodder", 
    "description": "This module manages podcasts via gpodder.net service. It allows listing podcast subscriptions, unread podcast episodes, and marking episodes as played.",
    "type": "personal",
    "complexity": 0,
    "configuration_parameters": {
        "username": {
            "type": "string",
            "description": "gpodder.net username for authentication.",
            "required": True
        },
        "password": {
            "type": "string", 
            "description": "gpodder.net password for authentication.",
            "required": True
        }
    }
}

class TomGpodder:
    
    def __init__(self, config, llm) -> None:
        
        # Validate required config fields
        required_fields = ['username', 'password']
        for field in required_fields:
            if field not in config:
                raise KeyError(f"Missing required config field: {field}")
        
        self.username = config['username']
        self.password = config['password']
        
        # Initialize cache database path
        if tom_config["type"] == 'personal':
            user_datadir = config.get('user_datadir', './data/users/')
            username = config.get('username', 'default')
            user_dir = os.path.join(user_datadir, username)
            os.makedirs(user_dir, exist_ok=True)
            self.cache_db = os.path.join(user_dir, 'gpodder.sqlite')
        
        # Initialize gpodder client
        try:
            # Use MygPodderClient for device management and episode actions
            self.advanced_client = mygpoclient.api.MygPodderClient(
                username=self.username,
                password=self.password
            )
            
            # Use SimpleClient for basic subscriptions
            self.client = mygpoclient.api.simple.SimpleClient(
                username=self.username,
                password=self.password
            )
            
            # Get or create a device_id using advanced client
            devices = self.advanced_client.get_devices()
            if devices:
                self.device_id = devices[0].device_id
                logger.info(f"Using existing device: {self.device_id}", module_name="gpodder")
            else:
                # Use a default device name if no devices exist
                self.device_id = "tom-gpodder-client"
                logger.info(f"Using default device: {self.device_id}", module_name="gpodder")
            
            logger.info("Successfully initialized gpodder clients", module_name="gpodder")
        except Exception as e:
            logger.error(f"Error initializing gpodder client: {str(e)}", module_name="gpodder")
            raise
        
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "gpodder_list_subscriptions",
                    "description": "List all podcast subscriptions from gpodder.net",
                    "strict": True,
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
                    "name": "gpodder_list_episodes",
                    "description": "List episodes for a specific podcast, optionally filtering by read status",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "podcast_url": {
                                "type": "string",
                                "description": "The URL of the podcast feed to get episodes for",
                            },
                            "unread_only": {
                                "type": "boolean", 
                                "description": "If true, only return unread/unplayed episodes. Default is false.",
                            }
                        },
                        "required": ["podcast_url", "unread_only"],
                        "additionalProperties": False,
                    },
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "gpodder_mark_episode",
                    "description": "Mark an episode as played/read or unplayed/unread",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "episode_url": {
                                "type": "string",
                                "description": "The URL of the episode to mark",
                            },
                            "action": {
                                "type": "string",
                                "enum": ["play", "download", "delete"],
                                "description": "The action to mark for this episode. 'play' marks as played/read.",
                            },
                            "position": {
                                "type": "integer",
                                "description": "Position in seconds where playback stopped (set to 0 if not applicable)",
                            },
                            "total": {
                                "type": "integer", 
                                "description": "Total duration in seconds (set to 0 if not applicable)",
                            }
                        },
                        "required": ["episode_url", "action", "position", "total"],
                        "additionalProperties": False,
                    },
                }
            }
        ]
        
        self.systemContext = "You can help manage podcasts through gpodder.net integration. You can list subscriptions, show episodes, and mark them as played."
        self.complexity = tom_config.get("complexity", 0)
        
        self.functions = {
            "gpodder_list_subscriptions": {
                "function": functools.partial(self.list_subscriptions)
            },
            "gpodder_list_episodes": {
                "function": functools.partial(self.list_episodes)  
            },
            "gpodder_mark_episode": {
                "function": functools.partial(self.mark_episode)
            }
        }
    
    def list_subscriptions(self):
        """List all podcast subscriptions"""
        try:
            subscriptions = self.client.get_subscriptions(self.device_id)
            
            subscription_list = []
            for url in subscriptions:
                subscription_list.append({
                    "url": url,
                    "title": url  # mygpoclient simple API doesn't provide titles
                })
            
            result = {
                "status": "success",
                "subscriptions": subscription_list,
                "count": len(subscription_list)
            }
            
            logger.info(f"Retrieved {len(subscription_list)} subscriptions", module_name="gpodder")
            return json.dumps(result)
            
        except Exception as e:
            error_msg = f"Error retrieving subscriptions: {str(e)}"
            logger.error(error_msg, module_name="gpodder")
            return json.dumps({"status": "error", "message": error_msg})
    
    def list_episodes(self, podcast_url, unread_only=False):
        """List episodes for a podcast"""
        try:
            # Get episode actions to determine read status using advanced client
            episode_actions = self.advanced_client.download_episode_actions()
            
            # Filter actions for this podcast
            podcast_actions = {}
            for action in episode_actions:
                if action.podcast == podcast_url:
                    if action.episode not in podcast_actions:
                        podcast_actions[action.episode] = []
                    podcast_actions[action.episode].append({
                        'action': action.action,
                        'timestamp': action.timestamp.isoformat() if action.timestamp else None,
                        'position': getattr(action, 'position', None),
                        'total': getattr(action, 'total', None)
                    })
            
            episodes = []
            for episode_url, actions in podcast_actions.items():
                # Check if episode is played (has 'play' action)
                is_played = any(action['action'] == 'play' for action in actions)
                
                if unread_only and is_played:
                    continue
                    
                episodes.append({
                    "url": episode_url,
                    "played": is_played,
                    "actions": actions
                })
            
            result = {
                "status": "success", 
                "podcast_url": podcast_url,
                "episodes": episodes,
                "count": len(episodes),
                "unread_only": unread_only
            }
            
            filter_text = " unread" if unread_only else ""
            logger.info(f"Retrieved {len(episodes)}{filter_text} episodes for {podcast_url}", module_name="gpodder")
            return json.dumps(result)
            
        except Exception as e:
            error_msg = f"Error retrieving episodes for {podcast_url}: {str(e)}"
            logger.error(error_msg, module_name="gpodder")
            return json.dumps({"status": "error", "message": error_msg})
    
    def mark_episode(self, episode_url, action, position=0, total=0):
        """Mark episode with specified action"""
        try:
            # Create episode action
            episode_action = mygpoclient.api.EpisodeAction(
                podcast='',  # Will be determined by the service
                episode=episode_url,
                action=action,
                timestamp=datetime.now(),
                position=position if position else None,
                total=total if total else None
            )
            
            # Upload the action using advanced client
            self.advanced_client.upload_episode_actions([episode_action])
            
            result = {
                "status": "success",
                "message": f"Episode marked with action '{action}'",
                "episode_url": episode_url,
                "action": action
            }
            
            logger.info(f"Marked episode {episode_url} with action '{action}'", module_name="gpodder")
            return json.dumps(result)
            
        except Exception as e:
            error_msg = f"Error marking episode {episode_url}: {str(e)}"
            logger.error(error_msg, module_name="gpodder")
            return json.dumps({"status": "error", "message": error_msg})
