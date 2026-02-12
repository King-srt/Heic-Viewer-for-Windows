# King Viewer

A fullscreen desktop image viewer built with Python + PyQt6 for fast photo browsing, keyboard-first navigation, and useful metadata display.

## Why I built this
Default viewers were not smooth enough for my workflow.  
I wanted a viewer that is:
- fast when moving between photos
- keyboard-friendly
- able to read many formats (including RAW/HEIC when dependencies are installed)
- simple but practical for daily use

## Features
- Fullscreen-first image viewing
- Folder scan with thumbnail sidebar
- Previous/next navigation (`Left/Right`, `Home/End`)
- Selection mode with `PgUp/PgDown`, then open with `Enter/Space`
- Rotate image
- Zoom presets and fit-to-view
- Metadata panel (camera, ISO, shutter, aperture, focal length, date, GPS)
- Help overlay with shortcuts
- First-run help behavior (shown once, toggle with `H`)
- Background loading + cache for smoother navigation

## Supported formats
- Common: JPG, PNG, BMP, GIF, WEBP, TIFF
- HEIC/HEIF (via `pillow-heif`)
- RAW: CR2, NEF, ARW, DNG (via `rawpy`)

## Tech stack
- Python
- PyQt6
- Pillow
- optional: `pillow-heif`, `rawpy`

## Run locally
```bash
python viewer.py
