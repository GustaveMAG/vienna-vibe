<div align="center">

# 🇦🇹 🎵 Vienna Vibe

**Your atmospheric music companion.**

<br>

![Vienna Vibe App](images/screenshot.png)

<br>

*Automatically generates Spotify playlists based on the live weather in Vienna.*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flet](https://img.shields.io/badge/UI-Flet-purple?style=for-the-badge&logo=flutter&logoColor=white)](https://flet.dev/)
[![Spotify](https://img.shields.io/badge/Spotify-API-1DB954?style=for-the-badge&logo=spotify&logoColor=white)](https://developer.spotify.com/documentation/web-api/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

[Features](#-features) • [Installation](#-installation) • [Configuration](#-configuration) • [Usage](#-usage) • [License](#-license)

</div>

---

## 📖 About

**Vienna Vibe** creates a bridge between the atmosphere outside and the music in your ears. Using **Open-Meteo** weather data and **Spotify's Audio Features** (Valence, Energy, Tempo), the app curates a unique playlist that perfectly matches the current mood of the city.

## ✨ Features

- **🌥️ Real-Time Sync:** Fetches live weather data for Vienna, Austria
- **🧠 Smart Mood Algorithm:**
  - **Clear Sky:** High Energy, Pop/Disco 🎸
  - **Rain:** Low Valence, Blues/Jazz 🌧️
  - **Snow:** Peaceful, Classical ❄️
  - **Thunderstorm:** Intense, Rock/Metal ⚡
- **🎨 Modern UI:** Beautiful animated interface with dark/light themes
- **📊 5-Day Forecast:** View upcoming weather in side panel
- **👀 Track Preview:** See first 6 songs before opening Spotify
- **🔗 Deep Integration:** Creates public playlists directly on your Spotify account

## 🏗️ Architecture

Modular architecture with 7 specialized modules:
```
vienna-vibe/
├── main.py              # Application orchestrator
├── config.py            # Centralized configuration
├── spotify_manager.py   # Spotify API interactions
├── weather_logic.py     # Weather API & smart algorithm
├── ui_components.py     # Reusable UI components
├── splash_screen.py     # Animated startup screen
├── event_handlers.py    # User interaction logic
└── utils.py             # Utilities (clock, etc.)
```

---

## 🛠️ Installation

### 1. Clone the repository
```bash
git clone https://github.com/GustaveMAG/vienna-vibe.git
cd vienna-vibe
```

### 2. Set up the environment

It is recommended to use a virtual environment:
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

---

## ⚙️ Configuration (Required)

To make the magic happen, you need to set up your Spotify API keys.

### 1. Get Spotify Credentials

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Log in with your Spotify account
3. Click **"Create App"**
4. Fill in:
   - **App Name:** Vienna Vibe
   - **App Description:** Weather-based playlist generator
   - **Redirect URI:** `http://127.0.0.1:8888/callback`
5. Click **"Save"**
6. Copy your **Client ID** and **Client Secret**

### 2. Create `.env` file

Create a file named `.env` in the root directory:
```ini
# .env file
SPOTIPY_CLIENT_ID=your_client_id_here
SPOTIPY_CLIENT_SECRET=your_client_secret_here
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

> **⚠️ Important:** Never commit your `.env` file to Git! It's already in `.gitignore`.

---

## 🚀 Usage

### Option 1: Using Flet command
```bash
flet run
```

### Option 2: Using Python directly
```bash
python main.py
```

### Option 3: Double-click (Windows)
```bash
run.bat
```

### First Run

1. Click on **"GENERATE VIBE"**
2. A browser window will open for Spotify authentication
3. Click **"Accept"** to grant permissions
4. Once the playlist is ready, click **"OPEN IN SPOTIFY"**

---

## 🎯 How It Works

### The Algorithm

**3-Layer Intelligence:**

1. **Time of Day**
   - Morning → Softer music
   - Day → Energetic music
   - Evening → Calmer music
   - Night → Ambient/chill

2. **Weather Condition**
   - Clear → High valence (happy)
   - Rain → Low valence (melancholic)
   - Cloudy → Neutral mood
   - Snow → Peaceful, slow tempo
   - Storm → High energy, intense

3. **Micro-adjustments**
   - Wind speed → Affects tempo
   - Temperature → Affects acousticness

---

## 🔧 Troubleshooting

| Error | Cause | Solution |
|:---|:---|:---|
| `[WinError 10013]` | Port 8888 is busy | Close other apps using port 8888 or restart PC |
| `Auth Error` | Bad credentials | Check your Client ID/Secret in `.env` file |
| `Browser not opening` | OS restriction | Copy URL from terminal and paste manually |
| `Module not found` | Missing dependencies | Run `pip install -r requirements.txt` |

---

## 📸 Screenshots

<div align="center">
  <img src="images/main_screen.png" alt="Main Screen" width="400"/>
  <img src="images/dark_theme.png" alt="Dark Theme" width="400"/>
</div>

---

## 🙏 Acknowledgments

- [Spotify Web API](https://developer.spotify.com/documentation/web-api/) - Music streaming platform
- [Open-Meteo](https://open-meteo.com/) - Free weather API
- [Flet](https://flet.dev/) - Python UI framework

---

<div align="center">
  

</div>
