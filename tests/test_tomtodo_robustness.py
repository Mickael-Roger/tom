import unittest
from unittest.mock import patch, MagicMock
import sys
import os
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))

# Mock logger before importing
with patch('tomtodo.logger') as mock_logger:
    from tomtodo import TomTodo

class TestTomTodoRobustness(unittest.TestCase):
    """
    Robustness tests for TomTodo module that test error handling
    and edge cases without requiring a real CalDAV server.
    """
    
    def setUp(self):
        self.config = {
            'url': 'https://test.example.com/dav/',
            'user': 'testuser',
            'password': 'testpass',
            'list': 'TestTodo'
        }
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_init_with_connection_error(self, mock_logger, mock_dav_client):
        """Test initialization when CalDAV server is unreachable"""
        # Mock connection failure
        mock_dav_client.side_effect = Exception("Connection failed")
        
        with self.assertRaises(Exception):
            TomTodo(self.config, None)
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_close_with_caldav_not_found_error(self, mock_logger, mock_dav_client):
        """Test closing task with CalDAV NotFoundError"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'TestTodo'}
        mock_calendar.todos.return_value = []
        
        # Mock NotFoundError when searching for task
        from caldav.lib.error import NotFoundError
        mock_calendar.todo_by_uid.side_effect = NotFoundError("Task not found")
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        todo = TomTodo(self.config, None)
        
        result = todo.close('non-existent-task')
        
        # Should return False and log error
        self.assertFalse(result)
        mock_logger.error.assert_called_once()
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_close_with_generic_exception(self, mock_logger, mock_dav_client):
        """Test closing task with generic exception"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'TestTodo'}
        mock_calendar.todos.return_value = []
        
        # Mock generic exception
        mock_calendar.todo_by_uid.side_effect = Exception("Server error")
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        todo = TomTodo(self.config, None)
        
        result = todo.close('some-task-id')
        
        # Should return False and log error
        self.assertFalse(result)
        mock_logger.error.assert_called_once()
        
        # Check error message contains task ID
        call_args = mock_logger.error.call_args[0][0]
        self.assertIn('some-task-id', call_args)
        self.assertIn('Server error', call_args)
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_close_with_task_save_error(self, mock_logger, mock_dav_client):
        """Test closing task when save operation fails"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        mock_task = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'TestTodo'}
        mock_calendar.todos.return_value = []
        mock_calendar.todo_by_uid.return_value = mock_task
        
        # Mock task with icalendar_component
        mock_task.icalendar_component.get.return_value = 'Test Task'
        
        # Mock save failure
        mock_task.save.side_effect = Exception("Save failed")
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        todo = TomTodo(self.config, None)
        
        result = todo.close('task-id')
        
        # Should return False and log error
        self.assertFalse(result)
        mock_logger.error.assert_called_once()
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_update_with_server_error(self, mock_logger, mock_dav_client):
        """Test update method when server returns error"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'TestTodo'}
        
        # Mock todos() method to raise exception
        mock_calendar.todos.side_effect = Exception("Server connection lost")
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        # This should raise during initialization
        with self.assertRaises(Exception):
            TomTodo(self.config, None)
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_create_with_invalid_due_date(self, mock_logger, mock_dav_client):
        """Test creating task with invalid due date format"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'TestTodo'}
        mock_calendar.todos.return_value = []
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        with patch('tomtodo.Todo') as mock_todo_class, \
             patch('tomtodo.iCalendar') as mock_icalendar:
            
            mock_todo = MagicMock()
            mock_todo_class.return_value = mock_todo
            mock_cal = MagicMock()
            mock_icalendar.return_value = mock_cal
            mock_cal.to_ical.return_value = b'ical_content'
            
            todo = TomTodo(self.config, None)
            
            # Test with invalid date format
            with self.assertRaises(ValueError):
                todo.create('Test Task', due='invalid-date-format')
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_calendar_not_found(self, mock_logger, mock_dav_client):
        """Test when specified calendar list is not found"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        
        # Mock calendar with different name
        mock_calendar = MagicMock()
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'DifferentList'}
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        # Should not find the specified list, todoCal should not be set
        with self.assertRaises(AttributeError):
            todo = TomTodo(self.config, None)
            # This will fail when trying to access self.todoCal.todos() in update()
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_list_tasks_with_malformed_todo(self, mock_logger, mock_dav_client):
        """Test listing tasks when one todo has malformed data"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'TestTodo'}
        
        # Mock one good todo and one malformed todo
        mock_good_todo = MagicMock()
        mock_good_todo.icalendar_component.get.side_effect = lambda key: {
            'summary': 'Good Task',
            'due': None,
            'priority': 1,
            'uid': 'good-uid'
        }.get(key)
        
        mock_bad_todo = MagicMock()
        # Make the bad todo raise exception when accessing component
        mock_bad_todo.icalendar_component.get.side_effect = Exception("Malformed data")
        
        mock_calendar.todos.return_value = [mock_good_todo, mock_bad_todo]
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        # Should handle malformed todo gracefully
        with self.assertRaises(Exception):
            TomTodo(self.config, None)
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_empty_task_name(self, mock_logger, mock_dav_client):
        """Test creating task with empty name"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'TestTodo'}
        mock_calendar.todos.return_value = []
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        with patch('tomtodo.Todo') as mock_todo_class, \
             patch('tomtodo.iCalendar') as mock_icalendar:
            
            mock_todo = MagicMock()
            mock_todo_class.return_value = mock_todo
            mock_cal = MagicMock()
            mock_icalendar.return_value = mock_cal
            mock_cal.to_ical.return_value = b'ical_content'
            
            todo = TomTodo(self.config, None)
            
            # Should handle empty task name
            result = todo.create('')
            self.assertEqual(result['status'], 'success')
            
            # Verify summary was set (even if empty)
            mock_todo.add.assert_called_with('summary', '')

if __name__ == '__main__':
    unittest.main()