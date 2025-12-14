# main.py
import flet as ft
import spotipy
from spotipy.oauth2 import SpotifyOAuth, CacheFileHandler
import os
import datetime
import threading
import time
from dotenv import load_dotenv
import random
from pathlib import Path

# --- CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

from weather_logic import get_current_weather, map_weather_to_spotify, MOOD_TO_SPOTIFY, get_forecast

SCOPE = "playlist-modify-public playlist-modify-private"
REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

# --- LOGIQUE SPOTIFY ---
def get_tracks_for_mood_via_search(sp_client, mood: str, desired_count: int = 25, market: str = "AT"):
    cfg = MOOD_TO_SPOTIFY.get(mood, MOOD_TO_SPOTIFY["Neutral"])
    genres = cfg["seed_genres"]
    all_tracks = []
    for genre in genres:
        try:
            results = sp_client.search(q=f'genre:"{genre}"', type="track", limit=50, market=market)
            items = results.get("tracks", {}).get("items", [])
            all_tracks.extend(t["uri"] for t in items if t.get("uri"))
        except: pass
    if len(all_tracks) < desired_count:
        try:
            or_query = " OR ".join([f'genre:"{g}"' for g in genres])
            results2 = sp_client.search(q=or_query, type="track", limit=50, market=market)
            items2 = results2.get("tracks", {}).get("items", [])
            all_tracks.extend(t["uri"] for t in items2 if t.get("uri"))
        except: pass
    all_tracks = list(dict.fromkeys(all_tracks))
    random.shuffle(all_tracks)
    return all_tracks[:desired_count]

def create_spotify_playlist(weather_data, sp_client):
    params = map_weather_to_spotify(weather_data)
    
    mood = params.pop("_mood", "Neutral")
    
    # Données techniques
    tech_data = {
        "Mood": mood,
        "Valence": params.get('target_valence', 0.5), # Float
        "Energy": params.get('target_energy', 0.5), # Float
        "Tempo": int(params.get('target_tempo', 100)), # Int
        "Genres": params.get('seed_genres', [])[:3]
    }

    # Valeur par défaut fixe
    desired_count = params.get("limit", 25)
    
    try:
        track_uris = get_tracks_for_mood_via_search(sp_client, mood=mood, desired_count=desired_count)
    except Exception as e: return f"Search Error: {e}", None, None, None
    
    if len(track_uris) < 5: return f"Not enough tracks ({len(track_uris)}).", None, None, None
    
    preview_list = []
    try:
        top_tracks = sp_client.tracks(track_uris[:6])
        for track in top_tracks['tracks']:
            artist = track['artists'][0]['name']
            title = track['name']
            try:
                img_url = track['album']['images'][-1]['url']
            except:
                img_url = ""
            preview_list.append(f"{artist}|{title}|{img_url}") 
    except:
        preview_list = ["System|Preview Unavailable|"]

    try:
        user_id = sp_client.me()["id"]
        playlist_name = f"Vienna Vibe: {weather_data['condition']} 🇦🇹"
        # Public par défaut
        public_flag = True 
        playlist = sp_client.user_playlist_create(
            user=user_id, name=playlist_name, public=public_flag,
            description=f"Weather: {weather_data['description']} | Mood: {mood}"
        )
        sp_client.playlist_add_items(playlist_id=playlist["id"], items=track_uris)
        return "Playlist Created!", playlist["external_urls"]["spotify"], tech_data, preview_list

    except Exception as e: return f"Creation Error: {e}", None, None, None


