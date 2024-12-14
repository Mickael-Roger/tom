import pronotepy

from datetime import datetime, timedelta

from pathlib import Path
import json
import sqlite3


################################################################################################
#                                                                                              #
#                                         Pronote                                              #
#                                                                                              #
################################################################################################
class Pronote:

  def __init__(self, config) -> None:

    self.connexion = []

    self.config = config['pronote']

    self.lastUpdate = datetime.now() - timedelta(hours=24)
    self.data = {}


    for child in self.config:
      db = child['cache']
      dbconn = sqlite3.connect(db)
      cursor = dbconn.cursor()
      cursor.execute('''
      CREATE TABLE IF NOT EXISTS grades (
         id TEXT PRIMARY KEY,  
         subject TEXT,
         date DATETIME,
         grade NUMERIC,
         out_of NUMERIC,
         min NUMERIC,
         max NUMERIC,
         average NUMERIC,
         comment TEXT
      )
      ''')
      dbconn.commit()
      dbconn.close()



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

    for child in self.config:

      if datetime.now() > (self.lastUpdate + timedelta(hours=1)):
        # Connect
        credentials = json.loads(Path(child['token']).read_text())
        client = pronotepy.ParentClient.token_login(**credentials)

        if client.logged_in:
          # save new credentials - IMPORTANT
          credentials = client.export_credentials()
          Path(child['token']).write_text(json.dumps(credentials))

          self.connexion.append({"children_name": child['name'], "client": client})

          name = client.info.name
          childname = child['name']
          print(f'Logged in as {name} for {childname}')

          db = child['cache']
          dbconn = sqlite3.connect(db)

          # Update the Grades DB content
          gradesIds = []
          entries = dbconn.execute('SELECT id FROM grades')

          for entry in entries:
            gradesIds.append(entry[0])

          for period in client.periods:
            for grade in period.grades:
              if grade.id not in gradesIds:
                dbconn.execute('INSERT INTO grades (id, subject, date, grade, out_of, min, max, average, comment) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (grade.id, grade.subject.name, grade.date.strftime('%Y-%m-%d %H:%M:%S'), str(grade.grade), str(grade.out_of), str(grade.min), str(grade.max), str(grade.average), grade.comment))

          self.lastUpdate = datetime.now() 
      else:
        print("Update too recent, use only cache")


  # List Anki decks
  def status(self):
    self.update()
    print(self.data)
    return True, self.data



