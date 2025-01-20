import json
from datetime import datetime, timedelta
import functools
import sqlite3
import time
import paramiko
import threading
import sys

################################################################################################
#                                                                                              #
#                                        VM usage                                              #
#                                                                                              #
################################################################################################

tom_config = {
  "module_name": "machine",
  "class_name": "TomVm",
  "description": "This module gives you access to a Linux Debian virtual machine with internet access. It allows you to execute commands as well as browse the internet, download tools, software, source code, etc. It also provides access to an environment where you can execute code if you need to develop something. This module is used asynchronously: the user asks you to do something (develop this, analyze that code, search for something on the internet, etc.). The response to the user's request will not be immediate, so this module also serves to list ongoing or past requests and access their results."
}

class TomVm:

  def __init__(self, config, llm) -> None:
  

    self.db = config['cache_db']

    self.llm = llm

    self.background_status = {"ts": int(time.time()), "status": None}

    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('''
    create table if not exists vmtasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_date DATETIME default current_date,
        result_date DATETIME default NULL,
        vm_id TEXT,
        request TEXT,
        status TEXT,
        current_status TEXT,
        result TEXT
    )
    ''')
    dbconn.commit()
    dbconn.close()

    self.client = paramiko.SSHClient()
    self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    self.client.connect(config['host'], port=22, username=config['username'], password=config['password'])


    self.tools = [
    ]

    self.systemContext = """
    """
    self.complexity = 1
    self.functions = {
    }

    #self.create('Count the number of line of code in that git repo: https://github.com/Mickael-Roger/tom')
    #self.process('Count the number of line of code in that git repo: https://github.com/Mickael-Roger/tom')
    #self.process('Clone that git repo: https://github.com/Mickael-Roger/tom and tell me if there are some security hole in the code in it. Install all software you need to perform this full and detailled security analysis')
    self.process("""You can access a file named '/root/cookomix.apk'. This file is an android apk that contains a receipe application. Your job is to analyze this apk and extract how the application search and display a receipe. You are free to install everything you need to do your job on the server.""")




  def execute_command(self, command):
    stdin, stdout, stderr = self.client.exec_command(command)
    output = stdout.read().decode('utf-8')
    error = stderr.read().decode('utf-8')

    return {"stdout": output, "stderr": error}


  def create(self, request):

    print("INSERT ******************************", file=sys.stdout)
    dbconn = sqlite3.connect(self.db)
    cursor = dbconn.cursor()
    cursor.execute('INSERT INTO vmtasks (request, status) VALUES (?, ?)', (request, 'in progress'))
    dbconn.commit()
    dbconn.close()

    print("Thread ******************************", file=sys.stdout)
    # Create a thread that process the request
    self.thread = threading.Thread(target=self.process, args=(request))
    self.thread.daemon = True  # Allow the thread to exit when the main program exits
    self.thread.start()
    

  def process(self, request):

    print("Thread 1 ******************************", file=sys.stdout)
    prompt = []

    tools = [
      {
        "type": "function",
        "function": {
          "name": "execute_command",
          "description": "Execute a Linux command and obtain the result",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "command": {
                "type": "string",
                "description": f"command to run",
              },
            },
            "required": ["command"],
            "additionalProperties": False,
          },
        },
      },
    ]


    # Create the LLM context
    prompt.append({"role": "system", "content": """You are an LLM agent that can interact with a Linux Debian machine to process the user's request.
    To do this, you will be able to execute commands on this machine and retrieve their results. You can persistently store files on the machine and access them later.
    For each command you execute, you will receive a response in JSON format:
    ```json
    {"return_code": RETURN_CODE_OF_THE_COMMAND, "stdout": COMMAND_STDOUT, "stderr": COMMAND_STDERR}
    ```
    Because the command and its output will be added to your contaxt that has a finite size, its a good idea to use silent mode or redirect output to a file for commands that could returns lots of data that is useless (for instance when running apt install, curl, tar, pip, wget or even docker run, ...) and more generaly, unles it is necessary always use silent mode or redirect output ot a file for command that provides progress information, ...
    """})

    prompt.append({"role": "user", "content": request})

    print("Thread 2 ******************************", file=sys.stdout)
    while True:
      response = self.llm.callLLM(messages=prompt, tools=tools, complexity=1, llm="deepseek")
  
      print(response, file=sys.stdout)
      if response != False:
        if response.choices[0].finish_reason == "stop":
          print("RESULTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTT", file=sys.stdout)
          print(response.choices[0].message.content)
          print("----------------------------------", file=sys.stdout)
          return response.choices[0].message.content
        elif response.choices[0].finish_reason == "tool_calls":
          prompt.append(response.choices[0].message.to_dict())
          for tool_call in response.choices[0].message.tool_calls:
            function_name = tool_call.function.name
            function_params = json.loads(tool_call.function.arguments)
            print("Call: " + str(function_name) + " with " + str(function_params), file=sys.stdout)
            res = functools.partial(self.execute_command)(**function_params)
            prompt.append({"role": 'tool', "content": json.dumps(res), "tool_call_id": tool_call.id})
    
    
            



    

