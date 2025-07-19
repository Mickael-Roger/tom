import unittest
from unittest.mock import patch, MagicMock, call
import sys
import os
from datetime import datetime, timedelta
import pytz
import json

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))

# Mock logger before importing
with patch('tomcalendar.logger') as mock_logger:
    from tomcalendar import TomCalendar

class TestTomCalendar(unittest.TestCase):
    
    def setUp(self):
        self.config = {
            'url': 'https://test.example.com/dav/',
            'user': 'testuser',
            'password': 'testpass',
            'calendar_name': 'Personal'
        }
        
        # Mock caldav components
        self.mock_client = MagicMock()
        self.mock_principal = MagicMock()
        self.mock_calendar1 = MagicMock()
        self.mock_calendar2 = MagicMock()
        
        # Setup calendar properties
        self.mock_calendar1.get_properties.return_value = {
            '{DAV:}displayname': 'Work Calendar'
        }
        self.mock_calendar2.get_properties.return_value = {
            '{DAV:}displayname': 'Personal'
        }
        
        # Mock calendar selection behavior
        def mock_get_properties_cal1(props=None):
            if props:
                return {'{DAV:}displayname': 'Work Calendar'}
            return {'{DAV:}displayname': 'Work Calendar'}
        
        def mock_get_properties_cal2(props=None):
            if props:
                return {'{DAV:}displayname': 'Personal'}
            return {'{DAV:}displayname': 'Personal'}
        
        self.mock_calendar1.get_properties = mock_get_properties_cal1
        self.mock_calendar2.get_properties = mock_get_properties_cal2
        
        # Setup the mock chain
        self.mock_client.principal.return_value = self.mock_principal
        self.mock_principal.calendars.return_value = [self.mock_calendar1, self.mock_calendar2]
        
        # Mock events for the calendar
        self.mock_event1 = MagicMock()
        self.mock_event2 = MagicMock()
        
        # Setup mock event components
        self.setup_mock_event_components()
        
        # Mock calendar search return
        self.mock_calendar2.search.return_value = [self.mock_event1, self.mock_event2]
        
    def setup_mock_event_components(self):
        """Setup mock event components with proper icalendar structure"""
        # Mock event 1 - Meeting
        mock_component1 = MagicMock()
        mock_component1.name = "VEVENT"
        mock_component1.get.side_effect = lambda key, default=None: {
            'uid': 'event-uid-1',
            'summary': 'Team Meeting',
            'description': 'Weekly team sync',
            'dtstart': MagicMock(dt=datetime(2024, 3, 15, 10, 0)),
            'dtend': MagicMock(dt=datetime(2024, 3, 15, 11, 0))
        }.get(key, default)
        mock_component1.subcomponents = []
        
        # Mock event 2 - Appointment with alarm
        mock_component2 = MagicMock()
        mock_component2.name = "VEVENT"
        mock_component2.get.side_effect = lambda key, default=None: {
            'uid': 'event-uid-2',
            'summary': 'Doctor Appointment',
            'description': 'Annual checkup',
            'dtstart': MagicMock(dt=datetime(2024, 3, 20, 14, 30)),
            'dtend': MagicMock(dt=datetime(2024, 3, 20, 15, 30))
        }.get(key, default)
        
        # Mock alarm
        mock_alarm = MagicMock()
        mock_alarm.name = "VALARM"
        mock_alarm.get.return_value = MagicMock(dt=timedelta(minutes=-15))
        mock_component2.subcomponents = [mock_alarm]
        
        # Setup walk method
        self.mock_event1.icalendar_instance.walk.return_value = [mock_component1]
        self.mock_event2.icalendar_instance.walk.return_value = [mock_component2]
        
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_init_basic(self, mock_logger, mock_dav_client):
        """Test basic initialization"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Verify client creation
        mock_dav_client.assert_called_once_with(
            url='https://test.example.com/dav/',
            username='testuser',
            password='testpass'
        )
        
        # Verify attributes
        self.assertEqual(calendar.tz.zone, 'Europe/Paris')
        self.assertEqual(calendar.defaultCalendar, self.mock_calendar2)  # Should select "Personal"
        self.assertIsInstance(calendar.calendarsContent, list)
        
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_init_with_timezone(self, mock_logger, mock_dav_client):
        """Test initialization with custom timezone"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None, tz='America/New_York')
        
        self.assertEqual(calendar.tz.zone, 'America/New_York')
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_init_calendar_not_found(self, mock_logger, mock_dav_client):
        """Test initialization when configured calendar is not found"""
        mock_dav_client.return_value = self.mock_client
        
        # Change calendar name to one that doesn't exist
        config_no_match = self.config.copy()
        config_no_match['calendar_name'] = 'NonExistent'
        
        calendar = TomCalendar(config_no_match, None)
        
        # Should default to first calendar
        self.assertEqual(calendar.defaultCalendar, self.mock_calendar1)
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_init_no_calendars(self, mock_logger, mock_dav_client):
        """Test initialization when no calendars are available"""
        mock_dav_client.return_value = self.mock_client
        self.mock_principal.calendars.return_value = []
        
        with self.assertRaises(Exception):
            TomCalendar(self.config, None)
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_search_events(self, mock_logger, mock_dav_client):
        """Test searching for events in a date range"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock update to not populate calendarsContent during init
        with patch.object(TomCalendar, 'update'):
            calendar = TomCalendar(self.config, None)
        
        # Now manually set calendar content with our test events
        calendar.calendarsContent = [
            {
                'id': 'event-1',
                'title': 'Meeting',
                'start': '2024-03-15 10:00:00',
                'end': '2024-03-15 11:00:00'
            },
            {
                'id': 'event-2', 
                'title': 'Appointment',
                'start': '2024-03-20 14:30:00',
                'end': '2024-03-20 15:30:00'
            },
            {
                'id': 'event-3',
                'title': 'Out of range',
                'start': '2024-04-01 10:00:00',
                'end': '2024-04-01 11:00:00'
            }
        ]
        
        # Mock update method to not change our test data
        with patch.object(calendar, 'update'):
            result = calendar.search('2024-03-01', '2024-03-31')
        
        events = json.loads(result)
        
        # Should return only events in March
        self.assertEqual(len(events), 2)
        # Check that we have the March events (order may vary)
        event_titles = [event['title'] for event in events]
        self.assertIn('Meeting', event_titles)
        self.assertIn('Appointment', event_titles)
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_search_invalid_dates(self, mock_logger, mock_dav_client):
        """Test search with invalid date formats"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        result = calendar.search('invalid-date', '2024-03-31')
        events = json.loads(result)
        
        # Should return empty list
        self.assertEqual(len(events), 0)
        
        # Should log error
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_list_event_basic(self, mock_logger, mock_dav_client):
        """Test listing events from calendar"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock timezone for datetime operations
        with patch.object(calendar, 'tz') as mock_tz:
            mock_tz.localize.side_effect = lambda dt: dt.replace(tzinfo=pytz.UTC)
            
            events = calendar.listEvent(
                start='2024-03-01 00:00:00',
                end='2024-03-31 23:59:59'
            )
        
        # Should return parsed events
        self.assertIsInstance(events, list)
        # The exact number depends on mock setup, but should be processed
        
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_list_event_no_calendar(self, mock_logger, mock_dav_client):
        """Test listing events when no calendar is available"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        calendar.defaultCalendar = None
        
        events = calendar.listEvent()
        
        # Should return empty list and log error
        self.assertEqual(events, [])
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_list_event_invalid_date_format(self, mock_logger, mock_dav_client):
        """Test listing events with invalid date format"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        events = calendar.listEvent(start='invalid-date')
        
        # Should return empty list and log error
        self.assertEqual(events, [])
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_add_event_basic(self, mock_logger, mock_dav_client):
        """Test adding a basic event"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock timezone for datetime operations
        with patch.object(calendar, 'tz') as mock_tz:
            mock_tz.localize.side_effect = lambda dt: dt.replace(tzinfo=pytz.UTC)
            
            result = calendar.addEvent(
                title='Test Meeting',
                start='2024-03-15 10:00',
                end='2024-03-15 11:00',
                description='Test description'
            )
        
        # Verify event was saved
        self.mock_calendar2.save_event.assert_called_once()
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'Event added')
        
        # Verify logging
        mock_logger.info.assert_called_once()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_add_event_invalid_date_format(self, mock_logger, mock_dav_client):
        """Test adding event with invalid date format"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        result = calendar.addEvent(
            title='Test Meeting',
            start='invalid-date',
            end='2024-03-15 11:00'
        )
        
        # Should return error
        self.assertEqual(result['status'], 'error')
        self.assertIn('Invalid date format', result['message'])
        
        # Should not call save_event
        self.mock_calendar2.save_event.assert_not_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_add_event_end_before_start(self, mock_logger, mock_dav_client):
        """Test adding event where end time is before start time"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock timezone for datetime operations
        with patch.object(calendar, 'tz') as mock_tz:
            mock_tz.localize.side_effect = lambda dt: dt.replace(tzinfo=pytz.UTC)
            
            result = calendar.addEvent(
                title='Invalid Event',
                start='2024-03-15 11:00',
                end='2024-03-15 10:00'  # End before start
            )
        
        # Should return error
        self.assertEqual(result['status'], 'error')
        self.assertIn('End time must be after start time', result['message'])
        
        # Should not call save_event
        self.mock_calendar2.save_event.assert_not_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_add_event_no_calendar(self, mock_logger, mock_dav_client):
        """Test adding event when no calendar is available"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        calendar.defaultCalendar = None
        
        result = calendar.addEvent(
            title='Test Meeting',
            start='2024-03-15 10:00',
            end='2024-03-15 11:00'
        )
        
        # Should return error
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['message'], 'No calendar available')
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_add_event_with_custom_calendar(self, mock_logger, mock_dav_client):
        """Test adding event to a specific calendar"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock timezone for datetime operations
        with patch.object(calendar, 'tz') as mock_tz:
            mock_tz.localize.side_effect = lambda dt: dt.replace(tzinfo=pytz.UTC)
            
            result = calendar.addEvent(
                title='Work Meeting',
                start='2024-03-15 10:00',
                end='2024-03-15 11:00',
                calendar=self.mock_calendar1
            )
        
        # Verify event was saved to the specified calendar
        self.mock_calendar1.save_event.assert_called_once()
        
        # Verify response
        self.assertEqual(result['status'], 'success')
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_update_method(self, mock_logger, mock_dav_client):
        """Test update method"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock listEvent to return controlled data
        with patch.object(calendar, 'listEvent') as mock_list_event:
            mock_list_event.return_value = [
                {'id': '1', 'title': 'Event 1'},
                {'id': '2', 'title': 'Event 2'}
            ]
            
            calendar.update()
        
        # Should have called listEvent for each calendar
        expected_calls = len(calendar.calendars)
        self.assertEqual(mock_list_event.call_count, expected_calls)
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_tools_structure(self, mock_logger, mock_dav_client):
        """Test that tools are properly structured"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        self.assertIsInstance(calendar.tools, list)
        self.assertEqual(len(calendar.tools), 4)  # Now has 4 functions
        
        expected_functions = ['calendar_search', 'calendar_add', 'calendar_delete', 'calendar_update']
        
        for i, tool in enumerate(calendar.tools):
            self.assertEqual(tool['type'], 'function')
            self.assertIn('function', tool)
            self.assertEqual(tool['function']['name'], expected_functions[i])
            self.assertIn('description', tool['function'])
            self.assertIn('parameters', tool['function'])
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_functions_structure(self, mock_logger, mock_dav_client):
        """Test that functions are properly structured"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        expected_functions = ['calendar_search', 'calendar_add', 'calendar_delete', 'calendar_update']
        
        for func_name in expected_functions:
            self.assertIn(func_name, calendar.functions)
            self.assertIn('function', calendar.functions[func_name])
            self.assertTrue(callable(calendar.functions[func_name]['function']))
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_config_attributes(self, mock_logger, mock_dav_client):
        """Test that configuration attributes are set correctly"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        self.assertEqual(calendar.complexity, 0)
        self.assertEqual(calendar.systemContext, "")
        self.assertIsInstance(calendar.calendarsContent, list)
        self.assertIsNotNone(calendar.calendars)
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_calendar_selection_with_properties_error(self, mock_logger, mock_dav_client):
        """Test calendar selection when get_properties fails"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock calendar that raises exception on get_properties - both calls
        mock_bad_calendar = MagicMock()
        mock_bad_calendar.get_properties.side_effect = Exception("Properties error")
        
        # Also need to mock the DisplayName call to fail
        def mock_get_properties_bad(props=None):
            raise Exception("Properties error")
        
        mock_bad_calendar.get_properties = mock_get_properties_bad
        
        self.mock_principal.calendars.return_value = [mock_bad_calendar, self.mock_calendar2]
        
        calendar = TomCalendar(self.config, None)
        
        # Should still work and select the second calendar
        self.assertEqual(calendar.defaultCalendar, self.mock_calendar2)
        
        # Should log error
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_search_with_malformed_event(self, mock_logger, mock_dav_client):
        """Test search with malformed event data"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock update to not populate calendarsContent during init
        with patch.object(TomCalendar, 'update'):
            calendar = TomCalendar(self.config, None)
        
        # Mock calendar content with malformed event
        calendar.calendarsContent = [
            {
                'id': 'good-event',
                'title': 'Good Event',
                'start': '2024-03-15 10:00:00',
                'end': '2024-03-15 11:00:00'
            },
            {
                'id': 'bad-event',
                'title': 'Bad Event',
                'start': 'invalid-date',  # Malformed date
                'end': '2024-03-15 11:00:00'
            }
        ]
        
        # Mock update method to not change our test data
        with patch.object(calendar, 'update'):
            result = calendar.search('2024-03-01', '2024-03-31')
        
        events = json.loads(result)
        
        # Should return only the good event (malformed event should be skipped)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['title'], 'Good Event')
        
        # Should log error for malformed event
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_delete_event_basic(self, mock_logger, mock_dav_client):
        """Test deleting a basic event"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock event to delete
        mock_event_to_delete = MagicMock()
        mock_component = MagicMock()
        mock_component.name = "VEVENT"
        mock_component.get.side_effect = lambda key, default=None: {
            'uid': 'event-to-delete-123'
        }.get(key, default)
        
        mock_event_to_delete.icalendar_instance.walk.return_value = [mock_component]
        self.mock_calendar2.search.return_value = [mock_event_to_delete]
        
        result = calendar.deleteEvent('event-to-delete-123')
        
        # Verify event was deleted
        mock_event_to_delete.delete.assert_called_once()
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'Event deleted')
        
        # Verify logging
        mock_logger.info.assert_called_once()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_delete_event_not_found(self, mock_logger, mock_dav_client):
        """Test deleting event that doesn't exist"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock search to return no matching events
        self.mock_calendar2.search.return_value = []
        
        result = calendar.deleteEvent('nonexistent-event-123')
        
        # Should return error
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['message'], 'Event not found')
        
        # Should log error
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_delete_event_no_calendar(self, mock_logger, mock_dav_client):
        """Test deleting event when no calendar is available"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        calendar.defaultCalendar = None
        
        result = calendar.deleteEvent('event-123')
        
        # Should return error
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['message'], 'No calendar available')
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_update_event_basic(self, mock_logger, mock_dav_client):
        """Test updating a basic event"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock event to update
        mock_event_to_update = MagicMock()
        mock_component = MagicMock()
        mock_component.name = "VEVENT"
        mock_component.get.side_effect = lambda key, default=None: {
            'uid': 'event-to-update-123',
            'dtstart': MagicMock(dt=datetime(2024, 3, 15, 10, 0)),
            'dtend': MagicMock(dt=datetime(2024, 3, 15, 11, 0))
        }.get(key, default)
        
        mock_event_to_update.icalendar_instance.walk.return_value = [mock_component]
        self.mock_calendar2.search.return_value = [mock_event_to_update]
        
        # Mock timezone for datetime operations
        with patch.object(calendar, 'tz') as mock_tz:
            mock_tz.localize.side_effect = lambda dt: dt.replace(tzinfo=pytz.UTC)
            
            result = calendar.updateEvent(
                event_id='event-to-update-123',
                title='Updated Meeting',
                start='2024-03-15 14:00',
                end='2024-03-15 15:00'
            )
        
        # Verify event was deleted and calendar.save_event was called
        mock_event_to_update.delete.assert_called_once()
        self.mock_calendar2.save_event.assert_called_once()
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'Event updated')
        
        # Verify logging
        mock_logger.info.assert_called_once()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_update_event_not_found(self, mock_logger, mock_dav_client):
        """Test updating event that doesn't exist"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock search to return no matching events
        self.mock_calendar2.search.return_value = []
        
        result = calendar.updateEvent(
            event_id='nonexistent-event-123',
            title='Updated Title'
        )
        
        # Should return error
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['message'], 'Event not found')
        
        # Should log error
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_update_event_no_calendar(self, mock_logger, mock_dav_client):
        """Test updating event when no calendar is available"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        calendar.defaultCalendar = None
        
        result = calendar.updateEvent(
            event_id='event-123',
            title='Updated Title'
        )
        
        # Should return error
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['message'], 'No calendar available')
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_update_event_invalid_date_format(self, mock_logger, mock_dav_client):
        """Test updating event with invalid date format"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock event to update
        mock_event_to_update = MagicMock()
        mock_component = MagicMock()
        mock_component.name = "VEVENT"
        mock_component.get.side_effect = lambda key, default=None: {
            'uid': 'event-to-update-123',
            'summary': 'Original Title',
            'description': 'Original Description',
            'dtstart': MagicMock(dt=datetime(2024, 3, 15, 10, 0)),
            'dtend': MagicMock(dt=datetime(2024, 3, 15, 11, 0))
        }.get(key, default)
        
        mock_event_to_update.icalendar_instance.walk.return_value = [mock_component]
        self.mock_calendar2.search.return_value = [mock_event_to_update]
        
        result = calendar.updateEvent(
            event_id='event-to-update-123',
            start='invalid-date-format'
        )
        
        # Should return error
        self.assertEqual(result['status'], 'error')
        self.assertIn('Invalid start date format', result['message'])
        
        # Should not call save_event or delete  
        self.mock_calendar2.save_event.assert_not_called()
        mock_event_to_update.delete.assert_not_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_update_event_end_before_start(self, mock_logger, mock_dav_client):
        """Test updating event where end time is before start time"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock event to update
        mock_event_to_update = MagicMock()
        mock_component = MagicMock()
        mock_component.name = "VEVENT"
        mock_component.get.side_effect = lambda key, default=None: {
            'uid': 'event-to-update-123',
            'summary': 'Original Title',
            'description': 'Original Description',
            'dtstart': MagicMock(dt=datetime(2024, 3, 15, 10, 0)),
            'dtend': MagicMock(dt=datetime(2024, 3, 15, 11, 0))
        }.get(key, default)
        
        mock_event_to_update.icalendar_instance.walk.return_value = [mock_component]
        self.mock_calendar2.search.return_value = [mock_event_to_update]
        
        # Mock timezone for datetime operations
        with patch.object(calendar, 'tz') as mock_tz:
            mock_tz.localize.side_effect = lambda dt: dt.replace(tzinfo=pytz.UTC)
            
            result = calendar.updateEvent(
                event_id='event-to-update-123',
                start='2024-03-15 15:00',
                end='2024-03-15 14:00'  # End before start
            )
        
        # Should return error
        self.assertEqual(result['status'], 'error')
        self.assertIn('End time must be after start time', result['message'])
        
        # Should not call save_event or delete  
        self.mock_calendar2.save_event.assert_not_called()
        mock_event_to_update.delete.assert_not_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_update_event_partial_update(self, mock_logger, mock_dav_client):
        """Test updating only some fields of an event"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock event to update
        mock_event_to_update = MagicMock()
        mock_component = MagicMock()
        mock_component.name = "VEVENT"
        mock_component.get.side_effect = lambda key, default=None: {
            'uid': 'event-to-update-123',
            'summary': 'Original Title',
            'description': 'Original Description',
            'dtstart': MagicMock(dt=datetime(2024, 3, 15, 10, 0)),
            'dtend': MagicMock(dt=datetime(2024, 3, 15, 11, 0))
        }.get(key, default)
        
        mock_event_to_update.icalendar_instance.walk.return_value = [mock_component]
        self.mock_calendar2.search.return_value = [mock_event_to_update]
        
        result = calendar.updateEvent(
            event_id='event-to-update-123',
            title='Updated Title Only'
        )
        
        # Verify event was deleted and calendar.save_event was called
        mock_event_to_update.delete.assert_called_once()
        self.mock_calendar2.save_event.assert_called_once()
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'Event updated')
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_tools_structure_with_new_functions(self, mock_logger, mock_dav_client):
        """Test that tools are properly structured with new functions"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        self.assertIsInstance(calendar.tools, list)
        self.assertEqual(len(calendar.tools), 4)  # Now has 4 functions
        
        expected_functions = ['calendar_search', 'calendar_add', 'calendar_delete', 'calendar_update']
        
        for i, tool in enumerate(calendar.tools):
            self.assertEqual(tool['type'], 'function')
            self.assertIn('function', tool)
            self.assertEqual(tool['function']['name'], expected_functions[i])
            self.assertIn('description', tool['function'])
            self.assertIn('parameters', tool['function'])
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_functions_structure_with_new_functions(self, mock_logger, mock_dav_client):
        """Test that functions are properly structured with new functions"""
        mock_dav_client.return_value = self.mock_client
        
        calendar = TomCalendar(self.config, None)
        
        expected_functions = ['calendar_search', 'calendar_add', 'calendar_delete', 'calendar_update']
        
        for func_name in expected_functions:
            self.assertIn(func_name, calendar.functions)
            self.assertIn('function', calendar.functions[func_name])
            self.assertTrue(callable(calendar.functions[func_name]['function']))

if __name__ == '__main__':
    unittest.main()