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
        
        # Ensure new config format is used
        if 'list' in self.todo_config and 'todo_list' not in self.todo_config:
            # Convert legacy config for testing
            self.todo_config['todo_list'] = self.todo_config['list']
            self.todo_config['groceries_list'] = self.todo_config.get('groceries_list', self.todo_config['list'])
        
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
        self.assertTrue(
            'todo_list' in self.todo_config or 'list' in self.todo_config, 
            "todo_list or list should be in config"
        )
    
    def test_caldav_connection(self):
        """Test CalDAV server connection"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Test that we can connect and access calendars
        self.assertIsNotNone(self.todo.client, "CalDAV client should be created")
        self.assertIsNotNone(self.todo.todoCal, "Todo calendar should be found")
        self.assertEqual(self.todo.date_format, "%Y-%m-%d %H:%M:%S")
        
        # Test new config attributes
        self.assertIsNotNone(self.todo.defaultTodoListName, "Default todo list name should be set")
        self.assertIsNotNone(self.todo.defaultGroceriesListName, "Default groceries list name should be set")
        self.assertIsInstance(self.todo.todoCalendars, dict, "Todo calendars should be a dict")
    
    def test_list_available_lists(self):
        """Test listing available lists with real CalDAV server"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        result = self.todo.listAvailableLists()
        
        self.assertEqual(result['status'], 'success', "Should return success status")
        self.assertIn('lists', result, "Result should contain lists")
        self.assertIsInstance(result['lists'], list, "Lists should be a list")
        
        # Should contain at least the default todo list
        self.assertIn(self.todo.defaultTodoListName, result['lists'], 
                      f"Should contain default todo list '{self.todo.defaultTodoListName}'")
    
    def test_list_items_todo_list(self):
        """Test listing items from the todo list"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        result = self.todo.listItems(self.todo.defaultTodoListName)
        
        self.assertIsInstance(result, list, "Result should be a list")
        
        # Check structure of items if any exist
        for item in result:
            self.assertIn('name', item, "Item should have name")
            self.assertIn('due', item, "Item should have due (can be None)")
            self.assertIn('priority', item, "Item should have priority (can be None)")
            self.assertIn('id', item, "Item should have id")
            self.assertIsInstance(item['name'], str, "Item name should be string")
            self.assertIsInstance(item['id'], str, "Item ID should be string")
    
    def test_list_items_groceries_list(self):
        """Test listing items from the groceries list"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        result = self.todo.listItems(self.todo.defaultGroceriesListName)
        
        self.assertIsInstance(result, list, "Result should be a list")
        
        # Check structure of items if any exist
        for item in result:
            self.assertIn('name', item, "Item should have name")
            self.assertIn('id', item, "Item should have id")
            self.assertIsInstance(item['name'], str, "Item name should be string")
            self.assertIsInstance(item['id'], str, "Item ID should be string")
    
    def test_list_items_nonexistent_list(self):
        """Test listing items from non-existent list"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        result = self.todo.listItems('NonExistentList')
        
        self.assertIsInstance(result, dict, "Result should be a dict for error")
        self.assertEqual(result['status'], 'error', "Should return error status")
        self.assertIn('not found', result['message'], "Should indicate list not found")
    
    @patch('tomtodo.logger')
    def test_create_list(self, mock_logger):
        """Test creating a new list"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        test_list_name = f"TestList_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Test creation
        result = self.todo.createList(test_list_name)
        
        self.assertEqual(result['status'], 'success', "Should create list successfully")
        self.assertIn(test_list_name, result['message'], "Message should mention list name")
        
        # Verify list was created
        self.assertIn(test_list_name, self.todo.todoCalendars, "List should be in todoCalendars")
        
        # Verify it appears in available lists
        available_lists = self.todo.listAvailableLists()
        self.assertIn(test_list_name, available_lists['lists'], "List should be in available lists")
        
        # Verify we can list items from the new empty list
        items = self.todo.listItems(test_list_name)
        self.assertIsInstance(items, list, "Should return empty list for new list")
        self.assertEqual(len(items), 0, "New list should be empty")
    
    @patch('tomtodo.logger')
    def test_add_to_list_basic_todo(self, mock_logger):
        """Test adding a basic item to todo list"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        test_item_name = f"Integration Test Todo {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Test creation
        result = self.todo.addToList(test_item_name, self.todo.defaultTodoListName)
        
        self.assertEqual(result['status'], 'success', "Should add item successfully")
        self.assertIn(self.todo.defaultTodoListName, result['message'], "Message should mention list name")
        
        # Verify item was created by listing items
        items = self.todo.listItems(self.todo.defaultTodoListName)
        created_item = None
        for item in items:
            if item['name'] == test_item_name:
                created_item = item
                break
        
        self.assertIsNotNone(created_item, "Created item should be found in list")
        self.assertEqual(created_item['name'], test_item_name)
        
        # Clean up
        if created_item:
            try:
                with patch('tomtodo.logger'):
                    self.todo.removeFromList(created_item['id'], self.todo.defaultTodoListName)
            except Exception as e:
                print(f"Warning: Failed to clean up item {created_item['id']}: {e}")
    
    @patch('tomtodo.logger')
    def test_add_to_list_basic_grocery(self, mock_logger):
        """Test adding a basic item to groceries list"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        test_item_name = f"Integration Test Grocery {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Test creation
        result = self.todo.addToList(test_item_name, self.todo.defaultGroceriesListName)
        
        self.assertEqual(result['status'], 'success', "Should add item successfully")
        self.assertIn(self.todo.defaultGroceriesListName, result['message'], "Message should mention list name")
        
        # Verify item was created by listing items
        items = self.todo.listItems(self.todo.defaultGroceriesListName)
        created_item = None
        for item in items:
            if item['name'] == test_item_name:
                created_item = item
                break
        
        self.assertIsNotNone(created_item, "Created item should be found in list")
        self.assertEqual(created_item['name'], test_item_name)
        
        # Clean up
        if created_item:
            try:
                with patch('tomtodo.logger'):
                    self.todo.removeFromList(created_item['id'], self.todo.defaultGroceriesListName)
            except Exception as e:
                print(f"Warning: Failed to clean up item {created_item['id']}: {e}")
    
    @patch('tomtodo.logger')
    def test_add_to_list_with_priority_and_due(self, mock_logger):
        """Test adding an item with priority and due date"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        test_item_name = f"Priority Test Todo {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        test_priority = 2
        
        # Set due date to tomorrow at 14:30
        tomorrow = datetime.now() + timedelta(days=1)
        due_date = tomorrow.replace(hour=14, minute=30, second=0, microsecond=0)
        due_date_str = due_date.strftime("%Y-%m-%d %H:%M:%S")
        
        # Create item with priority and due date
        result = self.todo.addToList(test_item_name, self.todo.defaultTodoListName, 
                                    priority=test_priority, due=due_date_str)
        
        self.assertEqual(result['status'], 'success', "Should add item successfully")
        
        # Verify item was created with correct attributes
        items = self.todo.listItems(self.todo.defaultTodoListName)
        created_item = None
        for item in items:
            if item['name'] == test_item_name:
                created_item = item
                break
        
        self.assertIsNotNone(created_item, "Created item should be found")
        self.assertEqual(created_item['priority'], test_priority)
        self.assertIsNotNone(created_item['due'], "Item should have due date")
        
        # Parse the returned due date and compare
        returned_due = datetime.strptime(created_item['due'], "%Y-%m-%d %H:%M:%S")
        expected_due = datetime.strptime(due_date_str, "%Y-%m-%d %H:%M:%S")
        
        # Allow for small time differences due to timezone/server processing
        time_diff = abs((returned_due - expected_due).total_seconds())
        self.assertLess(time_diff, 60, "Due dates should be within 1 minute of each other")
        
        # Clean up
        if created_item:
            try:
                with patch('tomtodo.logger'):
                    self.todo.removeFromList(created_item['id'], self.todo.defaultTodoListName)
            except Exception as e:
                print(f"Warning: Failed to clean up item {created_item['id']}: {e}")
    
    @patch('tomtodo.logger')
    def test_add_and_remove_item_cycle(self, mock_logger):
        """Test complete cycle of adding and removing an item"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        test_item_name = f"Cycle Test Item {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Create item
        create_result = self.todo.addToList(test_item_name, self.todo.defaultTodoListName)
        self.assertEqual(create_result['status'], 'success')
        
        # Find the created item
        items = self.todo.listItems(self.todo.defaultTodoListName)
        created_item = None
        for item in items:
            if item['name'] == test_item_name:
                created_item = item
                break
        
        self.assertIsNotNone(created_item, "Created item should be found")
        
        # Remove the item
        remove_result = self.todo.removeFromList(created_item['id'], self.todo.defaultTodoListName)
        
        # Check if remove was successful
        if isinstance(remove_result, dict):
            self.assertEqual(remove_result['status'], 'success')
            self.assertIn(self.todo.defaultTodoListName, remove_result['message'])
        else:
            self.fail("Remove operation should return success dict")
    
    @patch('tomtodo.logger')
    def test_add_to_nonexistent_list(self, mock_logger):
        """Test adding item to non-existent list"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        result = self.todo.addToList("Test Item", "NonExistentList")
        
        self.assertEqual(result['status'], 'error', "Should return error status")
        self.assertIn('not found', result['message'], "Should indicate list not found")
    
    @patch('tomtodo.logger')
    def test_remove_from_nonexistent_list(self, mock_logger):
        """Test removing item from non-existent list"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        result = self.todo.removeFromList('fake-id', 'NonExistentList')
        
        self.assertEqual(result['status'], 'error', "Should return error status")
        self.assertIn('not found', result['message'], "Should indicate list not found")
    
    @patch('tomtodo.logger')
    def test_remove_nonexistent_item(self, mock_logger):
        """Test removing an item that doesn't exist"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        result = self.todo.removeFromList('non-existent-uid-12345', self.todo.defaultTodoListName)
        
        self.assertEqual(result['status'], 'error', "Should return error status")
        # Different CalDAV servers may behave differently:
        # - Some return None (our code returns "Item not found")
        # - Some raise NotFoundError (our code returns "Failed to remove item: NotFoundError...")
        self.assertTrue(
            result['message'] == 'Item not found' or 'Failed to remove item:' in result['message'],
            f"Should indicate item not found, got: {result['message']}"
        )
    
    def test_system_context_contains_list_names(self):
        """Test that system context contains the configured list names"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # System context should mention the configured list names
        self.assertIn(self.todo.defaultTodoListName, self.todo.systemContext,
                      "System context should contain todo list name")
        self.assertIn(self.todo.defaultGroceriesListName, self.todo.systemContext,
                      "System context should contain groceries list name")
        self.assertIn('TODO List', self.todo.systemContext,
                      "System context should mention TODO List")
        self.assertIn('Groceries List', self.todo.systemContext,
                      "System context should mention Groceries List")
    
    def test_timezone_handling(self):
        """Test timezone handling"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Test default timezone
        self.assertEqual(self.todo.tz.zone, 'Europe/Paris')
        
        # Test custom timezone
        with patch('tomtodo.logger'):
            todo_ny = TomTodo(self.todo_config, None, tz='America/New_York')
            if todo_ny.client:  # Only test if connection succeeded
                self.assertEqual(todo_ny.tz.zone, 'America/New_York')
    
    def test_module_tools_structure(self):
        """Test that module tools are properly structured"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        self.assertIsInstance(self.todo.tools, list, "Tools should be a list")
        self.assertEqual(len(self.todo.tools), 6, "Should have 6 tools")
        
        expected_functions = [
            'list_available_lists',
            'create_list', 
            'add_to_list',
            'list_items',
            'remove_from_list',
            'update_item_priority'
        ]
        
        for i, tool in enumerate(self.todo.tools):
            self.assertEqual(tool['type'], 'function')
            self.assertIn('function', tool)
            self.assertEqual(tool['function']['name'], expected_functions[i])
            self.assertIn('description', tool['function'])
            self.assertIn('parameters', tool['function'])
    
    def test_module_functions_structure(self):
        """Test that module functions are properly structured"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        expected_functions = [
            'list_available_lists',
            'create_list',
            'add_to_list', 
            'list_items',
            'remove_from_list',
            'update_item_priority'
        ]
        
        for func_name in expected_functions:
            self.assertIn(func_name, self.todo.functions, f"Should have {func_name} function")
            self.assertIn('function', self.todo.functions[func_name])
            self.assertTrue(callable(self.todo.functions[func_name]['function']))
    
    @patch('tomtodo.logger')
    def test_update_item_priority_complete_cycle(self, mock_logger):
        """Test complete cycle of creating item, updating priority, and cleaning up"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        test_item_name = f"Priority Update Test {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Create item without priority
        create_result = self.todo.addToList(test_item_name, self.todo.defaultTodoListName)
        self.assertEqual(create_result['status'], 'success')
        
        # Find the created item
        items = self.todo.listItems(self.todo.defaultTodoListName)
        created_item = None
        for item in items:
            if item['name'] == test_item_name:
                created_item = item
                break
        
        self.assertIsNotNone(created_item, "Created item should be found")
        
        # Update priority to high (1)
        update_result = self.todo.updateItemPriority(created_item['id'], self.todo.defaultTodoListName, 1)
        self.assertEqual(update_result['status'], 'success')
        self.assertIn('Priority updated to 1', update_result['message'])
        
        # Verify priority was updated
        items_after_update = self.todo.listItems(self.todo.defaultTodoListName)
        updated_item = None
        for item in items_after_update:
            if item['id'] == created_item['id']:
                updated_item = item
                break
        
        self.assertIsNotNone(updated_item, "Updated item should still exist")
        self.assertEqual(updated_item['priority'], 1, "Priority should be updated to 1")
        
        # Update priority to medium (5)
        update_result2 = self.todo.updateItemPriority(created_item['id'], self.todo.defaultTodoListName, 5)
        self.assertEqual(update_result2['status'], 'success')
        self.assertIn('Priority updated to 5', update_result2['message'])
        
        # Verify priority was updated again
        items_after_update2 = self.todo.listItems(self.todo.defaultTodoListName)
        updated_item2 = None
        for item in items_after_update2:
            if item['id'] == created_item['id']:
                updated_item2 = item
                break
        
        self.assertIsNotNone(updated_item2, "Updated item should still exist")
        self.assertEqual(updated_item2['priority'], 5, "Priority should be updated to 5")
        
        # Update priority to low (9)
        low_priority_result = self.todo.updateItemPriority(created_item['id'], self.todo.defaultTodoListName, 9)
        self.assertEqual(low_priority_result['status'], 'success')
        self.assertIn('Priority updated to 9', low_priority_result['message'])
        
        # Verify priority was updated to low
        items_after_low_update = self.todo.listItems(self.todo.defaultTodoListName)
        final_item = None
        for item in items_after_low_update:
            if item['id'] == created_item['id']:
                final_item = item
                break
        
        self.assertIsNotNone(final_item, "Item should still exist after priority update")
        self.assertEqual(final_item['priority'], 9, "Priority should be updated to 9")
        
        # Clean up
        try:
            with patch('tomtodo.logger'):
                self.todo.removeFromList(created_item['id'], self.todo.defaultTodoListName)
        except Exception as e:
            print(f"Warning: Failed to clean up item {created_item['id']}: {e}")
    
    @patch('tomtodo.logger')
    def test_update_priority_nonexistent_item(self, mock_logger):
        """Test updating priority for non-existent item"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        result = self.todo.updateItemPriority('non-existent-uid-12345', self.todo.defaultTodoListName, 2)
        
        self.assertEqual(result['status'], 'error', "Should return error status")
        # Different CalDAV servers may behave differently, similar to remove_nonexistent_item test
        self.assertTrue(
            result['message'] == 'Item not found' or 'Failed to update priority:' in result['message'],
            f"Should indicate item not found, got: {result['message']}"
        )
    
    @patch('tomtodo.logger')
    def test_update_priority_nonexistent_list(self, mock_logger):
        """Test updating priority in non-existent list"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        result = self.todo.updateItemPriority('some-uid', 'NonExistentList', 2)
        
        self.assertEqual(result['status'], 'error', "Should return error status")
        self.assertIn('not found', result['message'], "Should indicate list not found")
    
    @patch('tomtodo.logger')
    def test_update_priority_groceries_item(self, mock_logger):
        """Test that priority can be set on groceries items (even though it's unusual)"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        test_item_name = f"Priority Grocery Test {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Create item in groceries list
        create_result = self.todo.addToList(test_item_name, self.todo.defaultGroceriesListName)
        self.assertEqual(create_result['status'], 'success')
        
        # Find the created item
        items = self.todo.listItems(self.todo.defaultGroceriesListName)
        created_item = None
        for item in items:
            if item['name'] == test_item_name:
                created_item = item
                break
        
        self.assertIsNotNone(created_item, "Created item should be found")
        
        # Update priority (unusual for groceries, but should work)
        update_result = self.todo.updateItemPriority(created_item['id'], self.todo.defaultGroceriesListName, 3)
        self.assertEqual(update_result['status'], 'success')
        self.assertIn('Priority updated to 3', update_result['message'])
        
        # Clean up
        try:
            with patch('tomtodo.logger'):
                self.todo.removeFromList(created_item['id'], self.todo.defaultGroceriesListName)
        except Exception as e:
            print(f"Warning: Failed to clean up item {created_item['id']}: {e}")


if __name__ == '__main__':
    unittest.main()