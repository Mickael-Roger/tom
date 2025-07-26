import unittest
from unittest.mock import patch, MagicMock, call
import sys
import os
import json
import copy

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))

# Mock the logger before importing tomllm
with patch('tomllm.tomlogger') as mock_tomlogger:
    from tomllm import TomLLM

class TestTomLLMConfiguration(unittest.TestCase):
    
    def test_new_config_structure(self):
        """Test new global.llms.provider structure"""
        user_config = {
            'username': 'test_user',
            'personalContext': 'Test personal context'
        }
        
        global_config = {
            'global': {
                'llm': 'openai',
                'llms': {
                    'openai': {
                        'api': 'test-key-new-structure',
                        'env_var': 'OPENAI_API_KEY',
                        'models': ['openai/gpt-4o-mini', 'openai/gpt-4o', 'openai/gpt-4o']
                    },
                    'mistral': {
                        'api': 'test-mistral-key',
                        'env_var': 'MISTRAL_API_KEY',
                        'models': ['mistral/mistral-large-latest'] * 3
                    }
                }
            }
        }
        
        with patch('tomllm.tomlogger') as mock_tomlogger, \
             patch.dict('os.environ', {}, clear=True):
            llm = TomLLM(user_config, global_config)
            
            # Verify API keys are set in environment
            self.assertEqual(os.environ.get('OPENAI_API_KEY'), 'test-key-new-structure')
            self.assertEqual(os.environ.get('MISTRAL_API_KEY'), 'test-mistral-key')
            
            # Verify models are correctly configured
            self.assertEqual(llm.llms['openai'], ['openai/gpt-4o-mini', 'openai/gpt-4o', 'openai/gpt-4o'])
            self.assertEqual(llm.llms['mistral'], ['mistral/mistral-large-latest'] * 3)
    
    def test_legacy_config_structure(self):
        """Test backward compatibility with old structure"""
        user_config = {
            'username': 'test_user',
            'personalContext': 'Test personal context'
        }
        
        global_config = {
            'global': {
                'llm': 'openai',
                'openai': {'api': 'test-key-legacy-structure'},
                'deepseek': {'api': 'test-deepseek-key'}
            }
        }
        
        with patch('tomllm.tomlogger') as mock_tomlogger, \
             patch.dict('os.environ', {}, clear=True):
            llm = TomLLM(user_config, global_config)
            
            # Verify API keys are set in environment
            self.assertEqual(os.environ.get('OPENAI_API_KEY'), 'test-key-legacy-structure')
            self.assertEqual(os.environ.get('DEEPSEEK_API_KEY'), 'test-deepseek-key')
            
            # Verify default models are used
            self.assertEqual(llm.llms['openai'], ["openai/gpt-4o-mini", "openai/gpt-4o", "openai/gpt-4o"])
            self.assertEqual(llm.llms['deepseek'], ["deepseek/deepseek-chat", "deepseek/deepseek-chat", "deepseek/deepseek-reasoner"])
    
    def test_mixed_config_structure(self):
        """Test mixed new and legacy configuration"""
        user_config = {
            'username': 'test_user',
            'personalContext': 'Test personal context'
        }
        
        global_config = {
            'global': {
                'llm': 'openai',
                'llms': {
                    'openai': {
                        'api': 'test-new-openai-key',
                        'models': ['openai/gpt-4o-mini', 'openai/gpt-4o', 'openai/gpt-4o']
                    }
                },
                # Legacy structure for other providers
                'mistral': {'api': 'test-legacy-mistral-key'}
            }
        }
        
        with patch('tomllm.tomlogger') as mock_tomlogger, \
             patch.dict('os.environ', {}, clear=True):
            llm = TomLLM(user_config, global_config)
            
            # New structure should take precedence for OpenAI
            self.assertEqual(os.environ.get('OPENAI_API_KEY'), 'test-new-openai-key')
            # Legacy structure should work for Mistral
            self.assertEqual(os.environ.get('MISTRAL_API_KEY'), 'test-legacy-mistral-key')
    
    def test_custom_env_var(self):
        """Test custom environment variable names"""
        user_config = {
            'username': 'test_user',
            'personalContext': 'Test personal context'
        }
        
        global_config = {
            'global': {
                'llm': 'openai',
                'llms': {
                    'openai': {
                        'api': 'test-custom-key',
                        'env_var': 'CUSTOM_OPENAI_KEY',  # Custom env var name
                        'models': ['openai/gpt-4o-mini', 'openai/gpt-4o', 'openai/gpt-4o']
                    }
                }
            }
        }
        
        with patch('tomllm.tomlogger') as mock_tomlogger, \
             patch.dict('os.environ', {}, clear=True):
            llm = TomLLM(user_config, global_config)
            
            # Verify API key is set with custom environment variable name
            self.assertEqual(os.environ.get('CUSTOM_OPENAI_KEY'), 'test-custom-key')
            self.assertIsNone(os.environ.get('OPENAI_API_KEY'))  # Default should not be set
    
    def test_new_llm_provider(self):
        """Test adding a completely new LLM provider"""
        user_config = {
            'username': 'test_user',
            'personalContext': 'Test personal context'
        }
        
        global_config = {
            'global': {
                'llm': 'anthropic',  # New LLM not in defaults
                'llms': {
                    'anthropic': {
                        'api': 'sk-ant-test-key',
                        'env_var': 'ANTHROPIC_API_KEY',
                        'models': ['anthropic/claude-3-haiku', 'anthropic/claude-3-sonnet', 'anthropic/claude-3-opus']
                    }
                }
            }
        }
        
        with patch('tomllm.tomlogger') as mock_tomlogger, \
             patch.dict('os.environ', {}, clear=True):
            llm = TomLLM(user_config, global_config)
            
            # Verify new LLM is configured
            self.assertEqual(os.environ.get('ANTHROPIC_API_KEY'), 'sk-ant-test-key')
            self.assertEqual(llm.llms['anthropic'], ['anthropic/claude-3-haiku', 'anthropic/claude-3-sonnet', 'anthropic/claude-3-opus'])
            self.assertEqual(llm.llm, 'anthropic')
    
    def test_llm_not_configured_error(self):
        """Test error when configured LLM is not available"""
        user_config = {
            'username': 'test_user',
            'personalContext': 'Test personal context'
        }
        
        global_config = {
            'global': {
                'llm': 'nonexistent',  # LLM not configured
                'llms': {
                    'openai': {
                        'api': 'test-key',
                        'env_var': 'OPENAI_API_KEY'
                    }
                }
            }
        }
        
        with patch('tomllm.tomlogger') as mock_tomlogger, \
             patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(SystemExit):
                TomLLM(user_config, global_config)


