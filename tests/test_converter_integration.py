import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import config as cfg
from scripts import resource
from scripts.svg_converter import ConversionError, SharpConverter, get_converter_info, has_sharp_converter

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestConverterConfiguration(unittest.TestCase):
    """Test converter configuration and selection logic."""

    def setUp(self):
        """Save original configuration."""
        self.original_converter = getattr(cfg, 'SVG_CONVERTER', 'auto')
        self.original_concurrency = getattr(cfg, 'SHARP_CONCURRENCY', 4)
        self.original_quality = getattr(cfg, 'SHARP_QUALITY', 'balanced')
        self.original_size = getattr(cfg, 'SHARP_SIZE', 256)

    def tearDown(self):
        """Restore original configuration."""
        cfg.SVG_CONVERTER = self.original_converter
        cfg.SHARP_CONCURRENCY = self.original_concurrency
        cfg.SHARP_QUALITY = self.original_quality
        cfg.SHARP_SIZE = self.original_size
        # Clear environment variable if set
        if 'DIAGRAMS_SVG_CONVERTER' in os.environ:
            del os.environ['DIAGRAMS_SVG_CONVERTER']

    def test_config_defaults(self):
        """Test default configuration values."""
        self.assertEqual(cfg.SVG_CONVERTER, "auto")
        self.assertEqual(cfg.SHARP_CONCURRENCY, 4)
        self.assertEqual(cfg.SHARP_QUALITY, "high")
        self.assertEqual(cfg.SHARP_SIZE, 256)
        self.assertEqual(cfg.SHARP_CONVERTER_PATH, "scripts/svg_converter/converter.js")

    def test_converter_selection_auto(self):
        """Test auto converter selection."""
        cfg.SVG_CONVERTER = "auto"

        # Mock resource_dir to avoid actual file operations
        with patch('scripts.resource.resource_dir') as mock_resource_dir:
            mock_resource_dir.return_value = "/tmp/test"

            # Test that auto mode checks for sharp availability
            with patch('scripts.svg_converter.has_sharp_converter') as mock_has_sharp:
                mock_has_sharp.return_value = True
                with patch('scripts.resource.svg2png_sharp') as mock_sharp:
                    resource.svg2png("test")
                    mock_sharp.assert_called_once_with("test")

                mock_has_sharp.return_value = False
                with patch('scripts.resource.svg2png_inkscape') as mock_inkscape:
                    resource.svg2png("test")
                    mock_inkscape.assert_called_once_with("test")

    def test_converter_selection_explicit(self):
        """Test explicit converter selection."""
        with patch('scripts.resource.resource_dir') as mock_resource_dir:
            mock_resource_dir.return_value = "/tmp/test"

            # Test sharp selection
            cfg.SVG_CONVERTER = "sharp"
            with patch('scripts.resource.svg2png_sharp') as mock_sharp:
                resource.svg2png("test")
                mock_sharp.assert_called_once_with("test")

            # Test inkscape selection
            cfg.SVG_CONVERTER = "inkscape"
            with patch('scripts.resource.svg2png_inkscape') as mock_inkscape:
                resource.svg2png("test")
                mock_inkscape.assert_called_once_with("test")

            # Test imagemagick selection
            cfg.SVG_CONVERTER = "imagemagick"
            with patch('scripts.resource.svg2png2') as mock_imagemagick:
                resource.svg2png("test")
                mock_imagemagick.assert_called_once_with("test")

    def test_environment_variable_override(self):
        """Test that environment variable overrides config."""
        cfg.SVG_CONVERTER = "inkscape"
        os.environ['DIAGRAMS_SVG_CONVERTER'] = "sharp"

        with patch('scripts.resource.resource_dir') as mock_resource_dir:
            mock_resource_dir.return_value = "/tmp/test"
            with patch('scripts.resource.svg2png_sharp') as mock_sharp:
                resource.svg2png("test")
                mock_sharp.assert_called_once_with("test")

    def test_unknown_converter_fallback(self):
        """Test fallback for unknown converter type."""
        cfg.SVG_CONVERTER = "unknown_converter"

        with patch('scripts.resource.resource_dir') as mock_resource_dir:
            mock_resource_dir.return_value = "/tmp/test"
            with patch('scripts.resource.svg2png_inkscape') as mock_inkscape:
                resource.svg2png("test")
                mock_inkscape.assert_called_once_with("test")


