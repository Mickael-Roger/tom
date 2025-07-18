import unittest
from unittest.mock import patch, MagicMock
import sys
import os
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))
from tomweather import TomWeather

class TestTomWeather(unittest.TestCase):
    
    def setUp(self):
        self.config = {}
        self.llm = MagicMock()
        self.weather = TomWeather(self.config, self.llm)
    
    def test_convertWMO_valid_codes(self):
        """Test convertWMO with valid WMO codes"""
        self.assertEqual(self.weather.convertWMO("0"), "Clear sky")
        self.assertEqual(self.weather.convertWMO("1"), "Mainly clear sky")
        self.assertEqual(self.weather.convertWMO("45"), "Fog")
        self.assertEqual(self.weather.convertWMO("61"), "Slight rain")
        self.assertEqual(self.weather.convertWMO("95"), "Slight or moderate thunderstorm")
        self.assertEqual(self.weather.convertWMO("99"), "Thunderstorm with heavy hail")
    
    def test_convertWMO_invalid_codes(self):
        """Test convertWMO with invalid WMO codes"""
        self.assertIsNone(self.weather.convertWMO("invalid"))
        self.assertIsNone(self.weather.convertWMO("100"))
        self.assertIsNone(self.weather.convertWMO(""))
        self.assertIsNone(self.weather.convertWMO("999"))
    
    def test_convertWMO_edge_cases(self):
        """Test convertWMO with edge cases"""
        self.assertIsNone(self.weather.convertWMO(None))
        self.assertEqual(self.weather.convertWMO("0"), "Clear sky")
        self.assertEqual(self.weather.convertWMO("99"), "Thunderstorm with heavy hail")
    
    @patch('tomweather.requests.get')
    def test_getCity_success(self, mock_get):
        """Test getCity with successful API response"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'results': [
                {
                    'name': 'Paris',
                    'country': 'France',
                    'latitude': 48.8566,
                    'longitude': 2.3522
                },
                {
                    'name': 'Paris',
                    'country': 'United States',
                    'latitude': 33.6617,
                    'longitude': -95.5555
                }
            ]
        }
        mock_get.return_value = mock_response
        
        result = self.weather.getCity("Paris")
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], 'Paris')
        self.assertEqual(result[0]['country'], 'France')
        self.assertEqual(result[0]['gps_latitude'], 48.8566)
        self.assertEqual(result[0]['gps_longitude'], 2.3522)
        
        mock_get.assert_called_once_with(
            'https://geocoding-api.open-meteo.com/v1/search?name=Paris&count=10&language=fr&format=json'
        )
    
    @patch('tomweather.requests.get')
    def test_getCity_api_error(self, mock_get):
        """Test getCity with API error response"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        result = self.weather.getCity("NonExistentCity")
        
        self.assertFalse(result)
    
    @patch('tomweather.requests.get')
    def test_getCity_empty_results(self, mock_get):
        """Test getCity with empty API response"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'results': []}
        mock_get.return_value = mock_response
        
        result = self.weather.getCity("NonExistentCity")
        
        self.assertEqual(result, [])
    
    @patch('tomweather.requests.get')
    def test_getGps_success(self, mock_get):
        """Test getGps with successful API response"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'hourly': {
                'time': ['2024-01-01T00:00', '2024-01-01T01:00', '2024-01-02T00:00'],
                'temperature_2m': [15.5, 16.0, 14.2],
                'apparent_temperature': [14.8, 15.5, 13.8],
                'weather_code': [0, 1, 61]
            },
            'daily': {
                'time': ['2024-01-01', '2024-01-02'],
                'temperature_2m_min': [10.0, 8.5],
                'temperature_2m_max': [20.0, 18.0],
                'apparent_temperature_min': [9.5, 8.0],
                'apparent_temperature_max': [19.5, 17.5],
                'weather_code': [0, 61]
            }
        }
        mock_get.return_value = mock_response
        
        result = self.weather.getGps("48.8566", "2.3522", "2024-01-01", "2024-01-01")
        
        self.assertIn('hourly', result)
        self.assertIn('daily', result)
        self.assertEqual(len(result['hourly']), 2)
        self.assertEqual(len(result['daily']), 1)
        
        self.assertEqual(result['hourly'][0]['timestamp'], '2024-01-01T00:00')
        self.assertEqual(result['hourly'][0]['temperature'], 15.5)
        self.assertEqual(result['hourly'][0]['weather_condition'], 'Clear sky')
        
        self.assertEqual(result['daily'][0]['timestamp'], '2024-01-01')
        self.assertEqual(result['daily'][0]['temperature_min'], 10.0)
        self.assertEqual(result['daily'][0]['temperature_max'], 20.0)
        self.assertEqual(result['daily'][0]['weather_condition'], 'Clear sky')
    
    @patch('tomweather.requests.get')
    def test_getGps_api_error(self, mock_get):
        """Test getGps with API error response"""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        result = self.weather.getGps("48.8566", "2.3522", "2024-01-01", "2024-01-01")
        
        self.assertEqual(result, {"hourly": [], "daily": []})
    
    @patch('tomweather.requests.get')
    def test_getGps_date_filtering(self, mock_get):
        """Test getGps with date filtering"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'hourly': {
                'time': ['2023-12-31T23:00', '2024-01-01T00:00', '2024-01-01T12:00', '2024-01-02T00:00'],
                'temperature_2m': [10.0, 15.5, 18.0, 12.0],
                'apparent_temperature': [9.5, 14.8, 17.5, 11.5],
                'weather_code': [0, 1, 2, 3]
            },
            'daily': {
                'time': ['2023-12-31', '2024-01-01', '2024-01-02'],
                'temperature_2m_min': [8.0, 10.0, 8.5],
                'temperature_2m_max': [15.0, 20.0, 18.0],
                'apparent_temperature_min': [7.5, 9.5, 8.0],
                'apparent_temperature_max': [14.5, 19.5, 17.5],
                'weather_code': [0, 1, 2]
            }
        }
        mock_get.return_value = mock_response
        
        result = self.weather.getGps("48.8566", "2.3522", "2024-01-01", "2024-01-01")
        
        self.assertEqual(len(result['hourly']), 2)
        self.assertEqual(len(result['daily']), 1)
        
        self.assertEqual(result['hourly'][0]['timestamp'], '2024-01-01T00:00')
        self.assertEqual(result['hourly'][1]['timestamp'], '2024-01-01T12:00')
        self.assertEqual(result['daily'][0]['timestamp'], '2024-01-01')
    
    @patch('tomweather.requests.get')
    def test_getGps_no_data_in_range(self, mock_get):
        """Test getGps when no data falls within the specified date range"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'hourly': {
                'time': ['2023-12-31T23:00', '2024-01-02T00:00'],
                'temperature_2m': [10.0, 12.0],
                'apparent_temperature': [9.5, 11.5],
                'weather_code': [0, 3]
            },
            'daily': {
                'time': ['2023-12-31', '2024-01-02'],
                'temperature_2m_min': [8.0, 8.5],
                'temperature_2m_max': [15.0, 18.0],
                'apparent_temperature_min': [7.5, 8.0],
                'apparent_temperature_max': [14.5, 17.5],
                'weather_code': [0, 2]
            }
        }
        mock_get.return_value = mock_response
        
        result = self.weather.getGps("48.8566", "2.3522", "2024-01-01", "2024-01-01")
        
        self.assertEqual(len(result['hourly']), 0)
        self.assertEqual(len(result['daily']), 0)
    
    def test_wmo_table_completeness(self):
        """Test that WMO table contains expected codes"""
        expected_codes = ["0", "1", "2", "3", "45", "48", "51", "53", "55", "56", "57", 
                         "61", "63", "65", "66", "67", "71", "73", "75", "77", "80", 
                         "81", "82", "85", "86", "95", "96", "99"]
        
        for code in expected_codes:
            self.assertIn(code, self.weather.WMOTable)
            self.assertIsNotNone(self.weather.WMOTable[code])
            self.assertIsInstance(self.weather.WMOTable[code], str)
    
    def test_tools_structure(self):
        """Test that tools are properly structured"""
        self.assertIsInstance(self.weather.tools, list)
        self.assertEqual(len(self.weather.tools), 2)
        
        for tool in self.weather.tools:
            self.assertIn('type', tool)
            self.assertEqual(tool['type'], 'function')
            self.assertIn('function', tool)
            self.assertIn('name', tool['function'])
            self.assertIn('description', tool['function'])
            self.assertIn('parameters', tool['function'])
    
    def test_functions_structure(self):
        """Test that functions are properly structured"""
        self.assertIn('weather_get_by_gps_position', self.weather.functions)
        self.assertIn('get_gps_position_by_city_name', self.weather.functions)
        
        for func_name, func_data in self.weather.functions.items():
            self.assertIn('function', func_data)
            self.assertTrue(callable(func_data['function']))

if __name__ == '__main__':
    unittest.main()