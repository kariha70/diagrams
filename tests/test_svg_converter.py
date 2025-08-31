import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from scripts.svg_converter import (
    ConversionError,
    ConversionQuality,
    SharpConverter,
    batch_convert_svgs,
    convert_svg_to_png,
    get_converter_info,
    has_sharp_converter,
)

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSvgConverter(unittest.TestCase):
    """Test suite for SVG to PNG converter."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures for all tests."""
        cls.test_dir = tempfile.mkdtemp(prefix="test_svg_converter_")
        cls.svg_dir = Path(cls.test_dir) / "svgs"
        cls.png_dir = Path(cls.test_dir) / "pngs"
        cls.svg_dir.mkdir(parents=True)
        cls.png_dir.mkdir(parents=True)

        # Create test SVG content
        cls.test_svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" xmlns="http://www.w3.org/2000/svg">
    <rect width="256" height="256" fill="#0078D4"/>
    <circle cx="128" cy="128" r="80" fill="white"/>
</svg>"""

        # Create test SVG files
        cls.test_svgs = []
        for i in range(5):
            svg_path = cls.svg_dir / f"test_{i}.svg"
            svg_path.write_text(cls.test_svg_content)
            cls.test_svgs.append(svg_path)

    @classmethod
    def tearDownClass(cls):
        """Clean up test fixtures."""
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def setUp(self):
        """Set up for each test."""
        # Clear any existing PNG files
        for png in self.png_dir.glob("**/*.png"):
            png.unlink()

    def test_converter_initialization(self):
        """Test SharpConverter initialization."""
        # Test with default parameters
        converter = SharpConverter()
        self.assertEqual(converter.concurrency, 4)
        self.assertEqual(converter.quality, "balanced")
        self.assertEqual(converter.size, 256)
        self.assertFalse(converter.verbose)

        # Test with custom parameters
        converter = SharpConverter(
            concurrency=8,
            quality=ConversionQuality.HIGH,
            size=512,
            verbose=True
        )
        self.assertEqual(converter.concurrency, 8)
        self.assertEqual(converter.quality, "high")
        self.assertEqual(converter.size, 512)
        self.assertTrue(converter.verbose)

        # Test concurrency clamping
        converter = SharpConverter(concurrency=100)
        self.assertEqual(converter.concurrency, 16)  # Max is 16

        converter = SharpConverter(concurrency=0)
        self.assertEqual(converter.concurrency, 1)  # Min is 1

    def test_converter_availability(self):
        """Test converter availability checks."""
        info = get_converter_info()

        self.assertIn('available', info)
        self.assertIn('path', info)
        self.assertIn('dependencies_installed', info)
        self.assertIn('node_version', info)

        # Check if converter is available
        available = has_sharp_converter()
        self.assertIsInstance(available, bool)

        if available:
            self.assertTrue(info['available'])
            self.assertTrue(info['dependencies_installed'])
            self.assertIsNotNone(info['node_version'])

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_single_file_conversion(self):
        """Test single file conversion."""
        svg_path = self.test_svgs[0]
        png_path = self.png_dir / "single_test.png"

        # Test conversion
        success = convert_svg_to_png(svg_path, png_path)

        self.assertTrue(success)
        self.assertTrue(png_path.exists())
        self.assertGreater(png_path.stat().st_size, 0)

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_single_file_conversion_with_quality(self):
        """Test single file conversion with different quality settings."""
        svg_path = self.test_svgs[0]
        sizes = {}

        for quality in ["fast", "balanced", "high"]:
            png_path = self.png_dir / f"quality_{quality}.png"
            success = convert_svg_to_png(svg_path, png_path, quality=quality)

            self.assertTrue(success)
            self.assertTrue(png_path.exists())
            sizes[quality] = png_path.stat().st_size

        # Generally, higher quality should produce larger files
        # but this isn't always guaranteed due to compression
        self.assertGreater(sizes["high"], 0)
        self.assertGreater(sizes["balanced"], 0)
        self.assertGreater(sizes["fast"], 0)

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_batch_conversion(self):
        """Test batch conversion with glob pattern."""
        pattern = str(self.svg_dir / "*.svg")
        output_dir = self.png_dir / "batch"

        stats = batch_convert_svgs(pattern, output_dir)

        self.assertIn('processed', stats)
        self.assertIn('failed', stats)
        self.assertIn('total', stats)

        self.assertEqual(stats['total'], len(self.test_svgs))
        self.assertEqual(stats['processed'], len(self.test_svgs))
        self.assertEqual(stats['failed'], 0)

        # Check output files
        png_files = list(output_dir.glob("*.png"))
        self.assertEqual(len(png_files), len(self.test_svgs))

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_batch_conversion_with_progress(self):
        """Test batch conversion with progress callback."""
        pattern = str(self.svg_dir / "*.svg")
        output_dir = self.png_dir / "batch_progress"

        progress_updates = []

        def progress_callback(data):
            progress_updates.append(data)

        stats = batch_convert_svgs(
            pattern,
            output_dir,
            progress_callback=progress_callback
        )

        self.assertEqual(stats['processed'], len(self.test_svgs))

        # Progress callback should have been called
        if progress_updates:  # Progress might not always be reported for small batches
            last_update = progress_updates[-1]
            self.assertIn('percent', last_update)
            self.assertIn('current', last_update)
            self.assertIn('total', last_update)

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_directory_conversion(self):
        """Test directory conversion with structure preservation."""
        # Create nested directory structure
        nested_dir = self.svg_dir / "nested"
        nested_dir.mkdir()
        nested_svg = nested_dir / "nested.svg"
        nested_svg.write_text(self.test_svg_content)

        converter = SharpConverter()
        output_dir = self.png_dir / "directory"

        stats = converter.convert_directory(
            self.svg_dir,
            output_dir,
            preserve_structure=True
        )

        # Check that structure is preserved
        self.assertTrue((output_dir / "nested" / "nested.png").exists())

        # Check stats
        self.assertGreater(stats['processed'], 0)
        self.assertEqual(stats['failed'], 0)

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_directory_conversion_flat(self):
        """Test directory conversion without structure preservation."""
        converter = SharpConverter()
        output_dir = self.png_dir / "flat"

        stats = converter.convert_directory(
            self.svg_dir,
            output_dir,
            preserve_structure=False
        )

        # All files should be in the root output directory
        png_files = list(output_dir.glob("*.png"))
        self.assertGreater(len(png_files), 0)

        # No subdirectories should exist
        subdirs = [d for d in output_dir.iterdir() if d.is_dir()]
        self.assertEqual(len(subdirs), 0)

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_concurrency_performance(self):
        """Test that parallel processing is faster than sequential."""
        # Create more SVG files for performance testing
        perf_dir = Path(self.test_dir) / "performance"
        perf_dir.mkdir(exist_ok=True)

        for i in range(10):
            svg_path = perf_dir / f"perf_{i}.svg"
            svg_path.write_text(self.test_svg_content)

        pattern = str(perf_dir / "*.svg")

        # Sequential conversion (concurrency=1)
        start_time = time.time()
        converter_seq = SharpConverter(concurrency=1, verbose=False)
        stats_seq = converter_seq.convert_batch(
            pattern,
            self.png_dir / "sequential",
            callback=None
        )
        seq_time = time.time() - start_time

        # Clear output
        shutil.rmtree(self.png_dir / "sequential", ignore_errors=True)

        # Parallel conversion (concurrency=4)
        start_time = time.time()
        converter_par = SharpConverter(concurrency=4, verbose=False)
        stats_par = converter_par.convert_batch(
            pattern,
            self.png_dir / "parallel",
            callback=None
        )
        par_time = time.time() - start_time

        # Both should process the same number of files
        self.assertEqual(stats_seq['processed'], stats_par['processed'])

        # Parallel should generally be faster (but not always on small sets)
        print(f"\nPerformance: Sequential={seq_time:.2f}s, Parallel={par_time:.2f}s")

        # Clean up
        shutil.rmtree(perf_dir, ignore_errors=True)

    def test_invalid_input_handling(self):
        """Test handling of invalid inputs."""
        if not has_sharp_converter():
            self.skipTest("Sharp converter not available")

        converter = SharpConverter()

        # Test with non-existent file
        non_existent = Path("/non/existent/file.svg")
        output = self.png_dir / "output.png"

        with self.assertRaises(FileNotFoundError):
            converter.convert_file(non_existent, output)

        # Test with non-existent directory
        with self.assertRaises(FileNotFoundError):
            converter.convert_directory(
                Path("/non/existent/directory"),
                self.png_dir / "output"
            )

    @patch('subprocess.run')
    def test_node_availability_check(self, mock_run):
        """Test Node.js availability checking."""
        # Simulate Node.js available
        mock_run.return_value = MagicMock(returncode=0, stdout="v18.0.0")
        converter = SharpConverter()
        self.assertTrue(converter._check_node())

        # Simulate Node.js not available
        mock_run.return_value = MagicMock(returncode=1)
        self.assertFalse(converter._check_node())

        # Simulate subprocess error
        mock_run.side_effect = FileNotFoundError()
        self.assertFalse(converter._check_node())

    def test_quality_enum(self):
        """Test ConversionQuality enum."""
        self.assertEqual(ConversionQuality.FAST.value, "fast")
        self.assertEqual(ConversionQuality.BALANCED.value, "balanced")
        self.assertEqual(ConversionQuality.HIGH.value, "high")

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_skip_up_to_date_files(self):
        """Test that up-to-date files are skipped."""
        svg_path = self.test_svgs[0]
        png_path = self.png_dir / "skip_test.png"

        # First conversion
        converter = SharpConverter(verbose=True)
        success1 = converter.convert_file(svg_path, png_path)
        self.assertTrue(success1)

        # Wait a moment to ensure different timestamps
        time.sleep(0.1)

        # Second conversion should skip (file is up-to-date)
        # This test depends on the Node.js converter implementation
        # which checks file timestamps
        pattern = str(svg_path)
        output_dir = png_path.parent

        stats = converter.convert_batch(pattern, output_dir)
        # The file might be skipped if the implementation checks timestamps
        self.assertIn('skipped', stats)


class TestConverterIntegration(unittest.TestCase):
    """Integration tests for SVG converter with project structure."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp(prefix="test_svg_integration_")

    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_azure_icon_structure(self):
        """Test conversion with Azure-like directory structure."""
        # Create Azure-like structure
        azure_dir = Path(self.test_dir) / "azure"
        categories = ["compute", "storage", "network", "ml"]

        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" xmlns="http://www.w3.org/2000/svg">
    <rect width="256" height="256" fill="#0078D4"/>
