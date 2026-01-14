import flet as ft
import time
from config import COLOR_SPOTIFY_GREEN


def create_splash_screen():
    ## Creates and returns the startup screen with all its elements
   
    splash_icon = ft.Icon(
        ft.Icons.EQUALIZER_ROUNDED,
        size=100,
        color=COLOR_SPOTIFY_GREEN,
        opacity=0,
        animate_opacity=ft.Animation(1000, "easeIn"),
        scale=0.5,
        animate_scale=ft.Animation(1000, "elasticOut")
    )
    
    splash_title = ft.Text(
        "VIENNA VIBE",
        size=40,
        weight=ft.FontWeight.BOLD,
        color="white",
        opacity=0,
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
    
    splash_progress = ft.ProgressBar(
        width=250,
        color=COLOR_SPOTIFY_GREEN,
        bgcolor="#333333",
        height=2,
        opacity=0,
        animate_opacity=500,
        value=0
    )
    
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
        animate_opacity=ft.Animation(800, "easeOut")
    )
    
    return {
        "container": splash_container,
        "icon": splash_icon,
        "title": splash_title,
        "status": splash_status,
        "progress": splash_progress
    }


def animate_splash_intro(page, splash_elements):
    
    ## Animates the splash screen 
    
    splash_icon = splash_elements["icon"]
    splash_title = splash_elements["title"]
    splash_progress = splash_elements["progress"]
    splash_status = splash_elements["status"]
    
    # Step 1: Logo appearance
    time.sleep(0.1)
    splash_icon.opacity = 1
    splash_icon.scale = 1
    page.update()
    time.sleep(0.8)
    
    # Step 2: Title and bar appearance
    splash_title.opacity = 1
    splash_progress.opacity = 1
    splash_status.opacity = 1
    page.update()
    time.sleep(0.5)


def update_splash_status(page, splash_elements, status_text, progress_value):
    
    # Status and progress of the splash screen
    
    splash_elements["status"].value = status_text
    splash_elements["progress"].value = progress_value
    page.update()


def animate_splash_exit(page, splash_elements):
    
    ## Splash screen exit
    
    splash_container = splash_elements["container"]
    splash_icon = splash_elements["icon"]
    
    # Fade out with logo zoom
    splash_container.opacity = 0
    splash_icon.scale = 1.5
    page.update()
    
    # Wait for animation to finish
    time.sleep(0.8)
    
    # Clean up
    page.clean()


def show_splash_with_connection(page, connection_callback):
    """
    Displays the splash screen and executes connection
    
    Args:
        page: The Flet page
        connection_callback: Connection function that returns (success, user_name, sp_client)
    
    Returns:
        tuple: (user_name, sp_client)
    """
    splash_elements = create_splash_screen()
    page.add(splash_elements["container"])
    page.update()
    
    # Animate intro
    animate_splash_intro(page, splash_elements)
    
    # Connection phase
    update_splash_status(page, splash_elements, "Connecting to Spotify...", 0.3)
    
    try:
        # Call connection function
        success, user_name, sp_client = connection_callback()
        
        if success:
            update_splash_status(page, splash_elements, "Ready to Vibe.", 1.0)
            splash_elements["progress"].color = "white"
            page.update()
            time.sleep(0.6)
        else:
            update_splash_status(page, splash_elements, "Connection failed (Offline mode)", 0.8)
            splash_elements["status"].color = "red"
            page.update()
            time.sleep(1)
    
    except Exception as e:
        print(f"Splash error: {e}")
        update_splash_status(page, splash_elements, "Error during initialization", 0.5)
        splash_elements["status"].color = "red"
        page.update()
        time.sleep(1)
        user_name = "Guest"
        sp_client = None
    
    # Animate exit
    animate_splash_exit(page, splash_elements)
    
    return user_name, sp_client