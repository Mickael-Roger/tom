import unittest
from unittest.mock import patch, MagicMock, call
import sys
import os
from datetime import datetime
import pytz

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))

# Mock logger before importing
with patch('tomtodo.logger') as mock_logger:
    from tomtodo import TomTodo

class TestTomTodo(unittest.TestCase):
    
    def setUp(self):
        self.config = {
            'url': 'https://test.example.com/dav/',
            'user': 'testuser',
            'password': 'testpass',
            'list': 'TestTodo'
        }
        
        # Mock caldav components
        self.mock_client = MagicMock()
        self.mock_principal = MagicMock()
        self.mock_calendar = MagicMock()
        self.mock_calendar_props = MagicMock()
        
        # Setup calendar properties
        self.mock_calendar.get_properties.return_value = {
            '{DAV:}displayname': 'TestTodo'
        }
        
        # Mock calendar selection behavior
        def mock_get_properties(props=None):
            if props:
                return {'{DAV:}displayname': 'TestTodo'}
            return {'{DAV:}displayname': 'TestTodo'}
        
        self.mock_calendar.get_properties = mock_get_properties
        
        # Setup the mock chain
        self.mock_client.principal.return_value = self.mock_principal
        self.mock_principal.calendars.return_value = [self.mock_calendar]
        
        # Mock todos for the calendar
        self.mock_todo1 = MagicMock()
        self.mock_todo1.icalendar_component.get.side_effect = lambda key: {
            'summary': 'Test Task 1',
            'due': None,
            'priority': 1,
            'uid': 'test-uid-1'
        }.get(key)
        
        self.mock_todo2 = MagicMock()
        mock_due = MagicMock()
        mock_due.dt = datetime(2024, 12, 25, 10, 30)
        self.mock_todo2.icalendar_component.get.side_effect = lambda key: {
            'summary': 'Test Task 2',
            'due': mock_due,
            'priority': 3,
            'uid': 'test-uid-2'
        }.get(key)
        
        self.mock_calendar.todos.return_value = [self.mock_todo1, self.mock_todo2]
        
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_init_basic(self, mock_logger, mock_dav_client):
        """Test basic initialization"""
        mock_dav_client.return_value = self.mock_client
        
        todo = TomTodo(self.config, None)
        
        # Verify client creation
        mock_dav_client.assert_called_once_with(
            url='https://test.example.com/dav/',
            username='testuser',
            password='testpass'
        )
        
        # Verify attributes
        self.assertEqual(todo.date_format, "%Y-%m-%d %H:%M:%S")
        self.assertEqual(todo.tz.zone, 'Europe/Paris')
        self.assertIsNotNone(todo.todoCal)
        
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_init_with_timezone(self, mock_logger, mock_dav_client):
        """Test initialization with custom timezone"""
        mock_dav_client.return_value = self.mock_client
        
        todo = TomTodo(self.config, None, tz='America/New_York')
        
        self.assertEqual(todo.tz.zone, 'America/New_York')
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_update_tasks(self, mock_logger, mock_dav_client):
        """Test update method"""
        mock_dav_client.return_value = self.mock_client
        
        todo = TomTodo(self.config, None)
        
        # The update method is called during init, so tasks should be populated
        self.assertEqual(len(todo.tasks), 2)
        
        # Check first task (no due date)
        task1 = todo.tasks[0]
        self.assertEqual(task1['name'], 'Test Task 1')
        self.assertIsNone(task1['due'])
        self.assertEqual(task1['priority'], 1)
        self.assertEqual(task1['id'], 'test-uid-1')
        
        # Check second task (with due date)
        task2 = todo.tasks[1]
        self.assertEqual(task2['name'], 'Test Task 2')
        self.assertEqual(task2['due'], '2024-12-25 10:30:00')
        self.assertEqual(task2['priority'], 3)
        self.assertEqual(task2['id'], 'test-uid-2')
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_list_tasks(self, mock_logger, mock_dav_client):
        """Test listTasks method"""
        mock_dav_client.return_value = self.mock_client
        
        todo = TomTodo(self.config, None)
        
        # Mock fresh todos for update call
        mock_todo3 = MagicMock()
        mock_todo3.icalendar_component.get.side_effect = lambda key: {
            'summary': 'New Task',
            'due': None,
            'priority': 2,
            'uid': 'test-uid-3'
        }.get(key)
        
        self.mock_calendar.todos.return_value = [mock_todo3]
        
        result = todo.listTasks()
        
        # Should return updated list
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'New Task')
        self.assertEqual(result[0]['priority'], 2)
        self.assertEqual(result[0]['id'], 'test-uid-3')
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_close_task_success(self, mock_logger, mock_dav_client):
        """Test closing a task successfully"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock task to be closed - test multiple API paths
        mock_task = MagicMock()
        
        # Mock the preferred path: vobject_instance
        mock_task.vobject_instance = MagicMock()
        mock_task.vobject_instance.vtodo = MagicMock()
        mock_task.vobject_instance.vtodo.summary = MagicMock()
        mock_task.vobject_instance.vtodo.summary.value = 'Task to close'
        
        # Also mock icalendar_component as fallback
        mock_task.icalendar_component.get.return_value = 'Task to close'
        
        # Set hasattr to return True for vobject_instance
        def mock_hasattr(obj, attr):
            if attr == 'vobject_instance':
                return True
            elif attr == 'summary':
                return True
            return False
        
        self.mock_calendar.todo_by_uid.return_value = mock_task
        self.mock_calendar.todos.return_value = []  # Empty after closing
        
        with patch('builtins.hasattr', side_effect=mock_hasattr):
            todo = TomTodo(self.config, None)
            result = todo.close('test-uid-1')
        
        # Verify task was found and saved
        self.mock_calendar.todo_by_uid.assert_called_with('test-uid-1')
        mock_task.save.assert_called_once()
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'Todo task removed')
        
        # Verify logging - the task name should be extracted correctly
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        # The exact format may vary based on which API path is taken
        self.assertIn("has been closed", call_args[0][0])
        self.assertEqual(call_args[1]['module_name'], 'todo')
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_close_task_not_found(self, mock_logger, mock_dav_client):
        """Test closing a non-existent task"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock task not found - could be None or raise exception
        from unittest.mock import Mock
        
        def mock_todo_by_uid(uid):
            if uid == 'non-existent-uid':
                # Simulate CalDAV NotFoundError
                from caldav.lib.error import NotFoundError
                raise NotFoundError("Task not found")
            return None
            
        self.mock_calendar.todo_by_uid.side_effect = mock_todo_by_uid
        
        todo = TomTodo(self.config, None)
        
        result = todo.close('non-existent-uid')
        
        # Verify task was searched for
        self.mock_calendar.todo_by_uid.assert_called_with('non-existent-uid')
        
        # Verify response - should handle exception gracefully
        self.assertFalse(result)
        
        # Verify error was logged
        mock_logger.error.assert_called()
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_close_task_success_icalendar_api(self, mock_logger, mock_dav_client):
        """Test closing a task successfully using icalendar API"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock task to be closed - test icalendar path
        mock_task = MagicMock()
        
        # Mock no vobject_instance but has icalendar_instance
        mock_task.vobject_instance = None
        mock_task.icalendar_instance = MagicMock()
        
        # Mock icalendar_component properly
        mock_task.icalendar_component = MagicMock()
        mock_task.icalendar_component.get.return_value = 'Task to close'
        
        # Set hasattr to return appropriate values
        def mock_hasattr(obj, attr):
            if attr == 'vobject_instance':
                return True  # Exists but is None
            elif attr == 'icalendar_instance':
                return True
            return False
        
        self.mock_calendar.todo_by_uid.return_value = mock_task
        self.mock_calendar.todos.return_value = []  # Empty after closing
        
        with patch('builtins.hasattr', side_effect=mock_hasattr):
            todo = TomTodo(self.config, None)
            result = todo.close('test-uid-1')
        
        # Verify task was found and saved
        self.mock_calendar.todo_by_uid.assert_called_with('test-uid-1')
        mock_task.save.assert_called_once()
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'Todo task removed')
        
        # Verify logging
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        # The exact format may vary based on which API path is taken
        self.assertIn("has been closed", call_args[0][0])
        self.assertEqual(call_args[1]['module_name'], 'todo')
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    @patch('tomtodo.Todo')
    @patch('tomtodo.iCalendar')
    def test_create_task_basic(self, mock_icalendar, mock_todo_class, mock_logger, mock_dav_client):
        """Test creating a basic task"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock Todo and Calendar creation
        mock_todo = MagicMock()
        mock_todo_class.return_value = mock_todo
        mock_cal = MagicMock()
        mock_icalendar.return_value = mock_cal
        mock_cal.to_ical.return_value = b'ical_content'
        
        # Mock updated todos after creation
        self.mock_calendar.todos.return_value = []
        
        todo = TomTodo(self.config, None)
        
        result = todo.create('New Task')
        
        # Verify todo creation
        mock_todo.add.assert_called_with('summary', 'New Task')
        mock_cal.add_component.assert_called_with(mock_todo)
        self.mock_calendar.save_event.assert_called_with('ical_content')
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'Todo task added')
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    @patch('tomtodo.Todo')
    @patch('tomtodo.iCalendar')
    @patch('tomtodo.datetime')
    def test_create_task_with_priority_and_due(self, mock_datetime_class, mock_icalendar, mock_todo_class, mock_logger, mock_dav_client):
        """Test creating a task with priority and due date"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock datetime parsing
        test_datetime = datetime(2024, 12, 25, 15, 30)
        mock_datetime_class.strptime.return_value = test_datetime
        
        # Mock Todo and Calendar creation
        mock_todo = MagicMock()
        mock_todo_class.return_value = mock_todo
        mock_cal = MagicMock()
        mock_icalendar.return_value = mock_cal
        mock_cal.to_ical.return_value = b'ical_content'
        
        # Mock updated todos after creation
        self.mock_calendar.todos.return_value = []
        
        todo = TomTodo(self.config, None)
        
        result = todo.create('Important Task', priority=1, due='2024-12-25 15:30:00')
        
        # Verify todo creation with all parameters
        expected_calls = [
            call('summary', 'Important Task'),
            call('priority', 1),
            call('due', test_datetime)
        ]
        mock_todo.add.assert_has_calls(expected_calls)
        
        # Verify datetime parsing
        mock_datetime_class.strptime.assert_called_with('2024-12-25 15:30:00', "%Y-%m-%d %H:%M:%S")
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'Todo task added')
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    @patch('tomtodo.Todo')
    @patch('tomtodo.iCalendar')
    def test_create_task_with_priority_only(self, mock_icalendar, mock_todo_class, mock_logger, mock_dav_client):
        """Test creating a task with priority but no due date"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock Todo and Calendar creation
        mock_todo = MagicMock()
        mock_todo_class.return_value = mock_todo
        mock_cal = MagicMock()
        mock_icalendar.return_value = mock_cal
        mock_cal.to_ical.return_value = b'ical_content'
        
        todo = TomTodo(self.config, None)
        
        result = todo.create('Medium Priority Task', priority=5)
        
        # Verify todo creation
        expected_calls = [
            call('summary', 'Medium Priority Task'),
            call('priority', 5)
        ]
        mock_todo.add.assert_has_calls(expected_calls)
        
        # Verify no due date was added
        self.assertEqual(mock_todo.add.call_count, 2)
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_tools_structure(self, mock_logger, mock_dav_client):
        """Test that tools are properly structured"""
        mock_dav_client.return_value = self.mock_client
        
        todo = TomTodo(self.config, None)
        
        self.assertIsInstance(todo.tools, list)
        self.assertEqual(len(todo.tools), 3)
        
        expected_functions = ['todo_list_all', 'todo_create_task', 'todo_close_task']
        
        for i, tool in enumerate(todo.tools):
            self.assertEqual(tool['type'], 'function')
            self.assertIn('function', tool)
            self.assertEqual(tool['function']['name'], expected_functions[i])
            self.assertIn('description', tool['function'])
            self.assertIn('parameters', tool['function'])
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_functions_structure(self, mock_logger, mock_dav_client):
        """Test that functions are properly structured"""
        mock_dav_client.return_value = self.mock_client
        
        todo = TomTodo(self.config, None)
        
        expected_functions = ['todo_list_all', 'todo_create_task', 'todo_close_task']
        
        for func_name in expected_functions:
            self.assertIn(func_name, todo.functions)
            self.assertIn('function', todo.functions[func_name])
            self.assertTrue(callable(todo.functions[func_name]['function']))
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_config_attributes(self, mock_logger, mock_dav_client):
        """Test that configuration attributes are set correctly"""
        mock_dav_client.return_value = self.mock_client
        
        todo = TomTodo(self.config, None)
        
        self.assertEqual(todo.date_format, "%Y-%m-%d %H:%M:%S")
        self.assertEqual(todo.complexity, 0)
        self.assertEqual(todo.systemContext, "")
        self.assertIsInstance(todo.tasks, list)
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_calendar_selection(self, mock_logger, mock_dav_client):
        """Test calendar selection logic"""
        mock_dav_client.return_value = self.mock_client
        
        # Create multiple calendars with different names
        mock_cal1 = MagicMock()
        mock_cal1.get_properties.return_value = {'{DAV:}displayname': 'OtherCalendar'}
        
        mock_cal2 = MagicMock()
        mock_cal2.get_properties.return_value = {
            '{DAV:}displayname': 'TestTodo',
            '{urn:ietf:params:xml:ns:caldav}calendar-timezone': 'some_tz'  # This should be skipped
        }
        
        mock_cal3 = MagicMock()
        mock_cal3.get_properties.return_value = {'{DAV:}displayname': 'TestTodo'}
        mock_cal3.todos.return_value = []
        
        def mock_get_properties_cal3(props=None):
            if props:
                return {'{DAV:}displayname': 'TestTodo'}
            return {'{DAV:}displayname': 'TestTodo'}
        
        mock_cal3.get_properties = mock_get_properties_cal3
        
        self.mock_principal.calendars.return_value = [mock_cal1, mock_cal2, mock_cal3]
        
        todo = TomTodo(self.config, None)
        
        # Should select mock_cal3 (TestTodo without calendar-timezone)
        self.assertEqual(todo.todoCal, mock_cal3)
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_update_with_due_date_none(self, mock_logger, mock_dav_client):
        """Test update method when due date is None"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock todo with None due date
        mock_todo = MagicMock()
        mock_todo.icalendar_component.get.side_effect = lambda key: {
            'summary': 'Task without due',
            'due': None,
            'priority': None,
            'uid': 'no-due-uid'
        }.get(key)
        
        self.mock_calendar.todos.return_value = [mock_todo]
        
        todo = TomTodo(self.config, None)
        
        self.assertEqual(len(todo.tasks), 1)
        task = todo.tasks[0]
        self.assertEqual(task['name'], 'Task without due')
        self.assertIsNone(task['due'])
        self.assertIsNone(task['priority'])
        self.assertEqual(task['id'], 'no-due-uid')

if __name__ == '__main__':
    unittest.main()