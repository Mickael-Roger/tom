import unittest
from unittest.mock import patch
import sys
import os
import tempfile
import sqlite3
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))
sys.path.append(os.path.dirname(__file__))  # Add tests directory to path

# Import test config loader
from test_config_loader import load_test_config, skip_if_no_config, get_module_config_for_test

# Mock logger before importing
with patch('tomidfm.logger') as mock_logger:
    from tomidfm import TomIdfm

class TestTomIdfmIntegration(unittest.TestCase):
    """
    Integration tests for TomIdfm module that require real API calls.
    These tests require a valid test configuration with IDFM service configured.
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up class-level resources - load config once"""
        cls.test_config = load_test_config()
        cls.global_config = cls.test_config.get_global_config() or {}
    
    def setUp(self):
        """Set up test fixtures"""
        if not self.test_config.config_loaded:
            self.skipTest("Test configuration not available - skipping integration tests")
            
        if not self.test_config.has_service_config('idfm'):
            self.skipTest("IDFM service not configured - skipping integration tests")
        
        # Reset the class variable for each test
        TomIdfm._already_updated = False
        
        # Get module configuration using unified config
        self.idfm_config = get_module_config_for_test('idfm', self.global_config, is_personal=False)
        
        # Create TomIdfm instance with real config but mock logger
        with patch('tomidfm.logger') as mock_logger:
            self.idfm = TomIdfm(self.idfm_config, None)
        
    def test_config_loaded(self):
        """Test that configuration is properly loaded"""
        self.assertTrue(self.test_config.config_loaded, "Configuration should be loaded")
        self.assertIsNotNone(self.idfm_config, "IDFM config should not be None")
        self.assertIn('token', self.idfm_config, "Token should be in config")
    
    def test_database_initialization(self):
        """Test that database is properly initialized"""
        db_path = self.idfm.db
        self.assertTrue(os.path.exists(db_path), f"Database should exist at {db_path}")
        
        # Check database structure
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check that required tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        required_tables = ['stations', 'lines', 'station_line']
        for table in required_tables:
            self.assertIn(table, tables, f"Table {table} should exist")
        
        conn.close()
    
    def test_real_search_station(self):
        """Test search_station with real API call"""
        # Test with a well-known station
        result = self.idfm.search_station("Châtelet")
        
        self.assertIsNotNone(result, "Result should not be None")
        self.assertIsInstance(result, list, "Result should be a list")
        
        if result:  # If we got results
            self.assertGreater(len(result), 0, "Should find at least one station")
            
            # Check structure of first result
            station = result[0]
            self.assertIn('station_id', station, "Station should have station_id")
            self.assertIn('station_name', station, "Station should have station_name")
            self.assertIn('lines', station, "Station should have lines")
            self.assertIsInstance(station['lines'], list, "Lines should be a list")
    
    def test_real_search_place_gps(self):
        """Test search_place_gps with real API call"""
        # Test with a well-known place
        result = self.idfm.search_place_gps("Tour Eiffel")
        
        self.assertIsNotNone(result, "Result should not be None")
        self.assertIsInstance(result, list, "Result should be a list")
        
        if result:  # If we got results
            self.assertGreater(len(result), 0, "Should find at least one place")
            
            # Check structure of first result
            place = result[0]
            self.assertIn('place_name', place, "Place should have place_name")
            self.assertIn('city', place, "Place should have city")
            self.assertIn('place_type', place, "Place should have place_type")
            self.assertIn('gps_lat', place, "Place should have gps_lat")
            self.assertIn('gps_lon', place, "Place should have gps_lon")
    
    @patch('tomidfm.logger')
    def test_real_journey_planning(self, mock_logger):
        """Test journey planning with real API call"""
        # Get current date/time for the journey
        now = datetime.now()
        journey_time = now.strftime("%Y-%m-%d %H:%M:%S")
        
        # Use well-known station IDs or GPS coordinates
        # These are examples - you may need to adjust based on your database
        departure = "2.3522;48.8566"  # GPS coordinates near Louvre
        arrival = "2.2945;48.8584"    # GPS coordinates near Eiffel Tower
        
        result = self.idfm.journey(journey_time, departure, arrival)
        
        if result is not False:  # API might fail, that's OK for testing
            self.assertIsInstance(result, list, "Result should be a list")
            
            if result:  # If we got journeys
                # Check structure of first journey
                journey = result[0]
                self.assertIn('route_id', journey, "Journey should have route_id")
                self.assertIn('departure_datetime', journey, "Journey should have departure_datetime")
                self.assertIn('arrival_datetime', journey, "Journey should have arrival_datetime")
                self.assertIn('duration_in_seconds', journey, "Journey should have duration_in_seconds")
                self.assertIn('nb_transfers', journey, "Journey should have nb_transfers")
                self.assertIn('sections', journey, "Journey should have sections")
                self.assertIsInstance(journey['sections'], list, "Sections should be a list")
    
    def test_real_get_city(self):
        """Test get_city with real API call"""
        # Test with Paris coordinates
        result = self.idfm.get_city(48.8566, 2.3522)
        
        if result is not False:  # API might fail, that's OK for testing
            self.assertIsInstance(result, str, "Result should be a string")
            self.assertGreater(len(result), 0, "City name should not be empty")
    
    
    def test_list_stations_with_real_data(self):
        """Test list_stations with real database data"""
        result = self.idfm.list_stations()
        
        self.assertIsNotNone(result, "Result should not be None")
        self.assertIsInstance(result, list, "Result should be a list")
        
        # The database might be empty initially, so we just check structure
        if result:
            station = result[0]
            self.assertIn('station_id', station, "Station should have station_id")
            self.assertIn('station_name', station, "Station should have station_name")
            self.assertIn('station_city', station, "Station should have station_city")
    
    def test_list_lines_with_real_data(self):
        """Test list_lines with real database data"""
        result = self.idfm.list_lines()
        
        self.assertIsNotNone(result, "Result should not be None")
        self.assertIsInstance(result, list, "Result should be a list")
        
        # The result format from list_lines is different (returns raw DB result)
        # So we just check it's a list
    
    @patch('tomidfm.logger')
    def test_route_management(self, mock_logger):
        """Test route selection and retrieval"""
        # First, try to plan a journey
        now = datetime.now()
        journey_time = now.strftime("%Y-%m-%d %H:%M:%S")
        
        departure = "2.3522;48.8566"  # GPS coordinates
        arrival = "2.2945;48.8584"    # GPS coordinates
        
        journeys = self.idfm.journey(journey_time, departure, arrival)
        
        if journeys and len(journeys) > 0:
            # Keep the first route
            result = self.idfm.keep_route(0)
            self.assertEqual(result['status'], 'success', "Route should be kept successfully")
            
            # Retrieve the kept route
            kept_route = self.idfm.retreive_keeped_route()
            self.assertIsNotNone(kept_route, "Kept route should not be None")
            self.assertEqual(kept_route['route_id'], 0, "Kept route should have correct ID")
    
    def test_date_conversion_functions(self):
        """Test date conversion functions"""
        test_date = "2024-01-15 14:30:00"
        
        # Test conversion to IDFM format
        idfm_date = self.idfm.date_to_idfm(test_date)
        self.assertEqual(idfm_date, "20240115T143000", "Date conversion to IDFM should be correct")
        
        # Test conversion from IDFM format
        converted_back = self.idfm.date_from_idfm(idfm_date)
        self.assertEqual(converted_back, test_date, "Date conversion from IDFM should be correct")
    
    def test_module_configuration(self):
        """Test module configuration attributes"""
        self.assertEqual(self.idfm.url, "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia")
        self.assertEqual(self.idfm.apiKey, self.idfm_config['token'])
        self.assertEqual(self.idfm.db, self.idfm_config['cache_db'])
        self.assertEqual(self.idfm.complexity, 1)
        self.assertEqual(self.idfm.systemContext, "")
        self.assertIsNone(self.idfm.route)
        self.assertIsInstance(self.idfm.routes, list)
    
    @unittest.skipIf(not os.path.exists('/config.yml'), "Config file not available")
    def test_config_file_structure(self):
        """Test that config file has correct structure"""
        with open('/config.yml', 'r') as file:
            config = yaml.safe_load(file)
        
        self.assertIn('idfm', config, "Config should have idfm section")
        
        idfm_config = config['idfm']
        self.assertIn('token', idfm_config, "IDFM config should have token")
        self.assertIn('cache_db', idfm_config, "IDFM config should have cache_db")
        
        # Test that token is not empty
        self.assertIsInstance(idfm_config['token'], str, "Token should be a string")
        self.assertGreater(len(idfm_config['token']), 0, "Token should not be empty")
        
        # Test that cache_db path is valid
        self.assertIsInstance(idfm_config['cache_db'], str, "Cache DB should be a string")
        self.assertGreater(len(idfm_config['cache_db']), 0, "Cache DB path should not be empty")

if __name__ == '__main__':
    unittest.main()