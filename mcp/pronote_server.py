#!/usr/bin/env python3
"""
Pronote MCP Server
Provides school management functionality via MCP protocol
Based on the original tompronote.py module
"""

import json
import os
import sys
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pronotepy
import requests
import yaml
from mcp.server.fastmcp import FastMCP
from mcp.types import Tool, TextContent

# Add lib directory to path for imports
sys.path.insert(0, '/app/lib')
try:
    from tomlogger import init_logger
    import tomlogger
except ImportError:
    # Fallback if tomlogger is not available
    import logging
    logging.basicConfig(level=logging.INFO)
    tomlogger = None

# Initialize logging
log_level = os.environ.get('TOM_LOG_LEVEL', 'INFO')
if tomlogger:
    logger = init_logger(log_level)
    tomlogger.info(f"🚀 Pronote MCP Server starting with log level: {log_level}", module_name="pronote")
else:
    logger = logging.getLogger(__name__)

# Server configuration and description
SERVER_DESCRIPTION = "This module is used for Pronote. Pronote is an application used to manage children's school life. It is the only way to access schedules, homework, grades, grade books, and to communicate with schools, middle schools, high schools, and teachers."

# Initialize FastMCP server
server = FastMCP(name="pronote-server", stateless_http=True, host="0.0.0.0", port=80)


