import spotipy
from spotipy.oauth2 import SpotifyOAuth, CacheFileHandler
import random
from config import SCOPE, REDIRECT_URI, SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET
from weather_logic import map_weather_to_spotify, MOOD_TO_SPOTIFY


def initialize_spotify_client():
    
    ##Initializes and returns an authenticated Spotify client
    
    handler = CacheFileHandler(cache_path=".spotipyoauthcache")
    sp = spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            scope=SCOPE,
            cache_handler=handler
        )
    )
    return sp


def get_user_info(sp_client):
    
    ## Retrieves information for the connected user
    
    try:
        user_data = sp_client.me()
        return user_data.get('display_name', 'Music Lover'), user_data.get('id')
    except Exception as e:
        print(f"Error fetching user info: {e}")
        return "Guest", None


def get_tracks_for_mood_via_search(sp_client, mood: str, desired_count: int = 25, market: str = "AT"):
    
    ## Searches for Spotify tracks based on a given mood
    
    cfg = MOOD_TO_SPOTIFY.get(mood, MOOD_TO_SPOTIFY["Neutral"])
    genres = cfg["seed_genres"]
    all_tracks = []
    
    # Search by individual genre
    for genre in genres:
        try:
            results = sp_client.search(q=f'genre:"{genre}"', type="track", limit=50, market=market)
            items = results.get("tracks", {}).get("items", [])
            all_tracks.extend(t["uri"] for t in items if t.get("uri"))
        except:
            pass
    
    # Combined search if not enough results
    if len(all_tracks) < desired_count:
        try:
            or_query = " OR ".join([f'genre:"{g}"' for g in genres])
            results2 = sp_client.search(q=or_query, type="track", limit=50, market=market)
            items2 = results2.get("tracks", {}).get("items", [])
            all_tracks.extend(t["uri"] for t in items2 if t.get("uri"))
        except:
            pass
    
    # Deduplicate and shuffle
    all_tracks = list(dict.fromkeys(all_tracks))
    random.shuffle(all_tracks)
    return all_tracks[:desired_count]


def get_track_preview_info(sp_client, track_uris, count=6):
    
    ##Retrieves preview information for the first tracks
    ##Return format: list of strings "artist|title|image_url"
    
    preview_list = []
    try:
        top_tracks = sp_client.tracks(track_uris[:count])
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
    
    return preview_list


def create_spotify_playlist(weather_data, sp_client):
    
    ##Creates a Spotify playlist based on weather data
    ##Returns: (message, url, tech_data, preview_list)
    
    params = map_weather_to_spotify(weather_data)
    mood = params.pop("_mood", "Neutral")
    
    # Data for display
    tech_data = {
        "Mood": mood,
        "Valence": params.get('target_valence', 0.5),
        "Energy": params.get('target_energy', 0.5),
        "Tempo": int(params.get('target_tempo', 100)),
        "Genres": params.get('seed_genres', [])[:3]
    }
    
    desired_count = params.get("limit", 25)
    
    # Search for tracks
    try:
        track_uris = get_tracks_for_mood_via_search(
            sp_client, 
            mood=mood, 
            desired_count=desired_count
        )
    except Exception as e:
        return f"Search Error: {e}", None, None, None
    
    if len(track_uris) < 5:
        return f"Not enough tracks ({len(track_uris)}).", None, None, None
    
    # Track preview
    preview_list = get_track_preview_info(sp_client, track_uris)
    
    # Create playlist
    try:
        user_id = sp_client.me()["id"]
        playlist_name = f"Vienna Vibe: {weather_data['condition']} 🇦🇹"
        playlist = sp_client.user_playlist_create(
            user=user_id,
            name=playlist_name,
            public=True,
            description=f"Weather: {weather_data['description']} | Mood: {mood}"
        )
        sp_client.playlist_add_items(playlist_id=playlist["id"], items=track_uris)
        
        return "Playlist Created!", playlist["external_urls"]["spotify"], tech_data, preview_list
    
    except Exception as e:
        return f"Creation Error: {e}", None, None, None