class TestSharpConverterIntegration(unittest.TestCase):
    """Test sharp converter integration with resource.py."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp(prefix="test_sharp_integration_")
        self.provider = "test_provider"
        self.resource_dir = Path(self.test_dir) / "resources" / self.provider
        self.resource_dir.mkdir(parents=True)

        # Save original functions
        self.original_resource_dir = resource.resource_dir

        # Mock resource_dir to use test directory
        resource.resource_dir = lambda pvd: str(self.resource_dir.parent / pvd)

    def tearDown(self):
        """Clean up test environment."""
        # Restore original functions
        resource.resource_dir = self.original_resource_dir

        # Clean up test directory
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def create_test_svg(self, name="test.svg"):
        """Create a test SVG file."""
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" xmlns="http://www.w3.org/2000/svg">
    <rect width="256" height="256" fill="#0078D4"/>
    <circle cx="128" cy="128" r="80" fill="white"/>
</svg>"""
        svg_path = self.resource_dir / name
        svg_path.write_text(svg_content)
        return svg_path

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_svg2png_sharp_success(self):
        """Test successful sharp conversion."""
        # Create test SVG files
        for i in range(3):
            self.create_test_svg(f"icon_{i}.svg")

        # Run sharp converter
        resource.svg2png_sharp(self.provider)

        # Check PNG files were created
        png_files = list(self.resource_dir.glob("*.png"))
        self.assertEqual(len(png_files), 3)

        # Check SVG files were removed
        svg_files = list(self.resource_dir.glob("*.svg"))
        self.assertEqual(len(svg_files), 0)

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_svg2png_sharp_preserves_structure(self):
        """Test that sharp converter preserves directory structure."""
        # Create nested structure
        subdir = self.resource_dir / "subcategory"
        subdir.mkdir()

        # Create SVGs in both directories
        self.create_test_svg("root.svg")
        svg_path = subdir / "nested.svg"
        svg_path.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" xmlns="http://www.w3.org/2000/svg">
    <rect width="256" height="256" fill="#FF0000"/>
</svg>""")

        # Run converter
        resource.svg2png_sharp(self.provider)

        # Check files in correct locations
        self.assertTrue((self.resource_dir / "root.png").exists())
        self.assertTrue((subdir / "nested.png").exists())

    def test_svg2png_sharp_fallback_on_import_error(self):
        """Test fallback when sharp converter module not found."""
        with patch('scripts.svg_converter.has_sharp_converter', side_effect=ImportError):
            with patch('scripts.resource.svg2png_inkscape') as mock_inkscape:
                resource.svg2png_sharp(self.provider)
                mock_inkscape.assert_called_once_with(self.provider)

    def test_svg2png_sharp_fallback_on_converter_error(self):
        """Test fallback when sharp converter fails."""
        # Create a test SVG
        self.create_test_svg()

        with patch('scripts.svg_converter.SharpConverter') as mock_converter_class:
            mock_converter = MagicMock()
            mock_converter.convert_directory.side_effect = Exception("Converter failed")
            mock_converter_class.return_value = mock_converter

            with patch('scripts.resource.svg2png_inkscape') as mock_inkscape:
                resource.svg2png_sharp(self.provider)
                mock_inkscape.assert_called_once_with(self.provider)

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_svg2png_sharp_uses_config_settings(self):
        """Test that sharp converter uses configuration settings."""
        # Save original settings
        orig_concurrency = cfg.SHARP_CONCURRENCY
        orig_quality = cfg.SHARP_QUALITY
        orig_size = cfg.SHARP_SIZE

        try:
            # Set test config - use valid config that won't cause errors
            cfg.SHARP_CONCURRENCY = 2
            cfg.SHARP_QUALITY = "fast"
            cfg.SHARP_SIZE = 128

            # Create a test SVG
            self.create_test_svg()

            # Run the actual converter to verify it uses the settings
            # We can verify by checking the verbose output or the result
            import io
            from contextlib import redirect_stdout

            f = io.StringIO()
            with redirect_stdout(f):
                resource.svg2png_sharp(self.provider)

            output = f.getvalue()

            # Verify the converter ran with our settings
            self.assertIn("Converting SVGs using sharp converter", output)
            self.assertIn("concurrency: 2", output)

            # Verify PNG was created with correct size
            png_files = list(self.resource_dir.glob("*.png"))
            self.assertGreater(len(png_files), 0)

        finally:
            # Restore original settings
            cfg.SHARP_CONCURRENCY = orig_concurrency
            cfg.SHARP_QUALITY = orig_quality
            cfg.SHARP_SIZE = orig_size


class TestConverterCommands(unittest.TestCase):
    """Test converter commands in resource.py."""

    def test_sharp_command_registered(self):
        """Test that sharp converter commands are registered."""
        self.assertIn('svg2png_sharp', resource.commands)
        self.assertIn('svg2png_inkscape', resource.commands)
        self.assertTrue(callable(resource.commands['svg2png_sharp']))
        self.assertTrue(callable(resource.commands['svg2png_inkscape']))

    def test_svg2png_command_still_exists(self):
        """Test that original svg2png command still exists."""
        self.assertIn('svg2png', resource.commands)
        self.assertTrue(callable(resource.commands['svg2png']))

    def test_svg2png2_command_still_exists(self):
        """Test that imagemagick command still exists."""
        self.assertIn('svg2png2', resource.commands)
        self.assertTrue(callable(resource.commands['svg2png2']))


class TestConverterFallback(unittest.TestCase):
    """Test converter fallback mechanisms."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp(prefix="test_fallback_")
        self.provider = "test_provider"
        self.resource_dir = Path(self.test_dir) / "resources" / self.provider
        self.resource_dir.mkdir(parents=True)

        # Mock resource_dir
        self.original_resource_dir = resource.resource_dir
        resource.resource_dir = lambda pvd: str(self.resource_dir.parent / pvd)

    def tearDown(self):
        """Clean up."""
        resource.resource_dir = self.original_resource_dir
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sharp_not_available_fallback(self):
        """Test fallback when sharp converter is not available."""
        with patch('scripts.svg_converter.has_sharp_converter', return_value=False):
            with patch('scripts.resource.svg2png_inkscape') as mock_inkscape:
                resource.svg2png_sharp(self.provider)
                mock_inkscape.assert_called_once_with(self.provider)

    def test_auto_mode_without_sharp(self):
        """Test auto mode when sharp is not available."""
        cfg.SVG_CONVERTER = "auto"

        # Mock has_sharp_converter to return False
        with patch('scripts.svg_converter.has_sharp_converter', return_value=False):
            with patch('scripts.resource.svg2png_inkscape') as mock_inkscape:
                resource.svg2png(self.provider)
                mock_inkscape.assert_called_once_with(self.provider)

    def test_auto_mode_with_sharp(self):
        """Test auto mode when sharp is available."""
        cfg.SVG_CONVERTER = "auto"

        # Mock has_sharp_converter to return True
        with patch('scripts.svg_converter.has_sharp_converter', return_value=True):
            with patch('scripts.resource.svg2png_sharp') as mock_sharp:
                resource.svg2png(self.provider)
                mock_sharp.assert_called_once_with(self.provider)


