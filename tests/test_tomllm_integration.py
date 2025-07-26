import unittest
import sys
import os
import yaml
import copy
import warnings
from unittest.mock import patch

# Suppress warnings from external libraries
warnings.filterwarnings("ignore", category=DeprecationWarning, module="httpx")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
sys.path.append(os.path.dirname(__file__))  # Add tests directory to path

# Import test config loader
from test_config_loader import load_test_config

# Mock the logger before importing tomllm
with patch('tomllm.tomlogger') as mock_tomlogger:
    from tomllm import TomLLM


def load_test_cases():
    """Load test cases from YAML file and return them"""
    try:
        test_cases_path = os.path.join(os.path.dirname(__file__), 'triage_test_cases.yaml')
        with open(test_cases_path, 'r') as file:
            test_data = yaml.safe_load(file)
            return test_data.get('test_cases', [])
    except (FileNotFoundError, yaml.YAMLError):
        return []


class TestTomLLMTriageIntegration(unittest.TestCase):
    """Integration tests for triageModules using real LLM calls"""
    
    @classmethod
    def setUpClass(cls):
        """Load real configuration and test cases once for all tests"""
        cls.test_config = load_test_config()
        
        # Build global_config with the expected structure for TomLLM
        global_section = cls.test_config.get_global_config() or {}
        cls.global_config = {'global': global_section}
        
        # Extract available modules from services and user services
        cls.available_modules = []
        if cls.test_config.config_loaded:
            # Get global services
            services = cls.test_config.config.get('services', {})
            cls.available_modules.extend(services.keys())
            
            # Get user services (personal modules)
            users = cls.test_config.config.get('users', [])
            for user in users:
                user_services = user.get('services', {})
                for service_name in user_services.keys():
                    if service_name not in cls.available_modules:
                        cls.available_modules.append(service_name)
        
        # Load test cases
        cls.test_cases = load_test_cases()
    
    def setUp(self):
        """Set up test fixtures for each test"""
        if not self.test_config.config_loaded:
            self.skipTest("Test configuration not available - skipping integration test")
        
        if not self.test_cases:
            self.skipTest("Test cases file not available - skipping integration test")
        
        self.user_config = {
            'username': 'integration_test_user',
            'personalContext': 'Integration test personal context'
        }
        
        # Initialize TomLLM with real config
        with patch('tomllm.tomlogger') as mock_tomlogger:
            self.llm = TomLLM(self.user_config, self.global_config)
        
        # Set up mock services based on available modules
        self.llm.services = {}
        self.available_tools = []
        
        # Create mock services for each available module
        for module_name in self.available_modules:
            module_description = self._get_module_description(module_name)
            self.llm.services[module_name] = {
                'description': module_description,
                'tools': [{'type': 'function', 'function': {'name': f'{module_name}_function'}}],
                'systemContext': f'{module_name.title()} module context',
                'complexity': 0
            }
            self.available_tools.append({
                "module_name": module_name, 
                "module_description": module_description
            })
        
        # Base conversation template
        self.base_conversation = [
            {"role": "system", "content": "Today is Monday 20 January 2025 10:30:00. Week number is 4."},
            {"role": "system", "content": "Your name is Tom, and you are my personal assistant. You have access to numerous external functionalities via function calls..."}
        ]
    
    def _get_module_description(self, module_name):
        """Get description for a module based on its name"""
        descriptions = {
            'calendar': 'Calendar and scheduling functions',
            'groceries': 'Grocery list management',
            'idfm': 'Paris public transport information and route planning',
            'todo': 'Task management and todo lists',
            'deebot': 'Robot vacuum cleaner control and status'
        }
        return descriptions.get(module_name, f'{module_name.title()} module functionality')
    
    def _test_triage_case(self, test_case, case_index):
        """Test a single triage case"""
        prompt = test_case['prompt']
        expected_modules = test_case.get('expected_modules', [])
        description = test_case.get('description', 'No description')
        
        # Prepare conversation
        conversation = copy.deepcopy(self.base_conversation)
        conversation.append({"role": "user", "content": prompt})
        
        try:
            # Call triageModules
            result = self.llm.triageModules(
                conversation,
                self.available_tools,
                self.available_modules,
                'web'
            )
            
            # Verify result is a list
            self.assertIsInstance(result, list, 
                                f"Result should be a list, got {type(result)} for prompt: {prompt}")
            
            # Check expected modules
            if expected_modules:
                # Filter expected modules to only include those available in config
                available_expected = [mod for mod in expected_modules if mod in self.available_modules]
                
                if available_expected:
                    # At least one available expected module should be found
                    found_expected = any(mod in result for mod in available_expected)
                    self.assertTrue(found_expected, 
                                  f"None of expected modules {available_expected} found in result {result} for prompt: {prompt}")
            
            # Print result for debugging
            print(f"✓ Case {case_index}: '{prompt[:50]}...' -> Expected: {expected_modules}, Got: {result}")
            
        except Exception as e:
            self.fail(f"LLM call failed for case {case_index} with prompt '{prompt}': {str(e)}")


# Dynamically create test methods
def create_test_methods():
    """Create individual test methods for each test case"""
    test_cases = load_test_cases()
    
    for i, test_case in enumerate(test_cases):
        def make_test_method(tc, idx):
            def test_method(self):
                self._test_triage_case(tc, idx)
            return test_method
        
        # Create a descriptive test name
        prompt_snippet = test_case['prompt'][:30].replace(' ', '_').replace("'", "").replace('"', '').replace('?', '').replace('!', '').replace(',', '').replace('.', '').replace('à', 'a').replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('ç', 'c').replace('ô', 'o')
        description = test_case.get('description', '').replace(' ', '_').replace('-', '_').replace('à', 'a').replace('é', 'e').replace('è', 'e').replace('ê', 'e').replace('ç', 'c').replace('ô', 'o').lower()
        test_name = f"test_case_{i:03d}_{prompt_snippet}_{description}"
        
        # Clean up the test name to be a valid Python identifier
        test_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in test_name)
        test_name = test_name.replace('__', '_').strip('_')
        
        # Create the test method
        test_method = make_test_method(test_case, i)
        test_method.__name__ = test_name
        test_method.__doc__ = f"Test case {i}: {test_case.get('description', 'No description')} - '{test_case['prompt'][:50]}...'"
        
        # Add the method to the test class
        setattr(TestTomLLMTriageIntegration, test_name, test_method)


# Create the test methods when the module is imported
create_test_methods()


if __name__ == '__main__':
    unittest.main()
