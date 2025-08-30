import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock, mock_open

# Import the module to test
from scripts import azure_updater
import config as cfg


class AzureUpdaterTest(unittest.TestCase):
    """Test suite for Azure icon updater functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp(prefix="test_azure_")
        self.backup_dir = os.path.join(self.test_dir, "backups")
        self.resource_dir = os.path.join(self.test_dir, "resources", "azure")
        
        # Create test directories
        os.makedirs(self.resource_dir, exist_ok=True)
        
        # Store original config values
        self.original_azure_source = getattr(cfg, 'AZURE_ICON_SOURCE', None)
        self.original_azure_map = getattr(cfg, 'AZURE_CATEGORY_MAP', None)
        
        # Set test config
        cfg.AZURE_ICON_SOURCE = {
            "current_version": "test_v1",
            "download_url": "https://example.com/test_icons.zip",
            "last_updated": "2024-01-01",
            "backup_dir": self.backup_dir,
        }
        
        cfg.AZURE_CATEGORY_MAP = {
            "Test Category": "test",
            "Compute": "compute",
            "Storage": "storage",
        }
    
    def tearDown(self):
        """Clean up test fixtures."""
        # Remove test directory
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
        # Restore original config
        if self.original_azure_source:
            cfg.AZURE_ICON_SOURCE = self.original_azure_source
        else:
            delattr(cfg, 'AZURE_ICON_SOURCE')
            
        if self.original_azure_map:
            cfg.AZURE_CATEGORY_MAP = self.original_azure_map
        else:
            delattr(cfg, 'AZURE_CATEGORY_MAP')
    
    def test_show_download_progress(self):
        """Test download progress display."""
        # Test progress calculation
        with patch('builtins.print') as mock_print:
            azure_updater.show_download_progress(50, 1024, 102400)
            mock_print.assert_called_with("Downloading: 50.0%", end='\r')
            
            azure_updater.show_download_progress(100, 1024, 102400)
            mock_print.assert_called_with("Downloading: 100.0%", end='\r')
    
    def test_get_current_icons(self):
        """Test getting current icon list."""
        # Create test icon files
        test_icons = [
            os.path.join(self.resource_dir, "compute", "vm.png"),
            os.path.join(self.resource_dir, "storage", "blob.png"),
        ]
        
        for icon_path in test_icons:
            os.makedirs(os.path.dirname(icon_path), exist_ok=True)
            with open(icon_path, 'w') as f:
                f.write("test")
        
        with patch('scripts.azure_updater.resource_dir', return_value=self.resource_dir):
            icons = azure_updater.get_current_icons("azure")
            
            self.assertEqual(len(icons), 2)
            self.assertIn("compute/vm.png", icons)
            self.assertIn("storage/blob.png", icons)
    
    def test_backup_azure_no_existing(self):
        """Test backup when no existing icons."""
        # Don't create the resource dir to simulate no existing icons
        non_existent_dir = os.path.join(self.test_dir, "non_existent")
        
        with patch('scripts.azure_updater.resource_dir', return_value=non_existent_dir):
            with patch('builtins.print') as mock_print:
                azure_updater.backup_azure("azure")
                
                # Should print message about no existing icons
                mock_print.assert_called_with(f"No existing Azure icons to backup at {non_existent_dir}")
    
    def test_backup_azure_with_existing(self):
        """Test backup with existing icons."""
        # Create some test files
        test_file = os.path.join(self.resource_dir, "test.png")
        with open(test_file, 'w') as f:
            f.write("test content")
        
        with patch('scripts.azure_updater.resource_dir', return_value=self.resource_dir):
            result = azure_updater.backup_azure("azure")
            
            # Check backup was created
            self.assertTrue(os.path.exists(result))
            self.assertTrue(os.path.exists(os.path.join(result, "test.png")))
    
    def test_cleanup_old_backups(self):
        """Test cleanup of old backups."""
        # Create multiple backup directories
        os.makedirs(self.backup_dir)
        for i in range(5):
            backup = os.path.join(self.backup_dir, f"2024010{i}_120000")
            os.makedirs(backup)
        
        # Should keep only 3 most recent
        azure_updater.cleanup_old_backups(self.backup_dir, keep=3)
        
        remaining = [d for d in os.listdir(self.backup_dir) if os.path.isdir(os.path.join(self.backup_dir, d))]
        self.assertEqual(len(remaining), 3)
        self.assertIn("20240102_120000", remaining)
        self.assertIn("20240103_120000", remaining)
        self.assertIn("20240104_120000", remaining)
    
    @patch('os.remove')
    @patch('zipfile.ZipFile')
    @patch('urllib.request.urlretrieve')
    def test_download_azure_icons(self, mock_urlretrieve, mock_zipfile, mock_remove):
        """Test downloading Azure icons."""
        # Mock the download
        mock_urlretrieve.return_value = None
        
        # Mock zip extraction
        mock_zip = MagicMock()
        mock_zipfile.return_value.__enter__.return_value = mock_zip
        
        azure_updater.download_azure_icons("azure")
        
        # Check download was called with correct URL
        mock_urlretrieve.assert_called()
        call_args = mock_urlretrieve.call_args[0]
        self.assertEqual(call_args[0], cfg.AZURE_ICON_SOURCE['download_url'])
        
        # Check extraction was called
        mock_zip.extractall.assert_called_once()
        
        # Check zip file removal was attempted
        mock_remove.assert_called_once()
    
    def test_download_azure_icons_no_config(self):
        """Test download fails without configuration."""
        delattr(cfg, 'AZURE_ICON_SOURCE')
        
        with self.assertRaises(ValueError) as context:
            azure_updater.download_azure_icons("azure")
        
        self.assertIn("AZURE_ICON_SOURCE not configured", str(context.exception))
    
    def test_map_and_copy_icons(self):
        """Test mapping and copying icons to categories."""
        # Create test source directory structure
        source_dir = os.path.join(self.test_dir, "source")
        os.makedirs(os.path.join(source_dir, "Compute"))
        os.makedirs(os.path.join(source_dir, "Storage"))
        os.makedirs(os.path.join(source_dir, "Unknown Category"))
        
        # Create test SVG files
        with open(os.path.join(source_dir, "Compute", "vm.svg"), 'w') as f:
            f.write("<svg>test</svg>")
        with open(os.path.join(source_dir, "Storage", "blob.svg"), 'w') as f:
            f.write("<svg>test</svg>")
        with open(os.path.join(source_dir, "Unknown Category", "unknown.svg"), 'w') as f:
            f.write("<svg>test</svg>")
        
        target_dir = os.path.join(self.test_dir, "target")
        
        stats = azure_updater.map_and_copy_icons(source_dir, target_dir)
        
        # Check statistics
        self.assertEqual(stats['total_downloaded'], 3)
        self.assertEqual(stats['mapped_count'], 2)
        self.assertEqual(len(stats['unmapped_categories']), 1)
        self.assertIn("Unknown Category", stats['unmapped_categories'])
        
        # Check files were copied to correct locations
        self.assertTrue(os.path.exists(os.path.join(target_dir, "compute", "vm.svg")))
        self.assertTrue(os.path.exists(os.path.join(target_dir, "storage", "blob.svg")))
    
    def test_generate_update_report(self):
        """Test update report generation."""
        stats = {
            'total_downloaded': 100,
            'mapped_count': 95,
            'unmapped_categories': ['Unknown1', 'Unknown2'],
            'category_mappings': {
                'Compute': 'compute',
                'Storage': 'storage',
            },
            'category_counts': {
                'Compute': 50,
                'Storage': 45,
            },
            'final_category_counts': {
                'compute': 50,
                'storage': 45,
            },
        }
        
        previous = {"compute/old.png", "storage/old.png"}
        current = {"compute/new.png", "storage/old.png"}
        
        report = azure_updater.generate_update_report(stats, previous, current)
        
        # Check report contains expected sections
        self.assertIn("AZURE ICON UPDATE REPORT", report)
        self.assertIn("## SUMMARY", report)
        self.assertIn("Total icons downloaded: 100", report)
        self.assertIn("Successfully mapped: 95", report)
        self.assertIn("## CATEGORY MAPPING", report)
        self.assertIn("Compute -> compute (50 icons)", report)
        self.assertIn("## NEW ICONS", report)
        self.assertIn("+ compute/new.png", report)
        self.assertIn("## REMOVED ICONS", report)
        self.assertIn("- compute/old.png", report)
        self.assertIn("## UNMAPPED CATEGORIES", report)
        self.assertIn("! Unknown1", report)
    
    def test_save_report(self):
        """Test saving report to files."""
        report = "Test Report Content"
        stats = {"test": "data"}
        
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('os.makedirs') as mock_makedirs:
                with patch('shutil.copy') as mock_copy:
                    azure_updater.save_report(report, stats)
                    
                    # Check directories were created
                    mock_makedirs.assert_called()
                    
                    # Check files were written
                    calls = mock_file.call_args_list
                    self.assertTrue(any('.txt' in str(call) for call in calls))
                    self.assertTrue(any('.json' in str(call) for call in calls))
    
    @patch('scripts.azure_updater.download_azure_icons')
    @patch('scripts.azure_updater.map_and_copy_icons')
    @patch('scripts.azure_updater.backup_azure')
    @patch('scripts.azure_updater.generate_update_report')
    @patch('scripts.azure_updater.save_report')
    def test_update_azure_full_pipeline(self, mock_save, mock_report, mock_backup, mock_map, mock_download):
        """Test complete update pipeline."""
        # Setup mocks
        mock_download.return_value = "/tmp/extracted"
        mock_map.return_value = {
            'total_downloaded': 10,
            'mapped_count': 10,
            'unmapped_categories': [],
            'icon_list': ['test.png'],
        }
        mock_report.return_value = "Test Report"
        
        with patch('scripts.azure_updater.resource_dir', return_value=self.resource_dir):
            with patch('shutil.rmtree'):
                azure_updater.update_azure("azure")
        
        # Verify all steps were called
        mock_backup.assert_called_once()
        mock_download.assert_called_once()
        mock_map.assert_called_once()
        mock_report.assert_called_once()
        mock_save.assert_called_once()
    
    def test_update_azure_wrong_provider(self):
        """Test update fails for non-azure provider."""
        with patch('builtins.print') as mock_print:
            azure_updater.update_azure("aws")
            mock_print.assert_called_with("Error: update_azure only works for 'azure' provider, got 'aws'")
    
    def test_rollback_azure(self):
        """Test rollback functionality."""
        # Create a backup
        backup_path = os.path.join(self.backup_dir, "20240101_120000")
        os.makedirs(backup_path)
        with open(os.path.join(backup_path, "test.png"), 'w') as f:
            f.write("backup content")
        
        with patch('scripts.azure_updater.resource_dir', return_value=self.resource_dir):
            with patch('builtins.input', return_value='1'):
                with patch('builtins.print'):
                    azure_updater.rollback_azure("azure")
        
        # Check file was restored
        self.assertTrue(os.path.exists(os.path.join(self.resource_dir, "test.png")))
        with open(os.path.join(self.resource_dir, "test.png")) as f:
            self.assertEqual(f.read(), "backup content")
    
    def test_rollback_azure_cancel(self):
        """Test rollback cancellation."""
        # Create a backup so there's something to rollback
        backup_path = os.path.join(self.backup_dir, "20240101_120000")
        os.makedirs(backup_path)
        
        with patch('builtins.input', return_value='c'):
            with patch('builtins.print') as mock_print:
                azure_updater.rollback_azure("azure")
                
                # Check that cancellation message was printed
                print_calls = [str(call) for call in mock_print.call_args_list]
                self.assertTrue(any("cancelled" in call.lower() for call in print_calls))
    
    def test_check_azure_updates(self):
        """Test check for updates (placeholder function)."""
        with patch('builtins.print') as mock_print:
            azure_updater.check_azure_updates("azure")
            
            # Should print placeholder message
            calls = [str(call) for call in mock_print.call_args_list]
            self.assertTrue(any("not yet implemented" in call for call in calls))
            self.assertTrue(any("test_v1" in call for call in calls))  # Current version


class ResourceIntegrationTest(unittest.TestCase):
    """Test integration with resource.py."""
    
    def test_azure_commands_imported(self):
        """Test that Azure commands are available in resource.py."""
        from scripts import resource
        
        # Check commands are in the dictionary
        self.assertIn('update_azure', resource.commands)
        self.assertIn('backup_azure', resource.commands)
        self.assertIn('rollback_azure', resource.commands)
        self.assertIn('check_azure', resource.commands)
    
    def test_azure_commands_callable(self):
        """Test that Azure commands are callable."""
        from scripts import resource
        
        # Check commands are callable functions
        self.assertTrue(callable(resource.commands['update_azure']))
        self.assertTrue(callable(resource.commands['backup_azure']))
        self.assertTrue(callable(resource.commands['rollback_azure']))
        self.assertTrue(callable(resource.commands['check_azure']))


if __name__ == '__main__':
    unittest.main()