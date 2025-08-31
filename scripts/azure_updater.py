"""
Azure icon updater module for automated icon updates.

This module handles downloading, mapping, and processing Azure icons
from Microsoft's official icon collection.
"""

import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple
from urllib import request

import config as cfg

from . import resource_dir


def cleaner_azure(filename: str) -> str:
    """
    Apply Azure filename cleansing rules.
    Duplicated from resource.py to avoid circular import.
    Enhanced to handle new Azure icon naming patterns.
    
    Examples:
        "10001--icon-service-Azure-OpenAI.svg" → "azure-openai.svg"
        "00000-icon-service-API-Management.svg" → "api-management.svg"
        "Azure-Sphere.svg" → "sphere.svg"
        "ML + AI.svg" → "ml-ai.svg"
        "Data & Analytics.svg" → "data-and-analytics.svg"
        "Container Apps (preview).svg" → "container-apps-preview.svg"
    
    Rules applied in order:
        1. Remove numeric prefixes (5+ digits followed by hyphens)
        2. Remove "icon-service-" prefix
        3. Replace special characters (+, &, spaces, parentheses)
        4. Collapse multiple hyphens
        5. Remove Azure prefixes from config
        6. Convert to lowercase
    """
    import re

    f = filename
    # Remove .svg extension if present for processing
    if f.endswith('.svg'):
        f = f[:-4]
        add_ext = True
    else:
        add_ext = False

    # Remove numeric prefix (NNNNN- pattern)
    # Matches 5 or more digits followed by hyphen(s)
    f = re.sub(r'^\d{5,}--?', '', f)

    # Remove "icon-service-" pattern
    f = f.replace('icon-service-', '')

    # Apply standard cleaning rules
    f = f.replace("_", "-")
    f = f.replace("(", "").replace(")", "")
    f = f.replace("+", "-")  # Handle plus signs
    f = f.replace("&", "and")  # Handle ampersands
    f = "-".join(f.split())  # Replace spaces with hyphens

    # Clean up multiple consecutive hyphens
    while "--" in f:
        f = f.replace("--", "-")

    # Remove leading/trailing hyphens
    f = f.strip("-")

    # Remove Azure prefixes if configured (case-insensitive)
    if hasattr(cfg, 'FILE_PREFIXES') and 'azure' in cfg.FILE_PREFIXES:
        for p in cfg.FILE_PREFIXES["azure"]:
            if f.lower().startswith(p.lower()):
                f = f[len(p):]
                break

    # Return with or without extension
    if add_ext:
        return f.lower() + '.svg'
    else:
        return f.lower()


def show_download_progress(block_num: int, block_size: int, total_size: int) -> None:
    """Show download progress with size information."""
    downloaded = block_num * block_size
    percent = min(downloaded * 100 / total_size, 100)
    mb_downloaded = downloaded / (1024 * 1024)
    mb_total = total_size / (1024 * 1024)
    print(f"Downloading: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)", end='\r')


def get_current_icons(pvd: str) -> Set[str]:
    """Get list of current Azure icons."""
    icons = set()
    azure_dir = resource_dir(pvd)

    if not os.path.exists(azure_dir):
        return icons

    for root, _, files in os.walk(azure_dir):
        for file in files:
            if file.endswith('.png'):
                # Get relative path from azure root
                rel_path = os.path.relpath(os.path.join(root, file), azure_dir)
                icons.add(rel_path)

    return icons


def backup_icons(pvd: str) -> str:
    """
    Backup current Azure icons.

    Returns:
        str: Path to backup directory
    """
    if not hasattr(cfg, 'AZURE_ICON_SOURCE'):
        print("Warning: AZURE_ICON_SOURCE not found in config.py")
        backup_dir = ".azure_backups"
    else:
        backup_dir = cfg.AZURE_ICON_SOURCE.get('backup_dir', '.azure_backups')

    # Create timestamped backup directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, timestamp)

    # Copy current Azure resources
    source_dir = resource_dir(pvd)
    if os.path.exists(source_dir):
        print(f"Creating backup at {backup_path}")
        shutil.copytree(source_dir, backup_path)

        # Keep only last 3 backups
        cleanup_old_backups(backup_dir, keep=3)
    else:
        print(f"No existing Azure icons to backup at {source_dir}")

    return backup_path