class TestTomLLMTriageModules(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        self.user_config = {
            'username': 'test_user',
            'personalContext': 'Test personal context'
        }
        
        self.global_config = {
            'global': {
                'llm': 'openai',
                'openai': {'api': 'test_api_key'}
            }
        }
        
        # Mock the TomLLM initialization to avoid external dependencies
        with patch('tomllm.tomlogger') as mock_tomlogger:
            self.llm = TomLLM(self.user_config, self.global_config)
            
        # Set up mock services for testing
        self.llm.services = {
            'weather': {
                'description': 'Weather information and forecasts',
                'tools': [{'type': 'function', 'function': {'name': 'get_weather'}}],
                'systemContext': 'Weather module context',
                'complexity': 0
            },
            'calendar': {
                'description': 'Calendar and scheduling functions',
                'tools': [{'type': 'function', 'function': {'name': 'add_event'}}],
                'systemContext': 'Calendar module context',
                'complexity': 1
            },
            'todo': {
                'description': 'Task management and todo lists',
                'tools': [{'type': 'function', 'function': {'name': 'add_task'}}],
                'systemContext': 'Todo module context',
                'complexity': 0
            }
        }
        
        self.available_tools = [
            {"module_name": "weather", "module_description": "Weather information and forecasts"},
            {"module_name": "calendar", "module_description": "Calendar and scheduling functions"},
            {"module_name": "todo", "module_description": "Task management and todo lists"}
        ]
        
        self.modules_name_list = ["weather", "calendar", "todo"]
        
        # Sample conversation for testing
        self.conversation = [
            {"role": "system", "content": "Today is Monday 20 January 2025 10:30:00. Week number is 4."},
            {"role": "system", "content": "Your name is Tom, and you are my personal assistant..."},
            {"role": "user", "content": "What's the weather like today?"}
        ]
    
    @patch('tomllm.TomLLM.callLLM')
    @patch('tomllm.TomLLM.set_response_context')
    def test_triageModules_successful_module_identification(self, mock_set_response_context, mock_callLLM):
        """Test successful module identification during triage"""
        mock_set_response_context.return_value = "Response context"
        
        # Mock LLM response indicating weather module is needed
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].finish_reason = "tool_calls"
        mock_response.choices[0].message.tool_calls = [MagicMock()]
        mock_response.choices[0].message.tool_calls[0].function.name = "modules_needed_to_answer_user_prompt"
        mock_response.choices[0].message.tool_calls[0].function.arguments = '{"modules_name": "weather"}'
        
        mock_callLLM.return_value = mock_response
        
        result = self.llm.triageModules(
            self.conversation, 
            self.available_tools, 
            self.modules_name_list, 
            'web'
        )
        
        self.assertEqual(result, ["weather"])
        mock_callLLM.assert_called_once()
        mock_set_response_context.assert_called_once_with('web')
    
    @patch('tomllm.TomLLM.callLLM')
    @patch('tomllm.TomLLM.set_response_context')
    def test_triageModules_multiple_modules_identified(self, mock_set_response_context, mock_callLLM):
        """Test identification of multiple modules"""
        mock_set_response_context.return_value = "Response context"
        
        # Mock LLM response indicating multiple modules are needed
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].finish_reason = "tool_calls"
        mock_response.choices[0].message.tool_calls = [
            MagicMock(),
            MagicMock()
        ]
        
        # First tool call for weather
        mock_response.choices[0].message.tool_calls[0].function.name = "modules_needed_to_answer_user_prompt"
        mock_response.choices[0].message.tool_calls[0].function.arguments = '{"modules_name": "weather"}'
        
        # Second tool call for calendar
        mock_response.choices[0].message.tool_calls[1].function.name = "modules_needed_to_answer_user_prompt"
        mock_response.choices[0].message.tool_calls[1].function.arguments = '{"modules_name": "calendar"}'
        
        mock_callLLM.return_value = mock_response
        
        result = self.llm.triageModules(
            self.conversation, 
            self.available_tools, 
            self.modules_name_list, 
            'web'
        )
        
        self.assertEqual(set(result), {"weather", "calendar"})
    
    @patch('tomllm.TomLLM.callLLM')
    @patch('tomllm.TomLLM.set_response_context')
    def test_triageModules_direct_module_call(self, mock_set_response_context, mock_callLLM):
        """Test when LLM directly calls a module name as function (error case handling)"""
        mock_set_response_context.return_value = "Response context"
        
        # Mock LLM response with direct module call (error case)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].finish_reason = "tool_calls"
        mock_response.choices[0].message.tool_calls = [MagicMock()]
        mock_response.choices[0].message.tool_calls[0].function.name = "weather"  # Direct module call
        mock_response.choices[0].message.tool_calls[0].function.arguments = '{}'
        
        mock_callLLM.return_value = mock_response
        
        result = self.llm.triageModules(
            self.conversation, 
            self.available_tools, 
            self.modules_name_list, 
            'web'
        )
        
        self.assertEqual(result, ["weather"])
    
    @patch('tomllm.TomLLM.callLLM')
    @patch('tomllm.TomLLM.set_response_context')
    def test_triageModules_no_modules_needed(self, mock_set_response_context, mock_callLLM):
        """Test when no modules are identified as needed"""
        mock_set_response_context.return_value = "Response context"
        
        # Mock LLM response with no tool calls
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].finish_reason = "stop"
        mock_response.choices[0].message.content = "I can answer that directly."
        
        mock_callLLM.return_value = mock_response
        
        result = self.llm.triageModules(
            self.conversation, 
            self.available_tools, 
            self.modules_name_list, 
            'web'
        )
        
        self.assertEqual(result, [])
    
    @patch('tomllm.TomLLM.callLLM')
    @patch('tomllm.TomLLM.set_response_context')
    def test_triageModules_llm_failure(self, mock_set_response_context, mock_callLLM):
        """Test handling of LLM call failure"""
        mock_set_response_context.return_value = "Response context"
        
        # Mock LLM failure
        mock_callLLM.return_value = False
        
        result = self.llm.triageModules(
            self.conversation, 
            self.available_tools, 
            self.modules_name_list, 
            'web'
        )
        
        self.assertEqual(result, [])
    
    @patch('tomllm.TomLLM.callLLM')
    @patch('tomllm.TomLLM.set_response_context')
    def test_triageModules_malformed_tool_call(self, mock_set_response_context, mock_callLLM):
        """Test handling of malformed tool call arguments"""
        mock_set_response_context.return_value = "Response context"
        
        # Mock LLM response with malformed JSON
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].finish_reason = "tool_calls"
        mock_response.choices[0].message.tool_calls = [MagicMock()]
        mock_response.choices[0].message.tool_calls[0].function.name = "modules_needed_to_answer_user_prompt"
        mock_response.choices[0].message.tool_calls[0].function.arguments = 'invalid_json'
        
        mock_callLLM.return_value = mock_response
        
        # Should handle JSON decode error gracefully
        with self.assertRaises(json.JSONDecodeError):
            self.llm.triageModules(
                self.conversation, 
                self.available_tools, 
                self.modules_name_list, 
                'web'
            )
    
    @patch('tomllm.TomLLM.callLLM')
    @patch('tomllm.TomLLM.set_response_context')
    def test_triageModules_conversation_integrity(self, mock_set_response_context, mock_callLLM):
        """Test that the original conversation is not modified"""
        mock_set_response_context.return_value = "Response context"
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].finish_reason = "tool_calls"
        mock_response.choices[0].message.tool_calls = [MagicMock()]
        mock_response.choices[0].message.tool_calls[0].function.name = "modules_needed_to_answer_user_prompt"
        mock_response.choices[0].message.tool_calls[0].function.arguments = '{"modules_name": "weather"}'
        
        mock_callLLM.return_value = mock_response
        
        original_conversation = copy.deepcopy(self.conversation)
        
        self.llm.triageModules(
            self.conversation, 
            self.available_tools, 
            self.modules_name_list, 
            'web'
        )
        
        # Original conversation should be unchanged
        self.assertEqual(self.conversation, original_conversation)
    
    @patch('tomllm.TomLLM.callLLM')
    @patch('tomllm.TomLLM.set_response_context')
    def test_triageModules_correct_prompt_structure(self, mock_set_response_context, mock_callLLM):
        """Test that the triage prompt is correctly structured"""
        mock_set_response_context.return_value = "Response context"
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].finish_reason = "stop"
        
        mock_callLLM.return_value = mock_response
        
        self.llm.triageModules(
            self.conversation, 
            self.available_tools, 
            self.modules_name_list, 
            'web'
        )
        
        # Verify callLLM was called with correct structure
        call_args = mock_callLLM.call_args
        messages = call_args[1]['messages']
        tools = call_args[1]['tools']
        
        # Check that the system prompts were added correctly
        self.assertTrue(any("As an AI assistant" in msg.get('content', '') for msg in messages))
        self.assertTrue(any("weather" in json.dumps(msg.get('content', '')) for msg in messages))
        
        # Check tools structure
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]['function']['name'], 'modules_needed_to_answer_user_prompt')
        self.assertEqual(tools[0]['function']['parameters']['properties']['modules_name']['enum'], self.modules_name_list)
    
    @patch('tomllm.TomLLM.callLLM')
    @patch('tomllm.TomLLM.set_response_context')
    def test_triageModules_client_type_handling(self, mock_set_response_context, mock_callLLM):
        """Test that different client types are handled correctly"""
        mock_set_response_context.return_value = "TUI response context"
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].finish_reason = "stop"
        
        mock_callLLM.return_value = mock_response
        
        self.llm.triageModules(
            self.conversation, 
            self.available_tools, 
            self.modules_name_list, 
            'tui'
        )
        
        mock_set_response_context.assert_called_once_with('tui')

if __name__ == '__main__':
    unittest.main()