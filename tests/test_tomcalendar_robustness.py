import unittest
from unittest.mock import patch, MagicMock
import sys
import os
from datetime import datetime
import json

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))

# Mock logger before importing
with patch('tomcalendar.logger') as mock_logger:
    from tomcalendar import TomCalendar

class TestTomCalendarRobustness(unittest.TestCase):
    """
    Robustness tests for TomCalendar module that test error handling
    and edge cases without requiring a real CalDAV server.
    """
    
    def setUp(self):
        self.config = {
            'url': 'https://test.example.com/dav/',
            'user': 'testuser',
            'password': 'testpass',
            'calendar_name': 'Personal'
        }
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_init_with_connection_error(self, mock_logger, mock_dav_client):
        """Test initialization when CalDAV server is unreachable"""
        # Mock connection failure
        mock_dav_client.side_effect = Exception("Connection failed")
        
        with self.assertRaises(Exception):
            TomCalendar(self.config, None)
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_init_with_principal_error(self, mock_logger, mock_dav_client):
        """Test initialization when principal access fails"""
        mock_client = MagicMock()
        mock_client.principal.side_effect = Exception("Principal access failed")
        mock_dav_client.return_value = mock_client
        
        with self.assertRaises(Exception):
            TomCalendar(self.config, None)
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_init_with_calendars_access_error(self, mock_logger, mock_dav_client):
        """Test initialization when calendars access fails"""
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_principal.calendars.side_effect = Exception("Calendars access failed")
        
        mock_client.principal.return_value = mock_principal
        mock_dav_client.return_value = mock_client
        
        with self.assertRaises(Exception):
            TomCalendar(self.config, None)
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_update_with_list_event_error(self, mock_logger, mock_dav_client):
        """Test update method when listEvent fails for some calendars"""
        # Setup basic mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar1 = MagicMock()
        mock_calendar2 = MagicMock()
        
        mock_calendar1.get_properties.return_value = {'{DAV:}displayname': 'Calendar1'}
        mock_calendar2.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar1, mock_calendar2]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock listEvent to fail for first calendar but succeed for second
        with patch.object(calendar, 'listEvent') as mock_list_event:
            mock_list_event.side_effect = [
                Exception("Calendar access failed"),  # First call fails
                [{'id': '1', 'title': 'Event 1'}]      # Second call succeeds
            ]
            
            calendar.update()
        
        # Should continue processing other calendars and log error
        self.assertIsInstance(calendar.calendarsContent, list)
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_list_event_with_search_error(self, mock_logger, mock_dav_client):
        """Test listEvent when calendar search fails"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        mock_calendar.search.side_effect = Exception("Search failed")
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        result = calendar.listEvent()
        
        # Should return empty list and log error
        self.assertEqual(result, [])
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_list_event_with_malformed_event_data(self, mock_logger, mock_dav_client):
        """Test listEvent when event data is malformed"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        # Mock event with malformed component
        mock_event = MagicMock()
        mock_component = MagicMock()
        mock_component.name = "VEVENT"
        mock_component.get.side_effect = Exception("Component access failed")
        mock_component.subcomponents = []
        
        mock_event.icalendar_instance.walk.return_value = [mock_component]
        mock_calendar.search.return_value = [mock_event]
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock timezone for datetime operations
        with patch.object(calendar, 'tz') as mock_tz:
            mock_tz.localize.side_effect = lambda dt: dt
            
            result = calendar.listEvent()
        
        # Should handle malformed data gracefully and log error
        self.assertIsInstance(result, list)
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_list_event_with_missing_datetime_fields(self, mock_logger, mock_dav_client):
        """Test listEvent when event is missing start or end time"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        # Mock event with missing dtend
        mock_event = MagicMock()
        mock_component = MagicMock()
        mock_component.name = "VEVENT"
        mock_component.get.side_effect = lambda key, default=None: {
            'uid': 'event-uid-1',
            'summary': 'Event without end time',
            'description': 'Test event',
            'dtstart': MagicMock(dt=datetime(2024, 3, 15, 10, 0)),
            'dtend': None  # Missing end time
        }.get(key, default)
        mock_component.subcomponents = []
        
        mock_event.icalendar_instance.walk.return_value = [mock_component]
        mock_calendar.search.return_value = [mock_event]
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock timezone for datetime operations
        with patch.object(calendar, 'tz') as mock_tz:
            mock_tz.localize.side_effect = lambda dt: dt
            
            result = calendar.listEvent()
        
        # Should skip events with missing datetime fields and log error
        self.assertIsInstance(result, list)
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_add_event_with_save_error(self, mock_logger, mock_dav_client):
        """Test addEvent when save_event fails"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        mock_calendar.save_event.side_effect = Exception("Save failed")
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock timezone for datetime operations
        with patch.object(calendar, 'tz') as mock_tz:
            mock_tz.localize.side_effect = lambda dt: dt
            
            result = calendar.addEvent(
                title='Test Event',
                start='2024-03-15 10:00',
                end='2024-03-15 11:00'
            )
        
        # Should return error status and log error
        self.assertEqual(result['status'], 'error')
        self.assertIn('Failed to add event', result['message'])
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_search_with_update_error(self, mock_logger, mock_dav_client):
        """Test search when update fails"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock update to fail
        with patch.object(calendar, 'update') as mock_update:
            mock_update.side_effect = Exception("Update failed")
            
            result = calendar.search('2024-03-01', '2024-03-31')
        
        # Should return empty JSON array and log error
        self.assertEqual(result, json.dumps([]))
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_list_event_with_alarm_processing_error(self, mock_logger, mock_dav_client):
        """Test listEvent when alarm processing fails"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        # Mock event with problematic alarm
        mock_event = MagicMock()
        mock_component = MagicMock()
        mock_component.name = "VEVENT"
        mock_component.get.side_effect = lambda key, default=None: {
            'uid': 'event-uid-1',
            'summary': 'Event with bad alarm',
            'description': 'Test event',
            'dtstart': MagicMock(dt=datetime(2024, 3, 15, 10, 0)),
            'dtend': MagicMock(dt=datetime(2024, 3, 15, 11, 0))
        }.get(key, default)
        
        # Mock alarm that raises exception
        mock_alarm = MagicMock()
        mock_alarm.name = "VALARM"
        mock_alarm.get.side_effect = Exception("Alarm processing failed")
        mock_component.subcomponents = [mock_alarm]
        
        mock_event.icalendar_instance.walk.return_value = [mock_component]
        mock_calendar.search.return_value = [mock_event]
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock timezone for datetime operations
        with patch.object(calendar, 'tz') as mock_tz:
            mock_tz.localize.side_effect = lambda dt: dt
            
            result = calendar.listEvent()
        
        # Should still return the event but without alarms, and log error
        self.assertIsInstance(result, list)
        if result:  # If event was processed despite alarm error
            self.assertEqual(result[0]['alarms'], [])
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_invalid_config_missing_calendar_name(self, mock_logger, mock_dav_client):
        """Test initialization with missing calendar_name in config"""
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Default'}
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        invalid_config = {
            'url': 'https://test.example.com/dav/',
            'user': 'testuser',
            'password': 'testpass'
            # Missing calendar_name
        }
        
        with self.assertRaises(KeyError):
            TomCalendar(invalid_config, None)
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_invalid_config_missing_required_fields(self, mock_logger, mock_dav_client):
        """Test initialization with missing required config fields"""
        mock_client = MagicMock()
        mock_dav_client.return_value = mock_client
        
        # Test missing URL
        invalid_config1 = {
            'user': 'testuser',
            'password': 'testpass',
            'calendar_name': 'Personal'
        }
        
        with self.assertRaises(KeyError):
            TomCalendar(invalid_config1, None)
        
        # Test missing user
        invalid_config2 = {
            'url': 'https://test.example.com/dav/',
            'password': 'testpass',
            'calendar_name': 'Personal'
        }
        
        with self.assertRaises(KeyError):
            TomCalendar(invalid_config2, None)
        
        # Test missing password
        invalid_config3 = {
            'url': 'https://test.example.com/dav/',
            'user': 'testuser',
            'calendar_name': 'Personal'
        }
        
        with self.assertRaises(KeyError):
            TomCalendar(invalid_config3, None)
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_network_timeout_during_operations(self, mock_logger, mock_dav_client):
        """Test network timeout during various operations"""
        # Setup basic mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Test timeout during search
        mock_calendar.search.side_effect = Exception("Network timeout")
        result = calendar.listEvent()
        
        self.assertEqual(result, [])
        mock_logger.error.assert_called()
        
        # Reset for next test
        mock_logger.reset_mock()
        
        # Test timeout during save
        mock_calendar.save_event.side_effect = Exception("Network timeout")
        
        # Mock timezone for datetime operations
        with patch.object(calendar, 'tz') as mock_tz:
            mock_tz.localize.side_effect = lambda dt: dt
            
            result = calendar.addEvent(
                title='Test Event',
                start='2024-03-15 10:00',
                end='2024-03-15 11:00'
            )
        
        self.assertEqual(result['status'], 'error')
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_timezone_localization_error(self, mock_logger, mock_dav_client):
        """Test when timezone localization fails"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock timezone localization to fail
        with patch.object(calendar, 'tz') as mock_tz:
            mock_tz.localize.side_effect = Exception("Timezone error")
            
            result = calendar.addEvent(
                title='Test Event',
                start='2024-03-15 10:00',
                end='2024-03-15 11:00'
            )
        
        # Should return error
        self.assertEqual(result['status'], 'error')
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_calendar_properties_access_error(self, mock_logger, mock_dav_client):
        """Test when calendar properties access fails during initialization"""
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar1 = MagicMock()
        mock_calendar2 = MagicMock()
        
        # First calendar fails on get_properties
        mock_calendar1.get_properties.side_effect = Exception("Properties access failed")
        
        # Second calendar works
        mock_calendar2.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar1, mock_calendar2]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Should still initialize successfully with the working calendar
        self.assertEqual(calendar.defaultCalendar, mock_calendar2)
        
        # Should log error for the failed calendar
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_delete_event_with_search_error(self, mock_logger, mock_dav_client):
        """Test deleteEvent when calendar search fails"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        mock_calendar.search.side_effect = Exception("Search failed")
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        result = calendar.deleteEvent('event-123')
        
        # Should return error and log error
        self.assertEqual(result['status'], 'error')
        self.assertIn('Failed to delete event', result['message'])
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_delete_event_with_delete_operation_error(self, mock_logger, mock_dav_client):
        """Test deleteEvent when delete operation fails"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        # Mock event that raises exception on delete
        mock_event = MagicMock()
        mock_component = MagicMock()
        mock_component.name = "VEVENT"
        mock_component.get.side_effect = lambda key, default=None: {
            'uid': 'event-to-delete-123'
        }.get(key, default)
        mock_component.subcomponents = []
        
        mock_event.icalendar_instance.walk.return_value = [mock_component]
        mock_event.delete.side_effect = Exception("Delete failed")
        mock_calendar.search.return_value = [mock_event]
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        result = calendar.deleteEvent('event-to-delete-123')
        
        # Should return error and log error
        self.assertEqual(result['status'], 'error')
        self.assertIn('Failed to delete event', result['message'])
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_delete_event_with_malformed_events(self, mock_logger, mock_dav_client):
        """Test deleteEvent when searching through malformed events"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        # Mock events - one malformed, one valid
        mock_bad_event = MagicMock()
        mock_bad_event.icalendar_instance.walk.side_effect = Exception("Bad event")
        
        mock_good_event = MagicMock()
        mock_component = MagicMock()
        mock_component.name = "VEVENT"
        mock_component.get.side_effect = lambda key, default=None: {
            'uid': 'event-to-delete-123'
        }.get(key, default)
        mock_good_event.icalendar_instance.walk.return_value = [mock_component]
        
        mock_calendar.search.return_value = [mock_bad_event, mock_good_event]
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        result = calendar.deleteEvent('event-to-delete-123')
        
        # Should find and delete the good event despite malformed event
        self.assertEqual(result['status'], 'success')
        mock_good_event.delete.assert_called_once()
        # Should log error for malformed event
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_update_event_with_search_error(self, mock_logger, mock_dav_client):
        """Test updateEvent when calendar search fails"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        mock_calendar.search.side_effect = Exception("Search failed")
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        result = calendar.updateEvent('event-123', title='New Title')
        
        # Should return error and log error
        self.assertEqual(result['status'], 'error')
        self.assertIn('Failed to update event', result['message'])
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_update_event_with_save_error(self, mock_logger, mock_dav_client):
        """Test updateEvent when save operation fails"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        # Mock event that raises exception on save
        mock_event = MagicMock()
        mock_component = MagicMock()
        mock_component.name = "VEVENT"
        mock_component.get.side_effect = lambda key, default=None: {
            'uid': 'event-to-update-123',
            'summary': 'Original Title',
            'description': 'Original Description',
            'dtstart': MagicMock(dt=datetime(2024, 3, 15, 10, 0)),
            'dtend': MagicMock(dt=datetime(2024, 3, 15, 11, 0))
        }.get(key, default)
        mock_component.subcomponents = []
        
        mock_event.icalendar_instance.walk.return_value = [mock_component]
        mock_calendar.save_event.side_effect = Exception("Save failed")
        mock_calendar.search.return_value = [mock_event]
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        result = calendar.updateEvent('event-to-update-123', title='New Title')
        
        # Should return error and log error
        self.assertEqual(result['status'], 'error')
        self.assertIn('Failed to update event', result['message'])
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_update_event_with_malformed_events(self, mock_logger, mock_dav_client):
        """Test updateEvent when searching through malformed events"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        # Mock events - one malformed, one valid
        mock_bad_event = MagicMock()
        mock_bad_event.icalendar_instance.walk.side_effect = Exception("Bad event")
        
        mock_good_event = MagicMock()
        mock_component = MagicMock()
        mock_component.name = "VEVENT"
        mock_component.get.side_effect = lambda key, default=None: {
            'uid': 'event-to-update-123',
            'summary': 'Original Title',
            'description': 'Original Description',
            'dtstart': MagicMock(dt=datetime(2024, 3, 15, 10, 0)),
            'dtend': MagicMock(dt=datetime(2024, 3, 15, 11, 0))
        }.get(key, default)
        mock_good_event.icalendar_instance.walk.return_value = [mock_component]
        
        mock_calendar.search.return_value = [mock_bad_event, mock_good_event]
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        result = calendar.updateEvent('event-to-update-123', title='New Title')
        
        # Should find and update the good event despite malformed event
        self.assertEqual(result['status'], 'success')
        mock_good_event.delete.assert_called_once()
        mock_calendar.save_event.assert_called_once()
        # Should log error for malformed event
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_update_event_timezone_error(self, mock_logger, mock_dav_client):
        """Test updateEvent when timezone localization fails"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        # Mock event to update
        mock_event = MagicMock()
        mock_component = MagicMock()
        mock_component.name = "VEVENT"
        mock_component.get.side_effect = lambda key, default=None: {
            'uid': 'event-to-update-123',
            'summary': 'Original Title',
            'description': 'Original Description',
            'dtstart': MagicMock(dt=datetime(2024, 3, 15, 10, 0)),
            'dtend': MagicMock(dt=datetime(2024, 3, 15, 11, 0))
        }.get(key, default)
        mock_event.icalendar_instance.walk.return_value = [mock_component]
        mock_calendar.search.return_value = [mock_event]
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock timezone localization to fail
        with patch.object(calendar, 'tz') as mock_tz:
            mock_tz.localize.side_effect = Exception("Timezone error")
            
            result = calendar.updateEvent(
                'event-to-update-123',
                start='2024-03-15 10:00'
            )
        
        # Should return error
        self.assertEqual(result['status'], 'error')
        self.assertIn('Failed to update event', result['message'])
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_update_event_with_missing_datetime_components(self, mock_logger, mock_dav_client):
        """Test updateEvent with partial time update when existing event is missing datetime components"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        # Mock event with missing dtend
        mock_event = MagicMock()
        mock_component = MagicMock()
        mock_component.name = "VEVENT"
        mock_component.get.side_effect = lambda key, default=None: {
            'uid': 'event-to-update-123',
            'dtstart': None,  # Missing start time
            'dtend': None     # Missing end time
        }.get(key, default)
        mock_event.icalendar_instance.walk.return_value = [mock_component]
        mock_calendar.search.return_value = [mock_event]
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Mock timezone for datetime operations
        with patch.object(calendar, 'tz') as mock_tz:
            mock_tz.localize.side_effect = lambda dt: dt
            
            # Try to update only end time when start is missing
            result = calendar.updateEvent(
                'event-to-update-123',
                end='2024-03-15 15:00'
            )
        
        # Should still update successfully (start will remain None)
        self.assertEqual(result['status'], 'success')
        mock_event.delete.assert_called_once()
        mock_calendar.save_event.assert_called_once()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_network_timeout_during_delete_operations(self, mock_logger, mock_dav_client):
        """Test network timeout during delete operations"""
        # Setup basic mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Test timeout during search
        mock_calendar.search.side_effect = Exception("Network timeout")
        result = calendar.deleteEvent('event-123')
        
        self.assertEqual(result['status'], 'error')
        mock_logger.error.assert_called()
    
    @patch('tomcalendar.caldav.DAVClient')
    @patch('tomcalendar.logger')
    def test_network_timeout_during_update_operations(self, mock_logger, mock_dav_client):
        """Test network timeout during update operations"""
        # Setup basic mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Personal'}
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        calendar = TomCalendar(self.config, None)
        
        # Test timeout during search
        mock_calendar.search.side_effect = Exception("Network timeout")
        result = calendar.updateEvent('event-123', title='New Title')
        
        self.assertEqual(result['status'], 'error')
        mock_logger.error.assert_called()

if __name__ == '__main__':
    unittest.main()