class PronoteService:
    """Pronote service class based on original TomPronote"""
    
    def __init__(self):
        self.connexion = {}
        self.lastUpdate = datetime.now() - timedelta(hours=24)
        self.periods = []
        self.current_period = None
        self.children = []
        self.cal = {}
        self.background_status = {"ts": int(time.time()), "status": None}
        
        # Load configuration from environment or default paths
        self.config = self._load_config()
        
        # Initialize database and children
        self._initialize_children()
        
        # Start background update thread if there are children configured
        if self.children:
            self.thread = threading.Thread(target=self.thread_update)
            self.thread.daemon = True
            self.thread.start()
        
        if tomlogger:
            tomlogger.info(f"Pronote service initialized with {len(self.children)} children", module_name="pronote")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load Pronote configuration from /data/config.yml"""
        config_path = '/data/config.yml'
        
        if not os.path.exists(config_path):
            if tomlogger:
                tomlogger.error(f"Config file not found: {config_path}", module_name="pronote")
            return {'children': []}
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                full_config = yaml.safe_load(f)
                
            # Extract pronote section
            pronote_config = full_config.get('pronote', {})
            
            children_config = []
            for child in pronote_config.get('children', []):
                child_name = child.get('name')
                if not child_name:
                    if tomlogger:
                        tomlogger.warning("Child configuration missing 'name' field", module_name="pronote")
                    continue
                
                # Build file paths based on new structure
                child_dir = Path(f'/data/childrens/{child_name}')
                token_path = child_dir / 'token.json'
                cache_path = child_dir / 'data.sqlite'
                
                children_config.append({
                    'name': child_name,
                    'token': str(token_path),
                    'cache': str(cache_path)
                })
            
            if tomlogger:
                tomlogger.info(f"Loaded Pronote config with {len(children_config)} children", module_name="pronote")
                
            return {'children': children_config}
            
        except (yaml.YAMLError, IOError) as e:
            if tomlogger:
                tomlogger.error(f"Failed to load Pronote config: {e}", module_name="pronote")
            return {'children': []}
    
    def _initialize_children(self):
        """Initialize children and their databases"""
        for child in self.config.get('children', []):
            child_name = child['name']
            self.children.append(child_name)
            self.cal[child_name] = []
            
            # Ensure child directory exists
            child_dir = Path(f'/data/childrens/{child_name}')
            child_dir.mkdir(parents=True, exist_ok=True)
            
            # Set up file paths
            token_path = child_dir / 'token.json'
            cache_path = child_dir / 'data.sqlite'
            
            # Update child config with full paths
            child['token'] = str(token_path)
            child['cache'] = str(cache_path)
            
            # Initialize database
            self._init_database(str(cache_path))
            
            if tomlogger:
                tomlogger.info(f"Initialized child '{child_name}' with directory {child_dir}", module_name="pronote")
        
        # Only update data if there are children configured
        if self.children:
            self.update()
        else:
            if tomlogger:
                tomlogger.info("No children configured for Pronote", module_name="pronote")
    
    def _init_database(self, db_path: str):
        """Initialize SQLite database with all required tables"""
        dbconn = sqlite3.connect(db_path)
        cursor = dbconn.cursor()
        
        # Create all tables as in original
        tables = [
            '''CREATE TABLE IF NOT EXISTS averages (
                period TEXT,
                name TEXT,
                student TEXT,
                class_min NUMERIC,
                class_max NUMERIC,
                class_avg NUMERIC
            )''',
            '''CREATE TABLE IF NOT EXISTS grades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,  
                subject TEXT,
                date DATETIME,
                grade NUMERIC,
                out_of NUMERIC,
                min NUMERIC,
                max NUMERIC,
                average NUMERIC,
                comment TEXT,
                is_new BOOLEAN DEFAULT 1
            )''',
            '''CREATE TABLE IF NOT EXISTS homeworks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,  
                subject TEXT,
                date DATETIME,
                description TEXT,
                done BOOLEAN DEFAULT 0
            )''',
            '''CREATE TABLE IF NOT EXISTS absences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,  
                date_from DATETIME,
                date_to DATETIME,
                duration TEXT,
                reasons TEXT,
                justified BOOLEAN DEFAULT 0
            )''',
            '''CREATE TABLE IF NOT EXISTS delays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,  
                datetime DATETIME,
                minutes INTEGER,
                justification TEXT,
                reasons TEXT,
                justified BOOLEAN DEFAULT 0
            )''',
            '''CREATE TABLE IF NOT EXISTS evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,  
                datetime DATETIME,
                name TEXT,
                subject TEXT,
                description TEXT,
                acquisitions TEXT,
                is_new BOOLEAN DEFAULT 1
            )''',
            '''CREATE TABLE IF NOT EXISTS punishments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,  
                datetime DATETIME,
                circumstances TEXT,
                nature TEXT,
                reasons TEXT,
                giver TEXT,
                is_new BOOLEAN DEFAULT 1
            )''',
            '''CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,  
                subject TEXT,
                name TEXT
            )''',
            '''CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,  
                datetime DATETIME,
                subject TEXT,
                teacher TEXT,
                title TEXT,
                comment TEXT,
                is_read BOOLEAN,
                with_ar BOOLEAN,
                is_new BOOLEAN DEFAULT 1
            )''',
            '''CREATE TABLE IF NOT EXISTS informations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,  
                creation_date DATETIME,
                title TEXT,
                content TEXT,
                author TEXT,
                date DATETIME,
                is_read BOOLEAN,
                is_new BOOLEAN DEFAULT 1
            )'''
        ]
        
        for table_sql in tables:
            cursor.execute(table_sql)
        
        dbconn.commit()
        dbconn.close()
    
    def connect(self, child_name: str, token_path: str) -> bool:
        """Connect to Pronote for a specific child"""
        try:
            credentials = json.loads(Path(token_path).read_text())
            client = pronotepy.ParentClient.token_login(**credentials)
            
            if client.logged_in:
                # Save new credentials
                credentials = client.export_credentials()
                Path(token_path).write_text(json.dumps(credentials))
                
                self.connexion[child_name] = client
                
                name = client.info.name
                if tomlogger:
                    tomlogger.info(f'Logged in as {name} for {child_name}', module_name="pronote")
                
                return True
            else:
                if tomlogger:
                    tomlogger.error(f'Failed to login for {child_name}', module_name="pronote")
                return False
                
        except Exception as e:
            if tomlogger:
                tomlogger.error(f'Connection error for {child_name}: {e}', module_name="pronote")
            return False
    
    def thread_update(self):
        """Background thread for updating data and checking notifications"""
        while True:
            try:
                if datetime.now() > (self.lastUpdate + timedelta(hours=4)):
                    if tomlogger:
                        tomlogger.info("Updating Pronote data...", module_name="pronote")
                    self.update()
            except Exception as e:
                if tomlogger:
                    tomlogger.error(f"Failed to update Pronote: {e}", module_name="pronote")
            
            # Check for new notifications
            msg = None
            for child in self.config.get('children', []):
                childname = child['name']
                db = child['cache']
                
                try:
                    dbconn = sqlite3.connect(db)
                    cursor = dbconn.cursor()
                    
                    cursor.execute('SELECT count(*) FROM grades WHERE is_new=1')
                    grades = cursor.fetchone()
                    cursor.execute('SELECT count(*) FROM observations WHERE is_new=1')
                    observations = cursor.fetchone()
                    cursor.execute('SELECT count(*) FROM punishments WHERE is_new=1')
                    punishments = cursor.fetchone()
                    cursor.execute('SELECT count(*) FROM informations WHERE is_new=1')
                    informations = cursor.fetchone()
                    
                    dbconn.close()
                    
                    if grades[0] > 0 or informations[0] > 0 or observations[0] > 0 or punishments[0] > 0:
                        if msg is None:
                            msg = ""
                        msg += f"{childname}: "
                        
                        if grades[0] > 0:
                            msg += f"{grades[0]} new grades,"
                        if informations[0] > 0:
                            msg += f"{informations[0]} new messages,"
                        if observations[0] > 0:
                            msg += f"{observations[0]} new observations,"
                        if punishments[0] > 0:
                            msg += f"{punishments[0]} new punishments,"
                        
                        msg = msg[:-1] + "\n"
                except Exception as e:
                    if tomlogger:
                        tomlogger.error(f"Error checking notifications for {childname}: {e}", module_name="pronote")
            
            if msg is not None:
                msg = msg[:-1]
            
            if msg != self.background_status['status']:
                self.background_status['ts'] = int(time.time())
                self.background_status['status'] = msg
            
            time.sleep(60)
    
    def update(self):
        """Update all Pronote data for all children"""
        if datetime.now() <= (self.lastUpdate + timedelta(hours=1)):
            if tomlogger:
                tomlogger.debug("Update too recent, using cache", module_name="pronote")
            return
        
        for child in self.config.get('children', []):
            childname = child['name']
            
            if not self.connect(child_name=childname, token_path=child['token']):
                continue
                
            client = self.connexion[childname]
            db = child['cache']
            dbconn = sqlite3.connect(db)
            
            self.current_period = client.current_period.name
            
            # Update all data types as in original
            self._update_averages(client, dbconn, childname)
            self._update_grades(client, dbconn, childname)
            self._update_homeworks(client, dbconn, childname)
            self._update_absences(client, dbconn, childname)
            self._update_delays(client, dbconn, childname)
            self._update_evaluations(client, dbconn, childname)
            self._update_punishments(client, dbconn, childname)
            self._update_teachers(client, dbconn, childname)
            self._update_informations(client, dbconn, childname)
            self._update_observations(client, dbconn, childname)
            self._update_calendar(client, childname)
            
            dbconn.close()
        
        self.lastUpdate = datetime.now()
    
    def _update_averages(self, client, dbconn, childname):
        """Update averages data"""
        try:
            for period in client.periods:
                period_name = period.name
                for average in period.averages:
                    if period_name not in self.periods:
                        self.periods.append(period_name)
                    
                    dbconn.execute('DELETE FROM averages WHERE period = ? AND name = ?', 
                                 (period_name, average.subject.name))
                    dbconn.execute('INSERT INTO averages (period, name, student, class_min, class_max, class_avg) VALUES (?, ?, ?, ?, ?, ?)', 
                                 (period_name, average.subject.name, str(average.student), 
                                  str(average.min), str(average.max), str(average.class_average)))
                    dbconn.commit()
        except Exception as e:
            if tomlogger:
                tomlogger.error(f'Could not update averages for {childname}: {e}', module_name="pronote")
    
    def _update_grades(self, client, dbconn, childname):
        """Update grades data"""
        try:
            res = dbconn.execute('SELECT date FROM grades ORDER BY date DESC LIMIT 1').fetchone()
            if res:
                max_date = datetime.strptime(res[0], "%Y-%m-%d").date()
            else:
                max_date = datetime.strptime("2020-01-01", "%Y-%m-%d").date()
            
            for period in client.periods:
                for grade in period.grades:
                    if grade.date >= max_date:
                        if grade.date == max_date:
                            # Check for pre-existence
                            res = dbconn.execute('SELECT 1 FROM grades WHERE subject = ? AND date = ? AND comment = ?', 
                                               (grade.subject.name, grade.date.strftime('%Y-%m-%d'), grade.comment)).fetchone()
                            if res:
                                continue
                        
                        dbconn.execute('INSERT INTO grades (subject, date, grade, out_of, min, max, average, comment) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', 
                                     (grade.subject.name, grade.date.strftime('%Y-%m-%d'), 
                                      str(grade.grade), str(grade.out_of), str(grade.min), 
                                      str(grade.max), str(grade.average), grade.comment))
                        dbconn.commit()
        except Exception as e:
            if tomlogger:
                tomlogger.error(f'Could not update grades for {childname}: {e}', module_name="pronote")
    
    def _update_homeworks(self, client, dbconn, childname):
        """Update homeworks data"""
        try:
            todayTxt = datetime.now().strftime('%Y-%m-%d')
            dbconn.execute('DELETE FROM homeworks WHERE date >= ?', (todayTxt,))
            
            for homework in client.homework(date_from=datetime.now().date()):
                dbconn.execute('INSERT INTO homeworks (subject, date, description, done) VALUES (?, ?, ?, ?)', 
                             (homework.subject.name, homework.date.strftime('%Y-%m-%d'), 
                              homework.description, homework.done))
            dbconn.commit()
        except Exception as e:
            if tomlogger:
                tomlogger.error(f'Could not update homeworks for {childname}: {e}', module_name="pronote")
    
    def _update_absences(self, client, dbconn, childname):
        """Update absences data"""
        try:
            res = dbconn.execute('SELECT date_from FROM absences ORDER BY date_from DESC LIMIT 1').fetchone()
            if res:
                max_date = datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S")
            else:
                max_date = datetime.strptime("2020-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
            
            for absence in client.current_period.absences:
                if absence.from_date > max_date:
                    reasonTxt = ""
                    for reason in absence.reasons:
                        reasonTxt += str(reason) + "\n"
                    
                    dbconn.execute('INSERT INTO absences (date_from, date_to, duration, reasons, justified) VALUES (?, ?, ?, ?, ?)', 
                                 (absence.from_date.strftime('%Y-%m-%d %H:%M:%S'), 
                                  absence.to_date.strftime('%Y-%m-%d %H:%M:%S'), 
                                  absence.hours, reasonTxt, absence.justified))
                    dbconn.commit()
        except Exception as e:
            if tomlogger:
                tomlogger.error(f'Could not update absences for {childname}: {e}', module_name="pronote")
    
    def _update_delays(self, client, dbconn, childname):
        """Update delays data"""
        try:
            res = dbconn.execute('SELECT datetime FROM delays ORDER BY datetime DESC LIMIT 1').fetchone()
            if res:
                max_date = datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S")
            else:
                max_date = datetime.strptime("2020-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
            
            for delay in client.current_period.delays:
                if delay.date > max_date:
                    reasonTxt = ""
                    for reason in delay.reasons:
                        reasonTxt += str(reason) + "\n"
                    
                    dbconn.execute('INSERT INTO delays (datetime, minutes, justification, reasons, justified) VALUES (?, ?, ?, ?, ?)', 
                                 (delay.datetime.strftime('%Y-%m-%d %H:%M:%S'), 
                                  str(delay.minutes), delay.justification, reasonTxt, delay.justified))
                    dbconn.commit()
        except Exception as e:
            if tomlogger:
                tomlogger.error(f'Could not update delays for {childname}: {e}', module_name="pronote")
    
    def _update_evaluations(self, client, dbconn, childname):
        """Update evaluations data"""
        try:
            res = dbconn.execute('SELECT datetime FROM evaluations ORDER BY datetime DESC LIMIT 1').fetchone()
            if res:
                max_date = datetime.strptime(res[0], "%Y-%m-%d").date()
            else:
                max_date = datetime.strptime("2020-01-01", "%Y-%m-%d").date()
            
            for period in client.periods:
                for evaluation in period.evaluations:
                    if evaluation.date >= max_date:
                        if evaluation.date == max_date:
                            # Check for pre-existence
                            res = dbconn.execute('SELECT 1 FROM evaluations WHERE name = ? AND datetime = ? AND subject = ?', 
                                               (evaluation.name, evaluation.date.strftime('%Y-%m-%d'), evaluation.subject.name)).fetchone()
                            if res:
                                continue
                        
                        acquisitionTxt = ""
                        for acquisition in evaluation.acquisitions:
                            if acquisition.level is not None and acquisition.name is not None:
                                acquisitionTxt += "\n" + acquisition.level + ": " + acquisition.name
                        
                        dbconn.execute('INSERT INTO evaluations (datetime, name, subject, description, acquisitions) VALUES (?, ?, ?, ?, ?)', 
                                     (evaluation.date.strftime('%Y-%m-%d'), evaluation.name, 
                                      evaluation.subject.name, evaluation.description, acquisitionTxt))
                        dbconn.commit()
        except Exception as e:
            if tomlogger:
                tomlogger.error(f'Could not update evaluations for {childname}: {e}', module_name="pronote")
    
    def _update_punishments(self, client, dbconn, childname):
        """Update punishments data"""
        try:
            res = dbconn.execute('SELECT datetime FROM punishments ORDER BY datetime DESC LIMIT 1').fetchone()
            if res:
                max_date = datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S")
            else:
                max_date = datetime.strptime("2020-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
            
            for punishment in client.current_period.punishments:
                if punishment.date > max_date:
                    reasonTxt = ""
                    for reason in punishment.reasons:
                        reasonTxt += str(reason) + "\n"
                    
                    dbconn.execute('INSERT INTO punishments (datetime, circumstances, nature, reasons, giver) VALUES (?, ?, ?, ?, ?)', 
                                 (punishment.date.strftime('%Y-%m-%d %H:%M:%S'), 
                                  punishment.circumstances, punishment.nature, reasonTxt, punishment.giver))
                    dbconn.commit()
        except Exception as e:
            if tomlogger:
                tomlogger.error(f'Could not update punishments for {childname}: {e}', module_name="pronote")
    
    def _update_teachers(self, client, dbconn, childname):
        """Update teachers data"""
        try:
            dbconn.execute('DELETE FROM teachers')
            
            for teacher in client.get_teaching_staff():
                if teacher.subjects:
                    dbconn.execute('INSERT INTO teachers (subject, name) VALUES (?, ?)', 
                                 (teacher.subjects[0].name, teacher.name))
            dbconn.commit()
        except Exception as e:
            if tomlogger:
                tomlogger.error(f'Could not update teachers for {childname}: {e}', module_name="pronote")
    
    def _update_informations(self, client, dbconn, childname):
        """Update informations data"""
        try:
            res = dbconn.execute('SELECT creation_date FROM informations ORDER BY creation_date DESC LIMIT 1').fetchone()
            if res:
                max_date = datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S")
            else:
                max_date = datetime.strptime("2020-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
            
            informations = client.information_and_surveys()
            for information in informations:
                if information.creation_date > max_date:
                    dbconn.execute('INSERT INTO informations (creation_date, date, title, author, content, is_read) VALUES (?, ?, ?, ?, ?, ?)', 
                                 (information.creation_date, information.start_date.strftime('%Y-%m-%d'), 
                                  information.title, information.author, information.content, information.read))
                    dbconn.commit()
        except Exception as e:
            if tomlogger:
                tomlogger.error(f'Could not update informations for {childname}: {e}', module_name="pronote")
    
    def _update_observations(self, client, dbconn, childname):
        """Update observations data"""
        try:
            data = {
                "DateDebut": {
                    "V": client.current_period.start.strftime("%-m/%-d/%Y %-H:%-M:%-S"),
                    "_T": 7
                },
                "DateFin": {
                    "V": client.current_period.end.strftime("%-m/%-d/%Y %-H:%-M:%-S"),
                    "_T": 7
                },
                "periode": {
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
            
            for observation in val['dataSec']['data']['listeAbsences']['V']:
                if "genreObservation" in observation.keys():
                    date = datetime.strptime(observation['date']['V'], "%d/%m/%Y %H:%M:%S")
                    
                    if date > max_date:
                        is_read = observation['estLue']
                        with_ar = observation['avecARObservation']
                        
                        dbconn.execute('INSERT INTO observations (datetime, subject, teacher, title, comment, is_read, with_ar) VALUES (?, ?, ?, ?, ?, ?, ?)', 
                                     (date.strftime('%Y-%m-%d %H:%M:%S'), 
                                      observation['matiere']['V']['L'], 
                                      observation['demandeur']['V']['L'], 
                                      observation['L'], 
                                      observation['commentaire'], 
                                      is_read, with_ar))
                        dbconn.commit()
        except Exception as e:
            if tomlogger:
                tomlogger.error(f'Could not update observations for {childname}: {e}', module_name="pronote")
    
    def _update_calendar(self, client, childname):
        """Update calendar data"""
        try:
            self.cal[childname] = []
            l = client.parametres_utilisateur['dataSec']['data']['ressource']['L']
            g = client.parametres_utilisateur['dataSec']['data']['ressource']['G']
            n = client.parametres_utilisateur['dataSec']['data']['ressource']['N']
            
            for i in range(0, 4):
                week = client.week + i
                data = {
                    "ressource": {"N": n, "G": g, "L": l},
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
                    "Ressource": {"N": n, "G": g, "L": l},
                    "NumeroSemaine": week
                }
                
                cal_week = client.post("PageEmploiDuTemps", 16, data)
                
                for lesson in cal_week['dataSec']['data']['ListeCours']:
                    start_date = datetime.strptime(lesson['DateDuCours']['V'], "%d/%m/%Y %H:%M:%S")
                    duration = lesson['duree'] * 0.5
                    end_date = start_date + timedelta(hours=duration)
                    
                    start = start_date.strftime("%Y-%m-%d %H:%M:%S")
                    end = end_date.strftime("%Y-%m-%d %H:%M:%S")
                    
                    subject = ""
                    for contenu in lesson['ListeContenus']['V']:
                        if contenu['G'] == 16:
                            subject = contenu['L']
                    
                    is_canceled = lesson.get('estAnnule', False)
                    status = lesson.get('Statut', "")
                    
                    self.cal[childname].append({
                        "subject": subject, 
                        "start": start, 
                        "end": end, 
                        "status": status, 
                        "is_canceled": is_canceled
                    })
        except Exception as e:
            if tomlogger:
                tomlogger.error(f'Could not update calendar for {childname}: {e}', module_name="pronote")
    
    def exec_select(self, child_name: str, req: str):
        """Execute SELECT query on child's database"""
        self.update()
        
        db = None
        for child in self.config.get('children', []):
            if child['name'] == child_name:
                db = child['cache']
                break
        
        if db is None:
            return False
        
        try:
            dbconn = sqlite3.connect(db)
            cursor = dbconn.cursor()
            cursor.execute(req)
            entries = cursor.fetchall()
            dbconn.close()
            return entries
        except Exception as e:
            if tomlogger:
                tomlogger.error(f'Database query failed for {child_name}: {e}', module_name="pronote")
            return False
    
    def exec_update(self, child_name: str, req: str):
        """Execute UPDATE query on child's database"""
        db = None
        for child in self.config.get('children', []):
            if child['name'] == child_name:
                db = child['cache']
                break
        
        if db is None:
            return False
        
        try:
            dbconn = sqlite3.connect(db)
            dbconn.execute(req)
            dbconn.commit()
            dbconn.close()
            return True
        except Exception as e:
            if tomlogger:
                tomlogger.error(f'Database update failed for {child_name}: {e}', module_name="pronote")
            return False


