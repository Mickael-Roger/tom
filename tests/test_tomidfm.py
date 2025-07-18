import unittest
from unittest.mock import patch, MagicMock, call
import sys
import os
import sqlite3
import tempfile
from datetime import datetime
import json

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'core_modules'))

# Mock the logger before importing tomidfm
with patch('tomidfm.logger') as mock_logger:
    from tomidfm import TomIdfm

class TestTomIdfm(unittest.TestCase):
    
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        
        self.config = {
            'token': 'test_token',
            'cache_db': self.temp_db.name
        }
        self.llm = MagicMock()
        
        # Reset class variable for testing
        TomIdfm._already_updated = False
        
        # Create a mock for the initial data update and logger
        with patch('tomidfm.requests.get') as mock_get, \
             patch('tomidfm.logger') as mock_logger:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = []
            mock_get.return_value = mock_response
            
            self.idfm = TomIdfm(self.config, self.llm)
    
    def tearDown(self):
        try:
            os.unlink(self.temp_db.name)
        except:
            pass
    
    def test_date_to_idfm_valid_date(self):
        """Test date_to_idfm with valid date string"""
        result = self.idfm.date_to_idfm("2024-01-15 14:30:00")
        self.assertEqual(result, "20240115T143000")
    
    def test_date_to_idfm_edge_cases(self):
        """Test date_to_idfm with edge cases"""
        result = self.idfm.date_to_idfm("2024-12-31 23:59:59")
        self.assertEqual(result, "20241231T235959")
        
        result = self.idfm.date_to_idfm("2024-01-01 00:00:00")
        self.assertEqual(result, "20240101T000000")
    
    def test_date_from_idfm_valid_date(self):
        """Test date_from_idfm with valid IDFM date string"""
        result = self.idfm.date_from_idfm("20240115T143000")
        self.assertEqual(result, "2024-01-15 14:30:00")
    
    def test_date_from_idfm_edge_cases(self):
        """Test date_from_idfm with edge cases"""
        result = self.idfm.date_from_idfm("20241231T235959")
        self.assertEqual(result, "2024-12-31 23:59:59")
        
        result = self.idfm.date_from_idfm("20240101T000000")
        self.assertEqual(result, "2024-01-01 00:00:00")
    
    def test_date_conversion_roundtrip(self):
        """Test that date conversion is reversible"""
        original_date = "2024-06-15 10:45:30"
        idfm_date = self.idfm.date_to_idfm(original_date)
        converted_back = self.idfm.date_from_idfm(idfm_date)
        self.assertEqual(original_date, converted_back)
    
    @patch('tomidfm.requests.get')
    def test_get_city_success(self, mock_get):
        """Test get_city with successful API response"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'features': [
                {
                    'properties': {
                        'city': 'Paris'
                    }
                }
            ]
        }
        mock_get.return_value = mock_response
        
        result = self.idfm.get_city(48.8566, 2.3522)
        
        self.assertEqual(result, 'Paris')
        mock_get.assert_called_once_with(
            'https://api-adresse.data.gouv.fr/reverse/?lon=2.3522&lat=48.8566&limit=1'
        )
    
    @patch('tomidfm.requests.get')
    def test_get_city_no_features(self, mock_get):
        """Test get_city with empty features"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'features': []}
        mock_get.return_value = mock_response
        
        result = self.idfm.get_city(48.8566, 2.3522)
        
        self.assertEqual(result, "")
    
    @patch('tomidfm.requests.get')
    def test_get_city_api_error(self, mock_get):
        """Test get_city with API error"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        result = self.idfm.get_city(48.8566, 2.3522)
        
        self.assertFalse(result)
    
    @patch('tomidfm.TomIdfm.apiCall')
    def test_search_station_success(self, mock_api_call):
        """Test search_station with successful API response"""
        # Setup database with test data
        conn = sqlite3.connect(self.temp_db.name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO stations (id, name, latitude, longitude, city) VALUES (?, ?, ?, ?, ?)', 
                      ('12345', 'Châtelet', 48.8585, 2.3475, 'Paris'))
        cursor.execute('INSERT INTO lines (id, name, commercial_name, type) VALUES (?, ?, ?, ?)', 
                      ('M1', '1', 'Métro 1', 'METRO'))
        cursor.execute('INSERT INTO station_line (line_id, station_id) VALUES (?, ?)', 
                      ('M1', '12345'))
        conn.commit()
        conn.close()
        
        mock_api_call.return_value = {
            'places': [
                {
                    'id': 'stop_area:IDFM:12345',
                    'stop_area': {
                        'name': 'Châtelet'
                    }
                }
            ]
        }
        
        result = self.idfm.search_station("Châtelet")
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['station_id'], '12345')
        self.assertEqual(result[0]['station_name'], 'Châtelet')
        self.assertEqual(len(result[0]['lines']), 1)
        self.assertEqual(result[0]['lines'][0]['line_id'], 'M1')
        self.assertEqual(result[0]['lines'][0]['line_name'], 'Métro 1')
    
    @patch('tomidfm.TomIdfm.apiCall')
    def test_search_station_api_error(self, mock_api_call):
        """Test search_station with API error"""
        mock_api_call.return_value = False
        
        result = self.idfm.search_station("InvalidStation")
        
        self.assertFalse(result)
    
    @patch('tomidfm.TomIdfm.apiCall')
    def test_search_place_gps_success(self, mock_api_call):
        """Test search_place_gps with successful API response"""
        mock_api_call.return_value = {
            'places': [
                {
                    'name': 'Tour Eiffel',
                    'embedded_type': 'poi',
                    'poi': {
                        'poi_type': {'name': 'Monument'},
                        'coord': {'lat': 48.8584, 'lon': 2.2945},
                        'administrative_regions': [
                            {'level': 8, 'name': 'Paris'}
                        ]
                    }
                },
                {
                    'name': '1 Rue de la Paix',
                    'embedded_type': 'address',
                    'address': {
                        'coord': {'lat': 48.8698, 'lon': 2.3316},
                        'administrative_regions': [
                            {'level': 8, 'name': 'Paris'}
                        ]
                    }
                }
            ]
        }
        
        result = self.idfm.search_place_gps("Tour Eiffel")
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['place_name'], 'Tour Eiffel')
        self.assertEqual(result[0]['place_type'], 'Monument')
        self.assertEqual(result[0]['city'], 'Paris')
        self.assertEqual(result[0]['gps_lat'], 48.8584)
        self.assertEqual(result[0]['gps_lon'], 2.2945)
        
        self.assertEqual(result[1]['place_name'], '1 Rue de la Paix')
        self.assertEqual(result[1]['place_type'], 'address')
        self.assertEqual(result[1]['city'], 'Paris')
    
    @patch('tomidfm.TomIdfm.apiCall')
    def test_search_place_gps_api_error(self, mock_api_call):
        """Test search_place_gps with API error"""
        mock_api_call.return_value = False
        
        result = self.idfm.search_place_gps("InvalidPlace")
        
        self.assertFalse(result)
    
    def test_list_stations_success(self):
        """Test list_stations with valid database data"""
        # Setup database with test data
        conn = sqlite3.connect(self.temp_db.name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO stations (id, name, latitude, longitude, city) VALUES (?, ?, ?, ?, ?)', 
                      ('12345', 'Châtelet', 48.8585, 2.3475, 'Paris'))
        cursor.execute('INSERT INTO stations (id, name, latitude, longitude, city) VALUES (?, ?, ?, ?, ?)', 
                      ('67890', 'Gare du Nord', 48.8809, 2.3553, 'Paris'))
        conn.commit()
        conn.close()
        
        result = self.idfm.list_stations()
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['station_id'], '12345')
        self.assertEqual(result[0]['station_name'], 'Châtelet')
        self.assertEqual(result[0]['station_city'], 'Paris')
        self.assertEqual(result[1]['station_id'], '67890')
        self.assertEqual(result[1]['station_name'], 'Gare du Nord')
    
    def test_list_stations_empty_db(self):
        """Test list_stations with empty database"""
        result = self.idfm.list_stations()
        
        self.assertEqual(result, [])
    
    def test_list_lines_success(self):
        """Test list_lines with valid database data"""
        # Setup database with test data
        conn = sqlite3.connect(self.temp_db.name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO lines (id, name, commercial_name, type) VALUES (?, ?, ?, ?)', 
                      ('M1', '1', 'Métro 1', 'METRO'))
        cursor.execute('INSERT INTO lines (id, name, commercial_name, type) VALUES (?, ?, ?, ?)', 
                      ('RER_A', 'A', 'RER A', 'TRAIN'))
        conn.commit()
        conn.close()
        
        result = self.idfm.list_lines()
        
        self.assertEqual(len(result), 2)
        # Note: The function returns the raw database result, not the processed list
        self.assertEqual(result[0][0], 'M1')
        self.assertEqual(result[0][1], 'Métro 1')
        self.assertEqual(result[0][2], 'METRO')
    
    def test_list_lines_empty_db(self):
        """Test list_lines with empty database"""
        result = self.idfm.list_lines()
        
        self.assertEqual(result, [])
    
    @patch('tomidfm.logger')
    @patch('tomidfm.TomIdfm.apiCall')
    def test_journey_success(self, mock_api_call, mock_logger):
        """Test journey with successful API response"""
        mock_api_call.return_value = {
            'journeys': [
                {
                    'duration': 1800,
                    'nb_transfers': 1,
                    'departure_date_time': '20240115T143000',
                    'arrival_date_time': '20240115T150000',
                    'sections': [
                        {
                            'type': 'public_transport',
                            'duration': 900,
                            'departure_date_time': '20240115T143000',
                            'arrival_date_time': '20240115T144500',
                            'from': {'name': 'Châtelet'},
                            'to': {'name': 'République'},
                            'display_informations': {
                                'physical_mode': 'Métro',
                                'label': 'Ligne 1'
                            },
                            'best_boarding_positions': ['Milieu']
                        },
                        {
                            'type': 'waiting',
                            'duration': 300
                        }
                    ]
                }
            ]
        }
        
        result = self.idfm.journey("2024-01-15 14:30:00", "12345", "67890")
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['route_id'], 0)
        self.assertEqual(result[0]['duration_in_seconds'], 1800)
        self.assertEqual(result[0]['nb_transfers'], 1)
        self.assertEqual(result[0]['departure_datetime'], '2024-01-15 14:30:00')
        self.assertEqual(result[0]['arrival_datetime'], '2024-01-15 15:00:00')
        
        sections = result[0]['sections']
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0]['section_type'], 'Métro Ligne 1')
        self.assertEqual(sections[0]['section_from'], 'Châtelet')
        self.assertEqual(sections[0]['section_to'], 'République')
        self.assertEqual(sections[0]['section_best_boarding_position'], 'Milieu')
        self.assertEqual(sections[1]['section_type'], 'waiting')
        self.assertEqual(sections[1]['section_duration_in_seconds'], 300)
    
    @patch('tomidfm.logger')
    @patch('tomidfm.TomIdfm.apiCall')
    def test_journey_with_gps_coordinates(self, mock_api_call, mock_logger):
        """Test journey with GPS coordinates"""
        mock_api_call.return_value = {'journeys': []}
        
        self.idfm.journey("2024-01-15 14:30:00", "2.3522;48.8566", "2.3316;48.8698")
        
        # Check that GPS coordinates are passed as-is
        mock_api_call.assert_called_once_with(
            "/journeys", 
            params={
                "from": "2.3522;48.8566",
                "to": "2.3316;48.8698",
                "datetime": "20240115T143000",
                "datetime_represents": "departure"
            }
        )
    
    @patch('tomidfm.logger')
    @patch('tomidfm.TomIdfm.apiCall')
    def test_journey_with_station_ids(self, mock_api_call, mock_logger):
        """Test journey with station IDs"""
        mock_api_call.return_value = {'journeys': []}
        
        self.idfm.journey("2024-01-15 14:30:00", "12345", "67890")
        
        # Check that station IDs are prefixed with stop_area:IDFM:
        mock_api_call.assert_called_once_with(
            "/journeys", 
            params={
                "from": "stop_area:IDFM:12345",
                "to": "stop_area:IDFM:67890",
                "datetime": "20240115T143000",
                "datetime_represents": "departure"
            }
        )
    
    @patch('tomidfm.TomIdfm.apiCall')
    def test_journey_api_error(self, mock_api_call):
        """Test journey with API error"""
        mock_api_call.return_value = False
        
        result = self.idfm.journey("2024-01-15 14:30:00", "12345", "67890")
        
        self.assertFalse(result)
    
    @patch('tomidfm.logger')
    @patch('tomidfm.TomIdfm.apiCall')
    def test_keep_route_and_retrieve(self, mock_api_call, mock_logger):
        """Test keep_route and retreive_keeped_route functions"""
        # First create a journey
        mock_api_call.return_value = {
            'journeys': [
                {
                    'duration': 1800,
                    'nb_transfers': 1,
                    'departure_date_time': '20240115T143000',
                    'arrival_date_time': '20240115T150000',
                    'sections': []
                }
            ]
        }
        
        self.idfm.journey("2024-01-15 14:30:00", "12345", "67890")
        
        # Keep the route
        result = self.idfm.keep_route(0)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['message'], 'Route kept')
        
        # Retrieve the kept route
        kept_route = self.idfm.retreive_keeped_route()
        
        self.assertEqual(kept_route['route_id'], 0)
        self.assertEqual(kept_route['duration_in_seconds'], 1800)
        self.assertEqual(kept_route['nb_transfers'], 1)
    
    @patch('tomidfm.requests.get')
    def test_apiCall_success(self, mock_get):
        """Test apiCall with successful response"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'test': 'data'}
        mock_get.return_value = mock_response
        
        result = self.idfm.apiCall("/test", params={'param': 'value'})
        
        self.assertEqual(result, {'test': 'data'})
        mock_get.assert_called_once_with(
            'https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia/test',
            headers={'apiKey': 'test_token', 'accept': 'application/json'},
            params={'param': 'value'}
        )
    
    @patch('tomidfm.logger')
    @patch('tomidfm.requests.get')
    def test_apiCall_error(self, mock_get, mock_logger):
        """Test apiCall with error response"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = 'Not Found'
        mock_get.return_value = mock_response
        
        result = self.idfm.apiCall("/test")
        
        self.assertFalse(result)
    
    @patch('tomidfm.logger')
    @patch('tomidfm.TomIdfm.apiCall')
    def test_disruption_success(self, mock_api_call, mock_logger):
        """Test disruption function with successful response"""
        mock_api_call.return_value = {
            'disruptions': [
                {
                    'id': 'disruption_1',
                    'status': 'active',
                    'severity': {'effect': 'REDUCED_SERVICE'}
                }
            ]
        }
        
        # Setup lines attribute (normally this would be set elsewhere)
        self.idfm.lines = {'M1': {'id': 'M1_ID'}}
        
        result = self.idfm.disruption('M1')
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], 'disruption_1')
        mock_api_call.assert_called_once_with('/lines/line:IDFM:M1_ID')
    
    @patch('tomidfm.logger')
    @patch('tomidfm.TomIdfm.apiCall')
    def test_disruption_api_error(self, mock_api_call, mock_logger):
        """Test disruption function with API error"""
        mock_api_call.return_value = False
        
        # Setup lines attribute
        self.idfm.lines = {'M1': {'id': 'M1_ID'}}
        
        result = self.idfm.disruption('M1')
        
        self.assertFalse(result)
    
    def test_tools_structure(self):
        """Test that tools are properly structured"""
        self.assertIsInstance(self.idfm.tools, list)
        self.assertEqual(len(self.idfm.tools), 5)
        
        expected_functions = [
            'search_station',
            'search_place_gps', 
            'plan_a_journey',
            'select_a_route',
            'retreived_current_selected_route'
        ]
        
        for i, tool in enumerate(self.idfm.tools):
            self.assertEqual(tool['type'], 'function')
            self.assertIn('function', tool)
            self.assertEqual(tool['function']['name'], expected_functions[i])
            self.assertIn('description', tool['function'])
            self.assertIn('parameters', tool['function'])
    
    def test_functions_structure(self):
        """Test that functions are properly structured"""
        expected_functions = [
            'search_station',
            'search_place_gps',
            'plan_a_journey',
            'select_a_route',
            'retreived_current_selected_route'
        ]
        
        for func_name in expected_functions:
            self.assertIn(func_name, self.idfm.functions)
            self.assertIn('function', self.idfm.functions[func_name])
            self.assertTrue(callable(self.idfm.functions[func_name]['function']))
    
    def test_config_attributes(self):
        """Test that configuration attributes are set correctly"""
        self.assertEqual(self.idfm.url, "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia")
        self.assertEqual(self.idfm.apiKey, 'test_token')
        self.assertEqual(self.idfm.db, self.temp_db.name)
        self.assertEqual(self.idfm.complexity, 1)
        self.assertEqual(self.idfm.systemContext, "")
        self.assertIsNone(self.idfm.route)
        self.assertEqual(self.idfm.routes, [])

if __name__ == '__main__':
    unittest.main()