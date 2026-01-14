"""
Centralized configuration for Vienna Vibe application
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Paths
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

# Spotify Configuration
SCOPE = "playlist-modify-public playlist-modify-private"
REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")

# UI Configuration
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 800
MAIN_CARD_WIDTH = 360
MAIN_CARD_HEIGHT = 600
LEFT_PANEL_WIDTH = 320
RIGHT_PANEL_WIDTH = 300

# Colors
COLOR_SPOTIFY_GREEN = "#1DB954"
COLOR_DARK_BG = "#000000"
COLOR_PANEL_BG = "#111111"
COLOR_CARD_BG = "#121212"