#!/bin/bash

app_root_dir="diagrams"

# Parse command line arguments
UPDATE_AZURE=false
USE_SHARP=false
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --update-azure) UPDATE_AZURE=true ;;
        --use-sharp) USE_SHARP=true ;;
        --help)
            echo "Usage: $0 [--update-azure] [--use-sharp]"
            echo "  --update-azure: Update Azure icons from Microsoft before processing"
            echo "  --use-sharp: Use fast sharp converter for SVG to PNG conversion (requires Node.js)"
            exit 0
            ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

# Check and install sharp converter dependencies if requested
if [ "$USE_SHARP" = true ]; then
    if [ -x "$(command -v node)" ]; then
        if [ ! -d "scripts/svg_converter/node_modules" ]; then
            echo "Installing sharp converter dependencies..."
            cd scripts/svg_converter && npm install && cd ../..
            if [ $? -eq 0 ]; then
                echo "Sharp converter dependencies installed successfully"
                # Set environment variable to use sharp converter
                export DIAGRAMS_SVG_CONVERTER="sharp"
            else
                echo "Warning: Failed to install sharp converter dependencies, will use inkscape"
                export DIAGRAMS_SVG_CONVERTER="inkscape"
            fi
        else
            echo "Sharp converter ready"
            export DIAGRAMS_SVG_CONVERTER="sharp"
        fi
    else
        echo "Warning: Node.js not found, cannot use sharp converter"
        echo "Install Node.js for 10-50x faster SVG conversion"
        export DIAGRAMS_SVG_CONVERTER="inkscape"
    fi
fi

# Update Azure icons if requested
if [ "$UPDATE_AZURE" = true ]; then
    echo "Updating Azure icons from Microsoft..."
    python -m scripts.resource update_icons azure
    echo "Azure icons updated successfully"
fi

# NOTE: azure icon set is not latest version
providers=(
  "onprem"
  "aws"
  "azure"
  "digitalocean"
  "gcp"
  "ibm"
  "firebase"
  "k8s"
  "alibabacloud"
  "oci"
  "programming"
  "saas"
  "elastic"
  "generic"
  "openstack"
  "outscale"
  "gis"
)

if ! [ -x "$(command -v round)" ]; then
  echo 'round is not installed'
  exit 1
fi

if ! [ -x "$(command -v inkscape)" ]; then
  echo 'inkscape is not installed'
  exit 1
fi

if ! [ -x "$(command -v convert)" ]; then
  echo 'image magick is not installed'
  exit 1
fi

if ! [ -x "$(command -v black)" ]; then
  echo 'black is not installed'
  exit 1
fi

# preprocess the resources
for pvd in "${providers[@]}"; do
  # convert the svg to png for azure provider
  if [ "$pvd" = "onprem" ] || [ "$pvd" = "azure" ]; then
    echo "converting the svg to png using inkscape for provider '$pvd'"
    python -m scripts.resource svg2png "$pvd"
  fi
  if [ "$pvd" == "oci" ] || [ "$pvd" = "ibm" ]; then
    echo "converting the svg to png using image magick for provider '$pvd'"
    python -m scripts.resource svg2png2 "$pvd"
  fi
  echo "cleaning the resource names for provider '$pvd'"
  python -m scripts.resource clean "$pvd"
  # round the all png images for aws provider
  if [ "$pvd" = "aws" ]; then
    echo "rounding the resources for provider '$pvd'"
    python -m scripts.resource round "$pvd"
  fi
done

# generate the module classes and docs
for pvd in "${providers[@]}"; do
  echo "generating the modules & docs for provider '$pvd'"
  python -m scripts.generate "$pvd"
done

# Generate doc for custom module
echo "generating the docs for custom"
python -m scripts.generate "custom"

# copy icons across to website
echo "copying icons to website static folder"
cp -r resources website/static/img/

# run black
echo "linting the all the diagram modules"
black "$app_root_dir"/**/*.py
