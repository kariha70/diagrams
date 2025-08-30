"""
resources.py provides useful tools for resources processing.

There are 2 commands available.
- clean: clean and unify the resources file names with some rules.
- round: generate the rounded images from the original squared images.
"""

import os
import subprocess
import sys

import config as cfg

from . import resource_dir

_usage = "Usage: resource.py <cmd> <pvd>"


def cleaner_onprem(f):
    f = f.replace("_", "-")
    return f.lower()


def cleaner_aws(f):
    f = f.replace("_", "-")
    f = f.replace("@4x", "")
    f = f.replace("@5x", "")
    f = f.replace("2.0", "2-0")
    f = f.replace("-light-bg4x", "")
    f = f.replace("-light-bg", "")
    for p in cfg.FILE_PREFIXES["aws"]:
        if f.startswith(p):
            f = f[len(p):]
            break
    return f.lower()


def cleaner_azure(f):
    f = f.replace("_", "-")
    f = f.replace("(", "").replace(")", "")
    f = "-".join(f.split())
    for p in cfg.FILE_PREFIXES["azure"]:
        if f.startswith(p):
            f = f[len(p):]
            break
    return f.lower()


def cleaner_gcp(f):
    f = f.replace("_", "-")
    f = "-".join(f.split())
    for p in cfg.FILE_PREFIXES["gcp"]:
        if f.startswith(p):
            f = f[len(p):]
            break
    return f.lower()


def cleaner_ibm(f):
    f = f.replace("_", "-")
    f = "-".join(f.split())
    for p in cfg.FILE_PREFIXES["ibm"]:
        if f.startswith(p):
            f = f[len(p):]
            break
    return f.lower()


def cleaner_firebase(f):
    f = f.replace("_", "-")
    f = "-".join(f.split())
    for p in cfg.FILE_PREFIXES["firebase"]:
        if f.startswith(p):
            f = f[len(p):]
            break
    return f.lower()


def cleaner_k8s(f):
    f = f.replace("-256", "")
    for p in cfg.FILE_PREFIXES["k8s"]:
        if f.startswith(p):
            f = f[len(p):]
            break
    return f.lower()


def cleaner_digitalocean(f):
    f = f.replace("-32", "")
    for p in cfg.FILE_PREFIXES["digitalocean"]:
        if f.startswith(p):
            f = f[len(p):]
            break
    return f.lower()


def cleaner_alibabacloud(f):
    for p in cfg.FILE_PREFIXES["alibabacloud"]:
        if f.startswith(p):
            f = f[len(p):]
            break
    return f.lower()


def cleaner_oci(f):
    f = f.replace(" ", "-")
    f = f.replace("_", "-")
    for p in cfg.FILE_PREFIXES["oci"]:
        if f.startswith(p):
            f = f[len(p):]
            break
    return f.lower()


def cleaner_programming(f):
    return f.lower()


def cleaner_generic(f):
    return f.lower()


def cleaner_saas(f):
    return f.lower()


def cleaner_elastic(f):
    return f.lower()


def cleaner_outscale(f):
    return f.lower()


def cleaner_openstack(f):
    return f.lower()


def cleaner_gis(f):
    return f.lower()


cleaners = {
    "onprem": cleaner_onprem,
    "aws": cleaner_aws,
    "azure": cleaner_azure,
    "digitalocean": cleaner_digitalocean,
    "gcp": cleaner_gcp,
    "ibm": cleaner_ibm,
    "firebase": cleaner_firebase,
    "k8s": cleaner_k8s,
    "alibabacloud": cleaner_alibabacloud,
    "oci": cleaner_oci,
    "programming": cleaner_programming,
    "saas": cleaner_saas,
    "elastic": cleaner_elastic,
    "outscale": cleaner_outscale,
    "generic": cleaner_generic,
    "openstack": cleaner_openstack,
    "gis": cleaner_gis,
}


def clean_png(pvd: str) -> None:
    """Refine the resources files names."""

    def _rename(base: str, png: str):
        new = cleaners[pvd](png)
        old_path = os.path.join(base, png)
        new_path = os.path.join(base, new)
        os.rename(old_path, new_path)

    for root, _, files in os.walk(resource_dir(pvd)):
        pngs = filter(lambda f: f.endswith(".png"), files)
        [_rename(root, png) for png in pngs]


def round_png(pvd: str) -> None:
    """Round the images."""

    def _round(base: str, path: str):
        path = os.path.join(base, path)
        subprocess.run([cfg.CMD_ROUND, *cfg.CMD_ROUND_OPTS, path])

    for root, _, files in os.walk(resource_dir(pvd)):
        pngs = filter(lambda f: f.endswith(".png"), files)
        paths = filter(lambda f: "rounded" not in f, pngs)
        [_round(root, path) for path in paths]