# Initialize pronote service
pronote_service = PronoteService()


# MCP Tool implementations

@server.tool()
def list_grade_averages(child_name: str) -> str:
    """Get child averages from pronote.
    
    Args:
        child_name: Name of the child. Available children: """ + ", ".join(pronote_service.children) + """
    """
    child_name = child_name.lower()
    if tomlogger:
        tomlogger.info(f"Tool call: list_grade_averages for {child_name}", module_name="pronote")
        if log_level == 'DEBUG':
            tomlogger.debug(f"Available children: {pronote_service.children}", module_name="pronote")
    
    if child_name not in pronote_service.children:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Child {child_name} not found in available children", module_name="pronote")
        return json.dumps({"error": "Child not found"}, ensure_ascii=False)
    
    avgs = pronote_service.exec_select(child_name=child_name, 
                                     req='SELECT period, name, student, class_min, class_max, class_avg FROM averages ORDER BY period, name ASC')
    
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"Retrieved {len(avgs) if avgs else 0} averages for {child_name}", module_name="pronote")
    
    if avgs == False:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Failed to retrieve averages for {child_name}", module_name="pronote")
        return json.dumps({"error": "Failed to retrieve averages"}, ensure_ascii=False)
    
    averages = {"current_period": pronote_service.current_period, "grades_averages": []}
    
    for avg in avgs:
        averages['grades_averages'].append({
            "period": avg[0], 
            "subject": avg[1], 
            "student_avg": avg[2], 
            "class_min_avg": avg[3], 
            "class_max_avg": avg[4], 
            "class_avg": avg[5]
        })
    
    return json.dumps({"child": child_name, "grades_averages": averages}, ensure_ascii=False)


