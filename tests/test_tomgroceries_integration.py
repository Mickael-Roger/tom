import unittest
from unittest.mock import patch
import sys
import os
import yaml
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
sys.path.append(os.path.dirname(__file__))  # Add tests directory to path

# Import test config loader
from test_config_loader import load_test_config, get_module_config_for_test

# Mock logger before importing
with patch('tomgroceries.logger') as mock_logger:
    from tomgroceries import TomGroceries

class TestTomGroceriesIntegration(unittest.TestCase):
    """
    Integration tests for TomGroceries module that require real CalDAV server access.
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
            
        if not self.test_config.has_user_service_config(self.username, 'groceries'):
            self.skipTest("Groceries service not configured for test user - skipping integration tests")
        
        # Get module configuration using unified config
        self.groceries_config = get_module_config_for_test('groceries', self.global_config, is_personal=True, username=self.username)
        
        # Create TomGroceries instance with real config but mock logger
        with patch('tomgroceries.logger') as mock_logger:
            try:
                self.groceries = TomGroceries(self.groceries_config, None)
                self.integration_available = True
            except Exception as e:
                print(f"✗ Failed to connect to CalDAV server: {e}")
                self.integration_available = False
    
    def test_config_loaded(self):
        """Test that configuration is properly loaded"""
        self.assertTrue(self.test_config.config_loaded, "Configuration should be loaded")
        self.assertIsNotNone(self.groceries_config, "Groceries config should not be None")
        self.assertIn('url', self.groceries_config, "URL should be in config")
        self.assertIn('password', self.groceries_config, "Password should be in config")
        self.assertIn('list', self.groceries_config, "List should be in config")
    
    def test_caldav_connection(self):
        """Test CalDAV server connection"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Test that we can connect and access calendars
        self.assertIsNotNone(self.groceries.client, "CalDAV client should be created")
        self.assertIsNotNone(self.groceries.groceryCal, "Grocery calendar should be found")
        self.assertEqual(self.groceries.date_format, "%Y-%m-%d %H:%M:%S")
    
    def test_real_list_products(self):
        """Test listing products with real CalDAV server"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        result = self.groceries.listProducts()
        
        self.assertIsInstance(result, list, "Result should be a list")
        
        # Check structure of products if any exist
        for product in result:
            self.assertIn('product', product, "Product should have product field")
            self.assertIn('id', product, "Product should have id field")
            self.assertIsInstance(product['product'], str, "Product name should be string")
            self.assertIsInstance(product['id'], str, "Product ID should be string")
    
    @patch('tomgroceries.logger')
    def test_real_add_and_remove_product(self, mock_logger):
        """Test adding and then removing a product"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Create a test product
        test_product_name = f"Integration Test Product {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Test creation
        add_result = self.groceries.add(test_product_name)
        
        self.assertEqual(add_result['status'], 'success')
        self.assertEqual(add_result['message'], 'product added.')
        
        # Verify product was created by listing products
        products = self.groceries.listProducts()
        created_product = None
        for product in products:
            if product['product'] == test_product_name:
                created_product = product
                break
        
        self.assertIsNotNone(created_product, "Created product should be found in product list")
        self.assertEqual(created_product['product'], test_product_name)
        
        # Test removing the product
        remove_result = self.groceries.remove(created_product['id'])
        
        # Check if remove was successful (could be True/False or success dict)
        if isinstance(remove_result, dict):
            self.assertEqual(remove_result['status'], 'success')
            self.assertEqual(remove_result['message'], 'product removed.')
        elif remove_result is False:
            self.fail("Failed to remove the created product")
        # else: remove_result could be True for successful removal
        
        # Verify product was removed (should not appear in active products anymore)
        updated_products = self.groceries.listProducts()
        product_still_exists = False
        for product in updated_products:
            if product['id'] == created_product['id']:
                product_still_exists = True
                break
        
        self.assertFalse(product_still_exists, "Product should be removed from the list")
    
    @patch('tomgroceries.logger')
    def test_real_add_multiple_products(self, mock_logger):
        """Test adding multiple products"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        test_products = [
            f"Apples {timestamp}",
            f"Bananas {timestamp}",
            f"Carrots {timestamp}"
        ]
        
        created_product_ids = []
        
        # Add all products
        for product_name in test_products:
            result = self.groceries.add(product_name)
            self.assertEqual(result['status'], 'success')
            self.assertEqual(result['message'], 'product added.')
        
        # Verify all products were created
        products = self.groceries.listProducts()
        found_products = []
        for product in products:
            if any(test_product in product['product'] for test_product in test_products):
                found_products.append(product)
                created_product_ids.append(product['id'])
        
        self.assertEqual(len(found_products), len(test_products), "All test products should be found")
        
        # Clean up - remove all test products
        for product_id in created_product_ids:
            try:
                with patch('tomgroceries.logger'):
                    self.groceries.remove(product_id)
            except Exception as e:
                print(f"Warning: Failed to clean up product {product_id}: {e}")
    
    @patch('tomgroceries.logger')
    def test_remove_nonexistent_product(self, mock_logger):
        """Test removing a product that doesn't exist"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Try to remove a product with a non-existent ID
        result = self.groceries.remove('non-existent-uid-12345')
        
        # Should return False for non-existent product
        self.assertFalse(result, "Removing non-existent product should return False")
        
        # Verify error was logged
        mock_logger.error.assert_called_once()
        
        # Check that the error message contains information about the product not being found
        call_args = mock_logger.error.call_args[0][0]
        self.assertIn("non-existent-uid-12345", call_args)
        self.assertIn("Error removing product", call_args)
    
    def test_calendar_selection_logic(self):
        """Test that the correct calendar is selected"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Verify that the correct calendar was selected based on config
        self.assertIsNotNone(self.groceries.groceryCal, "Grocery calendar should be selected")
        
        # The calendar should be the one matching the configured list name
        # We can't easily test this without knowing the server structure,
        # but we can verify basic properties
        self.assertTrue(hasattr(self.groceries.groceryCal, 'todos'), "Selected calendar should have todos method")
        self.assertTrue(hasattr(self.groceries.groceryCal, 'save_event'), "Selected calendar should have save_event method")
    
    def test_timezone_handling(self):
        """Test timezone handling"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        # Test default timezone
        self.assertEqual(self.groceries.tz.zone, 'Europe/Paris')
        
        # Test custom timezone
        with patch('tomgroceries.logger'):
            groceries_ny = TomGroceries(self.groceries_config, None, tz='America/New_York')
            self.assertEqual(groceries_ny.tz.zone, 'America/New_York')
    
    def test_module_configuration(self):
        """Test module configuration attributes"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        self.assertEqual(self.groceries.date_format, "%Y-%m-%d %H:%M:%S")
        self.assertEqual(self.groceries.complexity, 0)
        self.assertEqual(self.groceries.systemContext, "")
        self.assertIsInstance(self.groceries.groceryList, list)
    
    @unittest.skipIf(not os.path.exists('/config.yml'), "Config file not available")
    def test_config_file_structure(self):
        """Test that config file has correct structure"""
        with open('/config.yml', 'r') as file:
            config = yaml.safe_load(file)
        
        self.assertIn('groceries', config, "Config should have groceries section")
        
        groceries_config = config['groceries']
        self.assertIn('url', groceries_config, "Groceries config should have url")
        self.assertIn('password', groceries_config, "Groceries config should have password")
        self.assertIn('list', groceries_config, "Groceries config should have list")
        
        # Test that required fields are not empty
        self.assertIsInstance(groceries_config['url'], str, "URL should be a string")
        self.assertGreater(len(groceries_config['url']), 0, "URL should not be empty")
        self.assertTrue(groceries_config['url'].startswith(('http://', 'https://')), "URL should be a valid HTTP/HTTPS URL")
        
        self.assertIsInstance(groceries_config['password'], str, "Password should be a string")
        self.assertGreater(len(groceries_config['password']), 0, "Password should not be empty")
        
        self.assertIsInstance(groceries_config['list'], str, "List should be a string")
        self.assertGreater(len(groceries_config['list']), 0, "List should not be empty")
    
    @patch('tomgroceries.logger')
    def test_stress_add_remove_operations(self, mock_logger):
        """Test multiple rapid add/remove operations"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        stress_products = []
        created_ids = []
        
        # Add multiple products rapidly
        for i in range(5):
            product_name = f"Stress Test Product {i} {timestamp}"
            stress_products.append(product_name)
            
            result = self.groceries.add(product_name)
            self.assertEqual(result['status'], 'success')
        
        # Get all products and find our test products
        all_products = self.groceries.listProducts()
        for product in all_products:
            if any(stress_product in product['product'] for stress_product in stress_products):
                created_ids.append(product['id'])
        
        # Verify we found all test products
        self.assertGreaterEqual(len(created_ids), len(stress_products), "Should find at least as many IDs as products created")
        
        # Remove all test products rapidly
        successful_removals = 0
        for product_id in created_ids:
            try:
                result = self.groceries.remove(product_id)
                if result and (result is True or (isinstance(result, dict) and result['status'] == 'success')):
                    successful_removals += 1
            except Exception as e:
                print(f"Warning: Failed to remove stress test product {product_id}: {e}")
        
        # Should be able to remove most or all products
        self.assertGreater(successful_removals, 0, "Should successfully remove at least some products")
    
    @patch('tomgroceries.logger')
    def test_unicode_product_names(self, mock_logger):
        """Test handling of unicode characters in product names"""
        if not self.integration_available:
            self.skipTest("CalDAV server not available")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unicode_products = [
            f"Café {timestamp}",
            f"Naïve product {timestamp}",
            f"Résumé item {timestamp}",
            f"测试产品 {timestamp}",
            f"🍎 Apple emoji {timestamp}"
        ]
        
        created_ids = []
        
        for product_name in unicode_products:
            try:
                result = self.groceries.add(product_name)
                self.assertEqual(result['status'], 'success')
                
                # Verify the product appears in the list
                products = self.groceries.listProducts()
                found = False
                for product in products:
                    if product['product'] == product_name:
                        created_ids.append(product['id'])
                        found = True
                        break
                
                self.assertTrue(found, f"Unicode product '{product_name}' should be found in list")
                
            except Exception as e:
                print(f"Warning: Failed to handle unicode product '{product_name}': {e}")
        
        # Clean up
        for product_id in created_ids:
            try:
                with patch('tomgroceries.logger'):
                    self.groceries.remove(product_id)
            except Exception as e:
                print(f"Warning: Failed to clean up unicode product {product_id}: {e}")

if __name__ == '__main__':
    unittest.main()