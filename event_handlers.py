
import flet as ft
import datetime
from weather_logic import get_current_weather, get_forecast
from spotify_manager import create_spotify_playlist
from ui_components import get_card_gradient, get_weather_icon, create_forecast_card, create_track_tile


class EventHandlers:
    
    def __init__(self, page, ui_elements, sp_client):
        
        ##Initializes handlers with UI elements and Spotify client
        
        self.page = page
        self.ui = ui_elements
        self.sp_client = sp_client
        
        # Application state
        self.last_weather_data = None
        self.last_tech_data = None
        self.last_preview_list = None
    
    def close_left_panel(self, e):
        ##Closes the left panel
        panel = self.ui["left_panel"]["panel"]
        panel.width = 0
        panel.padding = 0
        panel.opacity = 0
        self.page.update()
    
    def close_right_panel(self, e):
        ##Closes the right panel
        panel = self.ui["right_panel"]["panel"]
        panel.width = 0
        panel.padding = 0
        panel.opacity = 0
        self.page.update()
    
    def toggle_left_panel(self, e):
        ##Shows/hides the weather forecast panel
        panel = self.ui["left_panel"]["panel"]
        content = self.ui["left_panel"]["content"]
        
        try:
            forecast = get_forecast(5)
        except Exception:
            forecast = []
        
        if not forecast:
            content.controls = [ft.Text("Forecast unavailable", color="red")]
        else:
            # Header
            header = ft.Row([
                ft.Text("5-Day Forecast", size=16, color="white", weight=ft.FontWeight.BOLD),
                ft.Container(expand=True),
                ft.Icon(ft.Icons.CALENDAR_MONTH, size=16, color="#1DB954")
            ], alignment=ft.MainAxisAlignment.CENTER)
            
            # Forecast cards
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
            
            content.controls = [
                header,
                ft.Container(height=10),
                ft.Column(cards, spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
            ]
        
        # Toggle visibility
        if panel.width > 0:
            self.close_left_panel(None)
        else:
            panel.width = 320
            panel.padding = 25
            panel.opacity = 1
            self.page.update()
    
    def toggle_right_panel(self, e):
        """Shows/hides the tracks panel"""
        panel = self.ui["right_panel"]["panel"]
        content = self.ui["right_panel"]["content"]
        
        if not self.last_preview_list:
            content.controls = [ft.Text("Generate first!", color="red")]
        else:
            tracks_ui = []
            for i, raw_track in enumerate(self.last_preview_list):
                try:
                    artist, title, img_url = raw_track.split("|")
                    tracks_ui.append(create_track_tile(i+1, artist, title, img_url))
                except:
                    pass
            content.controls = tracks_ui
        
        # Toggle visibilité
        if panel.width > 0:
            self.close_right_panel(None)
        else:
            panel.width = 300
            panel.padding = 25
            panel.opacity = 1
            self.page.update()
    
    def handle_reset(self, e):
        ##Resets the application to its initial state
        # Reset state
        self.last_weather_data = None
        self.last_tech_data = None
        self.last_preview_list = None
        
        # Close panels
        self.close_left_panel(None)
        self.close_right_panel(None)
        
        # Reset visual elements
        main_card = self.ui["main_card"]
        weather_icon = main_card["weather_icon"]
        weather_temp = main_card["weather_temp"]
        weather_desc = main_card["weather_desc"]
        status_container = main_card["status_container"]
        playlist_link = main_card["playlist_link"]
        progress = main_card["progress"]
        gen_btn = main_card["gen_btn"]
        
        weather_icon.name = ft.Icons.CLOUD_QUEUE
        weather_icon.color = "white70"
        weather_temp.value = "--°"
        weather_desc.value = "Ready to scan"
        
        main_card["card"].gradient = get_card_gradient("Neutral")
        
        status_container.visible = False
        playlist_link.visible = False
        progress.visible = False
        gen_btn.text = "GENERATE VIBE"
        gen_btn.disabled = False
        
        self.page.update()
    
    def update_weather_display(self):
        ##Updates the weather display
        if not self.last_weather_data:
            return
        
        cond = self.last_weather_data['condition']
        main_card = self.ui["main_card"]
        
        # Update gradient
        main_card["card"].gradient = get_card_gradient(cond)
        
        # Update icon
        main_card["weather_icon"].name = get_weather_icon(cond)
        
        # Update text
        main_card["weather_temp"].value = f"{self.last_weather_data['temperature']:.0f}°"
        main_card["weather_desc"].value = f"{cond} | {self.last_weather_data['wind_speed']} km/h"
        
        self.page.update()
    
    def toggle_theme(self, e):
        ##Toggles between light and dark theme
        is_dark = self.page.theme_mode == ft.ThemeMode.DARK
        self.page.theme_mode = ft.ThemeMode.LIGHT if is_dark else ft.ThemeMode.DARK
        self.page.bgcolor = "#FFFFFF" if is_dark else "#000000"
        
        e.control.icon = ft.Icons.DARK_MODE if is_dark else ft.Icons.WB_SUNNY
        e.control.icon_color = "black" if is_dark else "white"
        
        # Update text colors
        text_col = "black" if is_dark else "white"
        self.ui["main_card"]["title_text_1"].color = text_col
        self.ui["main_card"]["title_text_2"].color = text_col
        
        self.page.appbar.bgcolor = "#F0F0F0" if is_dark else "#121212"
        self.page.update()
    
    def on_generate_click(self, e):
        ##Generates a new playlist based on weather
        main_card = self.ui["main_card"]
        gen_btn = main_card["gen_btn"]
        progress = main_card["progress"]
        status_container = main_card["status_container"]
        status_text = main_card["status_text"]
        status_icon = main_card["status_icon"]
        playlist_link = main_card["playlist_link"]
        
        # Update UI - start process
        gen_btn.text = "SCANNING..."
        gen_btn.disabled = True
        progress.visible = True
        playlist_link.visible = False
        status_container.visible = False
        
        # Close panels
        self.close_left_panel(None)
        self.close_right_panel(None)
        
        self.page.update()
        
        try:
            # Get weather
            self.last_weather_data = get_current_weather()
            self.update_weather_display()
            
            # Create playlist
            msg, url, tech, preview = create_spotify_playlist(
                self.last_weather_data,
                self.sp_client
            )
            
            self.last_tech_data = tech
            self.last_preview_list = preview
            progress.visible = False
            
            # Update UI - result
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
            print(f"Generation error: {err}")
            status_text.value = "Error"
            status_container.bgcolor = "red"
            status_container.visible = True
        
        # Restore button
        gen_btn.text = "GENERATE VIBE"
        gen_btn.disabled = False
        progress.visible = False
        self.page.update()