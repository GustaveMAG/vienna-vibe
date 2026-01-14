
import flet as ft
import datetime
import threading
import time


class ClockManager:
    ##Manages the clock display and updates
    
    
    def __init__(self, page):
        self.page = page
        self.clock_text = ft.Text(
            datetime.datetime.now().strftime("%a %d %b %H:%M:%S"),
            size=12,
            color="grey"
        )
        self._running = False
        self._thread = None
    
    def get_control(self):
        ##Returns the clock UI control
        return self.clock_text
    
    def update(self):
        ##Manually updates the clock
        self.clock_text.value = datetime.datetime.now().strftime("%a %d %b %H:%M:%S")
        try:
            self.page.update()
        except:
            pass
    
    def _clock_loop(self):
        ##Internal update loop
        while self._running:
            time.sleep(1)
            self.update()
    
    def start(self):
        ##Starts automatic update
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._clock_loop, daemon=True)
            self._thread.start()
    
    def stop(self):
        ##Stops automatic update
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)


def create_appbar(clock_manager, user_name, event_handlers):
    """
    Creates and returns the application bar (AppBar)
    
    Args:
        clock_manager: ClockManager instance
        user_name: User name
        event_handlers: EventHandlers instance
    
    Returns:
        Configured ft.AppBar
    """
    user_name_text = ft.Text(user_name, size=12, color="grey")
    
    appbar = ft.AppBar(
        leading=ft.Icon(ft.Icons.EQUALIZER, color="#1DB954"),
        leading_width=40,
        title=ft.Text("Vienna Vibe", size=16, weight=ft.FontWeight.BOLD),
        center_title=False,
        bgcolor="#121212",
        actions=[
            ft.Row(
                [clock_manager.get_control()],
                alignment=ft.MainAxisAlignment.CENTER
            ),
            ft.Container(width=8),
            ft.IconButton(
                ft.Icons.RESTART_ALT,
                icon_color="white",
                on_click=event_handlers.handle_reset,
                tooltip="Reset"
            ),
            ft.IconButton(
                ft.Icons.WB_SUNNY,
                icon_color="white",
                on_click=event_handlers.toggle_theme,
                tooltip="Switch Theme"
            ),
            ft.IconButton(
                ft.Icons.INSERT_CHART_OUTLINED,
                icon_color="#1DB954",
                on_click=event_handlers.toggle_left_panel,
                tooltip="Show Data (Left)"
            ),
            ft.IconButton(
                ft.Icons.QUEUE_MUSIC,
                icon_color="#1DB954",
                on_click=event_handlers.toggle_right_panel,
                tooltip="Show Tracks (Right)"
            ),
            ft.Container(width=12),
            ft.Row(
                [
                    ft.Icon(ft.Icons.PERSON, size=16, color="grey"),
                    user_name_text
                ],
                alignment=ft.MainAxisAlignment.CENTER
            ),
            ft.Container(width=15),
        ]
    )
    
    return appbar