def cleanup_old_backups(backup_dir: str, keep: int = 3) -> None:
    """Keep only the most recent backups."""
    if not os.path.exists(backup_dir):
        return

    # Get all backup directories (format: YYYYMMDD_HHMMSS)
    backups = []
    for item in os.listdir(backup_dir):
        if item != 'update_reports':  # Skip reports directory
            full_path = os.path.join(backup_dir, item)
            if os.path.isdir(full_path):
                backups.append(full_path)

    # Sort by name (timestamp format ensures chronological order)
    backups.sort()

    # Remove old backups
    if len(backups) > keep:
        for old_backup in backups[:-keep]:
            print(f"Removing old backup: {old_backup}")
            shutil.rmtree(old_backup)


def download_azure_icons(pvd: str) -> str:
    """
    Download Azure icons from configured URL.

    Returns:
        str: Path to extracted icons directory
    """
    if not hasattr(cfg, 'AZURE_ICON_SOURCE'):
        raise ValueError("Error: AZURE_ICON_SOURCE not configured in config.py\nPlease ensure config.py contains AZURE_ICON_SOURCE dictionary")

    url = cfg.AZURE_ICON_SOURCE.get('download_url')
    if not url:
        raise ValueError("Error: No download_url specified in AZURE_ICON_SOURCE\nPlease check config.py AZURE_ICON_SOURCE['download_url']")

    print(f"Downloading Azure icons from: {url}")

    # Create temp directory for download
    temp_dir = tempfile.mkdtemp(prefix="azure_icons_")
    zip_path = os.path.join(temp_dir, "azure_icons.zip")

    # Get timeout from config or use default
    timeout = getattr(cfg, 'AZURE_ICON_TIMEOUT', 300)
    
    try:
        # Download the file with timeout
        import socket
        socket.setdefaulttimeout(timeout)
        request.urlretrieve(url, zip_path, reporthook=show_download_progress)
        print("\nDownload complete!")

        # Extract the zip file
        extract_dir = os.path.join(temp_dir, "extracted")
        print(f"Extracting to {extract_dir}")

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        # Skip excluded folders from config
        excluded = getattr(cfg, 'AZURE_EXCLUDED_FOLDERS', ['__MACOSX', '.DS_Store'])
        for excluded_folder in excluded:
            excluded_path = os.path.join(extract_dir, excluded_folder)
            if os.path.exists(excluded_path):
                shutil.rmtree(excluded_path, ignore_errors=True)

        # Remove the zip file to save space
        os.remove(zip_path)

        return extract_dir

    except Exception as e:
        # Clean up on error
        shutil.rmtree(temp_dir, ignore_errors=True)
        error_msg = f"""Error downloading Azure icons: {e}

Troubleshooting:
1. Check internet connection
2. Verify URL is accessible: {url}
3. Try increasing timeout in config.py (AZURE_ICON_TIMEOUT = {timeout})
4. Check if Microsoft has changed the download URL

For manual download, visit:
https://learn.microsoft.com/en-us/azure/architecture/icons/"""
        raise Exception(error_msg)


