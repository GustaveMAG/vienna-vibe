Je comprends. Pour éviter les erreurs de formatage en collant plusieurs morceaux, voici **le fichier `README.md` complet et final** en un seul bloc.

**Fais ceci :**

1.  Ouvre ton fichier `README.md`.
2.  **Efface tout** ce qu'il contient (il doit être vide).
3.  **Copie et colle** l'intégralité du bloc ci-dessous.

-----

````markdown
<div align="center">

# 🇦🇹 🎵 Vienna Vibe

**Your atmospheric music companion.**
<br>
*Automatically generates Spotify playlists based on the live weather in Vienna.*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flet](https://img.shields.io/badge/UI-Flet-purple?style=for-the-badge&logo=flutter&logoColor=white)](https://flet.dev/)
[![Spotify](https://img.shields.io/badge/Spotify-API-1DB954?style=for-the-badge&logo=spotify&logoColor=white)](https://developer.spotify.com/documentation/web-api/)

[Features](#-features) • [Installation](#-installation) • [Configuration](#-configuration) • [Usage](#-usage)

</div>

---

## 📖 About

**Vienna Vibe** creates a bridge between the atmosphere outside and the music in your ears. Using **OpenWeather** logic and **Spotify's Audio Features** (Valence, Energy, Tempo), the app curates a unique playlist that perfectly matches the current mood of the city.

## ✨ Features

- **🌥️ Real-Time Sync:** Fetches live weather data for Vienna, Austria.
- **🧠 Smart Mood Algorithm:**
  - **Clear Sky:** High Energy, Pop/Rock 🎸
  - **Rain:** Low Valence, Acoustic, Lo-fi 🌧️
  - **Thunderstorm:** Intense, Heavy, Dynamic ⚡
- **🎨 Modern UI:** A beautiful dark-mode interface built with Flet, featuring smooth animations.
- **🔗 Deep Integration:** Creates public playlists directly on your Spotify account.

---

## 🛠️ Installation

### 1. Clone the repository
```bash
git clone [https://github.com/Pozzzzzz/vienna-vibe.git](https://github.com/Pozzzzzz/vienna-vibe.git)
cd vienna-vibe
````

### 2\. Set up the environment

It is recommended to use a virtual environment:

```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3\. Install dependencies

```bash
pip install -r requirements.txt
```

-----

## ⚙️ Configuration (Required)

To make the magic happen, you need to set up your API keys.

1.  Create a file named **`.env`** in the root directory.
2.  Paste your Spotify Developer credentials inside:

<!-- end list -->

```ini
# .env file
SPOTIPY_CLIENT_ID=your_client_id_here
SPOTIPY_CLIENT_SECRET=your_client_secret_here
SPOTIPY_REDIRECT_URI=[http://127.0.0.1:8888/callback](http://127.0.0.1:8888/callback)
```

> **⚠️ Important:** Ensure you have added `http://127.0.0.1:8888/callback` to the **Redirect URIs** in your [Spotify Dashboard](https://developer.spotify.com/dashboard) settings.

-----

## 🚀 Usage

Run the application with Flet:

```bash
flet run main.py
```

1.  Click on **"GENERATE VIBE"**.
2.  A browser window will open for the first connection: click **Accept**.
3.  Once the playlist is ready, click **"OPEN IN SPOTIFY"**.

-----

## 🔧 Troubleshooting

| Error | Cause | Solution |
| :--- | :--- | :--- |
| `[WinError 10013]` | Port 8888 is busy | Close other Python scripts or restart your PC. |
| `Auth Error` | Bad credentials | Check your Client ID/Secret in the `.env` file. |
| `Browser not opening` | OS restriction | Copy the URL from the terminal and paste it manually. |

-----

\<div align="center"\>

Made with ❤️ in Python
<br>
*Enjoy the Vibe\!*

\</div\>

```
```