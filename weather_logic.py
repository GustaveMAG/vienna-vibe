# weather_logic.py
import requests
import datetime
import pytz 

# CONFIGURATION & DICTIONARY 
VIENNA_LAT = 48.2085
VIENNA_LON = 16.3721
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# We keep this dictionary because main.py imports it, even though we use smarter logic below
MOOD_TO_SPOTIFY = {
    "Energize": {"seed_genres": ["pop", "dance", "electronic"]},
    "Calm": {"seed_genres": ["acoustic", "jazz", "lo-fi"]},
    "Reflective": {"seed_genres": ["indie", "alternative"]},
    "Melancholy": {"seed_genres": ["blues", "sad", "piano"]},
    "Intense": {"seed_genres": ["rock", "metal", "punk"]},
    "Neutral": {"seed_genres": ["chill", "ambient"]},
}

# RETRIEVAL FUNCTION 
def get_current_weather():
    ##Retrieves weather and adds temporal details
    params = {
        "latitude": VIENNA_LAT,
        "longitude": VIENNA_LON,
        "hourly": "temperature_2m,rain,snowfall,wind_speed_10m,weather_code,visibility",
        "timezone": "auto",
        "forecast_days": 1
    }

    try:
        response = requests.get(WEATHER_URL, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Current hour
        now = datetime.datetime.now()
        current_hour_index = now.hour
        
        # Data extraction
        temp = data['hourly']['temperature_2m'][current_hour_index]
        weather_code = data['hourly']['weather_code'][current_hour_index]
        wind = data['hourly']['wind_speed_10m'][current_hour_index]
        
        # Determine condition
        condition = "Neutral"
        if weather_code == 0: condition = "Clear"
        elif weather_code in [1, 2, 3]: condition = "Cloudy"
        elif weather_code in [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82]: condition = "Rain"
        elif weather_code in [71, 73, 75, 77, 85, 86]: condition = "Snow"
        elif weather_code in [95, 96, 99]: condition = "Thunderstorm"

        description = f"{condition} | {temp:.1f}°C | Wind {wind:.1f} km/h"

        return {
            'condition': condition,
            'temperature': temp,
            'wind_speed': wind,
            'hour': current_hour_index,
            'description': description
        }

    except Exception as e:
        print(f"API Error: {e}")
        return {'condition': "Neutral", 'temperature': 15, 'wind_speed': 10, 'hour': 12, 'description': "Offline Mode"}

# SPOTIFY ALGORITHM 
def map_weather_to_spotify(weather_data):
    
    ##Calculates precise audio parameters (Valence, Energy, Tempo) based on weather AND time of day.
    
    
    condition = weather_data['condition']
    hour = weather_data['hour']
    temp = weather_data['temperature']
    wind = weather_data['wind_speed']
    
    # Default values
    seed_genres = ["pop"] 
    target_valence = 0.5  
    target_energy = 0.5   
    target_tempo = 110    
    target_acousticness = 0.0

    # TEMPORAL LOGIC
    if 5 <= hour < 12:
        time_vibe = "Morning"
        target_energy -= 0.2
    elif 12 <= hour < 18:
        time_vibe = "Day"
        target_energy += 0.2
    elif 19 <= hour < 23:
        time_vibe = "Evening"
        target_energy -= 0.1
        target_tempo -= 10
    else:
        time_vibe = "Night"
        target_energy = 0.4 
        seed_genres = ["deep-house", "ambient", "minimal-techno"]

    # WEATHER LOGIC
    if condition == "Clear":
        target_valence = 0.8
        if time_vibe == "Morning": seed_genres = ["acoustic", "folk", "singer-songwriter"]
        elif time_vibe == "Day": seed_genres = ["pop", "disco", "summer"]
        elif time_vibe == "Night": seed_genres = ["tropical-house", "synth-pop"]

    elif condition == "Cloudy":
        target_valence = 0.5
        seed_genres = ["indie", "alternative", "lo-fi"]
        
    elif condition == "Rain":
        target_valence = 0.3
        target_energy -= 0.1
        if time_vibe == "Night": seed_genres = ["jazz", "piano", "sleep"]
        else: seed_genres = ["blues", "soul", "r-n-b"]

    elif condition == "Snow":
        target_valence = 0.6 
        target_energy = 0.3
        target_tempo = 80
        seed_genres = ["classical", "ambient", "christmas"]

    elif condition == "Thunderstorm":
        target_energy = 0.9
        target_valence = 0.2 
        seed_genres = ["rock", "metal", "soundtracks"]

    # MICRO-ADJUSTMENTS
    if wind > 20: target_tempo += (wind * 0.5)
    if temp < 5: target_acousticness = 0.7
    else: target_acousticness = 0.2

    # Normalization
    target_valence = max(0, min(1, target_valence))
    target_energy = max(0, min(1, target_energy))

    return {
        "limit": 20,
        "seed_genres": seed_genres[:5],
        "target_valence": target_valence,
        "target_energy": target_energy,
        "target_tempo": target_tempo,
        "target_acousticness": target_acousticness,
        "_mood": f"{condition} {time_vibe}" 
    }


def get_forecast(forecast_days: int = 5):
    ##Returns a list of data for the next days:
    
    params = {
        "latitude": VIENNA_LAT,
        "longitude": VIENNA_LON,
        "daily": "temperature_2m_max,temperature_2m_min,weathercode",
        "timezone": "auto",
        "forecast_days": forecast_days
    }

    try:
        resp = requests.get(WEATHER_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        dates = data.get('daily', {}).get('time', [])
        tmax = data.get('daily', {}).get('temperature_2m_max', [])
        tmin = data.get('daily', {}).get('temperature_2m_min', [])
        codes = data.get('daily', {}).get('weathercode', [])

        forecast = []
        for i, d in enumerate(dates):
            code = codes[i] if i < len(codes) else None
            if code is None:
                condition = 'Neutral'
            elif code == 0:
                condition = 'Clear'
            elif code in [1,2,3]:
                condition = 'Cloudy'
            elif code in [51,53,55,56,57,61,63,65,66,67,80,81,82]:
                condition = 'Rain'
            elif code in [71,73,75,77,85,86]:
                condition = 'Snow'
            elif code in [95,96,99]:
                condition = 'Thunderstorm'
            else:
                condition = 'Neutral'

            forecast.append({
                'date': d,
                'max': tmax[i] if i < len(tmax) else None,
                'min': tmin[i] if i < len(tmin) else None,
                'weather_code': code,
                'condition': condition
            })

        return forecast
    except Exception as e:
        print(f"Forecast API error: {e}")
        return []


def get_hourly_forecast(date_str: str, days: int = 5):
    ##Returns the list of hours for a given date (YYYY-MM-DD).
    
    params = {
        "latitude": VIENNA_LAT,
        "longitude": VIENNA_LON,
        "hourly": "temperature_2m,weathercode,wind_speed_10m",
        "timezone": "auto",
        "forecast_days": days
    }

    try:
        resp = requests.get(WEATHER_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        times = data.get('hourly', {}).get('time', [])
        temps = data.get('hourly', {}).get('temperature_2m', [])
        codes = data.get('hourly', {}).get('weathercode', [])
        winds = data.get('hourly', {}).get('wind_speed_10m', [])

        hourly = []
        for i, t in enumerate(times):
            if t.startswith(date_str):
                hourly.append({
                    'time': t,
                    'temp': temps[i] if i < len(temps) else None,
                    'weather_code': codes[i] if i < len(codes) else None,
                    'wind': winds[i] if i < len(winds) else None
                })

        return hourly
    except Exception as e:
        print(f"Hourly forecast API error: {e}")
        return []