import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))

# Mock logger before importing
with patch('tomgroceries.logger') as mock_logger:
    from tomgroceries import TomGroceries

class TestTomGroceriesRobustness(unittest.TestCase):
    """
    Robustness tests for TomGroceries module that test error handling
    and edge cases without requiring a real CalDAV server.
    """
    
    def setUp(self):
        self.config = {
            'url': 'https://test.example.com/dav/',
            'user': 'testuser',
            'password': 'testpass',
            'list': 'Courses'
        }
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_init_with_connection_error(self, mock_logger, mock_dav_client):
        """Test initialization when CalDAV server is unreachable"""
        # Mock connection failure
        mock_dav_client.side_effect = Exception("Connection failed")
        
        with self.assertRaises(Exception):
            TomGroceries(self.config, None)
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_remove_with_caldav_not_found_error(self, mock_logger, mock_dav_client):
        """Test removing product with CalDAV NotFoundError"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Courses'}
        mock_calendar.todos.return_value = []
        
        # Mock NotFoundError when searching for product
        from caldav.lib.error import NotFoundError
        mock_calendar.todo_by_uid.side_effect = NotFoundError("Product not found")
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        groceries = TomGroceries(self.config, None)
        
        result = groceries.remove('non-existent-product')
        
        # Should return False and log error
        self.assertFalse(result)
        mock_logger.error.assert_called_once()
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_remove_with_generic_exception(self, mock_logger, mock_dav_client):
        """Test removing product with generic exception"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Courses'}
        mock_calendar.todos.return_value = []
        
        # Mock generic exception
        mock_calendar.todo_by_uid.side_effect = Exception("Server error")
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        groceries = TomGroceries(self.config, None)
        
        result = groceries.remove('some-product-id')
        
        # Should return False and log error
        self.assertFalse(result)
        mock_logger.error.assert_called_once()
        
        # Check error message contains product ID
        call_args = mock_logger.error.call_args[0][0]
        self.assertIn('some-product-id', call_args)
        self.assertIn('Server error', call_args)
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_remove_with_product_delete_error(self, mock_logger, mock_dav_client):
        """Test removing product when delete operation fails"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        mock_product = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Courses'}
        mock_calendar.todos.return_value = []
        mock_calendar.todo_by_uid.return_value = mock_product
        
        # Mock product with icalendar_component
        mock_product.icalendar_component.get.return_value = 'Test Product'
        
        # Mock delete failure
        mock_product.delete.side_effect = Exception("Delete failed")
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        groceries = TomGroceries(self.config, None)
        
        result = groceries.remove('product-id')
        
        # Should return False and log error
        self.assertFalse(result)
        mock_logger.error.assert_called_once()
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_add_with_save_event_error(self, mock_logger, mock_dav_client):
        """Test adding product when save_event operation fails"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Courses'}
        mock_calendar.todos.return_value = []
        
        # Mock save_event failure
        mock_calendar.save_event.side_effect = Exception("Save failed")
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        with patch('tomgroceries.Todo') as mock_todo_class, \
             patch('tomgroceries.iCalendar') as mock_icalendar:
            
            mock_todo = MagicMock()
            mock_todo_class.return_value = mock_todo
            mock_cal = MagicMock()
            mock_icalendar.return_value = mock_cal
            mock_cal.to_ical.return_value = b'ical_content'
            
            groceries = TomGroceries(self.config, None)
            
            result = groceries.add('Test Product')
            
            # Should return error status and log error
            self.assertEqual(result['status'], 'error')
            self.assertIn('Failed to add product', result['message'])
            mock_logger.error.assert_called_once()
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_update_with_server_error(self, mock_logger, mock_dav_client):
        """Test update method when server returns error"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Courses'}
        
        # Mock initial todos() call to succeed, then fail on subsequent calls
        mock_calendar.todos.return_value = []  # First call succeeds
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        # Create instance successfully
        groceries = TomGroceries(self.config, None)
        
        # Now mock exception for subsequent update calls
        mock_calendar.todos.side_effect = Exception("Server connection lost")
        
        # This should handle the exception gracefully
        groceries.update()
        
        # Should set empty list and log error
        self.assertEqual(groceries.groceryList, [])
        mock_logger.error.assert_called_once()
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
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
        
        # Should not find the specified list, groceryCal should not be set
        # update() will catch the AttributeError and handle it gracefully
        groceries = TomGroceries(self.config, None)
        
        # Should set empty list due to AttributeError in update() and log error
        self.assertEqual(groceries.groceryList, [])
        mock_logger.error.assert_called_once()
        
        # Verify groceryCal was not set
        self.assertFalse(hasattr(groceries, 'groceryCal'))
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_list_products_with_malformed_product(self, mock_logger, mock_dav_client):
        """Test listing products when one product has malformed data"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Courses'}
        
        # Mock one good product and one malformed product
        mock_good_product = MagicMock()
        mock_good_product.icalendar_component.get.side_effect = lambda key: {
            'summary': 'Good Product',
            'uid': 'good-uid'
        }.get(key)
        
        mock_bad_product = MagicMock()
        # Make the bad product raise exception when accessing component
        mock_bad_product.icalendar_component.get.side_effect = Exception("Malformed data")
        
        mock_calendar.todos.return_value = [mock_good_product, mock_bad_product]
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        # Should handle malformed product gracefully - update() has error handling
        groceries = TomGroceries(self.config, None)
        
        # Should set empty list due to error handling and log error
        self.assertEqual(groceries.groceryList, [])
        mock_logger.error.assert_called_once()
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_empty_product_name(self, mock_logger, mock_dav_client):
        """Test adding product with empty name"""
        # Setup mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Courses'}
        mock_calendar.todos.return_value = []
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        with patch('tomgroceries.Todo') as mock_todo_class, \
             patch('tomgroceries.iCalendar') as mock_icalendar:
            
            mock_todo = MagicMock()
            mock_todo_class.return_value = mock_todo
            mock_cal = MagicMock()
            mock_icalendar.return_value = mock_cal
            mock_cal.to_ical.return_value = b'ical_content'
            
            groceries = TomGroceries(self.config, None)
            
            # Should handle empty product name
            result = groceries.add('')
            self.assertEqual(result['status'], 'success')
            
            # Verify summary was set (even if empty)
            mock_todo.add.assert_called_with('summary', '')
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_invalid_config_missing_password(self, mock_logger, mock_dav_client):
        """Test initialization with missing password in config"""
        mock_client = MagicMock()
        mock_dav_client.return_value = mock_client
        
        invalid_config = {
            'url': 'https://test.example.com/dav/',
            'user': 'testuser',
            'list': 'Courses'
            # Missing password
        }
        
        with self.assertRaises(KeyError):
            TomGroceries(invalid_config, None)
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_invalid_config_missing_url(self, mock_logger, mock_dav_client):
        """Test initialization with missing URL in config"""
        mock_client = MagicMock()
        mock_dav_client.return_value = mock_client
        
        invalid_config = {
            'user': 'testuser',
            'password': 'testpass',
            'list': 'Courses'
            # Missing url
        }
        
        with self.assertRaises(KeyError):
            TomGroceries(invalid_config, None)
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_invalid_config_missing_list(self, mock_logger, mock_dav_client):
        """Test initialization with missing list in config"""
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'SomeList'}
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        invalid_config = {
            'url': 'https://test.example.com/dav/',
            'user': 'testuser',
            'password': 'testpass'
            # Missing list
        }
        
        with self.assertRaises(KeyError):
            TomGroceries(invalid_config, None)
    
    @patch('tomgroceries.caldav.DAVClient')
    @patch('tomgroceries.logger')
    def test_network_timeout_during_operations(self, mock_logger, mock_dav_client):
        """Test network timeout during various operations"""
        # Setup basic mocks
        mock_client = MagicMock()
        mock_principal = MagicMock()
        mock_calendar = MagicMock()
        
        mock_calendar.get_properties.return_value = {'{DAV:}displayname': 'Courses'}
        mock_calendar.todos.return_value = []
        
        mock_client.principal.return_value = mock_principal
        mock_principal.calendars.return_value = [mock_calendar]
        mock_dav_client.return_value = mock_client
        
        groceries = TomGroceries(self.config, None)
        
        # Test timeout during list operation
        mock_calendar.todos.side_effect = Exception("Network timeout")
        groceries.listProducts()  # Should handle gracefully due to update() error handling
        
        # Verify error was logged
        mock_logger.error.assert_called()
        
        # Reset for next test
        mock_logger.reset_mock()
        mock_calendar.todos.side_effect = None
        mock_calendar.todos.return_value = []
        
        # Test timeout during remove operation
        mock_calendar.todo_by_uid.side_effect = Exception("Network timeout")
        result = groceries.remove('some-id')
        
        self.assertFalse(result)
        mock_logger.error.assert_called()

if __name__ == '__main__':
    unittest.main()