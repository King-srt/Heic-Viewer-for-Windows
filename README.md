# King Viewer

A fullscreen desktop image viewer built with Python + PyQt6 for fast photo browsing, keyboard-first navigation, and useful metadata display.

---
# Screenshots

![Main Viewer](screenshots/main_view.png)

---

## Why I built this

The main reason I built **King Viewer** is very simple:

> **On Windows, users have to pay just to open HEIC / HEIF images.**

Microsoft requires users to purchase a codec extension from the Microsoft Store in order to view HEIC files — a modern image format that should be **freely accessible**.
This felt unnecessary and unreasonable.
So I built King Viewer to provide:

* **Free access** to HEIC / HEIF images
* Fast, smooth, fullscreen viewing
* Keyboard-first navigation
* Broad format support without artificial restrictions

In short:

> **Basic image viewing should not be locked behind a paywall.**

---

## Features

* Fullscreen-first image viewing
* Folder scan with thumbnail sidebar
* Previous/next navigation (`Left/Right`, `Home/End`)
* Selection mode with `PgUp/PgDown`, then open with `Enter/Space`
* Rotate image
* Zoom presets and fit-to-view
* Metadata panel (camera, ISO, shutter, aperture, focal length, date, GPS)
* Help overlay with shortcuts
* First-run help behavior (shown once, toggle with `H`)
* Background loading + cache for smoother navigation

---

## Supported formats

* Common: JPG, PNG, BMP, GIF, WEBP, TIFF
* HEIC/HEIF (via `pillow-heif`)
* RAW: CR2, NEF, ARW, DNG (via `rawpy`)

---

## Tech stack

* Python 3.9+
* PyQt6
* Pillow
* `pillow-heif`, `rawpy`

---

# Installation

## 1. Clone repository

```bash
https://github.com/King-srt/Heic-Viewer-for-Windows.git
cd Heic-Viewer-for-Windows
```

## 2. Create virtual environment (recommended but optional)

```bash
python -m venv venv
venv\\Scripts\\activate   # Windows
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```
---

# Run locally

```bash
python viewer.py
```

---

# Build standalone application (Windows)

## Install PyInstaller

```bash
pip install pyinstaller
```

## Build portable app 

make sure u have the icon -> mine is named icon.png

```bash
python -m PyInstaller --noconfirm --windowed --onedir \
  --name KingViewer \
  --icon icon.png \
  --hidden-import=PIL.ImageQt \
  --hidden-import=pillow_heif \
  --hidden-import=PyQt6.sip \
  viewer.py
```

### Output

```
dist/KingViewer/
```

To distribute the app, **zip and share the entire ********KingViewer******** folder**.

---

# Keyboard shortcuts

| Key           | Action                 |
| ------------- | ---------------------- |
| Left / Right  | Previous / Next image  |
| PgUp / PgDown | Navigate file list     |
| Enter / Space | Open selected image    |
| R             | Rotate image           |
| Mouse Wheel   | Zoom                   |
| 1             | Fit to screen          |
| 2             | 100% zoom              |
| 3             | 200% zoom              |
| H             | Toggle help overlay    |
| T             | Toggle thumbnail panel |
| E             | Toggle metadata panel  |
| Esc           | Exit fullscreen        |

---

# Requirements file (requirements.txt)

```txt
PyQt6
Pillow
pillow-heif
rawpy
```

---

# License

None

---

# Project goals

King Viewer is designed to be:

* fast
* stable
* keyboard-first
* professional-grade

Suitable for photography workflows, forensic image analysis, and daily image browsing.

---