def map_and_copy_icons(source_dir: str, target_dir: str) -> Dict:
    """
    Map Microsoft categories to diagrams structure and copy icons.
    
    Now tracks whether icons are new, updated, or preserved.

    Returns:
        Dict: Statistics about the mapping process
    """
    if not hasattr(cfg, 'AZURE_CATEGORY_MAP'):
        raise ValueError("Error: AZURE_CATEGORY_MAP not configured in config.py\nThis dictionary maps Microsoft categories to diagrams categories")

    stats = {
        'total_downloaded': 0,
        'mapped_count': 0,
        'new_icons': [],        # Icons that didn't exist before
        'updated_icons': [],    # Icons that were overwritten
        'unmapped_categories': [],
        'category_mappings': {},
        'category_counts': {},
        'final_category_counts': {},
        'icon_list': []
    }

    # Track which icons we process
    processed_icons = set()
    
    # Count total categories and files for progress reporting
    total_categories = 0
    for root, dirs, files in os.walk(source_dir):
        if any(f.endswith('.svg') for f in files):
            total_categories += 1
    
    print(f"  Found {total_categories} Microsoft categories to process")
    categories_processed = 0

    # Find all SVG files in the source directory
    for root, dirs, files in os.walk(source_dir):
        # Skip if no SVG files
        svg_files = [f for f in files if f.endswith('.svg')]
        if not svg_files:
            continue

        # Get the category name (parent folder name)
        rel_path = os.path.relpath(root, source_dir)
        if rel_path == '.':
            # Files in root - put in general
            ms_category = 'General'
        else:
            # Use the folder name as category
            ms_category = os.path.basename(root)

        # Check if this category is mapped
        diag_category = cfg.AZURE_CATEGORY_MAP.get(ms_category)

        if diag_category:
            # Create target directory
            target_cat_dir = os.path.join(target_dir, diag_category)
            os.makedirs(target_cat_dir, exist_ok=True)

            # Copy all SVG files with filename cleansing
            for svg_file in svg_files:
                source_file = os.path.join(root, svg_file)
                # Apply Azure filename cleansing (remove .svg, clean, add .svg back)
                name_without_ext = svg_file[:-4] if svg_file.endswith('.svg') else svg_file
                cleaned_name = cleaner_azure(name_without_ext) + '.svg'
                target_file = os.path.join(target_cat_dir, cleaned_name)
                relative_path = f"{diag_category}/{cleaned_name}"
                
                # Track if this is new or updated
                if os.path.exists(target_file):
                    stats['updated_icons'].append(relative_path)
                else:
                    stats['new_icons'].append(relative_path)
                
                # Copy the file
                shutil.copy2(source_file, target_file)
                processed_icons.add(relative_path)

                stats['total_downloaded'] += 1
                stats['mapped_count'] += 1
                stats['icon_list'].append(relative_path)

            # Update statistics
            stats['category_mappings'][ms_category] = diag_category
            stats['category_counts'][ms_category] = len(svg_files)

            # Update final category counts
            if diag_category not in stats['final_category_counts']:
                stats['final_category_counts'][diag_category] = 0
            stats['final_category_counts'][diag_category] += len(svg_files)

            categories_processed += 1
            print(f"  [{categories_processed}/{total_categories}] Mapped {ms_category} -> {diag_category} ({len(svg_files)} icons)")
        else:
            # Unmapped category
            stats['unmapped_categories'].append(ms_category)
            stats['total_downloaded'] += len(svg_files)
            categories_processed += 1
            print(f"  [{categories_processed}/{total_categories}] WARNING: Unmapped category '{ms_category}' with {len(svg_files)} icons")

    # Get existing icons that weren't processed (preserved icons)
    existing_icons = get_current_icons("azure")
    stats['preserved_icons'] = list(existing_icons - processed_icons)

    return stats