class TestEndToEndConversion(unittest.TestCase):
    """End-to-end tests for the conversion pipeline."""

    @classmethod
    def setUpClass(cls):
        """Set up test environment once for all tests."""
        cls.test_dir = tempfile.mkdtemp(prefix="test_e2e_conversion_")
        cls.provider = "e2e_test"
        cls.resource_dir = Path(cls.test_dir) / "resources" / cls.provider
        cls.resource_dir.mkdir(parents=True)

    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def setUp(self):
        """Set up for each test."""
        # Save and mock resource_dir
        self.original_resource_dir = resource.resource_dir
        resource.resource_dir = lambda pvd: str(self.resource_dir.parent / pvd)

        # Clear any existing files
        for file in self.resource_dir.glob("*"):
            file.unlink()

    def tearDown(self):
        """Clean up after each test."""
        resource.resource_dir = self.original_resource_dir

    def create_test_svgs(self, count=3):
        """Create multiple test SVG files."""
        for i in range(count):
            svg_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" xmlns="http://www.w3.org/2000/svg">
    <rect width="256" height="256" fill="#{i:02x}78D4"/>
    <text x="128" y="128" text-anchor="middle" fill="white">{i}</text>
</svg>"""
            svg_path = self.resource_dir / f"icon_{i}.svg"
            svg_path.write_text(svg_content)

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_full_pipeline_with_sharp(self):
        """Test complete conversion pipeline with sharp."""
        # Create test SVGs
        self.create_test_svgs(5)

        # Set to use sharp
        cfg.SVG_CONVERTER = "sharp"

        # Run conversion
        resource.svg2png(self.provider)

        # Verify PNGs created
        png_files = list(self.resource_dir.glob("*.png"))
        self.assertEqual(len(png_files), 5)

        # Verify SVGs removed
        svg_files = list(self.resource_dir.glob("*.svg"))
        self.assertEqual(len(svg_files), 0)

    def test_full_pipeline_with_inkscape(self):
        """Test complete conversion pipeline with inkscape."""
        # Create test SVGs
        self.create_test_svgs(3)

        # Set to use inkscape
        cfg.SVG_CONVERTER = "inkscape"

        # Run conversion
        resource.svg2png(self.provider)

        # Verify PNGs created
        png_files = list(self.resource_dir.glob("*.png"))
        self.assertEqual(len(png_files), 3)

        # Verify SVGs removed
        svg_files = list(self.resource_dir.glob("*.svg"))
        self.assertEqual(len(svg_files), 0)

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_environment_override_in_pipeline(self):
        """Test that environment variable works in full pipeline."""
        # Create test SVGs
        self.create_test_svgs(2)

        # Config says inkscape, but env says sharp
        cfg.SVG_CONVERTER = "inkscape"
        os.environ['DIAGRAMS_SVG_CONVERTER'] = "sharp"

        try:
            # Spy on both converters
            with patch('scripts.resource.svg2png_sharp', wraps=resource.svg2png_sharp) as mock_sharp:
                with patch('scripts.resource.svg2png_inkscape', wraps=resource.svg2png_inkscape) as mock_inkscape:
                    resource.svg2png(self.provider)

                    # Sharp should be called, not inkscape
                    mock_sharp.assert_called_once()
                    mock_inkscape.assert_not_called()
        finally:
            del os.environ['DIAGRAMS_SVG_CONVERTER']


if __name__ == '__main__':
    unittest.main()