def svg2png_sharp(pvd: str) -> None:
    """Convert SVG to PNG using sharp (Node.js) converter for better performance."""
    try:
        from .svg_converter import SharpConverter, has_sharp_converter
        
        if not has_sharp_converter():
            print("Sharp converter not available, falling back to inkscape")
            return svg2png_inkscape(pvd)
        
        converter = SharpConverter(
            concurrency=cfg.SHARP_CONCURRENCY,
            quality=cfg.SHARP_QUALITY,
            size=cfg.SHARP_SIZE,
            verbose=True
        )
        
        input_dir = resource_dir(pvd)
        output_dir = resource_dir(pvd)
        
        print(f"Converting SVGs using sharp converter (concurrency: {cfg.SHARP_CONCURRENCY})")
        stats = converter.convert_directory(
            input_dir,
            output_dir,
            preserve_structure=True
        )
        
        print(f"Conversion complete: {stats['processed']} processed, {stats['failed']} failed")
        
        # Remove original SVG files after successful conversion
        if stats['processed'] > 0:
            for root, _, files in os.walk(resource_dir(pvd)):
                svgs = filter(lambda f: f.endswith(".svg"), files)
                for svg in svgs:
                    svg_path = os.path.join(root, svg)
                    # Check if corresponding PNG exists before removing SVG
                    png_path = svg_path.replace('.svg', '.png')
                    if os.path.exists(png_path):
                        os.remove(svg_path)
                        
    except ImportError:
        print("Sharp converter module not found, falling back to inkscape")
        return svg2png_inkscape(pvd)
    except Exception as e:
        print(f"Sharp converter failed: {e}, falling back to inkscape")
        return svg2png_inkscape(pvd)


def svg2png_inkscape(pvd: str) -> None:
    """Convert the svg into png using inkscape (original implementation)."""

    def _convert(base: str, path: str):
        path = os.path.join(base, path)
        subprocess.run([cfg.CMD_SVG2PNG, *cfg.CMD_SVG2PNG_OPTS, path])
        subprocess.run(["rm", path])

    for root, _, files in os.walk(resource_dir(pvd)):
        svgs = filter(lambda f: f.endswith(".svg"), files)
        [_convert(root, path) for path in svgs]


def svg2png(pvd: str) -> None:
    """Convert the svg into png - automatically selects the best converter."""
    
    # Check environment variable first (set by autogen.sh)
    converter = os.environ.get('DIAGRAMS_SVG_CONVERTER', None)
    
    # If not set, check configured converter preference
    if not converter:
        converter = getattr(cfg, 'SVG_CONVERTER', 'auto')
    
    if converter == "sharp":
        return svg2png_sharp(pvd)
    elif converter == "imagemagick":
        return svg2png2(pvd)
    elif converter == "inkscape":
        return svg2png_inkscape(pvd)
    elif converter == "auto":
        # Try sharp first for better performance, fall back to inkscape
        try:
            from .svg_converter import has_sharp_converter
            if has_sharp_converter():
                return svg2png_sharp(pvd)
        except ImportError:
            pass
        return svg2png_inkscape(pvd)
    else:
        # Default to inkscape for unknown converter types
        return svg2png_inkscape(pvd)


def svg2png2(pvd: str) -> None:
    """Convert the svg into png using image magick"""

    def _convert(base: str, path: str):
        path_src = os.path.join(base, path)
        path_dest = path_src.replace(".svg", ".png")
        subprocess.run([cfg.CMD_SVG2PNG_IM, *
                        cfg.CMD_SVG2PNG_IM_OPTS, path_src, path_dest])
        subprocess.run(["rm", path_src])

    for root, _, files in os.walk(resource_dir(pvd)):
        svgs = filter(lambda f: f.endswith(".svg"), files)
        [_convert(root, path) for path in svgs]


# Import Azure updater functions
try:
    from .azure_updater import (
        update_icons,
        backup_icons,
        rollback_icons,
        check_icon_updates
    )
    icon_commands = {
        "update_icons": update_icons,
        "backup_icons": backup_icons,
        "rollback_icons": rollback_icons,
        "check_icons": check_icon_updates,
    }
except ImportError:
    # Icon updater not available
    icon_commands = {}

# fmt: off
commands = {
    "clean": clean_png,
    "round": round_png,
    "svg2png": svg2png,
    "svg2png2": svg2png2,
    "svg2png_sharp": svg2png_sharp,  # Direct access to sharp converter
    "svg2png_inkscape": svg2png_inkscape,  # Direct access to inkscape converter
    **icon_commands,  # Add icon update commands if available
}
# fmt: on

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(_usage)
        sys.exit()

    cmd = sys.argv[1]
    pvd = sys.argv[2]
    if cmd not in commands:
        sys.exit()
    if pvd not in cfg.PROVIDERS:
        sys.exit()
    commands[cmd](pvd)
