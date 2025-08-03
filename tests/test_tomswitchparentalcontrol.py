import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import sys
import os
import json
import asyncio
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))

# Mock all dependencies before importing
mock_authenticator = MagicMock()
mock_nintendo_parental = MagicMock()
mock_invalid_session_token_exception = Exception

# Mock tomlogger
mock_logger = MagicMock()
mock_logger.info = MagicMock()
mock_logger.warning = MagicMock()
mock_logger.error = MagicMock()

# Mock all modules that might be imported
sys.modules['tomlogger'] = MagicMock(logger=mock_logger)
sys.modules['pynintendoparental'] = MagicMock(
    Authenticator=mock_authenticator,
    NintendoParental=mock_nintendo_parental
)
sys.modules['pynintendoparental.exceptions'] = MagicMock(
    InvalidSessionTokenException=mock_invalid_session_token_exception
)

# Now import the module
from tomswitchparentalcontrol import TomSwitchParentalControl, tom_config


class TestTomSwitchParentalControl(unittest.TestCase):
    
    def setUp(self):
        self.config = {
            'nintendo_session_token': 'test_token_123',
            'all_datadir': './test_data/'
        }
        self.llm = MagicMock()
        
        # Mock filesystem operations
        with patch('os.makedirs'), \
             patch('os.path.exists', return_value=False), \
             patch('builtins.open', create=True):
            self.switch_control = TomSwitchParentalControl(self.config, self.llm)
    
    def test_tom_config_structure(self):
        """Test that tom_config is properly structured"""
        self.assertEqual(tom_config['module_name'], 'switchparentalcontrol')
        self.assertEqual(tom_config['class_name'], 'TomSwitchParentalControl')
        self.assertEqual(tom_config['type'], 'global')
        self.assertEqual(tom_config['complexity'], 1)
        self.assertIn('nintendo_session_token', tom_config['configuration_parameters'])
        self.assertTrue(tom_config['configuration_parameters']['nintendo_session_token']['required'])
    
    def test_init_missing_token(self):
        """Test initialization with missing Nintendo session token"""
        config_no_token = {}
        with self.assertRaises(ValueError) as context:
            TomSwitchParentalControl(config_no_token, self.llm)
        self.assertIn("Nintendo session token is required", str(context.exception))
    
    def test_init_with_token(self):
        """Test successful initialization with token"""
        self.assertEqual(self.switch_control.session_token, 'test_token_123')
        self.assertIsNotNone(self.switch_control.tools)
        self.assertIsNotNone(self.switch_control.functions)
        self.assertEqual(len(self.switch_control.tools), 4)
    
    def test_tools_structure(self):
        """Test that tools are properly structured"""
        expected_tools = [
            'get_switch_daily_usage',
            'extend_switch_playtime', 
            'reduce_switch_playtime',
            'list_switch_devices'
        ]
        
        tool_names = [tool['function']['name'] for tool in self.switch_control.tools]
        for expected_tool in expected_tools:
            self.assertIn(expected_tool, tool_names)
        
        for tool in self.switch_control.tools:
            self.assertEqual(tool['type'], 'function')
            self.assertIn('name', tool['function'])
            self.assertIn('description', tool['function'])
            self.assertIn('parameters', tool['function'])
            self.assertTrue(tool['function']['strict'])
    
    def test_functions_mapping(self):
        """Test that functions are properly mapped"""
        expected_functions = [
            'get_switch_daily_usage',
            'extend_switch_playtime',
            'reduce_switch_playtime', 
            'list_switch_devices'
        ]
        
        for func_name in expected_functions:
            self.assertIn(func_name, self.switch_control.functions)
            self.assertTrue(callable(self.switch_control.functions[func_name]['function']))
    
    def test_load_cache_empty(self):
        """Test loading cache when file doesn't exist"""
        with patch('os.path.exists', return_value=False):
            cache = self.switch_control._load_cache()
            self.assertEqual(cache, {"devices": {}, "last_update": None})
    
    def test_load_cache_with_data(self):
        """Test loading cache with existing data"""
        mock_cache_data = {
            "devices": {
                "device123": {"name": "Nintendo Switch", "device_id": "device123"}
            },
            "last_update": "2024-01-01T12:00:00"
        }
        
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', unittest.mock.mock_open(read_data=json.dumps(mock_cache_data))):
            cache = self.switch_control._load_cache()
            self.assertEqual(cache, mock_cache_data)
    
    def test_load_cache_invalid_json(self):
        """Test loading cache with invalid JSON"""
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', unittest.mock.mock_open(read_data="invalid json")):
            cache = self.switch_control._load_cache()
            self.assertEqual(cache, {"devices": {}, "last_update": None})
    
    def test_save_cache(self):
        """Test saving cache to file"""
        mock_file = unittest.mock.mock_open()
        with patch('builtins.open', mock_file):
            self.switch_control._save_cache()
            mock_file.assert_called_once()
    
    def test_get_cache_summary_empty(self):
        """Test cache summary when no devices cached"""
        self.switch_control.cache = {"devices": {}}
        summary = self.switch_control._get_cache_summary()
        self.assertEqual(summary, "No Nintendo Switch devices are currently cached.")
    
    def test_get_cache_summary_with_devices(self):
        """Test cache summary with cached devices"""
        self.switch_control.cache = {
            "devices": {
                "device123": {"name": "Nintendo Switch", "device_id": "device123"},
                "device456": {"name": "Switch Lite", "device_id": "device456"}
            }
        }
        summary = self.switch_control._get_cache_summary()
        self.assertIn("Nintendo Switch (ID: device123)", summary)
        self.assertIn("Switch Lite (ID: device456)", summary)
    
    def test_system_context(self):
        """Test system context property"""
        context = self.switch_control.systemContext
        self.assertIn("Nintendo Switch parental control functionality", context)
        self.assertIn("daily_limit_minutes is 0", context)
        self.assertIn("daily_limit_minutes is null/None", context)
        self.assertIn("daily_limit_minutes is a positive number", context)
    
    @patch('asyncio.run')
    def test_async_wrapper_new_loop(self, mock_run):
        """Test async wrapper creating new event loop"""
        mock_run.return_value = "test_result"
        
        async def test_func():
            return "test_result"
        
        with patch('asyncio.get_event_loop', side_effect=RuntimeError("No event loop")):
            result = self.switch_control._async_wrapper(test_func)
            mock_run.assert_called_once()
            self.assertEqual(result, "test_result")
    
    @patch('asyncio.get_event_loop')
    def test_async_wrapper_existing_loop_not_running(self, mock_get_loop):
        """Test async wrapper with existing loop not running"""
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = False
        mock_loop.run_until_complete.return_value = "test_result"
        mock_get_loop.return_value = mock_loop
        
        async def test_func():
            return "test_result"
        
        result = self.switch_control._async_wrapper(test_func)
        mock_loop.run_until_complete.assert_called_once()
        self.assertEqual(result, "test_result")
    
    @patch('concurrent.futures.ThreadPoolExecutor')
    @patch('asyncio.get_event_loop')
    def test_async_wrapper_existing_loop_running(self, mock_get_loop, mock_executor):
        """Test async wrapper with existing loop running"""
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        mock_get_loop.return_value = mock_loop
        
        mock_future = MagicMock()
        mock_future.result.return_value = "test_result"
        mock_executor_instance = MagicMock()
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value.__enter__.return_value = mock_executor_instance
        
        async def test_func():
            return "test_result"
        
        result = self.switch_control._async_wrapper(test_func)
        self.assertEqual(result, "test_result")