def generate_update_report(stats: Dict, previous_icons: Set[str], current_icons: Set[str]) -> str:
    """Generate detailed update report for additive updates."""
    report = []
    report.append("=" * 60)
    report.append("AZURE ICON UPDATE REPORT (Additive Mode)")
    report.append(f"Date: {datetime.now().isoformat()}")

    if hasattr(cfg, 'AZURE_ICON_SOURCE'):
        report.append(f"Version: {cfg.AZURE_ICON_SOURCE.get('current_version', 'Unknown')}")
    else:
        report.append("Version: Unknown")

    report.append("=" * 60)

    # Summary Statistics
    report.append("\n## SUMMARY")
    report.append(f"Total icons downloaded: {stats['total_downloaded']}")
    report.append(f"Successfully mapped: {stats['mapped_count']}")
    report.append(f"New icons added: {len(stats.get('new_icons', []))}")
    report.append(f"Icons updated: {len(stats.get('updated_icons', []))}")
    report.append(f"Icons preserved (not in source): {len(stats.get('preserved_icons', []))}")
    report.append(f"Unmapped categories: {len(stats['unmapped_categories'])}")

    # Category Mapping Details
    if stats['category_mappings']:
        report.append("\n## CATEGORY MAPPING")
        for ms_cat, diag_cat in sorted(stats['category_mappings'].items()):
            count = stats['category_counts'][ms_cat]
            report.append(f"  {ms_cat} -> {diag_cat} ({count} icons)")

    # New Icons
    if stats.get('new_icons'):
        report.append(f"\n## NEW ICONS ({len(stats['new_icons'])})")
        for icon in sorted(stats['new_icons'])[:20]:  # Show first 20
            report.append(f"  + {icon}")
        if len(stats['new_icons']) > 20:
            report.append(f"  ... and {len(stats['new_icons']) - 20} more")

    # Updated Icons
    if stats.get('updated_icons'):
        report.append(f"\n## UPDATED ICONS ({len(stats['updated_icons'])})")
        for icon in sorted(stats['updated_icons'])[:20]:  # Show first 20
            report.append(f"  ↻ {icon}")
        if len(stats['updated_icons']) > 20:
            report.append(f"  ... and {len(stats['updated_icons']) - 20} more")

    # Preserved Icons (deprecated but kept for backward compatibility)
    if stats.get('preserved_icons'):
        report.append(f"\n## PRESERVED ICONS ({len(stats['preserved_icons'])})")
        report.append("These icons are no longer in the Azure source but kept for backward compatibility:")
        for icon in sorted(stats['preserved_icons'])[:20]:  # Show first 20
            report.append(f"  ⚠ {icon}")
        if len(stats['preserved_icons']) > 20:
            report.append(f"  ... and {len(stats['preserved_icons']) - 20} more")

    # Unmapped Categories
    if stats['unmapped_categories']:
        report.append("\n## UNMAPPED CATEGORIES (ACTION REQUIRED)")
        for cat in sorted(stats['unmapped_categories']):
            report.append(f"  ! {cat}")
            report.append(f"    Suggestion: Add to AZURE_CATEGORY_MAP in config.py")

    # Final Statistics
    if stats['final_category_counts']:
        report.append("\n## FINAL STATISTICS")
        report.append("Icons per category:")
        for cat, count in sorted(stats['final_category_counts'].items()):
            report.append(f"  {cat}: {count}")

    return "\n".join(report)


def update_deprecation_manifest(preserved_icons: List[str], azure_dir: str) -> None:
    """
    Track icons preserved for backward compatibility.
    
    Creates or updates a manifest file that tracks icons that are no longer
    in Microsoft's collection but are kept for backward compatibility.
    
    Args:
        preserved_icons: List of icon paths that are preserved but not in source
        azure_dir: Azure resource directory path
    """
    manifest_path = os.path.join(azure_dir, '.deprecated_icons.json')
    
    manifest = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, IOError):
            # If manifest is corrupted, start fresh
            manifest = {}
    
    # Add newly deprecated icons with timestamp
    current_version = cfg.AZURE_ICON_SOURCE.get('current_version', 'Unknown') if hasattr(cfg, 'AZURE_ICON_SOURCE') else 'Unknown'
    
    for icon in preserved_icons:
        if icon not in manifest:
            manifest[icon] = {
                'deprecated_date': datetime.now().isoformat(),
                'last_seen_version': current_version,
                'status': 'preserved'
            }
        else:
            # Update status if it was previously removed but now exists
            manifest[icon]['status'] = 'preserved'
            manifest[icon]['last_update'] = datetime.now().isoformat()
    
    # Save updated manifest
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    
    print(f"  Updated deprecation manifest: {len(preserved_icons)} preserved icons tracked")


