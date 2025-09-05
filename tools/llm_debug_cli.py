"""Standalone script to debug LLM calls using litellm.

This script allows you to make a direct call to an LLM provider (specifically configured for OpenRouter)
by providing an API key, a model name, and JSON files for messages and tools.
It prints the full, raw response from the LLM to standard output.

Prerequisites:
- Python 3.7+
- litellm library (`pip install litellm`)

Example Usage:

1. Create a `messages.json` file:
   ```json
   [
     {"role": "system", "content": "You are a helpful assistant."}, 
     {"role": "user", "content": "What is the weather in Paris?"}
   ]
   ```

2. (Optional) Create a `tools.json` file:
   ```json
   [
     {
       "type": "function",
       "function": {
         "name": "get_current_weather",
         "description": "Get the current weather in a given location",
         "parameters": {
           "type": "object",
           "properties": {
             "location": {
               "type": "string",
               "description": "The city and state, e.g. San Francisco, CA"
             },
             "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
           },
           "required": ["location"]
         }
       }
     }
   ]
   ```

3. Run the script from your terminal:
   ```bash
   python tools/llm_debug_cli.py \
     --api-key "sk-or-..." \
     --model "mistralai/mistral-7b-instruct" \
     --messages-file "messages.json" \
     --tools-file "tools.json"
   ```
"""

import argparse
import json
import os
import sys
from typing import List, Dict, Any, Optional



def main():
    """Main function to parse arguments and call the LLM."""
    parser = argparse.ArgumentParser(
        description="A standalone script to debug LLM calls using litellm.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Example command:
  python %(prog)s \
    --api-key "YOUR_OPENROUTER_KEY" \
    --model "mistralai/mistral-7b-instruct" \
    --messages-file "path/to/messages.json" \
    --tools-file "path/to/tools.json"
"""
    )
    parser.add_argument(
        '--api-key',
        required=True,
        help="Your OpenRouter API key. This will be set as the OPENROUTER_API_KEY environment variable."
    )
    parser.add_argument(
        '--model',
        required=True,
        help="The model name to use (e.g., 'openai/gpt-4o', 'mistralai/mistral-7b-instruct')."
    )
    parser.add_argument(
        '--messages-file',
        required=True,
        help="Path to the JSON file containing the 'messages' array."
    )
    parser.add_argument(
        '--tools-file',
        required=False,
        default=None,
        help="Optional path to the JSON file containing the 'tools' array."
    )

    args = parser.parse_args()

    # --- Set API Key ---
    os.environ["OPENROUTER_API_KEY"] = args.api_key

    # --- Load Messages ---
    try:
        with open(args.messages_file, 'r', encoding='utf-8') as f:
            messages: List[Dict[str, Any]] = json.load(f)
        if not isinstance(messages, list):
            print(f"Error: The root of '{args.messages_file}' must be a JSON array.", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print(f"Error: Messages file not found at '{args.messages_file}'", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{args.messages_file}'. Please check its format.", file=sys.stderr)
        sys.exit(1)

    # --- Load Tools (Optional) ---
    tools: Optional[List[Dict[str, Any]]] = None
    if args.tools_file:
        try:
            with open(args.tools_file, 'r', encoding='utf-8') as f:
                tools = json.load(f)
            if not isinstance(tools, list):
                print(f"Error: The root of '{args.tools_file}' must be a JSON array.", file=sys.stderr)
                sys.exit(1)
        except FileNotFoundError:
            print(f"Error: Tools file not found at '{args.tools_file}'", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from '{args.tools_file}'. Please check its format.", file=sys.stderr)
            sys.exit(1)

    # --- Import litellm (now that args are parsed) ---
    try:
        import litellm
    except ImportError:
        print("Error: 'litellm' library not found. Please install it using 'pip install litellm'", file=sys.stderr)
        sys.exit(1)

    litellm._turn_on_debug() 

    # --- Call LLM ---
    print("---" + "Calling LLM" + "---")
    print(f"Model: {args.model}")
    print(f"Messages: {len(messages)} messages loaded.")
    print(f"Tools: {'Yes' if tools else 'No'}")
    print("---------------------" + "\n")

    # Set verbosity to see the raw request if needed
    # litellm.set_verbose=True

    kwargs = {
        "model": args.model,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    try:
        response = litellm.completion(**kwargs)

        # Print the full, pretty-printed JSON response
        print("--- LLM Response ---")
        print(response.model_dump_json(indent=2))
        print("--------------------")

    except Exception as e:
        print(f"\n--- An error occurred during the litellm API call ---", file=sys.stderr)
        print(f"Exception Type: {type(e).__name__}", file=sys.stderr)
        print(f"Exception Message: {e}", file=sys.stderr)

        # litellm exceptions often have useful attributes. Let's check for them.
        if hasattr(e, 'status_code'):
            print(f"Provider Status Code: {e.status_code}", file=sys.stderr)

        # Specifically check for litellm_debug_info and print it fully.
        if hasattr(e, 'litellm_debug_info'):
            print("--- Full litellm_debug_info ---", file=sys.stderr)
            print(e.litellm_debug_info, file=sys.stderr)
            print("-------------------------------", file=sys.stderr)

        # Try to find the raw response body from the provider, which might be in different attributes
        response_body = None
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            response_body = e.response.text
        elif hasattr(e, 'body'):  # Another common attribute name for the response body
            response_body = e.body

        if response_body:
            print("--- Provider Error Response ---", file=sys.stderr)
            try:
                # Try to pretty-print if the response is JSON
                error_json = json.loads(response_body)
                print(json.dumps(error_json, indent=2), file=sys.stderr)
            except (json.JSONDecodeError, TypeError):
                # Otherwise, print as raw text. It might be bytes, so decode safely.
                if isinstance(response_body, bytes):
                    print(response_body.decode('utf-8', errors='ignore'), file=sys.stderr)
                else:
                    print(response_body, file=sys.stderr)
            print("-----------------------------", file=sys.stderr)
        else:
            # If we couldn't find a specific body attribute, dump everything we can find.
            print("\n--- Full Exception Attributes (for debugging) ---", file=sys.stderr)
            if hasattr(e, '__dict__'):
                # __dict__ is often the most revealing, converting non-serializable items to string
                print(json.dumps(e.__dict__, indent=2, default=str), file=sys.stderr)
            else:
                # Fallback for exceptions without __dict__
                print(dir(e), file=sys.stderr)
            print("-------------------------------------------------", file=sys.stderr)

        print("\n--- Python Traceback ---", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
