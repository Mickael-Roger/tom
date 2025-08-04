import os
import ast
import json
import sys

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
        # Keys in dicts can be nodes too
        return {_ast_to_python(k): _ast_to_python(v) for k, v in zip(node.keys, node.values)}
    elif isinstance(node, ast.JoinedStr): # f-string
        # Attempt to format the f-string if it only contains constants
        return "".join([str(_ast_to_python(v)) for v in node.values])
    elif isinstance(node, ast.Attribute):
        # For things like `self.decks`, return a placeholder
        # We need to reconstruct the full attribute path if it's nested
        parts = []
        curr = node
        while isinstance(curr, ast.Attribute):
            parts.append(curr.attr)
            curr = curr.value
        if isinstance(curr, ast.Name):
            parts.append(curr.id)
            return f"<Attribute: {'.'.join(reversed(parts))}>"
        else:
            return f"<Attribute: ...>" # Fallback for complex cases
    elif isinstance(node, ast.Name):
        # For variable names
        return f"<Name: {node.id}>"
    # For older Python versions compatibility
    elif isinstance(node, ast.Str):
        return node.s
    elif isinstance(node, ast.Num):
        return node.n
    elif isinstance(node, ast.NameConstant):
        return node.value
    else:
        # For other unhandled nodes, return a placeholder
        return f"<Unsupported AST node: {type(node).__name__}>"

class ToolsVisitor(ast.NodeVisitor):
    """
    An AST visitor to find the 'self.tools' assignment in an __init__ method.
    """
    def __init__(self):
        self.tools_node = None

    def visit_FunctionDef(self, node):
        # Only inspect __init__ methods
        if node.name != '__init__':
            return

        for sub_node in node.body:
            if isinstance(sub_node, ast.Assign):
                # self.tools can be one of multiple targets
                for target in sub_node.targets:
                    if (isinstance(target, ast.Attribute) and
                            isinstance(target.value, ast.Name) and
                            target.value.id == 'self' and
                            target.attr == 'tools'):
                        self.tools_node = sub_node.value
                        # Found it, no need to look further in this function or other targets
                        return
        # We don't call generic_visit for FunctionDef to avoid visiting nested functions
        # within __init__ if we've already found what we're looking for.

class ClassVisitor(ast.NodeVisitor):
    """
    Visits classes to then apply the ToolsVisitor on their __init__ methods.
    """
    def __init__(self):
        self.tools_node = None

    def visit_ClassDef(self, node):
        # For each class, look for self.tools in its __init__
        tools_visitor = ToolsVisitor()
        tools_visitor.visit(node)
        if tools_visitor.tools_node:
            self.tools_node = tools_visitor.tools_node
        # Do not visit nested classes, stop at the first class with self.tools
        # This assumes one main class per file, which is the case here.
        if self.tools_node:
            return


def extract_tools_from_module(file_path):
    """
    Extracts the 'self.tools' list from a module file using AST parsing.
    """
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
    except SyntaxError as e:
        return {"error": f"Syntax error parsing file: {e}"}
    except Exception as e:
        return {"error": f"Error parsing file: {e}"}

def main():
    """
    Main function to iterate through modules, extract tools, and print the result.
    """
    # The script is in tests/, so modules/ is in the parent directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    modules_dir = os.path.join(project_root, 'modules')
    
    all_tools = {}

    if not os.path.isdir(modules_dir):
        print(json.dumps({"error": f"Directory '{modules_dir}' not found."}), file=sys.stderr)
        sys.exit(1)

    for filename in sorted(os.listdir(modules_dir)):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = os.path.splitext(filename)[0]
            file_path = os.path.join(modules_dir, filename)
            
            tools_data = extract_tools_from_module(file_path)
            
            if tools_data is not None:
                all_tools[module_name] = tools_data

    print(json.dumps(all_tools, indent=4))

if __name__ == '__main__':
    main()
