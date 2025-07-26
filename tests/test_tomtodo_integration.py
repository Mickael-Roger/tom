import unittest
from unittest.mock import patch
import sys
import os
import yaml
from datetime import datetime, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
sys.path.append(os.path.dirname(__file__))  # Add tests directory to path

# Import test config loader
from test_config_loader import load_test_config, get_module_config_for_test

# Mock logger before importing
with patch('tomtodo.logger') as mock_logger:
    from tomtodo import TomTodo

class TestTomTodoIntegration(unittest.TestCase):
    """
    Integration tests for TomTodo module that require real CalDAV server access.
    These tests require a valid config.yml file mounted at /config.yml in Docker.
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up class-level resources - load config once"""
        cls.test_config = load_test_config()
        cls.global_config = cls.test_config.get_global_config() or {}
        cls.username = 'test_user'
    
    def setUp(self):
        """Set up test fixtures"""
        if not self.test_config.config_loaded:
            self.skipTest("Test configuration not available - skipping integration tests")
            
        if not self.test_config.has_user_service_config(self.username, 'todo'):
            self.skipTest("Todo service not configured for test user - skipping integration tests")
        
        # Get module configuration using unified config
        self.todo_config = get_module_config_for_test('todo', self.global_config, is_personal=True, username=self.username)
        
        # Create TomTodo instance with real config but mock logger
        with patch('tomtodo.logger') as mock_logger:
            try:
                self.todo = TomTodo(self.todo_config, None)
                self.integration_available = True
            except Exception as e:
                print(f"✗ Failed to connect to CalDAV server: {e}")
                self.integration_available = False
    
    def test_config_loaded(self):
        """Test that configuration is properly loaded"""
        self.assertTrue(self.test_config.config_loaded, "Configuration should be loaded")
        self.assertIsNotNone(self.todo_config, "TODO config should not be None")
        self.assertIn('url', self.todo_config, "URL should be in config")
        self.assertIn('user', self.todo_config, "User should be in config")
        self.assertIn('password', self.todo_config, "Password should be in config")
        self.assertIn('list', self.todo_config, "List should be in config")
    
    def test_caldav_connection(self):
        """Test CalDAV server connection"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Test that we can connect and access calendars
        self.assertIsNotNone(self.todo.client, "CalDAV client should be created")
        self.assertIsNotNone(self.todo.todoCal, "Todo calendar should be found")
        self.assertEqual(self.todo.date_format, "%Y-%m-%d %H:%M:%S")
    
    def test_real_list_tasks(self):
        """Test listing tasks with real CalDAV server"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        result = self.todo.listTasks()
        
        self.assertIsInstance(result, list, "Result should be a list")
        
        # Check structure of tasks if any exist
        for task in result:
            self.assertIn('name', task, "Task should have name")
            self.assertIn('due', task, "Task should have due (can be None)")
            self.assertIn('priority', task, "Task should have priority (can be None)")
            self.assertIn('id', task, "Task should have id")
            self.assertIsInstance(task['name'], str, "Task name should be string")
            self.assertIsInstance(task['id'], str, "Task ID should be string")
    
    @patch('tomtodo.logger')
    def test_real_create_and_close_task(self, mock_logger):
        """Test creating and then closing a task"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Create a test task
        test_task_name = f"Integration Test Task {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Test creation
        create_result = self.todo.create(test_task_name)
        
        self.assertEqual(create_result['status'], 'success')
        self.assertEqual(create_result['message'], 'Todo task added')
        
        # Verify task was created by listing tasks
        tasks = self.todo.listTasks()
        created_task = None
        for task in tasks:
            if task['name'] == test_task_name:
                created_task = task
                break
        
        self.assertIsNotNone(created_task, "Created task should be found in task list")
        self.assertEqual(created_task['name'], test_task_name)
        
        # Test closing the task
        close_result = self.todo.close(created_task['id'])
        
        # Check if close was successful (could be True/False or success dict)
        if isinstance(close_result, dict):
            self.assertEqual(close_result['status'], 'success')
            self.assertEqual(close_result['message'], 'Todo task removed')
        elif close_result is False:
            self.fail("Failed to close the created task")
        # else: close_result could be True for successful completion
        
        # Verify task was closed (should not appear in active tasks anymore)
        # Note: Depending on CalDAV server, completed tasks might still be listed
        # but with a different status. We just verify the close operation succeeded.
    
    @patch('tomtodo.logger')
    def test_real_create_task_with_priority(self, mock_logger):
        """Test creating a task with priority"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        test_task_name = f"Priority Test Task {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        test_priority = 2
        
        # Create task with priority
        result = self.todo.create(test_task_name, priority=test_priority)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'Todo task added')
        
        # Verify task was created with correct priority
        tasks = self.todo.listTasks()
        created_task = None
        for task in tasks:
            if task['name'] == test_task_name:
                created_task = task
                break
        
        self.assertIsNotNone(created_task, "Created task should be found")
        self.assertEqual(created_task['priority'], test_priority)
        
        # Clean up
        if created_task:
            try:
                with patch('tomtodo.logger'):
                    self.todo.close(created_task['id'])
            except Exception as e:
                print(f"Warning: Failed to clean up task {created_task['id']}: {e}")
    
    @patch('tomtodo.logger')
    def test_real_create_task_with_due_date(self, mock_logger):
        """Test creating a task with due date"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        test_task_name = f"Due Date Test Task {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Set due date to tomorrow at 14:30
        tomorrow = datetime.now() + timedelta(days=1)
        due_date = tomorrow.replace(hour=14, minute=30, second=0, microsecond=0)
        due_date_str = due_date.strftime("%Y-%m-%d %H:%M:%S")
        
        # Create task with due date
        result = self.todo.create(test_task_name, due=due_date_str)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'Todo task added')
        
        # Verify task was created with correct due date
        tasks = self.todo.listTasks()
        created_task = None
        for task in tasks:
            if task['name'] == test_task_name:
                created_task = task
                break
        
        self.assertIsNotNone(created_task, "Created task should be found")
        self.assertIsNotNone(created_task['due'], "Task should have due date")
        
        # Parse the returned due date and compare
        # Note: Due date format might vary slightly due to timezone handling
        returned_due = datetime.strptime(created_task['due'], "%Y-%m-%d %H:%M:%S")
        expected_due = datetime.strptime(due_date_str, "%Y-%m-%d %H:%M:%S")
        
        # Allow for small time differences due to timezone/server processing
        time_diff = abs((returned_due - expected_due).total_seconds())
        self.assertLess(time_diff, 60, "Due dates should be within 1 minute of each other")
        
        # Clean up
        if created_task:
            try:
                with patch('tomtodo.logger'):
                    self.todo.close(created_task['id'])
            except Exception as e:
                print(f"Warning: Failed to clean up task {created_task['id']}: {e}")
    
    @patch('tomtodo.logger')
    def test_real_create_task_complete(self, mock_logger):
        """Test creating a task with all parameters"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        test_task_name = f"Complete Test Task {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        test_priority = 1
        
        # Set due date to next week
        next_week = datetime.now() + timedelta(days=7)
        due_date = next_week.replace(hour=9, minute=0, second=0, microsecond=0)
        due_date_str = due_date.strftime("%Y-%m-%d %H:%M:%S")
        
        # Create task with all parameters
        result = self.todo.create(test_task_name, priority=test_priority, due=due_date_str)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'Todo task added')
        
        # Verify task was created correctly
        tasks = self.todo.listTasks()
        created_task = None
        for task in tasks:
            if task['name'] == test_task_name:
                created_task = task
                break
        
        self.assertIsNotNone(created_task, "Created task should be found")
        self.assertEqual(created_task['name'], test_task_name)
        self.assertEqual(created_task['priority'], test_priority)
        self.assertIsNotNone(created_task['due'], "Task should have due date")
        
        # Clean up
        if created_task:
            try:
                with patch('tomtodo.logger'):
                    self.todo.close(created_task['id'])
            except Exception as e:
                print(f"Warning: Failed to clean up task {created_task['id']}: {e}")
    
    @patch('tomtodo.logger')
    def test_close_nonexistent_task(self, mock_logger):
        """Test closing a task that doesn't exist"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Try to close a task with a non-existent ID
        result = self.todo.close('non-existent-uid-12345')
        
        # Should return False for non-existent task
        self.assertFalse(result, "Closing non-existent task should return False")
        
        # Verify error was logged
        mock_logger.error.assert_called_once()
        
        # Check that the error message contains information about the task not being found
        call_args = mock_logger.error.call_args[0][0]
        self.assertIn("non-existent-uid-12345", call_args)
        self.assertIn("Error closing task", call_args)
    
    def test_calendar_selection_logic(self):
        """Test that the correct calendar is selected"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Verify that the correct calendar was selected based on config
        self.assertIsNotNone(self.todo.todoCal, "Todo calendar should be selected")
        
        # The calendar should be the one matching the configured list name
        # We can't easily test this without knowing the server structure,
        # but we can verify basic properties
        self.assertTrue(hasattr(self.todo.todoCal, 'todos'), "Selected calendar should have todos method")
        self.assertTrue(hasattr(self.todo.todoCal, 'save_event'), "Selected calendar should have save_event method")
    
    def test_timezone_handling(self):
        """Test timezone handling"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Test default timezone
        self.assertEqual(self.todo.tz.zone, 'Europe/Paris')
        
        # Test custom timezone
        with patch('tomtodo.logger'):
            todo_ny = TomTodo(self.todo_config, None, tz='America/New_York')
            self.assertEqual(todo_ny.tz.zone, 'America/New_York')
    
    def test_module_configuration(self):
        """Test module configuration attributes"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        self.assertEqual(self.todo.date_format, "%Y-%m-%d %H:%M:%S")
        self.assertEqual(self.todo.complexity, 0)
        self.assertEqual(self.todo.systemContext, "")
        self.assertIsInstance(self.todo.tasks, list)
    

if __name__ == '__main__':
    unittest.main()