@server.tool()
def list_grades(child_name: str, is_new: bool) -> str:
    """Get child grades from pronote.
    
    Args:
        child_name: Name of the child. Available children: """ + ", ".join(pronote_service.children) + """
        is_new: Set to true to return only new grades. Otherwise set to false to return all grades including the new
    """
    child_name = child_name.lower()
    if tomlogger:
        tomlogger.info(f"Tool call: list_grades for {child_name}, is_new={is_new}", module_name="pronote")
        if log_level == 'DEBUG':
            tomlogger.debug(f"Filter for new grades only: {is_new}", module_name="pronote")
    
    if child_name not in pronote_service.children:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Child {child_name} not found in available children", module_name="pronote")
        return json.dumps({"error": "Child not found"}, ensure_ascii=False)
    
    new_filter = " WHERE is_new = 1 " if is_new else ""
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"SQL filter applied: {new_filter}", module_name="pronote")
    
    val = pronote_service.exec_select(child_name=child_name, 
                                    req='SELECT date, subject, grade, out_of, min, max, average, comment, is_new, id FROM grades ' + new_filter + ' ORDER BY date, subject ASC')
    
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"Retrieved {len(val) if val else 0} grades for {child_name}", module_name="pronote")
    
    if val == False:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Failed to retrieve grades for {child_name}", module_name="pronote")
        return json.dumps({"error": "Failed to retrieve grades"}, ensure_ascii=False)
    
    grades = []
    
    for grade in val:
        grades.append({
            "id": grade[9], 
            "date": grade[0].replace(" 00:00:00", ""), 
            "subject": grade[1], 
            "grade": grade[2], 
            "grade_out_of": grade[3], 
            "class_min_grade": grade[4], 
            "class_max_grade": grade[5], 
            "class_avg_grade": grade[6], 
            "grade_comment": grade[7], 
            "is_new": str(grade[8]) == "1"
        })
    
    return json.dumps({"child": child_name, "grades": grades}, ensure_ascii=False)


