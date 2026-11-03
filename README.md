# MicaBay 🌊

> **The Sleek Dynamic Notch & Native Taskbar Companion for Windows 11 & 10**  
> Built with **Python 3.12** and **PySide6 (Qt6)**.

---

## 🌟 Overview

**MicaBay** transforms the Windows experience with an ultra-responsive, hardware-accelerated dynamic pill and taskbar integration. Whether perched at the top bezel like an organic display notch, nestled as a reversed pill emerging from the bottom taskbar, or seamlessly utilizing the left taskbar space with a borderless native integration, MicaBay blends fluid animations with deep Windows system hooks.

---

## ✨ Core Features

### 1. 📐 Three Dynamic Placement Modes
* **Top Bezel Notch**:
  * Pinned at the top-center of the screen.
  * Organic S-curve ears that blend smoothly into your physical display bezel.
  * Supports **Notch**, **Island (Floating)**, and **Line** geometries.
* **Taskbar Pill**:
  * Positioned on the bottom taskbar with reverse-fillet curves emerging upward from the bottom bezel.
  * Adjustable horizontal offset slider to center between the Start button and taskbar widgets.
* **Full Taskbar Mode ("Without Pill" Native Look)**:
  * Seamlessly utilizes the taskbar space from the left edge of your screen up to the Windows 11 Start button.
  * Borderless, transparent backdrop letting the native Windows taskbar surface show through.
  * **Self-Elastic Adjustable Layout**: Dynamically expands and contracts based on content width.
  * **Start Button Collision Guard ("Remove & Halt")**: Pack elements from left to right. If content would collide with the Start button, MicaBay automatically drops and halts elements (battery, then clock, then title ellipsis) so nothing ever overlaps or blocks the Windows Start menu.
  * Fully clickable across every pixel (powered by alpha-channel hit-testing).

### 2. 🪟 Glassmorphism & Edge-to-Center Transparency
* **Customizable Transparency (0% – 100%)**:
  * At 0%: Solid, deep dark glass.
  * As transparency increases, opacity smoothly fades from the outer edges inward to the center with realistic depth penetration.
* **Specular Refraction Highlight**:
  * Curved light reflection along the top surface simulating polished glass physics.

### 3. 🎵 Windows Media Integration (SMTC)
* Automatically hooks into Windows System Media Transport Controls (SMTC) to detect media playback from **Spotify, YouTube, Brave, Chrome, Edge, and media players**.
* Displays:
  * High-resolution album artwork thumbnail.
  * Track title and artist with smart character eliding.
  * **Animated Low-Height Baseline Equalizer**: Crisp white micro-ticks with parabolic acoustic frequencies along the bottom edge when music plays, smoothly resting when paused.
  * Dynamic accent color extraction matching the active album art.

### 4. 🌤️ Integrated Weather Engine
* Accurate live weather integration via Open-Meteo & reverse geocoding.
* Displays current temperature and weather conditions (e.g., `19°C · Partly cloudy`).
* **Day/Night Responsive Icons**: Shows `🌙☁️` at night and `⛅` by day.
* **Dynamic 5.5s Cycle**: Alternates smoothly between temperature and humidity feel (matching the Windows 11 Taskbar Weather widget).

### 5. 📋 Instant Clipboard Toast
* System-wide clipboard listener detecting copied text, images, and files.
* Transforms into a notification toast (`📋 Copied · Image` or `📋 Copied · "Text preview..."`) with an auto-retracting glow timer.

### 6. 📊 Expandable Dark Glass Dashboard
Click anywhere on the compact bar to smoothly expand upward into the full dark-theme control suite:
* **Hardware Gauges**: Real-time high-DPI anti-aliased radial meters for **CPU %**, **RAM %**, and **Disk %**.
* **Active Screen Time Tracker**: Live foreground window time tracking with weekly categorized bar charts.
* **Focus Pomodoro Timer**: 25:00 focus timer with Play/Pause controls.
* **Clipboard History Manager**: Searchable history with 1-click re-copying.
* **Quick Scratchpad Notes**: Instant notes auto-saved to disk.
* **Floating Dock Bar**: Quick pill navigation between dashboard categories.

### 7. 📁 File Shelf (Drop Zone)
* Drag and drop files from Windows Explorer directly onto the notch or taskbar to park them.
* Drag parked files out into any application, Discord, folder, or browser anytime.

### 8. ✍️ Apple-Style Cursive Typewriter Greeting
* **Contextual Greetings**: Automatically detects time of day and types `"Good morning"`, `"Good afternoon"`, or `"Good evening"`.
* **Typographic Identity**: Rendered in cursive (`Segoe Script`, `Segoe Print`) in chrome white (`#ffffff`) with a luminous ambient bloom.
* **Fluid Left-to-Right Typewriter**: Characters write out smoothly from left to right at 100ms per character on startup and Windows logon/unlock (`WM_WTSSESSION_CHANGE`).
* **5.5-Second Hold**: Stays visible on the taskbar for at least 5.5 seconds before smoothly cross-fading to active downloads/media or clock/battery idle.
* **Interactive**: Clicking anywhere during the greeting opens the expanded dashboard.