def save_report(report: str, stats: Dict) -> None:
    """Save report in multiple formats."""
    if hasattr(cfg, 'AZURE_ICON_SOURCE'):
        backup_dir = cfg.AZURE_ICON_SOURCE.get('backup_dir', '.azure_backups')
    else:
        backup_dir = '.azure_backups'

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = os.path.join(backup_dir, 'update_reports')
    os.makedirs(report_dir, exist_ok=True)

    # Save text report
    text_path = os.path.join(report_dir, f"update_{timestamp}.txt")
    with open(text_path, 'w') as f:
        f.write(report)

    # Save JSON report for programmatic access
    json_path = os.path.join(report_dir, f"update_{timestamp}.json")
    with open(json_path, 'w') as f:
        json.dump(stats, f, indent=2, default=str)

    # Also save as latest for easy access
    latest_text = os.path.join(report_dir, "latest.txt")
    latest_json = os.path.join(report_dir, "latest.json")
    shutil.copy(text_path, latest_text)
    shutil.copy(json_path, latest_json)

    print(f"\nUpdate report saved to: {text_path}")
    print(f"JSON report saved to: {json_path}")


def update_icons(pvd: str) -> None:
    """
    Complete Azure icon update pipeline.

    This function orchestrates the entire update process:
    1. Backs up current icons
    2. Downloads new icons from configured URL
    3. Maps and copies icons to correct categories
    4. Generates update report
    """
    if pvd != "azure":
        print(f"Error: update_icons only works for 'azure' provider, got '{pvd}'")
        return

    # Check update mode configuration
    update_mode = getattr(cfg, 'AZURE_UPDATE_MODE', 'additive')
    preserve_deprecated = getattr(cfg, 'AZURE_PRESERVE_DEPRECATED', True)
    track_deprecations = getattr(cfg, 'AZURE_TRACK_DEPRECATIONS', True)
    
    mode_desc = "Additive Mode" if update_mode == "additive" else "Sync Mode"
    print(f"\n=== Starting Azure Icon Update ({mode_desc}) ===\n")
    
    if update_mode != "additive":
        print("⚠️  WARNING: Sync mode may delete existing icons and break backward compatibility!")
        print("  Consider using 'additive' mode (AZURE_UPDATE_MODE = 'additive' in config.py)")

    try:
        # Step 1: Get current icons for comparison
        print("Getting current icon list...")
        previous_icons = get_current_icons(pvd)

        # Step 2: Backup current icons
        print("\nBacking up current icons...")
        backup_path = backup_icons(pvd)

        # Step 3: Download new icons
        print("\nDownloading new icons...")
        extracted_dir = download_azure_icons(pvd)

        # Step 4: Handle Azure directory based on update mode
        azure_dir = resource_dir(pvd)
        if update_mode == "sync":
            # Sync mode: Clear existing icons (original behavior)
            if os.path.exists(azure_dir):
                print(f"\nClearing existing icons at {azure_dir} (sync mode)")
                shutil.rmtree(azure_dir)
            os.makedirs(azure_dir, exist_ok=True)
        else:
            # Additive mode: Preserve existing icons (new behavior)
            os.makedirs(azure_dir, exist_ok=True)
            print(f"\nUsing Azure directory: {azure_dir} (preserving existing icons)")

        # Step 5: Map and copy icons
        print("\nMapping categories and copying icons...")
        print(f"  Source: {extracted_dir}")
        print(f"  Target: {azure_dir}")
        stats = map_and_copy_icons(extracted_dir, azure_dir)

        # Step 6: Get new icon list
        current_icons = set(stats['icon_list'])

        # Step 7: Update deprecation manifest if enabled and icons were preserved
        if track_deprecations and stats.get('preserved_icons'):
            print("\nUpdating deprecation manifest...")
            update_deprecation_manifest(stats['preserved_icons'], azure_dir)

        # Step 8: Generate and save report
        print("\nGenerating update report...")
        report = generate_update_report(stats, previous_icons, current_icons)
        save_report(report, stats)

        # Step 9: Clean up temp directory
        print("\nCleaning up temporary files...")
        shutil.rmtree(extracted_dir, ignore_errors=True)
        if os.path.exists(os.path.dirname(extracted_dir)):
            shutil.rmtree(os.path.dirname(extracted_dir), ignore_errors=True)

        # Print summary
        print("\n" + "=" * 60)
        print("UPDATE COMPLETE! (Additive Mode)")
        print(f"  Total icons: {stats['mapped_count']}")
        print(f"  New icons added: {len(stats.get('new_icons', []))}")
        print(f"  Icons updated: {len(stats.get('updated_icons', []))}")
        print(f"  Icons preserved: {len(stats.get('preserved_icons', []))}")

        if stats['unmapped_categories']:
            print(f"\n  ⚠️  {len(stats['unmapped_categories'])} unmapped categories require attention!")
            print("  See the update report for details.")

        print("\nNext steps:")
        print("  1. Review the update report")
        print("  2. Run: ./autogen.sh")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error during update: {e}")
        print("\nYou may need to:")
        print("  1. Check AZURE_ICON_SOURCE configuration in config.py")
        print("  2. Verify the download URL is correct")
        print("  3. Run rollback if needed: python -m scripts.resource rollback_icons azure")
        raise