@server.tool()
def list_homeworks(child_name: str) -> str:
    """Get all child school homeworks from pronote.
    
    Args:
        child_name: Name of the child. Available children: """ + ", ".join(pronote_service.children) + """
    """
    child_name = child_name.lower()
    if tomlogger:
        tomlogger.info(f"Tool call: list_homeworks for {child_name}", module_name="pronote")
        if log_level == 'DEBUG':
            tomlogger.debug(f"Retrieving homeworks for child: {child_name}", module_name="pronote")
    
    if child_name not in pronote_service.children:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Child {child_name} not found in available children", module_name="pronote")
        return json.dumps({"error": "Child not found"}, ensure_ascii=False)
    
    val = pronote_service.exec_select(child_name=child_name, 
                                    req="SELECT date, subject, description, done FROM homeworks WHERE date > DATE('now') ORDER BY date ASC")
    
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"Retrieved {len(val) if val else 0} homeworks for {child_name}", module_name="pronote")
    
    if val == False:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Failed to retrieve homeworks for {child_name}", module_name="pronote")
        return json.dumps({"error": "Failed to retrieve homeworks"}, ensure_ascii=False)
    
    homeworks = []
    
    for homework in val:
        homeworks.append({
            "due_date": homework[0].replace(" 00:00:00", ""), 
            "subject": homework[1], 
            "description": homework[2], 
            "is_done": homework[3] != "1"
        })
    
    return json.dumps({"child": child_name, "homeworks": homeworks}, ensure_ascii=False)