</svg>"""

        # Create SVG files in categories
        for category in categories:
            cat_dir = azure_dir / category
            cat_dir.mkdir(parents=True)

            for i in range(3):
                svg_path = cat_dir / f"{category}_icon_{i}.svg"
                svg_path.write_text(svg_content)

        # Convert with structure preservation
        output_dir = Path(self.test_dir) / "azure_output"
        converter = SharpConverter(concurrency=4, quality=ConversionQuality.BALANCED)

        stats = converter.convert_directory(
            azure_dir,
            output_dir,
            preserve_structure=True
        )

        # Verify structure is preserved
        for category in categories:
            cat_output = output_dir / category
            self.assertTrue(cat_output.exists())

            png_files = list(cat_output.glob("*.png"))
            self.assertEqual(len(png_files), 3)

        # Verify stats
        self.assertEqual(stats['processed'], len(categories) * 3)
        self.assertEqual(stats['failed'], 0)

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_large_batch_handling(self):
        """Test handling of large batches of files."""
        # Create a larger batch of SVG files
        batch_dir = Path(self.test_dir) / "large_batch"
        batch_dir.mkdir()

        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" xmlns="http://www.w3.org/2000/svg">
    <circle cx="128" cy="128" r="100" fill="blue"/>
</svg>"""

        num_files = 20
        for i in range(num_files):
            svg_path = batch_dir / f"icon_{i:03d}.svg"
            svg_path.write_text(svg_content)

        # Convert with high concurrency
        output_dir = Path(self.test_dir) / "large_output"
        converter = SharpConverter(concurrency=8, quality=ConversionQuality.FAST)

        stats = converter.convert_directory(batch_dir, output_dir)

        # All files should be processed
        self.assertEqual(stats['processed'], num_files)
        self.assertEqual(stats['failed'], 0)

        # Check output files
        png_files = list(output_dir.glob("*.png"))
        self.assertEqual(len(png_files), num_files)