def rollback_icons(pvd: str) -> None:
    """
    Rollback to a previous Azure icon backup.
    """
    if pvd != "azure":
        print(f"Error: rollback_icons only works for 'azure' provider, got '{pvd}'")
        return

    if hasattr(cfg, 'AZURE_ICON_SOURCE'):
        backup_dir = cfg.AZURE_ICON_SOURCE.get('backup_dir', '.azure_backups')
    else:
        backup_dir = '.azure_backups'

    if not os.path.exists(backup_dir):
        print("No backups found!")
        return

    # Get available backups
    backups = []
    for item in os.listdir(backup_dir):
        if item != 'update_reports':
            full_path = os.path.join(backup_dir, item)
            if os.path.isdir(full_path):
                backups.append((item, full_path))

    if not backups:
        print("No backups found!")
        return

    # Sort by name (timestamp)
    backups.sort(reverse=True)

    print("\nAvailable backups:")
    for i, (name, path) in enumerate(backups):
        print(f"  {i+1}. {name}")

    # Get user choice
    try:
        choice = input("\nSelect backup number (or 'c' to cancel): ")
        if choice.lower() == 'c':
            print("Rollback cancelled.")
            return

        idx = int(choice) - 1
        if idx < 0 or idx >= len(backups):
            print("Invalid selection!")
            return

        selected_name, selected_path = backups[idx]

        # Perform rollback
        azure_dir = resource_dir(pvd)
        print(f"\nRolling back to: {selected_name}")

        if os.path.exists(azure_dir):
            shutil.rmtree(azure_dir)

        shutil.copytree(selected_path, azure_dir)
        print("✓ Rollback complete!")
        print("\nNext steps:")
        print("  Run: ./autogen.sh")

    except (ValueError, KeyboardInterrupt):
        print("\nRollback cancelled.")


# Command functions for resource.py integration
def check_icon_updates(pvd: str) -> None:
    """Check if Azure icon updates are available (placeholder)."""
    print("Azure update checking not yet implemented.")
    print("Please manually check: https://learn.microsoft.com/en-us/azure/architecture/icons/")

    if hasattr(cfg, 'AZURE_ICON_SOURCE'):
        current = cfg.AZURE_ICON_SOURCE.get('current_version', 'Unknown')
        print(f"Current version in config: {current}")
