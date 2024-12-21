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
class TomPronote:

  def __init__(self, config) -> None:

    self.connexion = {}

    self.config = config

    self.lastUpdate = datetime.now() - timedelta(hours=24)
    self.periods = []
    self.current_period = None
    self.children = []

    self.cal = {} 


    for child in self.config:

      self.children.append(child['name'])
      self.cal[child['name']] = [] 

      db = child['cache']
      dbconn = sqlite3.connect(db)
      cursor = dbconn.cursor()

      cursor.execute('''
      CREATE TABLE IF NOT EXISTS averages (
         period TEXT,
         name TEXT,
         student TEXT,
         class_min NUMERIC,
         class_max NUMERIC,
         class_avg NUMERIC
      )
      ''')
      cursor.execute('''
      CREATE TABLE IF NOT EXISTS grades (
         id INTEGER PRIMARY KEY AUTOINCREMENT,  
         subject TEXT,
         date DATETIME,
         grade NUMERIC,
         out_of NUMERIC,
         min NUMERIC,
         max NUMERIC,
         average NUMERIC,
         comment TEXT,
         viewed INTEGER DEFAULT 0
      )
      ''')
      cursor.execute('''
      CREATE TABLE IF NOT EXISTS homeworks (
         id INTEGER PRIMARY KEY AUTOINCREMENT,  
         subject TEXT,
         date DATETIME,
         description TEXT,
         done INTEGER DEFAULT 0
      )
      ''')
      cursor.execute('''
      CREATE TABLE IF NOT EXISTS absences (
         id INTEGER PRIMARY KEY AUTOINCREMENT,  
         date_from DATETIME,
         date_to DATETIME,
         duration TEXT,
         reasons TEXT,
         justified INTEGER DEFAULT 0
      )
      ''')
      cursor.execute('''
      CREATE TABLE IF NOT EXISTS delays (
         id INTEGER PRIMARY KEY AUTOINCREMENT,  
         datetime DATETIME,
         minutes INTEGER,
         justification TEXT,
         reasons TEXT,
         justified INTEGER DEFAULT 0
      )
      ''')
      cursor.execute('''
      CREATE TABLE IF NOT EXISTS evaluations (
         id INTEGER PRIMARY KEY AUTOINCREMENT,  
         datetime DATETIME,
         name TEXT,
         subject TEXT,
         description TEXT,
         acquisitions TEXT,
         viewed INTEGER DEFAULT 0
      )
      ''')
      cursor.execute('''
      CREATE TABLE IF NOT EXISTS punishments (
         id INTEGER PRIMARY KEY AUTOINCREMENT,  
         datetime DATETIME,
         circumstances TEXT,
         nature TEXT,
         reasons TEXT,
         giver TEXT,
         viewed INTEGER DEFAULT 0
      )
      ''')
      cursor.execute('''
      CREATE TABLE IF NOT EXISTS teachers (
         id INTEGER PRIMARY KEY AUTOINCREMENT,  
         subject TEXT,
         name TEXT
      )
      ''')
      cursor.execute('''
      CREATE TABLE IF NOT EXISTS observations (
         id INTEGER PRIMARY KEY AUTOINCREMENT,  
         datetime DATETIME,
         subject TEXT,
         teacher TEXT,
         title TEXT,
         comment TEXT,
         is_read INTEGER,
         with_ar INTEGER
      )
      ''')
      cursor.execute('''
      CREATE TABLE IF NOT EXISTS informations (
         id INTEGER PRIMARY KEY AUTOINCREMENT,  
         creation_date DATETIME,
         title TEXT,
         content TEXT,
         author TEXT,
         date DATETIME,
         is_read INTEGER
      )
      ''')
      dbconn.commit()
      dbconn.close()


    self.update()

    self.tools = [
      {
        "type": "function",
        "function": {
          "description": "Get all child averages from pronote.",
          "name": "list_grade_averages",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "child_name": {
                "type": "string",
                "enum": self.children,
                "description": f"Name of the child.",
              },
            },
            "required": ["child_name"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "description": "Get all child grades from pronote.",
          "name": "list_grades",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "child_name": {
                "type": "string",
                "enum": self.children,
                "description": f"Name of the child.",
              },
            },
            "required": ["child_name"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "description": "Get all child school homeworks from pronote.",
          "name": "list_homeworks",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "child_name": {
                "type": "string",
                "enum": self.children,
                "description": f"Name of the child.",
              },
            },
            "required": ["child_name"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "description": "Get all child school absences from pronote.",
          "name": "list_school_absences",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "child_name": {
                "type": "string",
                "enum": self.children,
                "description": f"Name of the child.",
              },
            },
            "required": ["child_name"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "description": "Get all child school delays from pronote.",
          "name": "list_school_delays",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "child_name": {
                "type": "string",
                "enum": self.children,
                "description": f"Name of the child.",
              },
            },
            "required": ["child_name"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "description": "Get all child school evaluations from pronote.",
          "name": "list_school_evaluations",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "child_name": {
                "type": "string",
                "enum": self.children,
                "description": f"Name of the child.",
              },
            },
            "required": ["child_name"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "description": "Get all child school punishments from pronote.",
          "name": "list_school_punishments",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "child_name": {
                "type": "string",
                "enum": self.children,
                "description": f"Name of the child.",
              },
            },
            "required": ["child_name"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "description": "Get all child school observations from pronote (Like 'forgetting school supplies', 'Incomplete homework', 'Homework not done', ...).",
          "name": "list_school_observations",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "child_name": {
                "type": "string",
                "enum": self.children,
                "description": f"Name of the child.",
              },
            },
            "required": ["child_name"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "description": "Get all child school communication and information messages from pronote.",
          "name": "list_school_information_communication",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "child_name": {
                "type": "string",
                "enum": self.children,
                "description": f"Name of the child.",
              },
            },
            "required": ["child_name"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "description": "Get child school teachers from pronote.",
          "name": "list_school_teachers",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "child_name": {
                "type": "string",
                "enum": self.children,
                "description": f"Name of the child.",
              },
            },
            "required": ["child_name"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "description": "Mark a pronote element as read. Must be used when you return some information, grades, ... to indicate this information has been seen.",
          "name": "pronote_mark_as_seen",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "child_name": {
                "type": "string",
                "enum": self.children,
                "description": f"Name of the child.",
              },
              "object_type": {
                "type": "string",
                "enum": ["grade", "evaluation", "punishment", "information", "communication"],
                "description": f"Type of the element to mark as seen.",
              },
              "object_id": {
                "type": "string",
                "description": f"ID of the element to mark as seen.",
              },
            },
            "required": ["child_name", "type", "id"],
            "additionalProperties": False,
          },
        },
      },
      {
        "type": "function",
        "function": {
          "description": "Get child school daily calendar scheduling lessons. This function must be used when a children ask 'At what time do I start this morning?', 'What are my lessons tomorrow?', 'At what time do I finish school' or 'Do I have History today?'. Must also be used when a parent ask 'At what time my child finish school?', 'At what time will my child start tomorrow?', 'When is my next child french lesson?'",
          "name": "get_school_calendar",
          "strict": True,
          "parameters": {
            "type": "object",
            "properties": {
              "child_name": {
                "type": "string",
                "enum": self.children,
                "description": f"Name of the child.",
              },
              "date": {
                "type": "string",
                "description": f"Date of the calendar. Must be in form 'YYYY-MM-DD'",
              },
            },
            "required": ["child_name", "date"],
            "additionalProperties": False,
          },
        },
      },
    ]

    self.systemContext = "Pronote is the application that manage children's school life. Pronote is the only way to have access to children's timetable, homework to do, grades, grade book, evaluations, parent/teachers communication and mainly information about school and college."

    self.answerContext = {
      "list_grade_averages": "",
      "list_grades": "",
      "list_homeworks": "",
      "list_school_absences": "",
      "list_school_delays": "",
      "list_school_evaluations": "",
      "list_school_punishments": "",
      "list_school_teachers": "",
      "get_school_calendar": "",
      "list_school_observations": "",
      "list_school_information_communication": "",
      "pronote_mark_as_seen": "",
    }


  def connect(self, child_name, token):
    # Connect
    credentials = json.loads(Path(token).read_text())
    client = pronotepy.ParentClient.token_login(**credentials)

    if client.logged_in:
      # save new credentials - IMPORTANT
      credentials = client.export_credentials()
      Path(token).write_text(json.dumps(credentials))

      self.connexion[child_name] = client

      name = client.info.name
      print(f'Logged in as {name} for {child_name}')

      return True

    else:
      return False



  def update(self):

    for child in self.config:

      if datetime.now() > (self.lastUpdate + timedelta(hours=1)):

        childname = child['name']

        if self.connect(child_name=childname, token=child['token']):

          client = self.connexion[childname]
          name = client.info.name
          print(f'Logged in as {name} for {childname}')


          db = child['cache']
          dbconn = sqlite3.connect(db)

          self.current_period = client.current_period.name

          # Update the Averages DB content
          for period in client.periods:
            period_name = period.name
            for average in period.averages:
              if period_name not in self.periods:
                self.periods.append(period_name)

              dbconn.execute('DELETE FROM averages WHERE period = ? AND name = ?', (period_name, average.subject.name))
              dbconn.execute('INSERT INTO averages (period, name, student, class_min, class_max, class_avg) VALUES (?, ?, ?, ?, ?, ?)', (period_name, average.subject.name, str(average.student), str(average.min), str(average.max), str(average.class_average)))



          # Update the Grades DB content
          res = dbconn.execute('SELECT date FROM grades ORDER BY date DESC LIMIT 1').fetchone()
          if res:  
            max_date = datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S").date()
          else:
            max_date = datetime.strptime("2020-01-01 00:00:00", "%Y-%m-%d %H:%M:%S").date()

          for period in client.periods:
            for grade in period.grades:
              if grade.date >= max_date:
                if grade.date == max_date:
                  # Check for pre-existance
                  res = dbconn.execute('SELECT 1 FROM grades WHERE subject = ? AND date = ? AND comment = ?', (grade.subject.name, grade.date.strftime('%Y-%m-%d %H:%M:%S'), grade.comment)).fetchone()
                  if res:
                    break
                
                dbconn.execute('INSERT INTO grades (subject, date, grade, out_of, min, max, average, comment) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (grade.subject.name, grade.date.strftime('%Y-%m-%d %H:%M:%S'), str(grade.grade), str(grade.out_of), str(grade.min), str(grade.max), str(grade.average), grade.comment))



          # Update the Homeworks DB content
          todayTxt = datetime.now().strftime('%Y-%m-%d')

          dbconn.execute('DELETE FROM homeworks WHERE date >= ?', (todayTxt,))

          for homework in client.homework(date_from=datetime.now().date()):
            if homework.done:
              done = "1"
            else:
              done = "0"

              dbconn.execute('INSERT INTO homeworks (subject, date, description, done) VALUES (?, ?, ?, ?)', (homework.subject.name, homework.date.strftime('%Y-%m-%d'), homework.description, done))



          # Update the Absences DB content
          res = dbconn.execute('SELECT date_from FROM absences ORDER BY date_from DESC LIMIT 1').fetchone()
          if res:  
            max_date = datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S")
          else:
            max_date = datetime.strptime("2020-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")

          for absence in client.current_period.absences:
            if absence.from_date > max_date:
              reasonTxt = ""
              for reason in absence.reasons:
                reasonTxt = reasonTxt + str(reason) + "\n"

              if absence.justified:
                justified = "1"
              else:
                justified = "0"

              dbconn.execute('INSERT INTO absences (date_from, date_to, duration, reasons, justified) VALUES (?, ?, ?, ?, ?)', (absence.from_date.strftime('%Y-%m-%d %H:%M:%S'), absence.to_date.strftime('%Y-%m-%d %H:%M:%S'), absence.hours, reasonTxt, justified))


          # Update the Delays DB content
          res = dbconn.execute('SELECT datetime FROM delays ORDER BY datetime DESC LIMIT 1').fetchone()
          if res:  
            max_date = datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S")
          else:
            max_date = datetime.strptime("2020-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")


          for delay in client.current_period.delays:
            if delay.date > max_date:
              reasonTxt = ""
              for reason in delay.reasons:
                reasonTxt = reasonTxt + str(reason) + "\n"

              if delay.justified:
                justified = "1"
              else:
                justified = "0"

              dbconn.execute('INSERT INTO delays (datetime, minutes, justification, reasons, justified) VALUES (?, ?, ?, ?, ?)', (delay.datetime.strftime('%Y-%m-%d %H:%M:%S'), str(delay.minutes), delay.justification, reasonTxt, justified))


          # Update the Evaluations DB content
          res = dbconn.execute('SELECT datetime FROM evaluations ORDER BY datetime DESC LIMIT 1').fetchone()
          if res:  
            max_date = datetime.strptime(res[0], "%Y-%m-%d").date()
          else:
            max_date = datetime.strptime("2020-01-01", "%Y-%m-%d").date()


          for period in client.periods:
            for evaluation in period.evaluations:
              if evaluation.date >= max_date:
                if evaluation.date == max_date:
                  # Check for pre-existance
                  res = dbconn.execute('SELECT 1 FROM evaluations WHERE name = ? AND datetime = ? AND subject = ?', (evaluation.name, evaluation.date.strftime('%Y-%m-%d'), evaluation.subject.name)).fetchone()
                  if res:
                    break

                acquisitionTxt = ""
                for acquisition in evaluation.acquisitions:
                  if acquisition.level is not None and acquisition.name is not None:
                    acquisitionTxt = acquisitionTxt + "\n" + acquisition.level + ": " + acquisition.name

                dbconn.execute('INSERT INTO evaluations (datetime, name, subject, description, acquisitions) VALUES (?, ?, ?, ?, ?)', (evaluation.date.strftime('%Y-%m-%d'), evaluation.name, evaluation.subject.name, evaluation.description, acquisitionTxt))


          # Update the Punishment DB content
          res = dbconn.execute('SELECT datetime FROM punishments ORDER BY datetime DESC LIMIT 1').fetchone()
          if res:  
            max_date = datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S")
          else:
            max_date = datetime.strptime("2020-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")

          for punishment in client.current_period.punishments:
            if punishment.date > max_date:
              reasonTxt = ""
              for reason in punishment.reasons:
                reasonTxt = reasonTxt + str(reason) + "\n"

              dbconn.execute('INSERT INTO punishments (datetime, circumstances, nature, reasons, giver) VALUES (?, ?, ?, ?, ?)', (punishment.date.strftime('%Y-%m-%d %H:%M:%S'), punishment.circumstances, punishment.nature, reasonTxt, punishment.giver))



          # Update the Teachers DB content
          entries = dbconn.execute('DELETE FROM teachers')


          for teacher in client.get_teaching_staff():
            dbconn.execute('INSERT INTO teachers (subject, name) VALUES (?, ?)', (teacher.subjects[0].name, teacher.name))


          # Update the Information DB content
          res = dbconn.execute('SELECT creation_date FROM informations ORDER BY creation_date DESC LIMIT 1').fetchone()
          if res:  
            max_date = datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S")
          else:
            max_date = datetime.strptime("2020-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")

          informations = client.information_and_surveys()
          for information in informations:
            if information.creation_date > max_date:

              if information.read:
                is_read = "1"
              else:
                is_read = "0"

              dbconn.execute('INSERT INTO informations (creation_date, date, title, author, content, is_read) VALUES (?, ?, ?, ?, ?, ?)', (information.creation_date, information.start_date.strftime('%Y-%m-%d'), information.title, information.author, information.content, is_read))




          # UPdate observations
          data = {
            "DateDebut":{
              "V": client.current_period.start.strftime("%-m/%-d/%Y %-H:%-M:%-S"),
              "_T": 7
            },
            "DateFin":{
              "V": client.current_period.end.strftime("%-m/%-d/%Y %-H:%-M:%-S"),
              "_T": 7
            },
            "periode":{
              "N": client.current_period.id,
              "G": 2,
              "L": client.current_period.name
            }
          }

          val = client.post("PagePresence", 19, data)

          res = dbconn.execute('SELECT datetime FROM observations ORDER BY datetime DESC LIMIT 1').fetchone()
          if res:  
            max_date = datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S")
          else:
            max_date = datetime.strptime("2020-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")


          for observation in val['donneesSec']['donnees']['listeAbsences']['V']:
            if "genreObservation" in observation.keys():

              date = datetime.strptime(observation['date']['V'], "%d/%m/%Y %H:%M:%S")

              if date > max_date:

                if observation['estLue']:
                  is_read = "1"
                else:
                  is_read = "0"

                if observation['avecARObservation']:
                  with_ar = "1"
                else:
                  with_ar = "0"


                dbconn.execute('INSERT INTO observations (datetime, subject, teacher, title, comment, is_read, with_ar) VALUES (?, ?, ?, ?, ?, ?, ?)', (date.strftime('%Y-%m-%d %H:%M:%S'), observation['matiere']['V']['L'], observation['demandeur']['V']['L'], observation['L'], observation['commentaire'], is_read, with_ar ))


          dbconn.commit()
          dbconn.close()

          # Update Calendar
          self.cal[child['name']] = []
          l = client.parametres_utilisateur['donneesSec']['donnees']['ressource']['L']
          g = client.parametres_utilisateur['donneesSec']['donnees']['ressource']['G']
          n = client.parametres_utilisateur['donneesSec']['donnees']['ressource']['N']

          for i in range(0, 1):
            week = client.week+i
            data = {
              "ressource":{
                "N": n,
                "G": g,
                "L": l
              },
              "numeroSemaine": week,
              "avecAbsencesEleve": False,
              "avecConseilDeClasse": True,
              "avecRetenuesEleve": True,
              "estEDTPermanence": False,
              "avecAbsencesRessource": True,
              "avecCoursSortiePeda": True,
              "avecDisponibilites": True,
              "avecRessourcesLibrePiedHoraire": False,
              "avecInfosPrefsGrille": True,
              "Ressource":{
                "N": n,
                "G": g,
                "L": l
              },
              "NumeroSemaine": week
            }

            cal_week = client.post("PageEmploiDuTemps", 16, data)


            for lesson in cal_week['donneesSec']['donnees']['ListeCours']:

              start_date = datetime.strptime(lesson['DateDuCours']['V'], "%d/%m/%Y %H:%M:%S")
              duration = lesson['duree'] * 0.5
              end_date = start_date + timedelta(hours=duration)

              start = start_date.strftime("%Y-%m-%d %H:%M:%S") 
              end = end_date.strftime("%Y-%m-%d %H:%M:%S") 

              subject = ""
              for contenu in lesson['ListeContenus']['V']:
                if contenu['G'] == 16:
                  subject = contenu['L']

              if "estAnnule" in lesson:
                is_canceled = lesson['estAnnule']
              else:
                is_canceled = False

              if "Statut" in lesson:
                status = lesson['Statut'] 
              else:
                status = ""

              self.cal[childname].append({"subject": subject, "start": start, "end": end, "status": status, "is_canceled": is_canceled})
              

          self.lastUpdate = datetime.now() 

      else:
        print("Update too recent, use cache")


  def execSelect(self, child_name, req):

    self.update()

    db = None
    for child in self.config:
      if child['name'] == child_name:
        db = child['cache']

    if db is None:
      return False, f"Could not find child {child_name}"

    dbconn = sqlite3.connect(db)
    cursor = dbconn.cursor()

    cursor.execute(req)
    entries = cursor.fetchall()

    dbconn.close()

    return True, entries 

  def execUpdate(self, child_name, req):

    db = None
    for child in self.config:
      if child['name'] == child_name:
        db = child['cache']

    if db is None:
      return False, f"Could not find child {child_name}"

    dbconn = sqlite3.connect(db)
    dbconn.execute(req)
    dbconn.commit()
    dbconn.close()

    return True


  def averages(self, child_name, period=None):

    if period is not None:
      filter = f" WHERE period = '{period}' "
    else:
      filter = ""

    res, avgs = self.execSelect(child_name=child_name, req='SELECT period, name, student, class_min, class_max, class_avg FROM averages ' + filter + ' ORDER BY period, name ASC')

    if res is False:
      return False, avgs

    averages = {"current_period": self.current_period, "grades_averages": []}

    for avg in avgs:
      averages['grades_averages'].append({"period": avg[0], "subject": avg[1], "student_avg": avg[2], "class_min_avg": avg[3], "class_max_avg": avg[4], "class_avg": avg[5]})

    print(averages)

    return True, averages


  def grades(self, child_name):

    res, val = self.execSelect(child_name=child_name, req='SELECT date, subject, grade, out_of, min, max, average, comment, viewed FROM grades ORDER BY date, subject ASC')

    if res is False:
      return False, val

    grades = []

    for grade in val:
      if grade[8] == "1":
        new = False
      else:
        new = True

      grades.append({"date": grade[0].replace(" 00:00:00", ""), "subject": grade[1], "grade": grade[2], "grade_out_of": grade[3], "class_min_grade": grade[4], "class_max_grade": grade[5], "class_avg_grade": grade[6], "grade_comment": grade[7], "is_new": new})

    print(grades)

    return True, grades




  def homeworks(self, child_name):

    res, val = self.execSelect(child_name=child_name, req="SELECT date, subject, description, done FROM homeworks WHERE date > DATE('now') ORDER BY date ASC")

    if res is False:
      return False, val

    homeworks = []

    for homework in val:
      if homework[3] == "1":
        done = False
      else:
        done = True

      homeworks.append({"due_date": homework[0].replace(" 00:00:00", ""), "subject": homework[1], "description": homework[2], "is_done": done})

    print(homeworks)

    return True, homeworks



  def absences(self, child_name):

    res, val = self.execSelect(child_name=child_name, req="SELECT date_from, date_to, duration, reasons, justified FROM absences ORDER BY date_from DESC")

    if res is False:
      return False, val

    absences = []

    for absence in val:
      if absence[4] == "1":
        justified = False
      else:
        justified = True

      absences.append({"date_from": absence[0], "date_to": absence[1], "duration": absence[2], "reasons": absence[3], "is_justified": justified})

    print(absences)

    return True, absences


  def delays(self, child_name):

    res, val = self.execSelect(child_name=child_name, req="SELECT datetime, minutes, justificaton, reasons, justified FROM delays ORDER BY datetime DESC")

    if res is False:
      return False, val

    delays = []

    for delay in val:
      if delay[4] == "1":
        justified = False
      else:
        justified = True

      delays.append({"date": delay[0], "minutes": delay[1], "justification": delay[2], "reasons": delay[3], "is_justified": justified})

    print(delays)

    return True, delays


  def evaluations(self, child_name):

    res, val = self.execSelect(child_name=child_name, req="SELECT datetime, name, subject, description, acquisitions, viewed FROM evaluations ORDER BY datetime DESC")

    if res is False:
      return False, val

    evaluations = []

    for evaluation in val:
      if evaluation[5] == "1":
        new = False
      else:
        new = True

      evaluations.append({"date": evaluation[0].replace(" 00:00:00", ""), "name": evaluation[1], "subject": evaluation[2], "description": evaluation[3], "acquisitions": evaluation[4], "is_new": new})

    print(evaluations)

    return True, evaluations


  def punishments(self, child_name):

    res, val = self.execSelect(child_name=child_name, req="SELECT datetime, circumstances, nature, reasons, giver, viewed FROM punishments ORDER BY datetime DESC")

    if res is False:
      return False, val

    punishments = []

    for punishment in val:
      if punishment[5] == "1":
        new = False
      else:
        new = True

      punishments.append({"date": punishment[0].replace(" 00:00:00", ""), "circumstances": punishment[1], "nature": punishment[2], "reasons": punishment[3], "giver": punishment[4], "is_new": new})

    print(punishments)

    return True, punishments


  def teachers(self, child_name):

    res, val = self.execSelect(child_name=child_name, req="SELECT name, subject FROM teachers")

    if res is False:
      return False, val

    teachers = []

    for teacher in val:
      teachers.append({"name": teacher[0], "subject": teacher[1]})

    print(teachers)

    return True, teachers


  def getCal(self, child_name, date):

    if child_name not in self.cal:
      return False, f"Could not find {child_name} child"

    lessons = []

    for lesson in self.cal[child_name]:
      day = datetime.strptime(lesson['start'], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")

      if day == date:
        lessons.append(lesson)

    print(lessons)

    return True, lessons


  def observations(self, child_name):

    res, val = self.execSelect(child_name=child_name, req="SELECT id, datetime, subject, teacher, title, comment, is_read, with_ar FROM observations")

    if res is False:
      return False, val

    observations = []

    for observation in val:
      observations.append({"id": observation[0], "date": observation[1], "subject": observation[2], "teacher": observation[3], "observation_title": observation[4], "comment": observation[5],"is_new": observation[6], "need_ar": observation[7]})

    print(observations)

    return True, observations


  def informations(self, child_name):

    res, val = self.execSelect(child_name=child_name, req="SELECT id, date, title, author, content, is_read FROM informations ORDER BY date DESC")

    if res is False:
      return False, val

    informations = []

    for information in val:
      informations.append({"id": information[0], "date": information[1], "title": information[2], "author": information[3], "message": information[4], "is_read": information[5]})

    print(informations)

    return True, informations


  def mark_seen(self, child_name, object_type, object_id):

    if child_name not in self.cal:
      return False, f"Could not find {child_name} child"








