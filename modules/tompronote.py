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

    self.connexion = []

    self.config = config

    self.lastUpdate = datetime.now() - timedelta(hours=24)
    self.periods = []
    self.current_period = None
    self.children = []

    self.cal = {} 


    for child in self.config:

      self.children.append(child['name'])
      self.cal[child['name']] = {} 

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
         pronote_id TEXT,
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
         pronote_id TEXT,
         subject TEXT,
         date DATETIME,
         description TEXT,
         done INTEGER DEFAULT 0
      )
      ''')
      cursor.execute('''
      CREATE TABLE IF NOT EXISTS absences (
         id INTEGER PRIMARY KEY AUTOINCREMENT,  
         pronote_id TEXT,
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
         pronote_id TEXT,
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
         pronote_id TEXT,
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
         pronote_id TEXT,
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
         pronote_id TEXT,
         subject TEXT,
         name TEXT
      )
      ''')
      dbconn.commit()
      dbconn.close()


    self.update()

    self.getCal(child_name="ambre", date="2024-12-20")

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
    }


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
          gradesIds = []
          entries = dbconn.execute('SELECT pronote_id FROM grades')

          for entry in entries:
            gradesIds.append(entry[0])

          for period in client.periods:
            for grade in period.grades:
              if grade.id not in gradesIds:
                dbconn.execute('INSERT INTO grades (pronote_id, subject, date, grade, out_of, min, max, average, comment) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (grade.id, grade.subject.name, grade.date.strftime('%Y-%m-%d %H:%M:%S'), str(grade.grade), str(grade.out_of), str(grade.min), str(grade.max), str(grade.average), grade.comment))

          # Update the Homeworks DB content
          homeworksIds = []
          entries = dbconn.execute('SELECT pronote_id FROM homeworks')

          for entry in entries:
            homeworksIds.append(entry[0])

          for homework in client.homework(date_from=datetime.now().date()):
            if homework.done:
              done = "1"
            else:
              done = "0"

            if homework.id not in homeworksIds:
              dbconn.execute('INSERT INTO homeworks (pronote_id, subject, date, description, done) VALUES (?, ?, ?, ?, ?)', (homework.id, homework.subject.name, homework.date.strftime('%Y-%m-%d'), homework.description, done))

          # Update the Absences DB content
          absencesIds = []
          entries = dbconn.execute('SELECT pronote_id FROM absences')

          for entry in entries:
            absencesIds.append(entry[0])

          for absence in client.current_period.absences:
            if absence.id not in absencesIds:
              reasonTxt = ""
              for reason in absence.reasons:
                reasonTxt = reasonTxt + str(reason) + "\n"

              if absence.justified:
                justified = "1"
              else:
                justified = "0"

              dbconn.execute('INSERT INTO absences (pronote_id, date_from, date_to, duration, reasons, justified) VALUES (?, ?, ?, ?, ?, ?)', (absence.id, absence.from_date.strftime('%Y-%m-%d'), absence.to_date.strftime('%Y-%m-%d'), absence.hours, reasonTxt, justified))


          # Update the Delays DB content
          delaysIds = []
          entries = dbconn.execute('SELECT pronote_id FROM delays')

          for entry in entries:
            delaysIds.append(entry[0])

          for delay in client.current_period.delays:
            if delay.id not in delaysIds:
              reasonTxt = ""
              for reason in delay.reasons:
                reasonTxt = reasonTxt + str(reason) + "\n"

              if delay.justified:
                justified = "1"
              else:
                justified = "0"

              dbconn.execute('INSERT INTO delays (pronote_id, datetime, minutes, justification, reasons, justified) VALUES (?, ?, ?, ?, ?, ?)', (delay.id, delay.datetime.strftime('%Y-%m-%d %H:%M:%S'), str(delay.minutes), delay.justification, reasonTxt, justified))


          # Update the Evaluations DB content
          evaluationsIds = []
          entries = dbconn.execute('SELECT pronote_id FROM evaluations')

          for entry in entries:
            evaluationsIds.append(entry[0])


          for period in client.periods:
            for evaluation in period.evaluations:
              if evaluation.id not in evaluationsIds:
                acquisitionTxt = ""
                for acquisition in evaluation.acquisitions:
                  if acquisition.level is not None and acquisition.name is not None:
                    acquisitionTxt = acquisitionTxt + "\n" + acquisition.level + ": " + acquisition.name

                dbconn.execute('INSERT INTO evaluations (pronote_id, datetime, name, subject, description, acquisitions) VALUES (?, ?, ?, ?, ?, ?)', (evaluation.id, evaluation.date.strftime('%Y-%m-%d'), evaluation.name, evaluation.subject.name, evaluation.description, acquisitionTxt))


          # Update the Punishment DB content
          punishmentsIds = []
          entries = dbconn.execute('SELECT pronote_id FROM punishments')

          for entry in entries:
            punishmentsIds.append(entry[0])

          for punishment in client.current_period.punishments:
            if punishment.id not in punishmentsIds:
              reasonTxt = ""
              for reason in punishment.reasons:
                reasonTxt = reasonTxt + str(reason) + "\n"

              dbconn.execute('INSERT INTO punishments (pronote_id, datetime, circumstances, nature, reasons, giver) VALUES (?, ?, ?, ?, ?, ?)', (punishment.id, punishment.datetime.strftime('%Y-%m-%d %H:%M:%S'), punishment.circumstances, punishment.nature, reasonTxt, punishment.giver))


          # Update the Teachers DB content
          teachersIds = []
          entries = dbconn.execute('SELECT pronote_id FROM teachers')

          for entry in entries:
            teachersIds.append(entry[0])

          for teacher in client.get_teaching_staff():
            if teacher.id not in teachersIds:
              dbconn.execute('INSERT INTO teachers (pronote_id, subject, name) VALUES (?, ?, ?)', (teacher.id, teacher.subjects[0].name, teacher.name))

          dbconn.commit()
          dbconn.close()


          # Update Calendar
          self.cal[child['name']] = {}
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


            for course in cal_week['donneesSec']['donnees']['ListeCours']:
              day, start = course['DateDuCours']['V'].split(' ')
              day = datetime.strptime(day, "%d/%m/%Y").strftime("%Y-%m-%d")
              duration = course['duree'] * 0.5
              subject = ""
              for contenu in course['ListeContenus']['V']:
                if contenu['G'] == 16:
                  subject = contenu['L']
              
              self.cal[child['name']].setdefault(day, {}) 
              self.cal[child['name']][day].setdefault(start, {"subject": subject, "duration_in_hour": duration}) 

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

    self.execUpdate(child_name=child_name, req='UPDATE grades SET viewed=1')

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

    toto=dict(sorted(self.cal[child_name][date].items()))
    print(toto)

    return True, dict(sorted(self.cal[child_name][date].items()))






