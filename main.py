import flet as ft
from config import WINDOW_WIDTH, WINDOW_HEIGHT, COLOR_DARK_BG
from spotify_manager import initialize_spotify_client, get_user_info
from splash_screen import show_splash_with_connection
from ui_components import create_main_card, create_side_panel
from event_handlers import EventHandlers
from utils import ClockManager, create_appbar


def main(page: ft.Page):
    # Page configuration
    page.title = "Vienna Weather Vibe"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = COLOR_DARK_BG
    page.window_width = WINDOW_WIDTH
    page.window_height = WINDOW_HEIGHT
    page.padding = 20
    
    # SPLASH SCREEN AND CONNECTION 
    def connection_callback():
        ##Handles Spotify connection
        try:
            sp_client = initialize_spotify_client()
            user_name, user_id = get_user_info(sp_client)
            return True, user_name, sp_client
        except Exception as e:
            print(f"Connection error: {e}")
            return False, "Guest", None
    
    user_name, sp_client = show_splash_with_connection(page, connection_callback)
    
    # CREATE UI ELEMENTS
    
    # Main card
    main_card_elements = create_main_card()
    
    # Side panels
    left_panel_elements = create_side_panel("Forecast ⛅", ft.Icons.CALENDAR_MONTH, is_left=True)
    right_panel_elements = create_side_panel("Sneak Peek 🎵", ft.Icons.MUSIC_NOTE, is_left=False)
    
    # Gather all UI elements
    ui_elements = {
        "main_card": main_card_elements,
        "left_panel": left_panel_elements,
        "right_panel": right_panel_elements
    }
    
    # EVENT HANDLERS
    
    event_handlers = EventHandlers(page, ui_elements, sp_client)
    
    # Connect panel events
    left_panel_elements["close_btn"].on_click = event_handlers.close_left_panel
    right_panel_elements["close_btn"].on_click = event_handlers.close_right_panel
    
    # Connect main button event
    main_card_elements["gen_btn"].on_click = event_handlers.on_generate_click
    
    # CLOCK
    
    clock_manager = ClockManager(page)
    clock_manager.start()
    
    # APPLICATION BAR 
    
    page.appbar = create_appbar(clock_manager, user_name, event_handlers)
    
    # LAYOUT
    
    page.add(
        ft.Row(
            [
                left_panel_elements["panel"],
                main_card_elements["card"],
                right_panel_elements["panel"]
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.START,
            spacing=20
        )
    )


if __name__ == "__main__":
    ft.app(target=main, view=ft.WEB_BROWSER, port=8888)