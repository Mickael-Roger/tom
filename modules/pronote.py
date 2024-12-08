import pronotepy
from pathlib import Path

################################################################################################
#                                                                                              #
#                                         Pronote                                              #
#                                                                                              #
################################################################################################
class Pronote:

  def __init__(self) -> None:

    self.connexion = []
    self.data = {}

    self.update()



    self.tools = [
      {
        "type": "function",
        "description": "Get all information from pronote.",
        "function": {
            "name": "pronote_status",
            "parameters": {
            },
        },
      },
    ]

    self.systemContext = "Pronote is the application that manage children's school life. Pronote is the only way to have access to children's timetable, homework to do, grades, grade book, evaluations, parent/teachers communication and mainly information about school and college."


  def update(self):

    for child in config['pronote']:
      credentials = json.loads(Path(child['token']).read_text())
      client = pronotepy.Client.token_login(**credentials)

      if client.logged_in: # check if client successfully logged in
        # save new credentials - IMPORTANT
        #credentials = client.export_credentials()

        self.connexion.append({"children_name": child['name'], "client": client})

      name = client.info.name
      childname = child['name']
      print(f'Logged in as {name} for {childname}')

      for period in client.periods:
        for grade in period.grades:
          print(grade)

      credentials = client.export_credentials()
      Path(child['token']).write_text(json.dumps(credentials))



  # List Anki decks
  def status(self):
    self.update()
    print(self.data)
    return True, self.data