class TestTomSwitchParentalControlAsync(unittest.TestCase):
    """Test async methods with proper async test setup"""
    
    def setUp(self):
        self.config = {
            'nintendo_session_token': 'test_token_123',
            'all_datadir': './test_data/'
        }
        self.llm = MagicMock()
        
        with patch('os.makedirs'), \
             patch('os.path.exists', return_value=False), \
             patch('builtins.open', create=True):
            self.switch_control = TomSwitchParentalControl(self.config, self.llm)
    
    async def test_ensure_authenticated_success(self):
        """Test successful authentication"""
        mock_auth = AsyncMock()
        mock_control = AsyncMock()
        mock_device = AsyncMock()
        mock_device.name = "Nintendo Switch"
        mock_device.device_id = "device123"
        mock_control.devices = {"device123": mock_device}
        
        with patch.object(mock_authenticator, 'complete_login', return_value=mock_auth), \
             patch.object(mock_nintendo_parental, 'create', return_value=mock_control), \
             patch.object(self.switch_control, '_save_cache'):
            
            await self.switch_control._ensure_authenticated()
            
            self.assertEqual(self.switch_control.auth, mock_auth)
            self.assertEqual(self.switch_control.control, mock_control)
            self.assertIn("device123", self.switch_control.cache['devices'])
    
    async def test_ensure_authenticated_invalid_token(self):
        """Test authentication with invalid token"""
        with patch.object(mock_authenticator, 'complete_login', 
                          side_effect=mock_invalid_session_token_exception("Invalid token")):
            
            with self.assertRaises(ValueError) as context:
                await self.switch_control._ensure_authenticated()
            
            self.assertIn("Invalid Nintendo session token", str(context.exception))
    
    async def test_ensure_authenticated_connection_error(self):
        """Test authentication with connection error"""
        with patch.object(mock_authenticator, 'complete_login', 
                          side_effect=Exception("Event loop is closed")):
            
            with self.assertRaises(ValueError) as context:
                await self.switch_control._ensure_authenticated()
            
            self.assertIn("Nintendo Switch is not connected to the internet", str(context.exception))
    
    async def test_get_daily_usage_no_devices(self):
        """Test get_daily_usage when no devices found"""
        mock_control = AsyncMock()
        mock_control.devices = {}
        self.switch_control.control = mock_control
        self.switch_control.auth = AsyncMock()
        
        result = await self.switch_control.get_daily_usage()
        
        self.assertIn("error", result)
        self.assertEqual(result["error"], "No Nintendo Switch devices found")
    
    async def test_get_daily_usage_specific_device(self):
        """Test get_daily_usage for specific device"""
        mock_device = AsyncMock()
        mock_device.device_id = "device123"
        mock_device.name = "Nintendo Switch"
        mock_device.today_playing_time = 60
        mock_device.limit_time = 120
        mock_device.update = AsyncMock()
        
        mock_control = AsyncMock()
        mock_control.devices = {"device123": mock_device}
        
        self.switch_control.control = mock_control
        self.switch_control.auth = AsyncMock()
        
        result = await self.switch_control.get_daily_usage("device123")
        
        self.assertIn("devices_usage", result)
        self.assertEqual(len(result["devices_usage"]), 1)
        device_data = result["devices_usage"][0]
        self.assertEqual(device_data["device_id"], "device123")
        self.assertEqual(device_data["today_playing_time_minutes"], 60)
        self.assertEqual(device_data["daily_limit_minutes"], 120)
        self.assertEqual(device_data["remaining_time_minutes"], 60)
    
    async def test_get_daily_usage_device_not_found(self):
        """Test get_daily_usage for non-existent device"""
        mock_control = AsyncMock()
        mock_control.devices = {}
        self.switch_control.control = mock_control
        self.switch_control.auth = AsyncMock()
        
        result = await self.switch_control.get_daily_usage("nonexistent")
        
        self.assertIn("error", result)
        self.assertIn("Device with ID nonexistent not found", result["error"])
    
    async def test_extend_playtime_success(self):
        """Test successful playtime extension"""
        mock_device = AsyncMock()
        mock_device.device_id = "device123"
        mock_device.name = "Nintendo Switch"
        mock_device.limit_time = 120
        mock_device.update = AsyncMock()
        mock_device.set_limit_time = AsyncMock(return_value=True)
        
        mock_control = AsyncMock()
        mock_control.devices = {"device123": mock_device}
        
        self.switch_control.control = mock_control
        self.switch_control.auth = AsyncMock()
        
        result = await self.switch_control.extend_playtime("device123", 30)
        
        self.assertTrue(result["success"])
        self.assertEqual(result["device_id"], "device123")
        self.assertEqual(result["previous_limit_minutes"], 120)
        self.assertEqual(result["new_limit_minutes"], 150)
        self.assertEqual(result["extended_by_minutes"], 30)
        mock_device.set_limit_time.assert_called_once_with(150)
    
    async def test_reduce_playtime_success(self):
        """Test successful playtime reduction"""
        mock_device = AsyncMock()
        mock_device.device_id = "device123"
        mock_device.name = "Nintendo Switch"
        mock_device.limit_time = 120
        mock_device.update = AsyncMock()
        mock_device.set_limit_time = AsyncMock(return_value=True)
        
        mock_control = AsyncMock()
        mock_control.devices = {"device123": mock_device}
        
        self.switch_control.control = mock_control
        self.switch_control.auth = AsyncMock()
        
        result = await self.switch_control.reduce_playtime("device123", 30)
        
        self.assertTrue(result["success"])
        self.assertEqual(result["device_id"], "device123")
        self.assertEqual(result["previous_limit_minutes"], 120)
        self.assertEqual(result["new_limit_minutes"], 90)
        self.assertEqual(result["reduced_by_minutes"], 30)
        mock_device.set_limit_time.assert_called_once_with(90)
    
    async def test_list_devices_success(self):
        """Test successful device listing"""
        mock_device1 = AsyncMock()
        mock_device1.device_id = "device123"
        mock_device1.name = "Nintendo Switch"
        mock_device1.today_playing_time = 60
        mock_device1.limit_time = 120
        mock_device1.update = AsyncMock()
        
        mock_device2 = AsyncMock()
        mock_device2.device_id = "device456"
        mock_device2.name = "Switch Lite"
        mock_device2.today_playing_time = 30
        mock_device2.limit_time = None
        mock_device2.update = AsyncMock()
        
        mock_control = AsyncMock()
        mock_control.devices = {"device123": mock_device1, "device456": mock_device2}
        
        self.switch_control.control = mock_control
        self.switch_control.auth = AsyncMock()
        
        result = await self.switch_control.list_devices()
        
        self.assertIn("devices", result)
        self.assertEqual(len(result["devices"]), 2)
        
        device1_data = next(d for d in result["devices"] if d["device_id"] == "device123")
        self.assertEqual(device1_data["device_name"], "Nintendo Switch")
        self.assertEqual(device1_data["remaining_time_minutes"], 60)
        
        device2_data = next(d for d in result["devices"] if d["device_id"] == "device456")
        self.assertEqual(device2_data["device_name"], "Switch Lite")
        self.assertEqual(device2_data["remaining_time_minutes"], "unlimited")


def run_async_test(test_func):
    """Helper to run async tests"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(test_func())
    finally:
        loop.close()


# Add async test methods to be run with the helper
def add_async_tests():
    """Add async test methods to the main test class"""
    async_test_class = TestTomSwitchParentalControlAsync()
    
    for method_name in dir(async_test_class):
        if method_name.startswith('test_') and asyncio.iscoroutinefunction(getattr(async_test_class, method_name)):
            async_method = getattr(async_test_class, method_name)
            
            def make_test(async_func):
                def test_wrapper(self):
                    async_test_instance = TestTomSwitchParentalControlAsync()
                    async_test_instance.setUp()
                    return run_async_test(lambda: async_func(async_test_instance))
                return test_wrapper
            
            setattr(TestTomSwitchParentalControl, method_name, make_test(async_method))


if __name__ == '__main__':
    add_async_tests()
    unittest.main()