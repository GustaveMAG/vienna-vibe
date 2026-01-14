import flet as ft
from config import COLOR_SPOTIFY_GREEN


def get_card_gradient(condition):
    
    ##Returns a gradient adapted to the weather condition
    gradients = {
        "Clear": ft.LinearGradient(
            colors=["#ff9966", "#ff5e62"],
            begin=ft.alignment.top_left,
            end=ft.alignment.bottom_right
        ),
        "Rain": ft.LinearGradient(
            colors=["#000046", "#1CB5E0"],
            begin=ft.alignment.top_center,
            end=ft.alignment.bottom_center
        ),
        "Cloudy": ft.LinearGradient(
            colors=["#304352", "#d7d2cc"],
            begin=ft.alignment.top_left,
            end=ft.alignment.bottom_right
        ),
        "Snow": ft.LinearGradient(
            colors=["#83a4d4", "#b6fbff"],
            begin=ft.alignment.top_center,
            end=ft.alignment.bottom_center
        ),
        "Thunderstorm": ft.LinearGradient(
            colors=["#232526", "#414345"],
            begin=ft.alignment.top_center,
            end=ft.alignment.bottom_center
        )
    }
    
    return gradients.get(
        condition,
        ft.LinearGradient(
            colors=["#2b2b2b", "#1a1a1a"],
            begin=ft.alignment.top_left,
            end=ft.alignment.bottom_right
        )
    )


def get_weather_icon(condition):
    
    ##Returns the appropriate icon for a weather condition
    
    icons = {
        "Clear": ft.Icons.WB_SUNNY,
        "Rain": ft.Icons.WATER_DROP,
        "Cloudy": ft.Icons.CLOUD,
        "Snow": ft.Icons.AC_UNIT,
        "Thunderstorm": ft.Icons.FLASH_ON
    }
    return icons.get(condition, ft.Icons.MUSIC_NOTE)


def create_track_tile(index, artist, title, img_url):
    
    ##Creates a display tile for a track
    
    if img_url:
        visual_content = ft.Image(
            src=img_url,
            width=40,
            height=40,
            border_radius=5,
            fit=ft.ImageFit.COVER
        )
    else:
        visual_content = ft.Container(
            content=ft.Icon(ft.Icons.MUSIC_NOTE, color=COLOR_SPOTIFY_GREEN, size=20),
            width=40,
            height=40,
            bgcolor="#282828",
            border_radius=5,
            alignment=ft.alignment.center
        )
    
    return ft.Container(
        content=ft.Row([
            visual_content,
            ft.Column([
                ft.Text(
                    title,
                    color="white",
                    weight="bold",
                    size=13,
                    overflow=ft.TextOverflow.ELLIPSIS
                ),
                ft.Text(
                    artist,
                    color="grey",
                    size=11,
                    overflow=ft.TextOverflow.ELLIPSIS
                )
            ], spacing=2, expand=True)
        ], alignment=ft.MainAxisAlignment.START),
        padding=ft.padding.only(bottom=10),
        border=ft.border.only(bottom=ft.border.BorderSide(1, "#222222"))
    )


def create_forecast_card(date_label, condition, tmax, tmin):
    
    ##Creates a display card for weather forecast
    
    icon = ft.Icon(get_weather_icon(condition), size=22, color=COLOR_SPOTIFY_GREEN)
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
        shadow=ft.BoxShadow(
            blur_radius=6,
            color="#000000",
            offset=ft.Offset(0, 3)
        )
    )


