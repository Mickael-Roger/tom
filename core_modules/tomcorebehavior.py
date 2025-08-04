import os
import functools
import json


################################################################################################
#                                                                                              #
#                                   Behavior capability                                        #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "behavior",
  "class_name": "TomBehavior",
  "description": "This module is used to manage your behavioral instructions. It can be used to get or modify your behavior prompt. Use this module only if the user explicitly requests it, such as with phrases like: 'What are your behavior instructions?', 'Change your behavior' or 'Modify how you act'",
  "type": "core",
  "complexity": 0
}

class TomBehavior:

  def __init__(self, global_config, username) -> None:
    self.tom_config = tom_config

    behavior_path = os.path.join(os.getcwd(), global_config['global']['user_datadir'], username)
    os.makedirs(behavior_path, exist_ok=True)

    self.behavior_file = os.path.join(behavior_path, "behavior.md")

    # Create default behavior file if it doesn't exist
    if not os.path.exists(self.behavior_file):
      with open(self.behavior_file, 'w', encoding='utf-8') as f:
        f.write("# Instructions comportementales\n\nAucune instruction comportementale spécifique n'a été définie.\n")

    self.tools = [
      {
        "type": "function",
        "function": {
          "name": "tom_get_behavior_prompt",
          "description": "Get the current behavioral prompt content. Use this when the user asks about your current behavior instructions.",
          "parameters": {
          },
        },
      },
      {
        "type": "function",
        "function": {
          "name": "tom_modify_behavior_prompt",
          "description": "Modify the behavioral prompt based on user request. This will send the current prompt to the LLM to modify it according to the user's instruction.",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "user_instruction": {
                "type": "string",
                "description": "The user's instruction for how to modify the behavior (e.g., 'Add that you should be more formal', 'Remove the instruction about being casual')",
              },
            },
            "required": ["user_instruction"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = ""
    self.complexity = tom_config.get("complexity", 0)

    self.functions = {
      "tom_get_behavior_prompt": {
        "function": functools.partial(self.get_behavior_prompt)
      },
      "tom_modify_behavior_prompt": {
        "function": functools.partial(self.modify_behavior_prompt)
      },
    }

    # Store reference to llm for modify function (will be set by tomllm.py)
    self.llm = None


  def get_behavior_content(self):
    """Get the current behavior content from the markdown file"""
    try:
      with open(self.behavior_file, 'r', encoding='utf-8') as f:
        content = f.read().strip()
      
      # If file is empty or contains only the default message, return empty string
      if not content or content == "# Instructions comportementales\n\nAucune instruction comportementale spécifique n'a été définie.":
        return ""
      
      return content
    except:
      return ""


  def get_behavior_prompt(self):
    """Tool function to get the current behavioral prompt"""
    content = self.get_behavior_content()
    if not content:
      return {"status": "success", "content": "Aucune instruction comportementale spécifique n'a été définie."}
    
    return {"status": "success", "content": content}


  def modify_behavior_prompt(self, user_instruction):
    """Tool function to modify the behavioral prompt using LLM"""
    if not self.llm:
      return {"status": "error", "message": "LLM reference not available for behavior modification"}
    
    try:
      current_content = self.get_behavior_content()
      
      # Prepare the conversation for the LLM
      messages = [
        {
          "role": "system",
          "content": f"""You are an assistant that helps modify behavioral instructions for a chatbot.

Here is the current content of the behavior file:
```
{current_content if current_content else "# Instructions comportementales\n\nAucune instruction comportementale spécifique n'a été définie."}
```

The user wants to modify this behavior with the following instruction: "{user_instruction}"

You must return the complete new markdown file content that integrates this modification. The file must:
- Start with the title "# Instructions comportementales"
- Contain the updated behavioral instructions according to the request
- Be in French
- Be clear and well structured

Return ONLY the markdown file content, without any additional explanation."""
        }
      ]
      
      # Call LLM to modify the behavior
      response = self.llm.callLLM(messages=messages, complexity=1)
      
      if response and response.choices and response.choices[0].finish_reason == "stop":
        new_content = response.choices[0].message.content.strip()
        
        # Save the new content to the file
        with open(self.behavior_file, 'w', encoding='utf-8') as f:
          f.write(new_content)
        
        return {"status": "success", "message": "Instructions comportementales modifiées avec succès", "new_content": new_content}
      else:
        return {"status": "error", "message": "Erreur lors de la modification du comportement par le LLM"}
        
    except Exception as e:
      return {"status": "error", "message": f"Erreur lors de la modification : {str(e)}"}