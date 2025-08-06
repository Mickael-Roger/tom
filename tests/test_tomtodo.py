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
            'todo_list': 'TestTodo',
            'groceries_list': 'TestGroceries'
        }
        
        # Mock caldav components
        self.mock_client = MagicMock()
        self.mock_principal = MagicMock()
        self.mock_todo_calendar = MagicMock()
        self.mock_grocery_calendar = MagicMock()
        
        # Setup calendars with different names
        self.mock_todo_calendar.get_properties.return_value = {'{DAV:}displayname': 'TestTodo'}
        self.mock_grocery_calendar.get_properties.return_value = {'{DAV:}displayname': 'TestGroceries'}
        
        def mock_get_properties_todo(props=None):
            if props:
                return {'{DAV:}displayname': 'TestTodo'}
            return {'{DAV:}displayname': 'TestTodo'}
        
        def mock_get_properties_grocery(props=None):
            if props:
                return {'{DAV:}displayname': 'TestGroceries'}
            return {'{DAV:}displayname': 'TestGroceries'}
        
        self.mock_todo_calendar.get_properties = mock_get_properties_todo
        self.mock_grocery_calendar.get_properties = mock_get_properties_grocery
        
        # Setup the mock chain
        self.mock_client.principal.return_value = self.mock_principal
        self.mock_principal.calendars.return_value = [self.mock_todo_calendar, self.mock_grocery_calendar]
        
        # Mock items for the calendars
        self.mock_todo_item = MagicMock()
        self.mock_todo_item.icalendar_component.get.side_effect = lambda key: {
            'summary': 'Test Task',
            'due': None,
            'priority': 1,
            'uid': 'todo-uid-1'
        }.get(key)
        
        self.mock_grocery_item = MagicMock()
        mock_due = MagicMock()
        mock_due.dt = datetime(2024, 12, 25, 10, 30)
        self.mock_grocery_item.icalendar_component.get.side_effect = lambda key: {
            'summary': 'Milk',
            'due': mock_due,
            'priority': None,
            'uid': 'grocery-uid-1'
        }.get(key)
        
        self.mock_todo_calendar.todos.return_value = [self.mock_todo_item]
        self.mock_grocery_calendar.todos.return_value = [self.mock_grocery_item]
        
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
        self.assertEqual(todo.defaultTodoListName, 'TestTodo')
        self.assertEqual(todo.defaultGroceriesListName, 'TestGroceries')
        self.assertIsNotNone(todo.todoCal)
        self.assertEqual(len(todo.todoCalendars), 2)
        
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_init_connection_failure(self, mock_logger, mock_dav_client):
        """Test initialization when CalDAV connection fails"""
        mock_dav_client.side_effect = Exception("Connection failed")
        
        todo = TomTodo(self.config, None)
        
        # Should handle failure gracefully
        self.assertIsNone(todo.client)
        self.assertEqual(todo.todoCalendars, {})
        self.assertIsNone(todo.todoCal)
        mock_logger.error.assert_called_once()
        
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_list_available_lists(self, mock_logger, mock_dav_client):
        """Test listing available lists"""
        mock_dav_client.return_value = self.mock_client
        
        todo = TomTodo(self.config, None)
        result = todo.listAvailableLists()
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('TestTodo', result['lists'])
        self.assertIn('TestGroceries', result['lists'])
        
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_list_available_lists_no_connection(self, mock_logger, mock_dav_client):
        """Test listing available lists when no connection"""
        mock_dav_client.side_effect = Exception("Connection failed")
        
        todo = TomTodo(self.config, None)
        result = todo.listAvailableLists()
        
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['message'], 'CalDAV connection not available')
        
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_create_list_success(self, mock_logger, mock_dav_client):
        """Test creating a new list successfully"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock the new calendar creation
        mock_new_calendar = MagicMock()
        self.mock_principal.make_calendar.return_value = mock_new_calendar
        
        todo = TomTodo(self.config, None)
        result = todo.createList('NewList')
        
        # Verify calendar was created
        self.mock_principal.make_calendar.assert_called_once_with(name='NewList')
        mock_new_calendar.set_properties.assert_called_once()
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertIn('NewList', result['message'])
        
        # Verify it was added to todoCalendars
        self.assertIn('NewList', todo.todoCalendars)
        
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_list_items_success(self, mock_logger, mock_dav_client):
        """Test listing items from a specific list"""
        mock_dav_client.return_value = self.mock_client
        
        todo = TomTodo(self.config, None)
        result = todo.listItems('TestTodo')
        
        # Should return items from the TestTodo calendar
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Test Task')
        self.assertEqual(result[0]['priority'], 1)
        self.assertEqual(result[0]['id'], 'todo-uid-1')
        
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_list_items_not_found(self, mock_logger, mock_dav_client):
        """Test listing items from non-existent list"""
        mock_dav_client.return_value = self.mock_client
        
        todo = TomTodo(self.config, None)
        result = todo.listItems('NonExistentList')
        
        self.assertEqual(result['status'], 'error')
        self.assertIn('not found', result['message'])
        
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    @patch('tomtodo.Todo')
    @patch('tomtodo.iCalendar')
    def test_add_to_list_basic_item(self, mock_icalendar, mock_todo_class, mock_logger, mock_dav_client):
        """Test adding a basic item to a list"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock Todo and Calendar creation
        mock_todo = MagicMock()
        mock_todo_class.return_value = mock_todo
        mock_cal = MagicMock()
        mock_icalendar.return_value = mock_cal
        mock_cal.to_ical.return_value = b'ical_content'
        
        todo = TomTodo(self.config, None)
        result = todo.addToList('New Item', 'TestTodo')
        
        # Verify todo creation
        mock_todo.add.assert_called_with('summary', 'New Item')
        mock_cal.add_component.assert_called_with(mock_todo)
        self.mock_todo_calendar.save_event.assert_called_with('ical_content')
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertIn('TestTodo', result['message'])
        
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    @patch('tomtodo.Todo')
    @patch('tomtodo.iCalendar')
    @patch('tomtodo.datetime')
    def test_add_to_list_with_priority_and_due(self, mock_datetime_class, mock_icalendar, mock_todo_class, mock_logger, mock_dav_client):
        """Test adding an item with priority and due date"""
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
        
        todo = TomTodo(self.config, None)
        result = todo.addToList('Important Task', 'TestTodo', priority=1, due='2024-12-25 15:30:00')
        
        # Verify todo creation with all parameters
        expected_calls = [
            call('summary', 'Important Task'),
            call('priority', 1),
            call('due', test_datetime)
        ]
        mock_todo.add.assert_has_calls(expected_calls)
        
        # Verify datetime parsing
        mock_datetime_class.strptime.assert_called_with('2024-12-25 15:30:00', "%Y-%m-%d %H:%M:%S")
        
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_remove_from_list_success(self, mock_logger, mock_dav_client):
        """Test removing an item from a list successfully"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock item to be removed
        mock_item = MagicMock()
        mock_item.vobject_instance = MagicMock()
        mock_item.vobject_instance.vtodo = MagicMock()
        mock_item.vobject_instance.vtodo.summary = MagicMock()
        mock_item.vobject_instance.vtodo.summary.value = 'Item to remove'
        
        # Set hasattr to return True for vobject_instance
        def mock_hasattr(obj, attr):
            if attr == 'vobject_instance':
                return True
            elif attr == 'summary':
                return True
            return False
        
        self.mock_todo_calendar.todo_by_uid.return_value = mock_item
        
        with patch('builtins.hasattr', side_effect=mock_hasattr):
            todo = TomTodo(self.config, None)
            result = todo.removeFromList('todo-uid-1', 'TestTodo')
        
        # Verify item was found and marked completed
        self.mock_todo_calendar.todo_by_uid.assert_called_with('todo-uid-1')
        mock_item.save.assert_called_once()
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertIn('TestTodo', result['message'])
        
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_remove_from_list_not_found(self, mock_logger, mock_dav_client):
        """Test removing an item that doesn't exist"""
        mock_dav_client.return_value = self.mock_client
        
        self.mock_todo_calendar.todo_by_uid.return_value = None
        
        todo = TomTodo(self.config, None)
        result = todo.removeFromList('non-existent-uid', 'TestTodo')
        
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['message'], 'Item not found')
        
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_tools_structure(self, mock_logger, mock_dav_client):
        """Test that tools are properly structured for the new functions"""
        mock_dav_client.return_value = self.mock_client
        
        todo = TomTodo(self.config, None)
        
        self.assertIsInstance(todo.tools, list)
        self.assertEqual(len(todo.tools), 6)
        
        expected_functions = [
            'list_available_lists',
            'create_list', 
            'add_to_list',
            'list_items',
            'remove_from_list',
            'update_item_priority'
        ]
        
        for i, tool in enumerate(todo.tools):
            self.assertEqual(tool['type'], 'function')
            self.assertIn('function', tool)
            self.assertEqual(tool['function']['name'], expected_functions[i])
            self.assertIn('description', tool['function'])
            self.assertIn('parameters', tool['function'])
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_functions_structure(self, mock_logger, mock_dav_client):
        """Test that functions are properly structured for the new functions"""
        mock_dav_client.return_value = self.mock_client
        
        todo = TomTodo(self.config, None)
        
        expected_functions = [
            'list_available_lists',
            'create_list',
            'add_to_list', 
            'list_items',
            'remove_from_list',
            'update_item_priority'
        ]
        
        for func_name in expected_functions:
            self.assertIn(func_name, todo.functions)
            self.assertIn('function', todo.functions[func_name])
            self.assertTrue(callable(todo.functions[func_name]['function']))
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_system_context_contains_default_lists(self, mock_logger, mock_dav_client):
        """Test that system context contains the configured default list names"""
        mock_dav_client.return_value = self.mock_client
        
        todo = TomTodo(self.config, None)
        
        # System context should mention the configured list names
        self.assertIn('TestTodo', todo.systemContext)
        self.assertIn('TestGroceries', todo.systemContext)
        self.assertIn('TODO List', todo.systemContext)
        self.assertIn('Groceries List', todo.systemContext)
        
    @patch('tomtodo.caldav.DAVClient') 
    @patch('tomtodo.logger')
    def test_get_calendar_by_name(self, mock_logger, mock_dav_client):
        """Test getCalendarByName helper method"""
        mock_dav_client.return_value = self.mock_client
        
        todo = TomTodo(self.config, None)
        
        # Test getting existing calendar
        cal = todo.getCalendarByName('TestTodo')
        self.assertEqual(cal, self.mock_todo_calendar)
        
        # Test getting non-existent calendar
        cal = todo.getCalendarByName('NonExistent')
        self.assertIsNone(cal)
        
        # Test default behavior (should return todoCal)
        cal = todo.getCalendarByName(None)
        self.assertEqual(cal, todo.todoCal)
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_update_item_priority_success(self, mock_logger, mock_dav_client):
        """Test updating item priority successfully"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock item to be updated
        mock_item = MagicMock()
        mock_item.vobject_instance = MagicMock()
        mock_item.vobject_instance.vtodo = MagicMock()
        mock_item.vobject_instance.vtodo.summary = MagicMock()
        mock_item.vobject_instance.vtodo.summary.value = 'Item to update'
        
        # Mock existing priority attribute
        mock_priority = MagicMock()
        mock_item.vobject_instance.vtodo.priority = mock_priority
        
        # Set hasattr to return True for vobject_instance and priority
        def mock_hasattr(obj, attr):
            if attr == 'vobject_instance':
                return True
            elif attr == 'summary':
                return True
            elif attr == 'priority' and obj == mock_item.vobject_instance.vtodo:
                return True
            return False
        
        self.mock_todo_calendar.todo_by_uid.return_value = mock_item
        
        with patch('builtins.hasattr', side_effect=mock_hasattr):
            todo = TomTodo(self.config, None)
            result = todo.updateItemPriority('todo-uid-1', 'TestTodo', 3)
        
        # Verify item was found and priority updated
        self.mock_todo_calendar.todo_by_uid.assert_called_with('todo-uid-1')
        mock_priority.__setattr__.assert_called_with('value', 3)
        mock_item.save.assert_called_once()
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertIn('Priority updated to 3', result['message'])
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_update_item_priority_low(self, mock_logger, mock_dav_client):
        """Test setting item priority to low (9)"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock item to be updated
        mock_item = MagicMock()
        mock_item.vobject_instance = MagicMock()
        mock_item.vobject_instance.vtodo = MagicMock()
        mock_item.vobject_instance.vtodo.summary = MagicMock()
        mock_item.vobject_instance.vtodo.summary.value = 'Item to update'
        
        # Mock existing priority attribute
        mock_priority = MagicMock()
        mock_item.vobject_instance.vtodo.priority = mock_priority
        
        # Set hasattr to return True for vobject_instance and priority
        def mock_hasattr(obj, attr):
            if attr == 'vobject_instance':
                return True
            elif attr == 'summary':
                return True
            elif attr == 'priority' and obj == mock_item.vobject_instance.vtodo:
                return True
            return False
        
        self.mock_todo_calendar.todo_by_uid.return_value = mock_item
        
        with patch('builtins.hasattr', side_effect=mock_hasattr):
            todo = TomTodo(self.config, None)
            result = todo.updateItemPriority('todo-uid-1', 'TestTodo', 9)
        
        # Verify item was found and priority set to 9
        self.mock_todo_calendar.todo_by_uid.assert_called_with('todo-uid-1')
        mock_priority.__setattr__.assert_called_with('value', 9)
        mock_item.save.assert_called_once()
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertIn('Priority updated to 9', result['message'])
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_update_item_priority_not_found(self, mock_logger, mock_dav_client):
        """Test updating priority for non-existent item"""
        mock_dav_client.return_value = self.mock_client
        
        self.mock_todo_calendar.todo_by_uid.return_value = None
        
        todo = TomTodo(self.config, None)
        result = todo.updateItemPriority('non-existent-uid', 'TestTodo', 2)
        
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['message'], 'Item not found')
    
    @patch('tomtodo.caldav.DAVClient')
    @patch('tomtodo.logger')
    def test_update_item_priority_nonexistent_list(self, mock_logger, mock_dav_client):
        """Test updating priority in non-existent list"""
        mock_dav_client.return_value = self.mock_client
        
        todo = TomTodo(self.config, None)
        result = todo.updateItemPriority('some-uid', 'NonExistentList', 2)
        
        self.assertEqual(result['status'], 'error')
        self.assertIn('not found', result['message'])

if __name__ == '__main__':
    unittest.main()