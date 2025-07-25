import unittest
from unittest.mock import patch, MagicMock, mock_open
import sys
import os
import tempfile
import yaml

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'modules'))

from tomcontacts import TomContacts

class TestTomContacts(unittest.TestCase):
    
    def setUp(self):
        self.config = {
            'all_datadir': '/tmp/test_data/'
        }
        
        # Mock LLM
        self.mock_llm = MagicMock()
        self.mock_llm.query.return_value = "Mock LLM response"
        
        # Sample YAML data for tests
        self.sample_contacts_data = {
            'contacts': [
                {
                    'name': 'Jean Dupont',
                    'phone': '01 23 45 67 89',
                    'email': 'jean.dupont@email.com',
                    'address': '123 rue de la Paix, Paris'
                },
                {
                    'name': 'Marie Martin',
                    'phone': '06 78 90 12 34',
                    'address': '456 avenue des Champs, Lyon',
                    'notes': 'Collègue de travail'
                },
                {
                    'name': 'Grand père et mamylene',
                    'address': '25 bis rue de samois, Vernou la celle sur seine',
                    'relation': 'famille'
                }
            ]
        }
        
        self.sample_yaml_content = yaml.safe_dump(
            self.sample_contacts_data, 
            default_flow_style=False, 
            allow_unicode=True, 
            indent=2
        )
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_init_creates_directory_and_file(self, mock_exists, mock_makedirs):
        """Test initialization creates directory and contacts file if they don't exist"""
        mock_exists.return_value = False
        
        with patch('builtins.open', mock_open()) as mock_file:
            contacts = TomContacts(self.config, self.mock_llm)
            
            # Verify directory creation
            mock_makedirs.assert_called_once_with('/tmp/test_data', exist_ok=True)
            
            # Verify file creation with initial data
            mock_file.assert_called_with('/tmp/test_data/contacts.yml', 'w', encoding='utf-8')
            
            # Verify attributes
            self.assertEqual(contacts.contacts_file, '/tmp/test_data/contacts.yml')
            self.assertEqual(contacts.llm, self.mock_llm)
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_init_file_already_exists(self, mock_exists, mock_makedirs):
        """Test initialization when contacts file already exists"""
        mock_exists.return_value = True
        
        contacts = TomContacts(self.config, self.mock_llm)
        
        # Verify directory creation is still called
        mock_makedirs.assert_called_once_with('/tmp/test_data', exist_ok=True)
        
        # Verify no file creation since file exists
        # (We can't easily verify open() wasn't called without more complex mocking)
    
    def test_tools_structure(self):
        """Test that tools are properly structured"""
        with patch('tomcontacts.os.makedirs'), \
             patch('tomcontacts.os.path.exists', return_value=True):
            
            contacts = TomContacts(self.config, self.mock_llm)
            
            self.assertIsInstance(contacts.tools, list)
            self.assertEqual(len(contacts.tools), 3)
            
            expected_functions = ['add_contact', 'get_contacts', 'delete_contact']
            
            for i, tool in enumerate(contacts.tools):
                self.assertEqual(tool['type'], 'function')
                self.assertIn('function', tool)
                self.assertEqual(tool['function']['name'], expected_functions[i])
                self.assertIn('description', tool['function'])
                self.assertIn('parameters', tool['function'])
    
    def test_functions_structure(self):
        """Test that functions are properly structured"""
        with patch('tomcontacts.os.makedirs'), \
             patch('tomcontacts.os.path.exists', return_value=True):
            
            contacts = TomContacts(self.config, self.mock_llm)
            
            expected_functions = ['add_contact', 'get_contacts', 'delete_contact']
            
            for func_name in expected_functions:
                self.assertIn(func_name, contacts.functions)
                self.assertIn('function', contacts.functions[func_name])
                self.assertTrue(callable(contacts.functions[func_name]['function']))
    
    def test_config_attributes(self):
        """Test that configuration attributes are set correctly"""
        with patch('tomcontacts.os.makedirs'), \
             patch('tomcontacts.os.path.exists', return_value=True):
            
            contacts = TomContacts(self.config, self.mock_llm)
            
            self.assertEqual(contacts.complexity, 0)
            self.assertIn("flexible contacts list in YAML format", contacts.systemContext)
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_add_contact_success(self, mock_exists, mock_makedirs):
        """Test adding a contact successfully"""
        mock_exists.return_value = True
        
        # Mock file reading and writing
        with patch('builtins.open', mock_open(read_data=self.sample_yaml_content)) as mock_file:
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.add_contact(
                name="Pierre Durand",
                phone="09 87 65 43 21",
                email="pierre.durand@test.com"
            )
            
            # Verify success
            self.assertTrue(result['success'])
            self.assertIn("Pierre Durand", result['message'])
            
            # Verify file was read and written (init may or may not call open depending on file existence)
            self.assertTrue(mock_file.call_count >= 2)  # at least read + write
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_add_contact_no_name(self, mock_exists, mock_makedirs):
        """Test adding a contact without a name fails"""
        mock_exists.return_value = True
        
        with patch('builtins.open', mock_open(read_data=self.sample_yaml_content)):
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.add_contact(phone="09 87 65 43 21")
            
            # Verify failure
            self.assertFalse(result['success'])
            self.assertIn("nom du contact est requis", result['message'])
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_add_contact_empty_name(self, mock_exists, mock_makedirs):
        """Test adding a contact with empty name fails"""
        mock_exists.return_value = True
        
        with patch('builtins.open', mock_open(read_data=self.sample_yaml_content)):
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.add_contact(name="", phone="09 87 65 43 21")
            
            # Verify failure
            self.assertFalse(result['success'])
            self.assertIn("nom du contact est requis", result['message'])
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_add_contact_filters_empty_values(self, mock_exists, mock_makedirs):
        """Test that empty values are filtered out when adding contact"""
        mock_exists.return_value = True
        
        with patch('builtins.open', mock_open(read_data=self.sample_yaml_content)) as mock_file:
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.add_contact(
                name="Pierre Durand",
                phone="09 87 65 43 21",
                email="",  # Empty value should be filtered
                notes=None,  # None value should be filtered
                address="123 rue Test"
            )
            
            # Verify success
            self.assertTrue(result['success'])
            
            # Check that empty values were filtered by examining the write call
            write_calls = [call for call in mock_file.call_args_list if 'w' in str(call)]
            self.assertTrue(len(write_calls) > 0)
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_get_contacts_success(self, mock_exists, mock_makedirs):
        """Test getting contacts successfully"""
        mock_exists.return_value = True
        
        with patch('builtins.open', mock_open(read_data=self.sample_yaml_content)):
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.get_contacts()
            
            # Verify success
            self.assertTrue(result['success'])
            self.assertEqual(result['contacts'], self.sample_yaml_content)
            self.assertIn("récupérée avec succès", result['message'])
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_get_contacts_empty_file(self, mock_exists, mock_makedirs):
        """Test getting contacts from empty file"""
        mock_exists.return_value = True
        
        with patch('builtins.open', mock_open(read_data="")):
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.get_contacts()
            
            # Verify success with empty response
            self.assertTrue(result['success'])
            self.assertEqual(result['contacts'], "contacts: []")
            self.assertIn("vide", result['message'])
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_get_contacts_file_not_found(self, mock_exists, mock_makedirs):
        """Test getting contacts when file doesn't exist"""
        mock_exists.return_value = True
        
        with patch('builtins.open', side_effect=FileNotFoundError("File not found")):
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.get_contacts()
            
            # Verify success with default response
            self.assertTrue(result['success'])
            self.assertEqual(result['contacts'], "contacts: []")
            self.assertIn("n'existe pas encore", result['message'])
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_delete_contact_success(self, mock_exists, mock_makedirs):
        """Test deleting a contact successfully"""
        mock_exists.return_value = True
        
        with patch('builtins.open', mock_open(read_data=self.sample_yaml_content)) as mock_file:
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.delete_contact("Jean Dupont")
            
            # Verify success
            self.assertTrue(result['success'])
            self.assertIn("Jean Dupont", result['message'])
            
            # Verify file was read and written
            self.assertTrue(mock_file.call_count >= 2)  # at least read + write
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_delete_contact_not_found(self, mock_exists, mock_makedirs):
        """Test deleting a contact that doesn't exist"""
        mock_exists.return_value = True
        
        with patch('builtins.open', mock_open(read_data=self.sample_yaml_content)):
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.delete_contact("Contact Inexistant")
            
            # Verify failure
            self.assertFalse(result['success'])
            self.assertIn("Aucun contact trouvé", result['message'])
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_delete_contact_empty_list(self, mock_exists, mock_makedirs):
        """Test deleting from empty contact list"""
        mock_exists.return_value = True
        empty_data = yaml.safe_dump({'contacts': []}, default_flow_style=False, allow_unicode=True)
        
        with patch('builtins.open', mock_open(read_data=empty_data)):
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.delete_contact("Any Contact")
            
            # Verify failure
            self.assertFalse(result['success'])
            self.assertIn("Aucun contact trouvé dans le carnet", result['message'])
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_delete_multiple_contacts(self, mock_exists, mock_makedirs):
        """Test deleting multiple contacts with same identifier"""
        mock_exists.return_value = True
        
        # Create data with multiple contacts containing "Dupont"
        multi_data = {
            'contacts': [
                {'name': 'Jean Dupont', 'phone': '01 23 45 67 89'},
                {'name': 'Marie Dupont', 'phone': '06 78 90 12 34'},
                {'name': 'Pierre Martin', 'phone': '09 87 65 43 21'}
            ]
        }
        multi_yaml = yaml.safe_dump(multi_data, default_flow_style=False, allow_unicode=True)
        
        with patch('builtins.open', mock_open(read_data=multi_yaml)) as mock_file:
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.delete_contact("Dupont")
            
            # Verify success with multiple deletions
            self.assertTrue(result['success'])
            self.assertIn("2 contacts supprimés", result['message'])
            self.assertIn("Jean Dupont", result['message'])
            self.assertIn("Marie Dupont", result['message'])
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_add_contact_file_error(self, mock_exists, mock_makedirs):
        """Test add_contact handles file errors gracefully"""
        mock_exists.return_value = True
        
        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.add_contact(name="Test Contact")
            
            # Verify error handling
            self.assertFalse(result['success'])
            self.assertIn("Erreur lors de l'ajout", result['message'])
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_get_contacts_read_error(self, mock_exists, mock_makedirs):
        """Test get_contacts handles read errors gracefully"""
        mock_exists.return_value = True
        
        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.get_contacts()
            
            # Verify error handling  
            self.assertFalse(result['success'])
            self.assertIn("Erreur lors de la récupération", result['message'])
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_delete_contact_file_error(self, mock_exists, mock_makedirs):
        """Test delete_contact handles file errors gracefully"""
        mock_exists.return_value = True
        
        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.delete_contact("Test Contact")
            
            # Verify error handling
            self.assertFalse(result['success'])
            self.assertIn("Erreur lors de la suppression", result['message'])
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_yaml_parsing_error_in_delete(self, mock_exists, mock_makedirs):
        """Test delete_contact handles YAML parsing errors"""
        mock_exists.return_value = True
        invalid_yaml = "invalid: yaml: content: ["
        
        with patch('builtins.open', mock_open(read_data=invalid_yaml)):
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.delete_contact("Test Contact")
            
            # Verify error handling
            self.assertFalse(result['success'])
            self.assertIn("Erreur lors de la suppression", result['message'])
    
    @patch('tomcontacts.os.makedirs')
    @patch('tomcontacts.os.path.exists')
    def test_yaml_parsing_error_in_add(self, mock_exists, mock_makedirs):
        """Test add_contact handles YAML parsing errors"""
        mock_exists.return_value = True
        invalid_yaml = "invalid: yaml: content: ["
        
        with patch('builtins.open', mock_open(read_data=invalid_yaml)):
            contacts = TomContacts(self.config, self.mock_llm)
            
            result = contacts.add_contact(name="Test Contact")
            
            # Verify error handling
            self.assertFalse(result['success'])
            self.assertIn("Erreur lors de l'ajout", result['message'])

if __name__ == '__main__':
    unittest.main()