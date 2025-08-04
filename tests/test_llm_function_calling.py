import unittest
import sys
import os
import yaml
import json
import ast
import copy
from unittest.mock import patch, MagicMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
sys.path.append(os.path.dirname(__file__))

from test_config_loader import load_test_config

# Mock the logger before importing tomllm to avoid issues in test environment
with patch('tomllm.tomlogger') as mock_tomlogger:
    from tomllm import TomLLM

# --- AST Parsing Logic from extract_module_tools.py ---

def _ast_to_python(node):
    """
    Recursively convert an AST node to a Python literal.
    Handles basic literals and structures. Returns a placeholder for non-literals.
    """
    if isinstance(node, ast.Constant):
        return node.value
    elif isinstance(node, ast.List):
        return [_ast_to_python(e) for e in node.elts]
    elif isinstance(node, ast.Tuple):
        return tuple(_ast_to_python(e) for e in node.elts)
    elif isinstance(node, ast.Dict):
        return {_ast_to_python(k): _ast_to_python(v) for k, v in zip(node.keys, node.values)}
    elif isinstance(node, ast.JoinedStr): # f-string
        return "".join([str(_ast_to_python(v)) for v in node.values])
    elif isinstance(node, ast.Attribute):
        parts = []
        curr = node
        while isinstance(curr, ast.Attribute):
            parts.append(curr.attr)
            curr = curr.value
        if isinstance(curr, ast.Name):
            parts.append(curr.id)
            return f"<Attribute: {'.'.join(reversed(parts))}>"
        else:
            return f"<Attribute: ...>"
    elif isinstance(node, ast.Name):
        return f"<Name: {node.id}>"
    # Compatibility for older Python versions
    elif isinstance(node, ast.Str):
        return node.s
    elif isinstance(node, ast.Num):
        return node.n
    elif isinstance(node, ast.NameConstant):
        return node.value
    else:
        return f"<Unsupported AST node: {type(node).__name__}>"

class ToolsVisitor(ast.NodeVisitor):
    """AST visitor to find 'self.tools' assignment in an __init__ method."""
    def __init__(self):
        self.tools_node = None

    def visit_FunctionDef(self, node):
        if node.name != '__init__':
            return
        for sub_node in node.body:
            if isinstance(sub_node, ast.Assign):
                for target in sub_node.targets:
                    if (isinstance(target, ast.Attribute) and
                            isinstance(target.value, ast.Name) and
                            target.value.id == 'self' and
                            target.attr == 'tools'):
                        self.tools_node = sub_node.value
                        return

class ClassVisitor(ast.NodeVisitor):
    """Visits classes to apply the ToolsVisitor on their __init__ methods."""
    def __init__(self):
        self.tools_node = None

    def visit_ClassDef(self, node):
        tools_visitor = ToolsVisitor()
        tools_visitor.visit(node)
        if tools_visitor.tools_node:
            self.tools_node = tools_visitor.tools_node
        if self.tools_node:
            return

