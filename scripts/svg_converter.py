"""
Python wrapper for high-performance SVG to PNG conversion using Node.js sharp library.

This module provides a Python interface to the Node.js-based SVG converter,
offering significant performance improvements over Inkscape for batch conversions.
"""

import os
import sys
import json
import subprocess
import shutil
import time
from pathlib import Path
from typing import Optional, Callable, Dict, List, Union
from enum import Enum


class ConversionQuality(Enum):
    """Quality presets for conversion."""
    FAST = "fast"
    BALANCED = "balanced"
    HIGH = "high"


class ConversionError(Exception):
    """Exception raised when conversion fails."""
    pass


class SharpConverter:
    """
    Python wrapper for Node.js sharp-based SVG to PNG converter.
    
    Provides high-performance batch conversion with progress tracking
    and error handling.
    """
    
    def __init__(
        self,
        concurrency: int = 4,
        quality: ConversionQuality = ConversionQuality.BALANCED,
        size: int = 256,
        verbose: bool = False
    ):
        """
        Initialize the converter.
        
        Args:
            concurrency: Number of parallel conversions (1-16)
            quality: Conversion quality preset
            size: Output size in pixels
            verbose: Enable verbose output
        """
        self.converter_path = Path(__file__).parent / 'svg_converter' / 'converter.js'
        self.concurrency = max(1, min(16, concurrency))  # Clamp between 1 and 16
        self.quality = quality.value if isinstance(quality, ConversionQuality) else quality
        self.size = size
        self.verbose = verbose
        
        # Check if Node.js is available
        if not self._check_node():
            raise ConversionError("Node.js is not installed or not in PATH")
        
        # Check if converter exists and dependencies are installed
        if not self.converter_path.exists():
            raise ConversionError(f"Converter not found at {self.converter_path}")
        
        if not self._check_dependencies():
            raise ConversionError(
                "Node.js dependencies not installed. "
                "Run: cd scripts/svg_converter && npm install"
            )
    
    def _check_node(self) -> bool:
        """Check if Node.js is available."""
        try:
            result = subprocess.run(
                ['node', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def _check_dependencies(self) -> bool:
        """Check if Node.js dependencies are installed."""
        node_modules = self.converter_path.parent / 'node_modules'
        return node_modules.exists() and (node_modules / 'sharp').exists()
    
    def _run_converter(
        self,
        args: List[str],
        callback: Optional[Callable[[Dict], None]] = None
    ) -> Dict:
        """
        Run the Node.js converter with given arguments.
        
        Args:
            args: Command line arguments for converter
            callback: Optional callback for progress updates
            
        Returns:
            Dictionary with conversion statistics
        """
        cmd = ['node', str(self.converter_path)] + args
        
        if self.verbose:
            print(f"Running: {' '.join(cmd)}")
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            stats = {
                'processed': 0,
                'failed': 0,
                'skipped': 0,
                'total': 0
            }
            
            # Read output line by line
            with process.stdout as stdout:
                for line in stdout:
                    line = line.strip()
                    if not line:
                        continue
                    
                    if self.verbose:
                        print(line)
                    
                    # Parse progress updates
                    if 'Progress:' in line:
                        try:
                            # Extract progress like "Progress: 10/100 (10.0%)"
                            parts = line.split('Progress:')[1].strip()
                            current, total = parts.split('/')[0], parts.split('/')[1].split()[0]
                            stats['processed'] = int(current)
                            stats['total'] = int(total)
                            
                            if callback:
                                callback({
                                    'current': stats['processed'],
                                    'total': stats['total'],
                                    'percent': (stats['processed'] / stats['total'] * 100) if stats['total'] > 0 else 0
                                })
                        except (ValueError, IndexError):
                            pass
                    
                    # Parse final statistics
                    elif '✓ Processed:' in line:
                        stats['processed'] = int(line.split(':')[1].strip())
                    elif '⊙ Skipped:' in line:
                        stats['skipped'] = int(line.split(':')[1].strip())
                    elif '✗ Failed:' in line:
                        stats['failed'] = int(line.split(':')[1].strip())
                    elif 'Total files:' in line:
                        stats['total'] = int(line.split(':')[1].strip())
            
            # Wait for process to complete
            with process.stderr as stderr:
                stderr_output = stderr.read()
            process.wait()
            
            if process.returncode != 0 and stats['processed'] == 0:
                raise ConversionError(f"Converter failed: {stderr_output}")
            
            return stats
            
        except subprocess.TimeoutExpired:
            process.kill()
            raise ConversionError("Conversion timed out")
        except Exception as e:
            raise ConversionError(f"Conversion failed: {str(e)}")
    
    def convert_file(
        self,
        svg_path: Union[str, Path],
        png_path: Union[str, Path]
    ) -> bool:
        """
        Convert a single SVG file to PNG.
        
        Args:
            svg_path: Path to input SVG file
            png_path: Path to output PNG file
            
        Returns:
            True if successful, False otherwise
        """
        svg_path = Path(svg_path)
        png_path = Path(png_path)
        
        if not svg_path.exists():
            raise FileNotFoundError(f"SVG file not found: {svg_path}")
        
        # Ensure output directory exists
        png_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create temporary directory for single file conversion
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            # Copy SVG to temp directory with same name as desired output
            temp_svg = Path(tmpdir) / svg_path.name
            shutil.copy2(svg_path, temp_svg)
            
            temp_output_dir = Path(tmpdir) / "output"
            temp_output_dir.mkdir()
            
            args = [
                '--pattern', str(temp_svg),
                '--output', str(temp_output_dir),
                '--concurrency', '1',
                '--quality', self.quality,
                '--size', str(self.size)
            ]
            
            if self.verbose:
                args.append('--verbose')
            
            stats = self._run_converter(args)
            
            # Move the output file to the desired location
            if stats['processed'] > 0:
                temp_png = temp_output_dir / (svg_path.stem + '.png')
                if temp_png.exists():
                    shutil.move(str(temp_png), str(png_path))
                    return True
            
            return False
    
    def convert_batch(
        self,
        pattern: str,
        output_dir: Union[str, Path],
        callback: Optional[Callable[[Dict], None]] = None
    ) -> Dict:
        """
        Convert SVG files matching a glob pattern.
        
        Args:
            pattern: Glob pattern for SVG files (e.g., "*.svg", "**/*.svg")
            output_dir: Output directory for PNG files
            callback: Optional progress callback
            
        Returns:
            Dictionary with conversion statistics
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        args = [
            '--pattern', pattern,
            '--output', str(output_dir),
            '--concurrency', str(self.concurrency),
            '--quality', self.quality,
            '--size', str(self.size)
        ]
        
        if self.verbose:
            args.append('--verbose')
        
        return self._run_converter(args, callback)
    
    def convert_directory(
        self,
        input_dir: Union[str, Path],
        output_dir: Union[str, Path],
        callback: Optional[Callable[[Dict], None]] = None,
        preserve_structure: bool = True
    ) -> Dict:
        """
        Convert all SVG files in a directory.
        
        Args:
            input_dir: Input directory containing SVG files
            output_dir: Output directory for PNG files
            callback: Optional progress callback
            preserve_structure: Preserve directory structure
            
        Returns:
            Dictionary with conversion statistics
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        
        if not input_dir.exists():
            raise FileNotFoundError(f"Input directory not found: {input_dir}")
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if preserve_structure:
            args = [
                '--input', str(input_dir),
                '--output', str(output_dir),
                '--concurrency', str(self.concurrency),
                '--quality', self.quality,
                '--size', str(self.size)
            ]
        else:
            # Use pattern for flat output
            pattern = str(input_dir / '**' / '*.svg')
            args = [
                '--pattern', pattern,
                '--output', str(output_dir),
                '--concurrency', str(self.concurrency),
                '--quality', self.quality,
                '--size', str(self.size)
            ]
        
        if self.verbose:
            args.append('--verbose')
        
        return self._run_converter(args, callback)


def convert_svg_to_png(
    svg_path: Union[str, Path],
    png_path: Union[str, Path],
    quality: str = "balanced",
    size: int = 256
) -> bool:
    """
    Convenience function to convert a single SVG to PNG.
    
    Args:
        svg_path: Path to input SVG
        png_path: Path to output PNG
        quality: Quality preset (fast, balanced, high)
        size: Output size in pixels
        
    Returns:
        True if successful
    """
    converter = SharpConverter(quality=quality, size=size)
    return converter.convert_file(svg_path, png_path)


def batch_convert_svgs(
    input_pattern: str,
    output_dir: Union[str, Path],
    concurrency: int = 4,
    quality: str = "balanced",
    progress_callback: Optional[Callable] = None
) -> Dict:
    """
    Batch convert SVG files to PNG.
    
    Args:
        input_pattern: Glob pattern for input files
        output_dir: Output directory
        concurrency: Number of parallel conversions
        quality: Quality preset
        progress_callback: Optional progress callback
        
    Returns:
        Conversion statistics
    """
    converter = SharpConverter(concurrency=concurrency, quality=quality)
    return converter.convert_batch(input_pattern, output_dir, progress_callback)


# Fallback functions for compatibility
def has_sharp_converter() -> bool:
    """Check if sharp converter is available."""
    try:
        converter = SharpConverter()
        return True
    except ConversionError:
        return False


def get_converter_info() -> Dict:
    """Get information about the converter."""
    converter_path = Path(__file__).parent / 'svg_converter'
    node_modules = converter_path / 'node_modules'
    
    info = {
        'available': False,
        'path': str(converter_path),
        'dependencies_installed': node_modules.exists(),
        'node_version': None
    }
    
    try:
        result = subprocess.run(
            ['node', '--version'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            info['node_version'] = result.stdout.strip()
    except:
        pass
    
    info['available'] = info['dependencies_installed'] and info['node_version'] is not None
    
    return info


if __name__ == "__main__":
    # Test the wrapper
    print("Sharp SVG Converter - Python Wrapper")
    print("=" * 50)
    
    info = get_converter_info()
    print(f"Converter available: {info['available']}")
    print(f"Node.js version: {info['node_version']}")
    print(f"Dependencies installed: {info['dependencies_installed']}")
    
    if info['available']:
        print("\nTesting conversion...")
        
        # Create a test SVG
        test_svg = Path("test_wrapper.svg")
        test_png = Path("test_wrapper.png")
        
        svg_content = """<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" xmlns="http://www.w3.org/2000/svg">
    <rect width="256" height="256" fill="#0078D4"/>
    <circle cx="128" cy="128" r="80" fill="white"/>
    <text x="128" y="140" text-anchor="middle" fill="#0078D4" font-size="32">PYTHON</text>
</svg>"""
        
        test_svg.write_text(svg_content)
        
        try:
            # Test single file conversion
            converter = SharpConverter(verbose=True)
            success = converter.convert_file(test_svg, test_png)
            
            if success and test_png.exists():
                print(f"✓ Conversion successful! Output: {test_png} ({test_png.stat().st_size} bytes)")
            else:
                print("✗ Conversion failed")
            
            # Clean up
            test_svg.unlink()
            if test_png.exists():
                test_png.unlink()
                
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("\nConverter not available. Please install Node.js dependencies:")
        print("  cd scripts/svg_converter && npm install")