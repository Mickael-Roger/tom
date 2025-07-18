import unittest
from unittest.mock import patch
import sys
import os
import yaml
import json
from datetime import datetime, timedelta

# Add modules path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))

# Import tomlogger to initialize it properly for integration tests
from tomlogger import logger

# Import tomcalendar after logger is initialized
from tomcalendar import TomCalendar

class TestTomCalendarIntegration(unittest.TestCase):
    """
    Integration tests for TomCalendar module that require real CalDAV server access.
    These tests require a valid config.yml file mounted at /config.yml in Docker.
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up class-level resources - load config once"""
        cls.config_path = '/config.yml'
        cls.config_loaded = False
        cls.calendar_config = None
        
        # Try to load config
        try:
            if os.path.exists(cls.config_path):
                with open(cls.config_path, 'r') as file:
                    config = yaml.safe_load(file)
                    if 'calendar' in config:
                        cls.calendar_config = config['calendar']
                        cls.config_loaded = True
                        print(f"✓ Calendar config loaded from {cls.config_path}")
                    else:
                        print(f"✗ Calendar config not found in {cls.config_path}")
            else:
                print(f"✗ Config file not found at {cls.config_path}")
        except Exception as e:
            print(f"✗ Error loading config: {e}")
    
    def setUp(self):
        """Set up test fixtures"""
        if not self.config_loaded:
            self.skipTest("Config file not available - skipping integration tests")
        
        # Create TomCalendar instance with real config
        try:
            self.calendar = TomCalendar(self.calendar_config, None)
            self.integration_available = True
        except Exception as e:
            print(f"✗ Failed to connect to CalDAV server: {e}")
            self.integration_available = False
    
    def test_config_loaded(self):
        """Test that configuration is properly loaded"""
        self.assertTrue(self.config_loaded, "Configuration should be loaded")
        self.assertIsNotNone(self.calendar_config, "Calendar config should not be None")
        self.assertIn('url', self.calendar_config, "URL should be in config")
        self.assertIn('user', self.calendar_config, "User should be in config")
        self.assertIn('password', self.calendar_config, "Password should be in config")
        self.assertIn('calendar_name', self.calendar_config, "Calendar name should be in config")
    
    def test_caldav_connection(self):
        """Test CalDAV server connection"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Test that we can connect and access calendars
        self.assertIsNotNone(self.calendar.client, "CalDAV client should be created")
        self.assertIsNotNone(self.calendar.defaultCalendar, "Default calendar should be found")
        self.assertIsNotNone(self.calendar.calendars, "Calendars list should not be None")
        self.assertGreater(len(self.calendar.calendars), 0, "Should have at least one calendar")
    
    def test_real_search_events(self):
        """Test searching for events with real CalDAV server"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Search for events in the current month
        today = datetime.now()
        start_of_month = today.replace(day=1).strftime('%Y-%m-%d')
        end_of_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        end_of_month_str = end_of_month.strftime('%Y-%m-%d')
        
        result = self.calendar.search(start_of_month, end_of_month_str)
        
        self.assertIsInstance(result, str, "Result should be a JSON string")
        
        # Parse JSON result
        events = json.loads(result)
        self.assertIsInstance(events, list, "Events should be a list")
        
        # Check structure of events if any exist
        for event in events:
            self.assertIn('id', event, "Event should have id")
            self.assertIn('title', event, "Event should have title")
            self.assertIn('start', event, "Event should have start time")
            self.assertIn('end', event, "Event should have end time")
            self.assertIn('description', event, "Event should have description field")
            self.assertIn('alarms', event, "Event should have alarms field")
            
            # Validate date format
            try:
                datetime.strptime(event['start'], '%Y-%m-%d %H:%M:%S')
                datetime.strptime(event['end'], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                self.fail(f"Invalid date format in event: {event}")
    
    def test_real_add_and_search_event(self):
        """Test adding an event and then finding it through search"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Create a test event for tomorrow
        tomorrow = datetime.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = tomorrow.replace(hour=11, minute=0, second=0, microsecond=0)
        
        test_title = f"Integration Test Event {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        test_description = "This is a test event created by integration tests"
        
        # Add the event
        add_result = self.calendar.addEvent(
            title=test_title,
            start=start_time.strftime('%Y-%m-%d %H:%M'),
            end=end_time.strftime('%Y-%m-%d %H:%M'),
            description=test_description
        )
        
        self.assertEqual(add_result['status'], 'success')
        self.assertEqual(add_result['message'], 'Event added')
        
        # Search for the event
        search_date = tomorrow.strftime('%Y-%m-%d')
        search_result = self.calendar.search(search_date, search_date)
        events = json.loads(search_result)
        
        # Find our test event
        test_event = None
        for event in events:
            if event['title'] == test_title:
                test_event = event
                break
        
        self.assertIsNotNone(test_event, "Created event should be found in search results")
        self.assertEqual(test_event['title'], test_title)
        self.assertEqual(test_event['description'], test_description)
        self.assertEqual(test_event['start'], start_time.strftime('%Y-%m-%d %H:%M:%S'))
        self.assertEqual(test_event['end'], end_time.strftime('%Y-%m-%d %H:%M:%S'))
    
    def test_real_add_event_with_validation(self):
        """Test adding event with various validation scenarios"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Test valid event
        tomorrow = datetime.now() + timedelta(days=1)
        start_time = tomorrow.replace(hour=14, minute=30, second=0, microsecond=0)
        end_time = tomorrow.replace(hour=15, minute=30, second=0, microsecond=0)
        
        result = self.calendar.addEvent(
            title="Valid Test Event",
            start=start_time.strftime('%Y-%m-%d %H:%M'),
            end=end_time.strftime('%Y-%m-%d %H:%M')
        )
        
        self.assertEqual(result['status'], 'success')
        
        # Test event with end time before start time
        result_invalid = self.calendar.addEvent(
            title="Invalid Event",
            start=end_time.strftime('%Y-%m-%d %H:%M'),  # Later time
            end=start_time.strftime('%Y-%m-%d %H:%M')   # Earlier time
        )
        
        self.assertEqual(result_invalid['status'], 'error')
        self.assertIn('End time must be after start time', result_invalid['message'])
    
    def test_real_add_event_invalid_format(self):
        """Test adding event with invalid date format"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        result = self.calendar.addEvent(
            title="Invalid Format Event",
            start="invalid-date-format",
            end="2024-03-15 11:00"
        )
        
        self.assertEqual(result['status'], 'error')
        self.assertIn('Invalid date format', result['message'])
    
    def test_real_list_events(self):
        """Test listing events directly from calendar"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Get events for the current year
        current_year = datetime.now().year
        start = f"{current_year}-01-01 00:00:00"
        end = f"{current_year}-12-31 23:59:59"
        
        events = self.calendar.listEvent(start=start, end=end)
        
        self.assertIsInstance(events, list, "Events should be a list")
        
        # Check structure of events if any exist
        for event in events:
            self.assertIn('id', event, "Event should have id")
            self.assertIn('title', event, "Event should have title")
            self.assertIn('start', event, "Event should have start time")
            self.assertIn('end', event, "Event should have end time")
            self.assertIn('description', event, "Event should have description field")
            self.assertIn('alarms', event, "Event should have alarms field")
            
            # Check data types
            self.assertIsInstance(event['id'], str, "Event ID should be string")
            self.assertIsInstance(event['title'], str, "Event title should be string")
            self.assertIsInstance(event['alarms'], list, "Event alarms should be list")
    
    def test_calendar_selection_logic(self):
        """Test that the correct calendar is selected"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Verify that the correct calendar was selected based on config
        self.assertIsNotNone(self.calendar.defaultCalendar, "Default calendar should be selected")
        
        # The calendar should have basic CalDAV methods
        self.assertTrue(hasattr(self.calendar.defaultCalendar, 'search'), "Calendar should have search method")
        self.assertTrue(hasattr(self.calendar.defaultCalendar, 'save_event'), "Calendar should have save_event method")
    
    def test_timezone_handling(self):
        """Test timezone handling"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Test default timezone
        self.assertEqual(self.calendar.tz.zone, 'Europe/Paris')
        
        # Test custom timezone
        calendar_ny = TomCalendar(self.calendar_config, None, tz='America/New_York')
        self.assertEqual(calendar_ny.tz.zone, 'America/New_York')
    
    def test_module_configuration(self):
        """Test module configuration attributes"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        self.assertEqual(self.calendar.complexity, 0)
        self.assertEqual(self.calendar.systemContext, "")
        self.assertIsInstance(self.calendar.calendarsContent, list)
        self.assertIsNotNone(self.calendar.calendars)
    
    @unittest.skipIf(not os.path.exists('/config.yml'), "Config file not available")
    def test_config_file_structure(self):
        """Test that config file has correct structure"""
        with open('/config.yml', 'r') as file:
            config = yaml.safe_load(file)
        
        self.assertIn('calendar', config, "Config should have calendar section")
        
        calendar_config = config['calendar']
        self.assertIn('url', calendar_config, "Calendar config should have url")
        self.assertIn('user', calendar_config, "Calendar config should have user")
        self.assertIn('password', calendar_config, "Calendar config should have password")
        self.assertIn('calendar_name', calendar_config, "Calendar config should have calendar_name")
        
        # Test that required fields are not empty
        self.assertIsInstance(calendar_config['url'], str, "URL should be a string")
        self.assertGreater(len(calendar_config['url']), 0, "URL should not be empty")
        self.assertTrue(calendar_config['url'].startswith(('http://', 'https://')), "URL should be a valid HTTP/HTTPS URL")
        
        self.assertIsInstance(calendar_config['user'], str, "User should be a string")
        self.assertGreater(len(calendar_config['user']), 0, "User should not be empty")
        
        self.assertIsInstance(calendar_config['password'], str, "Password should be a string")
        self.assertGreater(len(calendar_config['password']), 0, "Password should not be empty")
        
        self.assertIsInstance(calendar_config['calendar_name'], str, "Calendar name should be a string")
        self.assertGreater(len(calendar_config['calendar_name']), 0, "Calendar name should not be empty")
    
    def test_stress_add_multiple_events(self):
        """Test adding multiple events rapidly"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_date = datetime.now() + timedelta(days=2)
        
        stress_events = []
        successful_adds = 0
        
        # Add multiple events rapidly
        for i in range(3):  # Reduced for integration tests
            start_time = base_date.replace(hour=9+i, minute=0, second=0, microsecond=0)
            end_time = base_date.replace(hour=10+i, minute=0, second=0, microsecond=0)
            
            event_title = f"Stress Test Event {i} {timestamp}"
            stress_events.append(event_title)
            
            try:
                result = self.calendar.addEvent(
                    title=event_title,
                    start=start_time.strftime('%Y-%m-%d %H:%M'),
                    end=end_time.strftime('%Y-%m-%d %H:%M')
                )
                
                if result['status'] == 'success':
                    successful_adds += 1
                    
            except Exception as e:
                print(f"Warning: Failed to add stress test event {i}: {e}")
        
        # Should be able to add most or all events
        self.assertGreater(successful_adds, 0, "Should successfully add at least some events")
    
    def test_unicode_event_titles(self):
        """Test handling of unicode characters in event titles"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        tomorrow = datetime.now() + timedelta(days=1)
        
        unicode_events = [
            f"Café meeting {timestamp}",
            f"Naïve event {timestamp}",
            f"Résumé review {timestamp}",
            f"测试事件 {timestamp}",
            f"🎉 Party event {timestamp}"
        ]
        
        successful_adds = 0
        
        for event_title in unicode_events:
            try:
                start_time = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
                end_time = tomorrow.replace(hour=15, minute=0, second=0, microsecond=0)
                
                result = self.calendar.addEvent(
                    title=event_title,
                    start=start_time.strftime('%Y-%m-%d %H:%M'),
                    end=end_time.strftime('%Y-%m-%d %H:%M')
                )
                
                if result['status'] == 'success':
                    successful_adds += 1
                    
                    # Verify the event appears in search
                    search_date = tomorrow.strftime('%Y-%m-%d')
                    search_result = self.calendar.search(search_date, search_date)
                    events = json.loads(search_result)
                    
                    found = any(event['title'] == event_title for event in events)
                    self.assertTrue(found, f"Unicode event '{event_title}' should be found in search")
                    
            except Exception as e:
                print(f"Warning: Failed to handle unicode event '{event_title}': {e}")
        
        # Should be able to handle most or all unicode events
        self.assertGreater(successful_adds, 0, "Should successfully add at least some unicode events")
    
    def test_search_date_range_validation(self):
        """Test search with various date ranges"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Test search with same start and end date
        today = datetime.now().strftime('%Y-%m-%d')
        result = self.calendar.search(today, today)
        events = json.loads(result)
        self.assertIsInstance(events, list)
        
        # Test search with one week range
        start_date = datetime.now()
        end_date = start_date + timedelta(days=7)
        
        result = self.calendar.search(
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )
        events = json.loads(result)
        self.assertIsInstance(events, list)
        
        # All events should be within the specified range
        for event in events:
            event_date = datetime.strptime(event['start'], '%Y-%m-%d %H:%M:%S')
            self.assertTrue(start_date <= event_date <= end_date + timedelta(days=1),
                          f"Event {event['title']} is outside search range")

if __name__ == '__main__':
    unittest.main()