@server.tool()
def list_school_absences(child_name: str) -> str:
    """Get all child school absences from pronote.
    
    Args:
        child_name: Name of the child. Available children: """ + ", ".join(pronote_service.children) + """
    """
    child_name = child_name.lower()
    if tomlogger:
        tomlogger.info(f"Tool call: list_school_absences for {child_name}", module_name="pronote")
        if log_level == 'DEBUG':
            tomlogger.debug(f"Retrieving absences for child: {child_name}", module_name="pronote")
    
    if child_name not in pronote_service.children:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Child {child_name} not found in available children", module_name="pronote")
        return json.dumps({"error": "Child not found"}, ensure_ascii=False)
    
    val = pronote_service.exec_select(child_name=child_name, 
                                    req="SELECT date_from, date_to, duration, reasons, justified, id FROM absences ORDER BY date_from DESC")
    
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"Retrieved {len(val) if val else 0} absences for {child_name}", module_name="pronote")
    
    if val == False:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Failed to retrieve absences for {child_name}", module_name="pronote")
        return json.dumps({"error": "Failed to retrieve absences"}, ensure_ascii=False)
    
    absences = []
    
    for absence in val:
        absences.append({
            "id": absence[5], 
            "date_from": absence[0], 
            "date_to": absence[1], 
            "duration": absence[2], 
            "reasons": absence[3], 
            "is_justified": absence[4] != "1"
        })
    
    return json.dumps({"child": child_name, "absences": absences}, ensure_ascii=False)


@server.tool()
def list_school_delays(child_name: str) -> str:
    """Get all child school delays from pronote.
    
    Args:
        child_name: Name of the child. Available children: """ + ", ".join(pronote_service.children) + """
    """
    child_name = child_name.lower()
    if tomlogger:
        tomlogger.info(f"Tool call: list_school_delays for {child_name}", module_name="pronote")
        if log_level == 'DEBUG':
            tomlogger.debug(f"Retrieving delays for child: {child_name}", module_name="pronote")
    
    if child_name not in pronote_service.children:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Child {child_name} not found in available children", module_name="pronote")
        return json.dumps({"error": "Child not found"}, ensure_ascii=False)
    
    val = pronote_service.exec_select(child_name=child_name, 
                                    req="SELECT datetime, minutes, justification, reasons, justified, id FROM delays ORDER BY datetime DESC")
    
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"Retrieved {len(val) if val else 0} delays for {child_name}", module_name="pronote")
    
    if val == False:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Failed to retrieve delays for {child_name}", module_name="pronote")
        return json.dumps({"error": "Failed to retrieve delays"}, ensure_ascii=False)
    
    delays = []
    
    for delay in val:
        delays.append({
            "id": delay[5], 
            "date": delay[0], 
            "minutes": delay[1], 
            "justification": delay[2], 
            "reasons": delay[3], 
            "is_justified": delay[4] != "1"
        })
    
    return json.dumps({"child": child_name, "delays": delays}, ensure_ascii=False)


@server.tool()
def list_school_evaluations(child_name: str) -> str:
    """Get all child school evaluations from pronote.
    
    Args:
        child_name: Name of the child. Available children: """ + ", ".join(pronote_service.children) + """
    """
    child_name = child_name.lower()
    if tomlogger:
        tomlogger.info(f"Tool call: list_school_evaluations for {child_name}", module_name="pronote")
        if log_level == 'DEBUG':
            tomlogger.debug(f"Retrieving evaluations for child: {child_name}", module_name="pronote")
    
    if child_name not in pronote_service.children:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Child {child_name} not found in available children", module_name="pronote")
        return json.dumps({"error": "Child not found"}, ensure_ascii=False)
    
    val = pronote_service.exec_select(child_name=child_name, 
                                    req="SELECT datetime, name, subject, description, acquisitions, is_new, id FROM evaluations ORDER BY datetime DESC")
    
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"Retrieved {len(val) if val else 0} evaluations for {child_name}", module_name="pronote")
    
    if val == False:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Failed to retrieve evaluations for {child_name}", module_name="pronote")
        return json.dumps({"error": "Failed to retrieve evaluations"}, ensure_ascii=False)
    
    evaluations = []
    
    for evaluation in val:
        evaluations.append({
            "id": evaluation[6], 
            "date": evaluation[0].replace(" 00:00:00", ""), 
            "name": evaluation[1], 
            "subject": evaluation[2], 
            "description": evaluation[3], 
            "acquisitions": evaluation[4], 
            "is_new": str(evaluation[5]) == "1"
        })
    
    return json.dumps({"child": child_name, "evaluations": evaluations}, ensure_ascii=False)


@server.tool()
def list_school_punishments(child_name: str) -> str:
    """Get all child school punishments from pronote.
    
    Args:
        child_name: Name of the child. Available children: """ + ", ".join(pronote_service.children) + """
    """
    child_name = child_name.lower()
    if tomlogger:
        tomlogger.info(f"Tool call: list_school_punishments for {child_name}", module_name="pronote")
        if log_level == 'DEBUG':
            tomlogger.debug(f"Retrieving punishments for child: {child_name}", module_name="pronote")
    
    if child_name not in pronote_service.children:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Child {child_name} not found in available children", module_name="pronote")
        return json.dumps({"error": "Child not found"}, ensure_ascii=False)
    
    val = pronote_service.exec_select(child_name=child_name, 
                                    req="SELECT datetime, circumstances, nature, reasons, giver, is_new, id FROM punishments ORDER BY datetime DESC")
    
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"Retrieved {len(val) if val else 0} punishments for {child_name}", module_name="pronote")
    
    if val == False:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Failed to retrieve punishments for {child_name}", module_name="pronote")
        return json.dumps({"error": "Failed to retrieve punishments"}, ensure_ascii=False)
    
    punishments = []
    
    for punishment in val:
        punishments.append({
            "id": punishment[6], 
            "date": punishment[0].replace(" 00:00:00", ""), 
            "circumstances": punishment[1], 
            "nature": punishment[2], 
            "reasons": punishment[3], 
            "giver": punishment[4], 
            "is_new": str(punishment[5]) == "1"
        })
    
    return json.dumps({"child": child_name, "punishments": punishments}, ensure_ascii=False)