def create_main_card():
    
    ##Creates and returns all elements of the main card
    
    title_text_1 = ft.Text(
        "VIENNA",
        size=24,
        weight=ft.FontWeight.BOLD,
        color="white",
        style=ft.TextStyle(letter_spacing=2)
    )
    title_text_2 = ft.Text(
        "VIBE",
        size=24,
        weight=ft.FontWeight.BOLD,
        color="white",
        style=ft.TextStyle(letter_spacing=2)
    )
    title_row = ft.Row(
        [title_text_1, title_text_2],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=5
    )
    subtitle = ft.Text("Vienna Weather Station", size=12, color="white70")
    
    weather_icon = ft.Icon(name=ft.Icons.CLOUD_QUEUE, size=50, color="white70")
    weather_temp = ft.Text("--°", size=50, weight=ft.FontWeight.BOLD, color="white")
    weather_desc = ft.Text("Ready to scan", size=16, color="white70")
    weather_row = ft.Row(
        [weather_icon, weather_temp],
        alignment=ft.MainAxisAlignment.CENTER
    )
    
    status_text = ft.Text("", size=14, color="white", weight=ft.FontWeight.BOLD)
    status_icon = ft.Icon(ft.Icons.CHECK_CIRCLE, color="white", size=20)
    status_container = ft.Container(
        content=ft.Row(
            [status_icon, status_text],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=10
        ),
        bgcolor=COLOR_SPOTIFY_GREEN,
        padding=ft.padding.symmetric(horizontal=20, vertical=12),
        border_radius=30,
        visible=False,
        animate_opacity=300
    )
    
    playlist_link = ft.ElevatedButton(
        "OPEN IN SPOTIFY",
        url="",
        visible=False,
        icon=ft.Icons.OPEN_IN_NEW,
        bgcolor="white",
        color="black",
        height=50,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=30))
    )
    
    progress = ft.ProgressBar(
        width=200,
        color="white",
        bgcolor="white24",
        visible=False
    )
    
    gen_btn = ft.ElevatedButton(
        text="GENERATE VIBE",
        icon=ft.Icons.PLAY_CIRCLE_FILLED,
        bgcolor=COLOR_SPOTIFY_GREEN,
        color="white",
        width=260,
        height=55,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=30),
            text_style=ft.TextStyle(size=16, weight=ft.FontWeight.BOLD)
        )
    )
    
    main_card = ft.Container(
        content=ft.Column([
            title_row,
            subtitle,
            ft.Divider(color="white24", height=30),
            weather_row,
            weather_desc,
            ft.Container(height=20),
            gen_btn,
            ft.Container(height=20),
            progress,
            status_container,
            playlist_link,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        width=360,
        height=600,
        padding=40,
        gradient=get_card_gradient("Neutral"),
        border_radius=30,
        animate=ft.Animation(duration=500, curve="easeOut"),
        shadow=ft.BoxShadow(
            blur_radius=30,
            color="#121212",
            offset=ft.Offset(0, 10)
        ),
    )
    
    return {
        "card": main_card,
        "title_text_1": title_text_1,
        "title_text_2": title_text_2,
        "weather_icon": weather_icon,
        "weather_temp": weather_temp,
        "weather_desc": weather_desc,
        "status_text": status_text,
        "status_icon": status_icon,
        "status_container": status_container,
        "playlist_link": playlist_link,
        "progress": progress,
        "gen_btn": gen_btn
    }


def create_side_panel(title, icon, is_left=True):
    
    ##Creates a side panel (left or right)
    
    panel_title = ft.Text(title, weight="bold", size=18, color="white")
    close_btn = ft.IconButton(ft.Icons.CLOSE, icon_color="white24", tooltip="Close")
    
    content_column = ft.Column(
        [],
        spacing=15 if not is_left else 20,
        scroll=ft.ScrollMode.HIDDEN if not is_left else None,
        alignment=ft.MainAxisAlignment.CENTER if is_left else None,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER if is_left else None
    )
    
    panel_children = [
        ft.Row(
            [panel_title, close_btn],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        ),
        ft.Container(content=ft.Divider(color="white12"), width=280),
    ]
    
    if is_left:
        panel_children.append(
            ft.Container(
                content=content_column,
                expand=True,
                alignment=ft.alignment.center
            )
        )
    else:
        panel_children.extend([
            content_column,
            ft.Container(height=10),
            ft.Text(
                "Full playlist is on Spotify.",
                size=10,
                color="grey",
                italic=True,
                text_align=ft.TextAlign.CENTER
            )
        ])
    
    panel = ft.Container(
        content=ft.Column(
            panel_children,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER if not is_left else None
        ),
        width=0,
        height=600,
        padding=0,
        bgcolor="#111111",
        border_radius=20,
        animate=ft.Animation(400, "easeOut"),
        animate_opacity=200,
        opacity=0,
        border=ft.border.all(1, "#333333"),
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        shadow=ft.BoxShadow(
            blur_radius=20,
            color="#000000",
            offset=ft.Offset(0, 5)
        )
    )
    
    return {
        "panel": panel,
        "content": content_column,
        "close_btn": close_btn
    }