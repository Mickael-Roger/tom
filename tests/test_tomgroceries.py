import unittest
from unittest.mock import patch, MagicMock, call
import sys
import os
from datetime import datetime
import pytz

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))

# Mock logger before importing
with patch('tomgroceries.logger') as mock_logger:
    from tomgroceries import TomGroceries

class TestTomGroceries(unittest.TestCase):
    
    def setUp(self):
        self.config = {
            'url': 'https://test.example.com/dav/',
            'user': 'testuser',
            'password': 'testpass',
            'list': 'Courses'
        }
        
        # Mock caldav components
        self.mock_client = MagicMock()
        self.mock_principal = MagicMock()
        self.mock_calendar = MagicMock()
        self.mock_calendar_props = MagicMock()
        
        # Setup calendar properties
        self.mock_calendar.get_properties.return_value = {
            '{DAV:}displayname': 'Courses'
        }
        
        # Mock calendar selection behavior
        def mock_get_properties(props=None):
            if props:
                return {'{DAV:}displayname': 'Courses'}
            return {'{DAV:}displayname': 'Courses'}
        
        self.mock_calendar.get_properties = mock_get_properties
        
        # Setup the mock chain
        self.mock_client.principal.return_value = self.mock_principal
        self.mock_principal.calendars.return_value = [self.mock_calendar]
        
        # Mock products for the calendar
        self.mock_product1 = MagicMock()
        self.mock_product1.icalendar_component.get.side_effect = lambda key: {
            'summary': 'Milk',
            'uid': 'product-uid-1'
        }.get(key)
        
        self.mock_product2 = MagicMock()
        self.mock_product2.icalendar_component.get.side_effect = lambda key: {
            'summary': 'Bread',
            'uid': 'product-uid-2'
        }.get(key)
        
        self.mock_calendar.todos.return_value = [self.mock_product1, self.mock_product2]
        
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_init_basic(self, mock_logger, mock_dav_client):
        """Test basic initialization"""
        mock_dav_client.return_value = self.mock_client
        
        groceries = TomGroceries(self.config, None)
        
        # Verify client creation
        mock_dav_client.assert_called_once_with(
            url='https://test.example.com/dav/',
            username='testuser',
            password='testpass'
        )
        
        # Verify attributes
        self.assertEqual(groceries.date_format, "%Y-%m-%d %H:%M:%S")
        self.assertEqual(groceries.tz.zone, 'Europe/Paris')
        self.assertIsNotNone(groceries.groceryCal)
        
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_init_with_timezone(self, mock_logger, mock_dav_client):
        """Test initialization with custom timezone"""
        mock_dav_client.return_value = self.mock_client
        
        groceries = TomGroceries(self.config, None, tz='America/New_York')
        
        self.assertEqual(groceries.tz.zone, 'America/New_York')
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_init_without_user_field(self, mock_logger, mock_dav_client):
        """Test initialization when config doesn't have user field"""
        mock_dav_client.return_value = self.mock_client
        
        config_no_user = {
            'url': 'https://test.example.com/dav/',
            'password': 'testpass',
            'list': 'Courses'
        }
        
        groceries = TomGroceries(config_no_user, None)
        
        # Should handle missing user gracefully
        mock_dav_client.assert_called_once_with(
            url='https://test.example.com/dav/',
            username='',  # Empty string for missing user
            password='testpass'
        )
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_update_products(self, mock_logger, mock_dav_client):
        """Test update method"""
        mock_dav_client.return_value = self.mock_client
        
        groceries = TomGroceries(self.config, None)
        
        # The update method is called during init, so products should be populated
        self.assertEqual(len(groceries.groceryList), 2)
        
        # Check first product
        product1 = groceries.groceryList[0]
        self.assertEqual(product1['product'], 'Milk')
        self.assertEqual(product1['id'], 'product-uid-1')
        
        # Check second product
        product2 = groceries.groceryList[1]
        self.assertEqual(product2['product'], 'Bread')
        self.assertEqual(product2['id'], 'product-uid-2')
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_list_products(self, mock_logger, mock_dav_client):
        """Test listProducts method"""
        mock_dav_client.return_value = self.mock_client
        
        groceries = TomGroceries(self.config, None)
        
        # Mock fresh products for update call
        mock_product3 = MagicMock()
        mock_product3.icalendar_component.get.side_effect = lambda key: {
            'summary': 'Eggs',
            'uid': 'product-uid-3'
        }.get(key)
        
        self.mock_calendar.todos.return_value = [mock_product3]
        
        result = groceries.listProducts()
        
        # Should return updated list
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['product'], 'Eggs')
        self.assertEqual(result[0]['id'], 'product-uid-3')
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_remove_product_success(self, mock_logger, mock_dav_client):
        """Test removing a product successfully"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock product to be removed - test multiple API paths
        mock_product = MagicMock()
        
        # Mock the preferred path: vobject_instance
        mock_product.vobject_instance = MagicMock()
        mock_product.vobject_instance.vtodo = MagicMock()
        mock_product.vobject_instance.vtodo.summary = MagicMock()
        mock_product.vobject_instance.vtodo.summary.value = 'Product to remove'
        
        # Also mock icalendar_component as fallback
        mock_product.icalendar_component.get.return_value = 'Product to remove'
        
        # Set hasattr to return True for vobject_instance
        def mock_hasattr(obj, attr):
            if attr == 'vobject_instance':
                return True
            elif attr == 'summary':
                return True
            return False
        
        self.mock_calendar.todo_by_uid.return_value = mock_product
        self.mock_calendar.todos.return_value = []  # Empty after removing
        
        with patch('builtins.hasattr', side_effect=mock_hasattr):
            groceries = TomGroceries(self.config, None)
            result = groceries.remove('product-uid-1')
        
        # Verify product was found and deleted
        self.mock_calendar.todo_by_uid.assert_called_with('product-uid-1')
        mock_product.delete.assert_called_once()
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'product removed.')
        
        # Verify logging
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        self.assertIn("has been removed from grocery list", call_args[0][0])
        self.assertEqual(call_args[1]['module_name'], 'groceries')
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_remove_product_not_found(self, mock_logger, mock_dav_client):
        """Test removing a non-existent product"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock product not found - could be None or raise exception
        def mock_todo_by_uid(uid):
            if uid == 'non-existent-uid':
                # Simulate CalDAV NotFoundError
                from caldav.lib.error import NotFoundError
                raise NotFoundError("Product not found")
            return None
            
        self.mock_calendar.todo_by_uid.side_effect = mock_todo_by_uid
        
        groceries = TomGroceries(self.config, None)
        
        result = groceries.remove('non-existent-uid')
        
        # Verify product was searched for
        self.mock_calendar.todo_by_uid.assert_called_with('non-existent-uid')
        
        # Verify response - should handle exception gracefully
        self.assertFalse(result)
        
        # Verify error was logged
        mock_logger.error.assert_called()
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_remove_product_success_icalendar_api(self, mock_logger, mock_dav_client):
        """Test removing a product successfully using icalendar API"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock product to be removed - test icalendar path
        mock_product = MagicMock()
        
        # Mock no vobject_instance but has icalendar_instance
        mock_product.vobject_instance = None
        mock_product.icalendar_instance = MagicMock()
        
        # Mock icalendar_component properly
        mock_product.icalendar_component = MagicMock()
        mock_product.icalendar_component.get.return_value = 'Product to remove'
        
        # Set hasattr to return appropriate values
        def mock_hasattr(obj, attr):
            if attr == 'vobject_instance':
                return True  # Exists but is None
            elif attr == 'icalendar_instance':
                return True
            return False
        
        self.mock_calendar.todo_by_uid.return_value = mock_product
        self.mock_calendar.todos.return_value = []  # Empty after removing
        
        with patch('builtins.hasattr', side_effect=mock_hasattr):
            groceries = TomGroceries(self.config, None)
            result = groceries.remove('product-uid-1')
        
        # Verify product was found and deleted
        self.mock_calendar.todo_by_uid.assert_called_with('product-uid-1')
        mock_product.delete.assert_called_once()
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'product removed.')
        
        # Verify logging
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        self.assertIn("has been removed from grocery list", call_args[0][0])
        self.assertEqual(call_args[1]['module_name'], 'groceries')
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    @patch('tomgroceries.Todo')
    @patch('tomgroceries.iCalendar')
    def test_add_product_basic(self, mock_icalendar, mock_todo_class, mock_logger, mock_dav_client):
        """Test adding a basic product"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock Todo and Calendar creation
        mock_todo = MagicMock()
        mock_todo_class.return_value = mock_todo
        mock_cal = MagicMock()
        mock_icalendar.return_value = mock_cal
        mock_cal.to_ical.return_value = b'ical_content'
        
        # Mock updated products after creation
        self.mock_calendar.todos.return_value = []
        
        groceries = TomGroceries(self.config, None)
        
        result = groceries.add('Apples')
        
        # Verify todo creation
        mock_todo.add.assert_called_once_with('summary', 'Apples')
        mock_cal.add_component.assert_called_with(mock_todo)
        self.mock_calendar.save_event.assert_called_with('ical_content')
        
        # Verify response
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'product added.')
        
        # Verify logging
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        self.assertIn("has been added to grocery list", call_args[0][0])
        self.assertEqual(call_args[1]['module_name'], 'groceries')
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    @patch('tomgroceries.Todo')
    @patch('tomgroceries.iCalendar')
    def test_add_product_with_error(self, mock_icalendar, mock_todo_class, mock_logger, mock_dav_client):
        """Test adding a product when save fails"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock Todo and Calendar creation
        mock_todo = MagicMock()
        mock_todo_class.return_value = mock_todo
        mock_cal = MagicMock()
        mock_icalendar.return_value = mock_cal
        mock_cal.to_ical.return_value = b'ical_content'
        
        # Mock save failure
        self.mock_calendar.save_event.side_effect = Exception("Save failed")
        
        groceries = TomGroceries(self.config, None)
        
        result = groceries.add('Bananas')
        
        # Verify response indicates error
        self.assertEqual(result['status'], 'error')
        self.assertIn('Failed to add product', result['message'])
        
        # Verify error was logged
        mock_logger.error.assert_called()
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_tools_structure(self, mock_logger, mock_dav_client):
        """Test that tools are properly structured"""
        mock_dav_client.return_value = self.mock_client
        
        groceries = TomGroceries(self.config, None)
        
        self.assertIsInstance(groceries.tools, list)
        self.assertEqual(len(groceries.tools), 3)
        
        expected_functions = ['grocery_list_content', 'grocery_list_add', 'grocery_list_remove']
        
        for i, tool in enumerate(groceries.tools):
            self.assertEqual(tool['type'], 'function')
            self.assertIn('function', tool)
            self.assertEqual(tool['function']['name'], expected_functions[i])
            self.assertIn('description', tool['function'])
            self.assertIn('parameters', tool['function'])
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_functions_structure(self, mock_logger, mock_dav_client):
        """Test that functions are properly structured"""
        mock_dav_client.return_value = self.mock_client
        
        groceries = TomGroceries(self.config, None)
        
        expected_functions = ['grocery_list_content', 'grocery_list_add', 'grocery_list_remove']
        
        for func_name in expected_functions:
            self.assertIn(func_name, groceries.functions)
            self.assertIn('function', groceries.functions[func_name])
            self.assertTrue(callable(groceries.functions[func_name]['function']))
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_config_attributes(self, mock_logger, mock_dav_client):
        """Test that configuration attributes are set correctly"""
        mock_dav_client.return_value = self.mock_client
        
        groceries = TomGroceries(self.config, None)
        
        self.assertEqual(groceries.date_format, "%Y-%m-%d %H:%M:%S")
        self.assertEqual(groceries.complexity, 0)
        self.assertEqual(groceries.systemContext, "")
        self.assertIsInstance(groceries.groceryList, list)
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_calendar_selection(self, mock_logger, mock_dav_client):
        """Test calendar selection logic"""
        mock_dav_client.return_value = self.mock_client
        
        # Create multiple calendars with different names
        mock_cal1 = MagicMock()
        mock_cal1.get_properties.return_value = {'{DAV:}displayname': 'OtherCalendar'}
        
        mock_cal2 = MagicMock()
        mock_cal2.get_properties.return_value = {
            '{DAV:}displayname': 'Courses',
            '{urn:ietf:params:xml:ns:caldav}calendar-timezone': 'some_tz'  # This should be skipped
        }
        
        mock_cal3 = MagicMock()
        mock_cal3.get_properties.return_value = {'{DAV:}displayname': 'Courses'}
        mock_cal3.todos.return_value = []
        
        def mock_get_properties_cal3(props=None):
            if props:
                return {'{DAV:}displayname': 'Courses'}
            return {'{DAV:}displayname': 'Courses'}
        
        mock_cal3.get_properties = mock_get_properties_cal3
        
        self.mock_principal.calendars.return_value = [mock_cal1, mock_cal2, mock_cal3]
        
        groceries = TomGroceries(self.config, None)
        
        # Should select mock_cal3 (Courses without calendar-timezone)
        self.assertEqual(groceries.groceryCal, mock_cal3)
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_update_with_server_error(self, mock_logger, mock_dav_client):
        """Test update method when server returns error"""
        mock_dav_client.return_value = self.mock_client
        
        # Mock todos() method to raise exception after init
        groceries = TomGroceries(self.config, None)
        
        # Now mock exception for subsequent update calls
        self.mock_calendar.todos.side_effect = Exception("Server connection lost")
        
        groceries.update()
        
        # Should handle exception gracefully and set empty list
        self.assertEqual(groceries.groceryList, [])
        
        # Verify error was logged
        mock_logger.error.assert_called()

if __name__ == '__main__':
    unittest.main()