@server.tool()
def list_school_observations(child_name: str) -> str:
    """Get all child school observations from pronote (Like 'forgetting school supplies', 'Incomplete homework', 'Homework not done', ...).
    
    Args:
        child_name: Name of the child. Available children: """ + ", ".join(pronote_service.children) + """
    """
    child_name = child_name.lower()
    if tomlogger:
        tomlogger.info(f"Tool call: list_school_observations for {child_name}", module_name="pronote")
        if log_level == 'DEBUG':
            tomlogger.debug(f"Retrieving observations for child: {child_name}", module_name="pronote")
    
    if child_name not in pronote_service.children:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Child {child_name} not found in available children", module_name="pronote")
        return json.dumps({"error": "Child not found"}, ensure_ascii=False)
    
    val = pronote_service.exec_select(child_name=child_name, 
                                    req="SELECT id, datetime, subject, teacher, title, comment, is_read, with_ar, is_new FROM observations")
    
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"Retrieved {len(val) if val else 0} observations for {child_name}", module_name="pronote")
    
    if val == False:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Failed to retrieve observations for {child_name}", module_name="pronote")
        return json.dumps({"error": "Failed to retrieve observations"}, ensure_ascii=False)
    
    observations = []
    
    for observation in val:
        observations.append({
            "id": observation[0], 
            "date": observation[1], 
            "subject": observation[2], 
            "teacher": observation[3], 
            "observation_title": observation[4], 
            "comment": observation[5], 
            "is_read": observation[6], 
            "need_ar": observation[7], 
            "is_new": str(observation[8]) == "1"
        })
    
    return json.dumps({"child": child_name, "observations": observations}, ensure_ascii=False)


@server.tool()
def list_school_information_communication(child_name: str, is_new: bool) -> str:
    """Get all child school communication and information messages from pronote. This function does not return the content of the information message.
    
    Args:
        child_name: Name of the child. Available children: """ + ", ".join(pronote_service.children) + """
        is_new: Set to true to return only new and non read information messages. Otherwise set to false to return all information messages including the new
    """
    child_name = child_name.lower()
    if tomlogger:
        tomlogger.info(f"Tool call: list_school_information_communication for {child_name}, is_new={is_new}", module_name="pronote")
        if log_level == 'DEBUG':
            tomlogger.debug(f"Filter for new information only: {is_new}", module_name="pronote")
    
    if child_name not in pronote_service.children:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Child {child_name} not found in available children", module_name="pronote")
        return json.dumps({"error": "Child not found"}, ensure_ascii=False)
    
    new_filter = " WHERE is_new = 1 " if is_new else ""
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"SQL filter applied: {new_filter}", module_name="pronote")
    
    val = pronote_service.exec_select(child_name=child_name, 
                                    req="SELECT id, date, title, author, is_read, is_new FROM informations " + new_filter + " ORDER BY date DESC")
    
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"Retrieved {len(val) if val else 0} informations for {child_name}", module_name="pronote")
    
    if val == False:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Failed to retrieve informations for {child_name}", module_name="pronote")
        return json.dumps({"error": "Failed to retrieve informations"}, ensure_ascii=False)
    
    informations = []
    
    for information in val:
        informations.append({
            "id": information[0], 
            "date": information[1], 
            "title": information[2], 
            "author": information[3], 
            "is_read": information[4], 
            "is_new": str(information[5]) == "1"
        })
    
    return json.dumps({"child": child_name, "informations": informations}, ensure_ascii=False)


@server.tool()
def get_school_information_communication_message(child_name: str, id: str) -> str:
    """Get the message content of an information message.
    
    Args:
        child_name: Name of the child. Available children: """ + ", ".join(pronote_service.children) + """
        id: ID of the information message
    """
    child_name = child_name.lower()
    if tomlogger:
        tomlogger.info(f"Tool call: get_school_information_communication_message for {child_name}, id={id}", module_name="pronote")
        if log_level == 'DEBUG':
            tomlogger.debug(f"Retrieving message content for ID: {id}", module_name="pronote")
    
    if child_name not in pronote_service.children:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Child {child_name} not found in available children", module_name="pronote")
        return json.dumps({"error": "Child not found"}, ensure_ascii=False)
    
    val = pronote_service.exec_select(child_name=child_name, 
                                    req="SELECT id, date, title, author, content, is_read, is_new FROM informations WHERE id = " + str(id))
    
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"Retrieved {len(val) if val else 0} information message(s) for ID {id}", module_name="pronote")
    
    if val == False:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Failed to retrieve information message for ID {id}", module_name="pronote")
        return json.dumps({"error": "Failed to retrieve information message"}, ensure_ascii=False)
    
    informations = []
    
    for information in val:
        informations.append({
            "id": information[0], 
            "date": information[1], 
            "title": information[2], 
            "author": information[3], 
            "message_content": information[4], 
            "is_read": information[5], 
            "is_new": str(information[6]) == "1"
        })
    
    return json.dumps({"child": child_name, "information_messages": informations}, ensure_ascii=False)


@server.tool()
def list_school_teachers(child_name: str) -> str:
    """Get child school teachers from pronote.
    
    Args:
        child_name: Name of the child. Available children: """ + ", ".join(pronote_service.children) + """
    """
    child_name = child_name.lower()
    if tomlogger:
        tomlogger.info(f"Tool call: list_school_teachers for {child_name}", module_name="pronote")
        if log_level == 'DEBUG':
            tomlogger.debug(f"Retrieving teachers for child: {child_name}", module_name="pronote")
    
    if child_name not in pronote_service.children:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Child {child_name} not found in available children", module_name="pronote")
        return json.dumps({"error": "Child not found"}, ensure_ascii=False)
    
    val = pronote_service.exec_select(child_name=child_name, 
                                    req="SELECT name, subject FROM teachers")
    
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"Retrieved {len(val) if val else 0} teachers for {child_name}", module_name="pronote")
    
    if val == False:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Failed to retrieve teachers for {child_name}", module_name="pronote")
        return json.dumps({"error": "Failed to retrieve teachers"}, ensure_ascii=False)
    
    teachers = []
    
    for teacher in val:
        teachers.append({
            "name": teacher[0], 
            "subject": teacher[1]
        })
    
    return json.dumps({"child": child_name, "teachers": teachers}, ensure_ascii=False)