def extract_tools_from_module(file_path):
    """Extracts 'self.tools' list from a module file using AST parsing."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return {"error": f"Error reading file: {e}"}

    try:
        tree = ast.parse(content, filename=os.path.basename(file_path))
        visitor = ClassVisitor()
        visitor.visit(tree)
        if visitor.tools_node:
            return _ast_to_python(visitor.tools_node)
        else:
            return None
    except Exception as e:
        return {"error": f"Error parsing file: {e}"}

# --- Test Case Loading ---

def load_function_calling_test_cases():
    """Loads test cases from the YAML file."""
    try:
        test_cases_path = os.path.join(os.path.dirname(__file__), 'llm_function_calling_test_cases.yaml')
        with open(test_cases_path, 'r', encoding='utf-8') as file:
            test_data = yaml.safe_load(file)
            return test_data.get('test_cases', [])
    except (FileNotFoundError, yaml.YAMLError):
        return []

# --- Test Class ---

class TestLLMFunctionCalling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_config = load_test_config()
        global_section = cls.test_config.get_global_config() or {}

        # Override LLM if provided via environment variable or command line
        if hasattr(cls, '_override_llm') and cls._override_llm:
            global_section = global_section.copy()
            global_section['llm'] = cls._override_llm

        cls.global_config = {'global': global_section}
        cls.test_cases = load_function_calling_test_cases()

    def setUp(self):
        if not self.test_config.config_loaded:
            self.skipTest("Test configuration not available - skipping integration test")
        if not self.test_cases:
            self.skipTest("Function calling test cases file not available - skipping integration test")

        self.user_config = {
            'username': 'fn_call_test_user',
            'personalContext': 'Function calling integration test personal context'
        }

        with patch('tomllm.tomlogger'):
            self.llm = TomLLM(self.user_config, self.global_config)

    def _test_function_calling_case(self, test_case, case_index):
        prompt = test_case['prompt']
        expected_modules = test_case.get('modules', [])
        expected_calls = test_case.get('expected_calls', [])

        # 1. Load tools for the required modules
        loaded_tools = []
        for module_name in expected_modules:
            module_file = os.path.join(os.path.dirname(__file__), '..', 'modules', f'{module_name}.py')
            if os.path.exists(module_file):
                tools = extract_tools_from_module(module_file)
                if tools and isinstance(tools, list):
                    loaded_tools.extend(tools)

        self.assertTrue(loaded_tools, f"Could not load tools for modules: {expected_modules}")

        # 2. Prepare conversation for the LLM
        conversation = [
            {"role": "system", "content": "Today is Monday 04 August 2025 10:30:00. Week number is 32."},
            {"role": "system", "content": "You are a helpful assistant. Call functions when necessary to answer the user's request."},
            {"role": "user", "content": prompt}
        ]

        # 3. Call the LLM with the prompt and tools
        try:
            response = self.llm.callLLM(
                messages=conversation,
                tools=loaded_tools,
                complexity=0  # Use lowest complexity for speed/cost
            )
        except Exception as e:
            self.fail(f"LLM call failed for case {case_index} ('{prompt}') with error: {e}")

        # 4. Assert the results
        llm_response_str = f"\nLLM Response:\n{response.choices[0].message}\n"

        self.assertIsNotNone(response, f"Response is None for case {case_index}")
        self.assertTrue(response.choices, f"Response has no choices for case {case_index}")
        
        response_message = response.choices[0].message
        actual_tool_calls = response_message.tool_calls
        
        self.assertIsNotNone(actual_tool_calls, f"LLM did not call any tools for case {case_index}: '{prompt}'" + llm_response_str)
        self.assertEqual(len(actual_tool_calls), len(expected_calls),
                         f"Expected {len(expected_calls)} tool calls, but got {len(actual_tool_calls)} for case {case_index}: '{prompt}'. Got: {[c.function.name for c in actual_tool_calls]}" + llm_response_str)

        # Use a copy of the actual calls to be able to remove matched calls
        remaining_actual_calls = [
            {'name': call.function.name, 'arguments': json.loads(call.function.arguments)}
            for call in actual_tool_calls
        ]

        for expected_call in expected_calls:
            expected_func_name = expected_call['function']
            expected_params = expected_call['parameters']
            
            match_found = False
            for i, actual_call in enumerate(remaining_actual_calls):
                if actual_call['name'] == expected_func_name:
                    # Check if parameters match
                    params_match = True
                    actual_params = actual_call['arguments']
                    for param, expected_value in expected_params.items():
                        if param not in actual_params:
                            params_match = False
                            break
                        
                        if expected_value == '*':
                            continue

                        actual_value = actual_params[param]
                        if isinstance(expected_value, str) and ',' in expected_value:
                            expected_list = sorted([item.strip() for item in expected_value.split(',')])
                            actual_list = sorted([item.strip() for item in str(actual_value).split(',')])
                            if expected_list != actual_list:
                                params_match = False
                                break
                        elif str(actual_value) != str(expected_value):
                            params_match = False
                            break
                    
                    if params_match:
                        match_found = True
                        del remaining_actual_calls[i]
                        break # Move to the next expected call
            
            self.assertTrue(match_found, f"Could not find a matching call for expected: {expected_call} in case {case_index}" + llm_response_str)

        self.assertEqual(len(remaining_actual_calls), 0, f"There were unexpected tool calls made by the LLM: {remaining_actual_calls} in case {case_index}" + llm_response_str)
        
        print(f"✓ Case {case_index}: '{prompt[:50]}...' -> OK")


def create_function_calling_tests():
    test_cases = load_function_calling_test_cases()
    for i, test_case in enumerate(test_cases):
        def make_test(tc, idx):
            def test_method(self):
                self._test_function_calling_case(tc, idx)
            return test_method

        description = test_case.get('description', f'case_{i}').replace(' ', '_').lower()
        test_name = f"test_case_{i:03d}_{description}"
        test_name = ''.join(c for c in test_name if c.isalnum() or c == '_')
        
        test_method = make_test(test_case, i)
        setattr(TestLLMFunctionCalling, test_name, test_method)

create_function_calling_tests()

def get_llm_override():
    """Get LLM override from environment variable or command line."""
    llm_override = os.environ.get('TEST_LLM_OVERRIDE')
    if llm_override:
        return llm_override
    
    for arg in sys.argv:
        if arg.startswith('--llm='):
            return arg.split('=', 1)[1]
    
    try:
        llm_index = sys.argv.index('--llm')
        if llm_index + 1 < len(sys.argv):
            # Temporarily remove the --llm argument so unittest doesn't see it
            override = sys.argv.pop(llm_index + 1)
            sys.argv.pop(llm_index)
            return override
    except ValueError:
        pass
    
    return None

# Check for LLM override when module is loaded
llm_override = get_llm_override()
if llm_override:
    TestLLMFunctionCalling._override_llm = llm_override
    print(f"Overriding LLM provider to: {llm_override}")
else:
    TestLLMFunctionCalling._override_llm = None

if __name__ == '__main__':
    unittest.main()