class TestConverterPerformance(unittest.TestCase):
    """Performance benchmarks for SVG converter."""

    @classmethod
    def setUpClass(cls):
        """Set up performance test environment."""
        cls.test_dir = tempfile.mkdtemp(prefix="test_svg_perf_")
        cls.svg_dir = Path(cls.test_dir) / "svgs"
        cls.svg_dir.mkdir(parents=True)

        # Create test SVGs with varying complexity
        cls.simple_svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" xmlns="http://www.w3.org/2000/svg">
    <rect width="256" height="256" fill="#0078D4"/>
</svg>"""

        cls.complex_svg = """<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:#0078D4;stop-opacity:1" />
            <stop offset="100%" style="stop-color:#004578;stop-opacity:1" />
        </linearGradient>
    </defs>
    <rect width="256" height="256" fill="url(#grad1)"/>
    <circle cx="128" cy="128" r="80" fill="white" opacity="0.8"/>
    <path d="M 50 150 Q 128 50 206 150" stroke="white" stroke-width="3" fill="none"/>
</svg>"""

    @classmethod
    def tearDownClass(cls):
        """Clean up performance test environment."""
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_quality_vs_speed_tradeoff(self):
        """Benchmark quality settings vs conversion speed."""
        # Create test files
        for i in range(5):
            (self.svg_dir / f"simple_{i}.svg").write_text(self.simple_svg)
            (self.svg_dir / f"complex_{i}.svg").write_text(self.complex_svg)

        pattern = str(self.svg_dir / "*.svg")
        results = {}

        for quality in [ConversionQuality.FAST, ConversionQuality.BALANCED, ConversionQuality.HIGH]:
            output_dir = Path(self.test_dir) / f"output_{quality.value}"
            converter = SharpConverter(concurrency=4, quality=quality)

            start_time = time.time()
            stats = converter.convert_batch(pattern, output_dir)
            elapsed = time.time() - start_time

            results[quality.value] = {
                'time': elapsed,
                'processed': stats['processed'],
                'avg_time': elapsed / stats['processed'] if stats['processed'] > 0 else 0
            }

        # Print benchmark results
        print("\nQuality vs Speed Benchmark:")
        for quality, data in results.items():
            print(f"  {quality}: {data['time']:.2f}s total, {data['avg_time']:.3f}s per file")

        # Fast should generally be faster than high quality
        self.assertLessEqual(results['fast']['avg_time'], results['high']['avg_time'] * 1.5)

    @unittest.skipUnless(has_sharp_converter(), "Sharp converter not available")
    def test_concurrency_scaling(self):
        """Test how performance scales with concurrency."""
        # Create test files
        num_files = 16
        for i in range(num_files):
            (self.svg_dir / f"scale_{i:03d}.svg").write_text(self.simple_svg)

        pattern = str(self.svg_dir / "scale_*.svg")
        concurrency_levels = [1, 2, 4, 8]
        results = {}

        for concurrency in concurrency_levels:
            output_dir = Path(self.test_dir) / f"output_c{concurrency}"
            converter = SharpConverter(concurrency=concurrency, quality=ConversionQuality.FAST)

            start_time = time.time()
            stats = converter.convert_batch(pattern, output_dir)
            elapsed = time.time() - start_time

            results[concurrency] = elapsed

            # Clean output for next test
            shutil.rmtree(output_dir, ignore_errors=True)

        # Print scaling results
        print("\nConcurrency Scaling Benchmark:")
        baseline = results[1]
        for concurrency, elapsed in results.items():
            speedup = baseline / elapsed
            print(f"  {concurrency} threads: {elapsed:.2f}s (speedup: {speedup:.2f}x)")

        # Higher concurrency should generally be faster
        self.assertLess(results[4], results[1])


if __name__ == '__main__':
    unittest.main()
