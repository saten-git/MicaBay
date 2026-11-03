# MicaBay - Technical Architecture & Feature Tracker

This document provides a comprehensive tracking record of all modules, algorithms, UI patterns, and system integration services built for **MicaBay**.

---

## 🏗️ Architectural Overview

```
                      ┌────────────────────────────────────────┐
                      │                main.py                 │
                      │   (QApplication, Tray, Lifecycle)      │
                      └──────────────────┬─────────────────────┘
                                         │
                 ┌───────────────────────┴────────────────────────┐
                 ▼                                                ▼
     ┌───────────────────────┐                        ┌───────────────────────┐
     │      NotchWindow      │                        │    SettingsWindow     │
     │ (Frameless Topmost    │                        │ (Preferences Dialog)  │
     │  Layered Window)      │                        └───────────────────────┘
     └───────────┬───────────┘
                 │
       ┌─────────┴───────────────────────┐
       ▼                                 ▼
┌──────────────┐                 ┌──────────────┐
│  CompactBar  │                 │  Dashboard   │
│ (Resting/    │                 │   Widget     │
│  Taskbar)    │                 │  (Expanded)  │
└──────────────┘                 └──────────────┘
```

---

## 🧩 Components & Module Details

### 1. Window & Compositing Architecture (`notch_window.py`)
- **Layered Window Hit-Testing**:
  - Employs `Qt.WidgetAttribute.WA_TranslucentBackground` and `Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool`.
  - Solves the Windows DWM `HTTRANSPARENT` alpha=0 click-through bug by filling the compact background with `QColor(0, 0, 0, 1)`. An alpha of $1/255$ is visually imperceptible to human vision on 8-bit displays, but forces the Windows kernel to register the bar as a solid mouse hit target over `Shell_TrayWnd`.
- **Three Window Geometries**:
  - `make_notch_path()` generates parametric Bezier curves:
    - **Top Notch**: Upper bezel cubic curves with smooth corner radii and dynamic ear extensions.
    - **Taskbar Pill**: Vertically mirrored Bezier curves emerging from the bottom bezel.
    - **Island**: Symmetrical rounded rectangles for floating pills.
    - **Expanded Dashboard**: Full rounded card floating directly above the taskbar.
- **Edge Light Physics**:
  - Animated traveling beam algorithms:
    - `twin_comets`: Symmetrical head-tail traveling rays with mid-reflection flashes.
    - `comet`: Unidirectional circuit around the notch perimeter.
    - `breathe`: Sinusoidal ambient pulse.
- **Baseline Parabolic Equalizer**:
  - Low-height acoustic baseline ($1.2\text{px} - 3.8\text{px}$) with parabolic envelope damping at the edges.
  - Generates organic harmonic frequencies when media is active, and rests at grounded micro-ticks when paused.

---

### 2. Elastic Taskbar Layout Engine (`compact_bar.py`)
- **Self-Elastic Boundary Optimization**:
  - Anchors elements strictly from left to right:
    `[Weather] [Art] [Song Title] [Equalizer] [Clock] [Battery]`
  - Bounded by the user's Start button coordinate ($X_{\text{limit}}$, default $505\text{px}$).
- **Collision Guard ("Remove & Halt" Algorithm)**:
  - If content width exceeds $X_{\text{limit}} - 14\text{px}$:
    1. Checks if both Clock and Battery fit comfortably with legible title space.
    2. If Battery would collide with the Start button: removes and halts Battery.
    3. If Clock would also collide: removes and halts Clock.
    4. Truncates Song Title with ellipsis before the Start button.
  - The window width dynamically contracts and expands with content, ensuring the Windows 11 Start button is never covered.
- **Dynamic Weather Badge Rotation**:
  - Alternates every 5.5 seconds between current temperature (`19°C`) and humidity description (`Humid`), matching native Windows 11 taskbar widget behavior.
- **Universal Click Redirector**:
  - `CompactClickRedirector` intercepts mouse presses across all child widgets, labels, and spacers, forwarding single clicks to smoothly expand the dashboard.

---

### 3. Productivity Dashboard Suite (`dashboard_widget.py`)
- **Hardware Performance Gauges**:
  - Real-time radial meters for CPU, Memory, and Disk utilization using custom `CircularGauge` widgets.
- **Active Window Screen Time Tracker**:
  - Hooks foreground window changes via Win32 `GetForegroundWindow` and `GetWindowThreadProcessId`.
  - Aggregates daily and weekly application usage stored in `screentime.json`.
  - Displays categorized weekly bar charts with day-by-day breakdowns.
- **Pomodoro Focus Timer**:
  - 25:00 countdown timer with play/pause/reset states and progress ring.
- **Clipboard History**:
  - Persistent stack of recently copied snippets with 1-click re-copying.
- **Quick Notes Scratchpad**:
  - Instant text notes with debounced persistence.
- **Floating Pill Dock**:
  - Horizontal segmented dock for switching between Performance, Screen Time, Focus, Clipboard, and Notes.

---

### 4. Background Services & OS Hooks

| Service File | Underlying Technology | Purpose |
| :--- | :--- | :--- |
| `media_service.py` | `winsdk` / `winrt` SMTC | Listens for system media sessions, track changes, playback status, and extracts album artwork thumbnails. |
| `weather_service.py` | Open-Meteo REST API & `ipapi.co` | Geocodes user location, fetches temperature, humidity, weather codes, and calculates day/night icons. |
| `clipboard_service.py` | `QClipboard.dataChanged` | Captures text, images, and file paths; formats previews for toasts. |
| `system_service.py` | `psutil` & Win32 API | Monitors CPU, RAM, Disk, Battery percentage/charging status, and active foreground window time. |
| `volume_service.py` | `pycaw` (Windows CoreAudio) | Polls master audio endpoint volume and mute state to trigger HUD. |
| `color_extractor.py` | Pillow / `QImage` sampling | Analyzes thumbnail byte arrays to determine dominant vibrant colors for glowing accents. |
| `settings_service.py` | JSON storage (`settings.json`) | Thread-safe, reactive settings manager emitting signals on preference modifications. |

---

## 📋 Comprehensive Feature Checklist

- [x] **Top Bezel Notch** with S-curve ear transitions
- [x] **Taskbar Pill** with inverted notch geometry
- [x] **Full Taskbar Mode** (borderless native look)
- [x] **Self-Elastic Adjustable Bar** with Start Button Collision Guard
- [x] **Alpha=1 Hit-Test Layering** for 100% click reliability
- [x] **Glass Specular Refraction Highlight**
- [x] **Edge-to-Center Transparency Slider (0% - 100%)**
- [x] **Low-Height Baseline Acoustic Equalizer**
- [x] **Dynamic Traveling Comets & Breath Light Effects**
- [x] **Windows SMTC Media Playback Integration**
- [x] **Dynamic Album Art Accent Color Extraction**
- [x] **Live Open-Meteo Weather with Day/Night Icons**
- [x] **5.5s Temperature / Humidity Alternation**
- [x] **Real-time CPU / RAM / Disk Radial Gauges**
- [x] **Foreground Window Screen Time & Weekly Bar Visualizer**
- [x] **25:00 Pomodoro Focus Timer**
- [x] **Clipboard History & Notification Toasts**
- [x] **Quick Notes Scratchpad**
- [x] **Drag-and-Drop File Shelf**
- [x] **CoreAudio Hardware Volume HUD**
- [x] **System Tray Icon & Menu**
- [x] **Silent Background Launcher (`Launch_MicaBay.bat`)**