@server.tool()
def get_school_calendar(child_name: str, date: str) -> str:
    """Get child school daily calendar scheduling lessons. This function must be used when a children ask 'At what time do I start this morning?', 'What are my lessons tomorrow?', 'At what time do I finish school' or 'Do I have History today?'. Must also be used when a parent ask 'At what time my child finish school?', 'At what time will my child start tomorrow?', 'When is my next child french lesson?'
    
    Args:
        child_name: Name of the child. Available children: """ + ", ".join(pronote_service.children) + """
        date: Date of the calendar. Must be in form 'YYYY-MM-DD'
    """
    child_name = child_name.lower()
    if tomlogger:
        tomlogger.info(f"Tool call: get_school_calendar for {child_name}, date={date}", module_name="pronote")
        if log_level == 'DEBUG':
            tomlogger.debug(f"Retrieving calendar for date: {date}", module_name="pronote")
    
    if child_name not in pronote_service.children:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Child {child_name} not found in available children", module_name="pronote")
        return json.dumps({"error": "Child not found"}, ensure_ascii=False)
    
    if child_name not in pronote_service.cal:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Calendar not available for child {child_name}", module_name="pronote")
        return json.dumps({"error": "Calendar not available for child"}, ensure_ascii=False)
    
    lessons = []
    
    for lesson in pronote_service.cal[child_name]:
        day = datetime.strptime(lesson['start'], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        
        if day == date:
            lessons.append(lesson)
    
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"Found {len(lessons)} lessons for {child_name} on {date}", module_name="pronote")
    
    return json.dumps({"child": child_name, "calendar": lessons}, ensure_ascii=False)


@server.tool()
def pronote_mark_as_seen(child_name: str, object_type: str, object_id: str) -> str:
    """Mark a pronote element as read. Must be used when you return some information, grades, ... to indicate this information has been seen.
    
    Args:
        child_name: Name of the child. Available children: """ + ", ".join(pronote_service.children) + """
        object_type: Type of the element to mark as seen (grade, evaluation, information, observation)
        object_id: ID of the element to mark as seen
    """
    child_name = child_name.lower()
    if tomlogger:
        tomlogger.info(f"Tool call: pronote_mark_as_seen for {child_name}, type={object_type}, id={object_id}", module_name="pronote")
        if log_level == 'DEBUG':
            tomlogger.debug(f"Marking as seen - Type: {object_type}, ID: {object_id}", module_name="pronote")
    
    if child_name not in pronote_service.children:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Child {child_name} not found in available children", module_name="pronote")
        return json.dumps({"error": "Child not found"}, ensure_ascii=False)
    
    if object_type not in ["grade", "evaluation", "information", "observation"]:
        if tomlogger and log_level == 'DEBUG':
            tomlogger.debug(f"Invalid object type: {object_type}", module_name="pronote")
        return json.dumps({"error": "Invalid object type"}, ensure_ascii=False)
    
    table_map = {
        "grade": "grades",
        "evaluation": "evaluations", 
        "information": "informations",
        "observation": "observations"
    }
    
    table = table_map[object_type]
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"Updating table {table} for object ID {object_id}", module_name="pronote")
    
    success = pronote_service.exec_update(child_name=child_name, 
                                        req=f"UPDATE {table} SET is_new=0 WHERE id = '{object_id}'")
    
    if tomlogger and log_level == 'DEBUG':
        tomlogger.debug(f"Mark as seen result: {'success' if success else 'failed'}", module_name="pronote")
    
    if success:
        return json.dumps({"status": "success", "message": "Marked as seen"}, ensure_ascii=False)
    else:
        return json.dumps({"error": "Failed to mark as seen"}, ensure_ascii=False)


# MCP Resources
@server.resource("description://pronote")
def description() -> str:
    """Return the server description."""
    return SERVER_DESCRIPTION


@server.resource("description://tom_notification")
def tom_notification() -> str:
    """Return current background notification status for Tom's /tasks endpoint."""
    return pronote_service.background_status.get('status', '') or ''


@server.resource("description://response_consign")
def response_consign() -> str:
    """Return response formatting instructions for pronote-related responses."""
    
    response_data = {
        "description": "Pronote response formatting instructions",
        "formatting_guidelines": {
            "response_style": "Keep responses concise and factual about school information",
            "data_presentation": "Always present school data (grades, homeworks, etc.) in a clear, organized format",
            "date_format": "Display dates in user-friendly format (e.g., 'Today', 'Tomorrow', '15 January 2024')",
            "grade_display": "Show grades with context: grade/total (e.g., '15/20') and class averages when available",
            "child_identification": "Always specify which child the information refers to when multiple children are configured"
        },
        "response_structure": {
            "school_data": "Present school information chronologically (most recent first for grades/observations, upcoming first for homeworks/calendar)",
            "context_information": "Include relevant context like subject, teacher names, and deadlines",
            "status_indicators": "Clearly indicate new/unread items and mark them as seen after displaying"
        },
        "user_experience": {
            "emoji_usage": "Use appropriate school-related emojis to enhance readability (📚 📝 📊 ⏰ 🎯)",
            "conversational_tone": "Maintain a supportive, informative tone appropriate for school-related discussions",
            "focus": "Focus on educational progress, upcoming tasks, and school communication"
        },
        "strict_instructions": {
            "mark_as_seen": "ALWAYS use pronote_mark_as_seen tool after displaying new grades, evaluations, observations, or information messages",
            "child_validation": "Verify child names exist before making API calls",
            "privacy_respect": "Handle school information with appropriate sensitivity and privacy"
        }
    }
    
    return json.dumps(response_data, ensure_ascii=False, separators=(',', ':'))


def main():
    """Main function to run the MCP server"""
    if tomlogger:
        tomlogger.info("🚀 Starting Pronote MCP Server on port 80", module_name="pronote")
    else:
        print("Starting Pronote MCP Server on port 80")
    
    # Run the FastMCP server with streamable HTTP transport
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