# --- UI PRINCIPALE ---
def main(page: ft.Page):
    # 1. Config
    page.title = "Vienna Weather Vibe"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#000000"
    page.window_width = 1100
    page.window_height = 800
    page.padding = 20

    # ---------------------------------------------------------
    # --- DEBUT DU SPLASH SCREEN AMÉLIORÉ ---
    # ---------------------------------------------------------
    
    # 1. Les éléments visuels
    # Le logo commence petit (scale=0.5) et invisible (opacity=0)
    splash_icon = ft.Icon(
        ft.Icons.EQUALIZER_ROUNDED, 
        size=100, 
        color="#1DB954",
        opacity=0,
        animate_opacity=ft.Animation(1000, "easeIn"),
        scale=0.5,
        animate_scale=ft.Animation(1000, "elasticOut") # Effet de rebond à l'apparition
    )

    # Le titre
    splash_title = ft.Text(
        "VIENNA VIBE", 
        size=40, 
        weight=ft.FontWeight.BOLD, 
        color="white", 
        opacity=0, # Invisible au début
        animate_opacity=ft.Animation(1000, "easeIn"),
        style=ft.TextStyle(letter_spacing=5)
    )

    splash_status = ft.Text(
        "Initializing...", 
        size=12, 
        color="white54", 
        italic=True,
        opacity=0,
        animate_opacity=500
    )

    # Barre de chargement fine et élégante
    splash_progress = ft.ProgressBar(
        width=250, 
        color="#1DB954", 
        bgcolor="#333333", 
        height=2, 
        opacity=0,
        animate_opacity=500,
        value=0 # Commence à 0
    )

    # Conteneur global du Splash (pour gérer la disparition finale)
    splash_container = ft.Container(
        content=ft.Column(
            [
                splash_icon,
                ft.Container(height=10),
                splash_title,
                ft.Container(height=50),
                splash_progress,
                ft.Container(height=10),
                splash_status,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        alignment=ft.alignment.center,
        expand=True,
        opacity=1,
        animate_opacity=ft.Animation(800, "easeOut") # Animation de disparition de l'écran
    )

    # Ajout à la page
    page.add(splash_container)
    page.update()

    # --- Séquence d'Animation ---
    
    # Etape 1 : Apparition du Logo (Pop !)
    time.sleep(0.1)
    splash_icon.opacity = 1
    splash_icon.scale = 1
    page.update()
    time.sleep(0.8)

    # Etape 2 : Apparition du Titre et de la barre
    splash_title.opacity = 1
    splash_progress.opacity = 1
    splash_status.opacity = 1
    page.update()
    time.sleep(0.5)

    # ---------------------------------------------------------
    # --- CHARGEMENT ET CONNEXION (SIMULÉ + RÉEL) ---
    # ---------------------------------------------------------

    # Variables globales
    last_weather_data = None
    last_tech_data = None
    last_preview_list = None
    user_name = "Guest"
    sp = None

    try:
        # Phase 1: Connexion (simulation visuelle de progression)
        splash_status.value = "Connecting to Spotify..."
        splash_progress.value = 0.3
        page.update()
        
        # --- VRAIE CONNEXION ---
        handler = CacheFileHandler(cache_path=".spotipyoauthcache")
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=os.getenv("SPOTIPY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
            redirect_uri=REDIRECT_URI, scope=SCOPE, cache_handler=handler))
        user_name = sp.me().get('display_name', 'Music Lover')
        print("Connected")
        # -----------------------

        splash_progress.value = 0.8
        page.update()
        time.sleep(0.4) # Petit délai pour voir la barre avancer

        # Phase 2: Finalisation
        splash_status.value = "Ready to Vibe."
        splash_progress.value = 1.0
        splash_progress.color = "white" # Petit flash blanc quand c'est fini
        page.update()
        time.sleep(0.6)

    except Exception as e: 
        splash_status.value = "Connection failed (Offline mode)"
        splash_status.color = "red"
        print(f"Auth Error: {e}")
        time.sleep(1)
        pass

    # ---------------------------------------------------------
    # --- FIN DU SPLASH SCREEN - TRANSITION DE SORTIE ---
    # ---------------------------------------------------------
    
    # On fait disparaître tout l'écran doucement (Fade Out)
    splash_container.opacity = 0
    splash_icon.scale = 1.5 # Le logo grandit un peu en disparaissant (effet zoom)
    page.update()
    
    # On attend la fin de l'animation (0.8s défini plus haut)
    time.sleep(0.8) 
    
    # On nettoie
    page.clean()

    # --- SUITE DU CODE ORIGINAL ---

    user_name_text = ft.Text(user_name, size=12, color="grey")
    
    # --- HELPERS VISUELS ---
    def get_card_gradient(condition):
        if condition == "Clear": return ft.LinearGradient(colors=["#ff9966", "#ff5e62"], begin=ft.alignment.top_left, end=ft.alignment.bottom_right)
        elif condition == "Rain": return ft.LinearGradient(colors=["#000046", "#1CB5E0"], begin=ft.alignment.top_center, end=ft.alignment.bottom_center)
        elif condition == "Cloudy": return ft.LinearGradient(colors=["#304352", "#d7d2cc"], begin=ft.alignment.top_left, end=ft.alignment.bottom_right)
        elif condition == "Snow": return ft.LinearGradient(colors=["#83a4d4", "#b6fbff"], begin=ft.alignment.top_center, end=ft.alignment.bottom_center)
        elif condition == "Thunderstorm": return ft.LinearGradient(colors=["#232526", "#414345"], begin=ft.alignment.top_center, end=ft.alignment.bottom_center)
        else: return ft.LinearGradient(colors=["#2b2b2b", "#1a1a1a"], begin=ft.alignment.top_left, end=ft.alignment.bottom_right)

    def create_track_tile(index, artist, title, img_url):
        if img_url:
            visual_content = ft.Image(src=img_url, width=40, height=40, border_radius=5, fit=ft.ImageFit.COVER)
        else:
            visual_content = ft.Container(
                content=ft.Icon(ft.Icons.MUSIC_NOTE, color="#1DB954", size=20),
                width=40, height=40, bgcolor="#282828", border_radius=5, alignment=ft.alignment.center
            )

        return ft.Container(
            content=ft.Row([
                visual_content,
                ft.Column([
                    ft.Text(title, color="white", weight="bold", size=13, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text(artist, color="grey", size=11, overflow=ft.TextOverflow.ELLIPSIS)
                ], spacing=2, expand=True)
            ], alignment=ft.MainAxisAlignment.START),
            padding=ft.padding.only(bottom=10),
            border=ft.border.only(bottom=ft.border.BorderSide(1, "#222222"))
        )

    # --- FORECAST CARD (styled) ---
    def create_forecast_card(date_label, condition, tmax, tmin):
        def _icon_for(cond):
            if cond == "Clear":
                return ft.Icons.WB_SUNNY
            if cond == "Rain":
                return ft.Icons.WATER_DROP
            if cond == "Cloudy":
                return ft.Icons.CLOUD
            if cond == "Snow":
                return ft.Icons.AC_UNIT
            if cond == "Thunderstorm":
                return ft.Icons.FLASH_ON
            return ft.Icons.WB_SUNNY

        icon = ft.Icon(_icon_for(condition), size=22, color="#1DB954")
        date_txt = ft.Text(date_label, size=13, color="white", weight=ft.FontWeight.BOLD)
        cond_txt = ft.Text(condition, size=11, color="white70")
        temps_txt = ft.Text(f"{tmax:.0f}° / {tmin:.0f}°", size=13, color="white")

        return ft.Container(
            content=ft.Row([
                ft.Column([date_txt, cond_txt]),
                ft.Container(expand=True),
                icon,
                ft.Container(width=12),
                temps_txt
            ], alignment=ft.MainAxisAlignment.CENTER),
            padding=ft.padding.symmetric(vertical=10, horizontal=12),
            bgcolor="#0b0b0b",
            border_radius=10,
            border=ft.border.all(1, "#1f1f1f"),
            shadow=ft.BoxShadow(blur_radius=6, color="#000000", offset=ft.Offset(0, 3))
        )

    # --- CARTE CENTRALE ---
    title_text_1 = ft.Text("VIENNA", size=24, weight=ft.FontWeight.BOLD, color="white", style=ft.TextStyle(letter_spacing=2))
    title_text_2 = ft.Text("VIBE", size=24, weight=ft.FontWeight.BOLD, color="white", style=ft.TextStyle(letter_spacing=2))
    title_row = ft.Row([title_text_1, title_text_2], alignment=ft.MainAxisAlignment.CENTER, spacing=5)
    subtitle = ft.Text("Vienna Weather Station", size=12, color="white70")
    
    weather_icon = ft.Icon(name=ft.Icons.CLOUD_QUEUE, size=50, color="white70")
    weather_temp = ft.Text("--°", size=50, weight=ft.FontWeight.BOLD, color="white")
    weather_desc = ft.Text("Ready to scan", size=16, color="white70")
    weather_row = ft.Row([weather_icon, weather_temp], alignment=ft.MainAxisAlignment.CENTER)
    
    status_text = ft.Text("", size=14, color="white", weight=ft.FontWeight.BOLD)
    status_icon = ft.Icon(ft.Icons.CHECK_CIRCLE, color="white", size=20)
    status_container = ft.Container(
        content=ft.Row([status_icon, status_text], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
        bgcolor="#1DB954", padding=ft.padding.symmetric(horizontal=20, vertical=12),
        border_radius=30, visible=False, animate_opacity=300
    )
    
    playlist_link = ft.ElevatedButton("OPEN IN SPOTIFY", url="", visible=False, icon=ft.Icons.OPEN_IN_NEW, bgcolor="white", color="black", height=50, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=30)))
    progress = ft.ProgressBar(width=200, color="white", bgcolor="white24", visible=False)
    
    gen_btn = ft.ElevatedButton(
        text="GENERATE VIBE", icon=ft.Icons.PLAY_CIRCLE_FILLED,
        bgcolor="#1DB954", color="white", width=260, height=55,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=30), text_style=ft.TextStyle(size=16, weight=ft.FontWeight.BOLD))
    )

    main_card = ft.Container(
        content=ft.Column([
            title_row, subtitle, ft.Divider(color="white24", height=30),
            weather_row, weather_desc, ft.Container(height=20),
            gen_btn, ft.Container(height=20),
            progress, status_container, playlist_link,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        width=360, height=600, padding=40,
        gradient=get_card_gradient("Neutral"),
        border_radius=30, animate=ft.Animation(duration=500, curve="easeOut"),
        shadow=ft.BoxShadow(blur_radius=30, color="#121212", offset=ft.Offset(0, 10)),
    )

    # --- PANNEAUX LATERAUX ---
    
    left_panel_title = ft.Text("Forecast ⛅", weight="bold", size=18, color="white")
    left_close_btn = ft.IconButton(ft.Icons.CLOSE, icon_color="white24", tooltip="Close")
    
    right_panel_title = ft.Text("Sneak Peek 🎵", weight="bold", size=18, color="white")
    right_close_btn = ft.IconButton(ft.Icons.CLOSE, icon_color="white24", tooltip="Close")

    # Contenu centré
    left_content = ft.Column([], spacing=20, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    
    left_panel = ft.Container(
        content=ft.Column([
            ft.Row([left_panel_title, left_close_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Container(content=ft.Divider(color="white12"), width=280), # Fix large divider
            ft.Container(content=left_content, expand=True, alignment=ft.alignment.center) 
        ]),
        width=0, height=600, padding=0,
        bgcolor="#111111",
        border_radius=20,
        animate=ft.Animation(400, "easeOut"), animate_opacity=200, opacity=0,
        border=ft.border.all(1, "#333333"), clip_behavior=ft.ClipBehavior.HARD_EDGE,
        shadow=ft.BoxShadow(blur_radius=20, color="#000000", offset=ft.Offset(0, 5))
    )

    right_content = ft.Column([], spacing=15, scroll=ft.ScrollMode.HIDDEN)
    right_panel = ft.Container(
        content=ft.Column([
            ft.Row([right_panel_title, right_close_btn], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Container(content=ft.Divider(color="white12"), width=280), # Fix large divider
            right_content,
            ft.Container(height=10), # Footer spacer
            ft.Text("Full playlist is on Spotify.", size=10, color="grey", italic=True, text_align=ft.TextAlign.CENTER) # Footer
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER), # Center footer text too
        width=0, height=600, padding=0,
        bgcolor="#111111",
        border_radius=20,
        animate=ft.Animation(400, "easeOut"), animate_opacity=200, opacity=0,
        border=ft.border.all(1, "#333333"), clip_behavior=ft.ClipBehavior.HARD_EDGE,
        shadow=ft.BoxShadow(blur_radius=20, color="#000000", offset=ft.Offset(0, 5))
    )

    # --- ACTIONS ---
    
    def close_left(e):
        left_panel.width = 0; left_panel.padding = 0; left_panel.opacity = 0; page.update()
    def close_right(e):
        right_panel.width = 0; right_panel.padding = 0; right_panel.opacity = 0; page.update()
        
    left_close_btn.on_click = close_left
    right_close_btn.on_click = close_right

    def toggle_left_panel(e):
        # Affiche la prévision météo multi-jours dans le panneau gauche
        try:
            forecast = get_forecast(5)
        except Exception:
            forecast = []

        if not forecast:
            left_content.controls = [ft.Text("Forecast unavailable", color="red")]
        else:
            # Header
            header = ft.Row([
                ft.Text("5-Day Forecast", size=16, color="white", weight=ft.FontWeight.BOLD),
                ft.Container(expand=True),
                ft.Icon(ft.Icons.CALENDAR_MONTH, size=16, color="#1DB954")
            ], alignment=ft.MainAxisAlignment.CENTER)

            cards = []
            for day in forecast:
                try:
                    dt = datetime.datetime.fromisoformat(day.get('date'))
                    date_label = dt.strftime('%a %d %b')
                except:
                    date_label = day.get('date')

                tmax = day.get('max') or 0
                tmin = day.get('min') or 0
                condition = day.get('condition', 'Neutral')
                cards.append(create_forecast_card(date_label, condition, tmax, tmin))

            left_content.controls = [
                header,
                ft.Container(height=10),
                ft.Column(cards, spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
            ]

        if left_panel.width > 0: close_left(None)
        else:
            left_panel.width = 320; left_panel.padding = 25; left_panel.opacity = 1; page.update()

    def toggle_right_panel(e):
        if not last_preview_list:
            right_content.controls = [ft.Text("Generate first!", color="red")]
        else:
            tracks_ui = []
            for i, raw_track in enumerate(last_preview_list):
                try:
                    artist, title, img_url = raw_track.split("|")
                    tracks_ui.append(create_track_tile(i+1, artist, title, img_url))
                except: pass
            right_content.controls = tracks_ui

        if right_panel.width > 0: close_right(None)
        else:
            right_panel.width = 300; right_panel.padding = 25; right_panel.opacity = 1; page.update()

    def handle_reset(e):
        nonlocal last_weather_data, last_tech_data, last_preview_list
        last_weather_data = None; last_tech_data = None; last_preview_list = None
        close_left(None); close_right(None)
        
        weather_icon.name = ft.Icons.CLOUD_QUEUE; weather_icon.color = "white70"
        weather_temp.value = "--°"; weather_desc.value = "Ready to scan"
        neutral_grad = get_card_gradient("Neutral")
        main_card.gradient = neutral_grad
        
        status_container.visible = False; playlist_link.visible = False; progress.visible = False
        gen_btn.text = "GENERATE VIBE"; gen_btn.disabled = False
        page.update()

    def update_display():
        nonlocal last_weather_data
        if not last_weather_data: return
        cond = last_weather_data['condition']
        
        main_card.gradient = get_card_gradient(cond)
        
        if cond == "Clear": weather_icon.name = ft.Icons.WB_SUNNY
        elif cond == "Rain": weather_icon.name = ft.Icons.WATER_DROP
        elif cond == "Cloudy": weather_icon.name = ft.Icons.CLOUD
        elif cond == "Snow": weather_icon.name = ft.Icons.AC_UNIT
        elif cond == "Thunderstorm": weather_icon.name = ft.Icons.FLASH_ON
        else: weather_icon.name = ft.Icons.MUSIC_NOTE
        weather_temp.value = f"{last_weather_data['temperature']:.0f}°"
        weather_desc.value = f"{cond} | {last_weather_data['wind_speed']} km/h"
        page.update()

    def toggle_theme(e):
        is_dark = page.theme_mode == ft.ThemeMode.DARK
        page.theme_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
        page.bgcolor = "#FFFFFF" if is_dark else "#000000"
        e.control.icon = ft.Icons.DARK_MODE if is_dark else ft.Icons.WB_SUNNY
        e.control.icon_color = "black" if is_dark else "white"
        
        text_col = "black" if is_dark else "white"
        title_text_1.color = text_col; title_text_2.color = text_col
        left_panel_title.color = "white"; right_panel_title.color = "white"
        page.appbar.bgcolor = "#F0F0F0" if is_dark else "#121212"
        page.update()

    # Horloge: affichage et rafraîchissement manuel
    clock_text = ft.Text(datetime.datetime.now().strftime("%a %d %b %H:%M:%S"), size=12, color="grey")

    def update_clock(e=None):
        clock_text.value = datetime.datetime.now().strftime("%a %d %b %H:%M:%S")
        page.update()

    # Toolbar
    page.appbar = ft.AppBar(
        leading=ft.Icon(ft.Icons.EQUALIZER, color="#1DB954"),
        leading_width=40,
        title=ft.Text("Vienna Vibe", size=16, weight=ft.FontWeight.BOLD),
        center_title=False,
        bgcolor="#121212",
        actions=[
                ft.Row([clock_text], alignment=ft.MainAxisAlignment.CENTER),
                ft.Container(width=8),
                ft.IconButton(ft.Icons.RESTART_ALT, icon_color="white", on_click=handle_reset, tooltip="Reset"),
                ft.IconButton(ft.Icons.WB_SUNNY, icon_color="white", on_click=toggle_theme, tooltip="Switch Theme"),
                ft.IconButton(ft.Icons.INSERT_CHART_OUTLINED, icon_color="#1DB954", on_click=toggle_left_panel, tooltip="Show Data (Left)"),
                ft.IconButton(ft.Icons.QUEUE_MUSIC, icon_color="#1DB954", on_click=toggle_right_panel, tooltip="Show Tracks (Right)"),
                ft.Container(width=12),
                ft.Row([ft.Icon(ft.Icons.PERSON, size=16, color="grey"), user_name_text], alignment=ft.MainAxisAlignment.CENTER),
                ft.Container(width=15),
        ]
    )

    # Démarrer le thread de mise à jour de l'horloge
    def _clock_loop():
        while True:
            time.sleep(1)
            try:
                update_clock()
            except Exception:
                pass

    threading.Thread(target=_clock_loop, daemon=True).start()

    def on_generate_click(e):
        nonlocal last_weather_data, last_tech_data, last_preview_list
        gen_btn.text = "SCANNING..."
        gen_btn.disabled = True
        progress.visible = True
        playlist_link.visible = False
        status_container.visible = False
        
        close_left(None); close_right(None)
        
        page.update()

        try:
            last_weather_data = get_current_weather()
            update_display()
            msg, url, tech, preview = create_spotify_playlist(last_weather_data, sp)
            last_tech_data = tech
            last_preview_list = preview
            progress.visible = False
            
            if url:
                status_text.value = msg
                status_icon.name = ft.Icons.CHECK_CIRCLE
                status_container.bgcolor = "#1DB954"
                status_container.visible = True
                playlist_link.url = url
                playlist_link.visible = True
            else:
                status_text.value = msg
                status_icon.name = ft.Icons.ERROR
                status_container.bgcolor = "red"
                status_container.visible = True

        except Exception as err:
            status_text.value = "Error"
            status_container.bgcolor = "red"
            status_container.visible = True

        gen_btn.text = "GENERATE VIBE"
        gen_btn.disabled = False
        progress.visible = False
        page.update()

    gen_btn.on_click = on_generate_click

    page.add(
        ft.Row(
            [left_panel, main_card, right_panel],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.START,
            spacing=20
        )
    )

if __name__ == "__main__":
    ft.app(target=main, view=ft.WEB_BROWSER, port=8888)