### 9. 📥 Active Download Tracking & Browser Resolver
* **Real Filename Resolution**: Automatically queries Chrome, Brave, and Edge SQLite download history to resolve temporary `"Unconfirmed <number>"` files into their actual filenames (e.g. `Doraemon Season 9-...zip`).
* **Live Transfer Metrics**: Displays active download filename, downloaded size in MB, and live transfer speed.

### 10. 🔄 Smart 3-Way Dynamic Rotation
* When active tasks (media playback or file downloads) are running, MicaBay automatically rotates every 5 seconds across:
  $$\text{DOWNLOAD} \longleftrightarrow \text{MEDIA} \longleftrightarrow \text{TIME / CLOUD / BATTERY (IDLE)}$$
* Keeps you fully informed without cluttering your taskbar.

### 11. 🔊 CoreAudio Volume HUD
* Listens to hardware volume keys and audio slider changes.
* Pops up a sleek compact volume HUD (`🔊 [========--] 64%`) with automatic 1.8s dismissal.

---

## 🛠️ Project Structure

```
micabay/
├── main.py                       # Application entry point, system tray, and service orchestration
├── notch_window.py               # Main frameless layered window, geometry, animations, and hit testing
├── compact_bar.py                # Self-elastic left-to-right bar, dynamic weather, media, and clock/battery
├── dashboard_widget.py           # Expandable dark-glass dashboard suite (gauges, screen time, notes, clipboard)
├── appearance_settings_widget.py # Settings UI (placement, styles, edge lights, transparency, barrier sliders)
├── settings_window.py            # Floating settings window frame
├── settings_service.py           # JSON-backed configuration persistence service
├── settings.json                 # Active user preferences configuration
│
├── weather_service.py            # Open-Meteo live weather fetcher and periodic updater
├── media_service.py              # Windows SMTC media transport listener & thumbnail extractor
├── clipboard_service.py          # Windows clipboard listener & notification service
├── system_service.py             # CPU, RAM, Disk, Battery, and active window screen time tracker
├── volume_service.py             # CoreAudio volume polling service
├── color_extractor.py            # Dominant album art color extraction
│
├── battery_glyph.py              # Chrome metallic battery widget with dynamic fill
├── audio_visualizer.py           # Animated equalizer bars widget
├── volume_bar.py                 # Gradient volume HUD bar widget
├── circular_gauge.py             # Anti-aliased radial gauge widget
├── weekly_bars.py                # Weekly screen time bar chart widget
├── shelf_widget.py               # Drag-and-drop file shelf widget
│
├── Launch_MicaBay.bat            # Silent background launcher
├── micabay_logo.jpg              # Tray & application icon
├── README.md                     # Project documentation
├── FEATURES.md                   # Full component architecture and technical log
└── .gitignore                    # Git ignore file
```

---

## 🚀 Getting Started

### Prerequisites

* **Operating System**: Windows 10 (1903+) or Windows 11
* **Python**: Python 3.10, 3.11, or 3.12

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/saten-git/micabay.git
   cd micabay
   ```

2. Install required Python packages:
   ```bash
   pip install PySide6 winrt-runtime pycaw psutil requests urllib3
   ```

3. Launch MicaBay:
   ```bash
   python main.py
   ```
   * Or double-click `Launch_MicaBay.bat` to run silently in the background without a command prompt window.

### Run on Windows Startup

1. Press `Win + R`, type `shell:startup`, and press **Enter**.
2. Create a shortcut to `Launch_MicaBay.bat` inside the Startup folder.

---

## ⚙️ Configuration

Preferences are stored in `settings.json` and can be adjusted anytime via the **⚙️ Settings** UI (accessible from the Dashboard or System Tray):

| Setting | Default | Description |
| :--- | :--- | :--- |
| `placement` | `"full_taskbar"` | `"top"`, `"taskbar"` (pill), or `"full_taskbar"` |
| `full_taskbar_width` | `505` | Start button barrier coordinate ($350\text{px} - 750\text{px}$) |
| `glass_transparency` | `0` | Edge-to-center glass transparency ($0 - 100\%$) |
| `notch_style` | `"island"` | Notch geometry: `"notch"`, `"island"`, or `"line"` |
| `notch_scale` | `70` | Scale percentage for compact pill mode |
| `edge_light_enabled` | `true` | Luminous traveling edge light |
| `edge_light_effect` | `"comet"` | `"twin_comets"`, `"comet"`, or `"breathe"` |
| `edge_light_intensity` | `48` | Glow brightness percentage ($20\% - 100\%$) |
| `weather_enabled` | `true` | Weather badge display toggle |
| `weather_unit` | `"°C"` | Temperature unit (`"°C"` or `"°F"`) |

---

## 📄 License

This project is licensed under the MIT License - feel free to customize and extend it.
