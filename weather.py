import re
import time

import requests
from datetime import datetime

_weather_cache: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 300  # seconds


def _esc(value) -> str:
    """Escape MarkdownV2 special characters in a plain-text fragment."""
    return re.sub(r'([_*\[\]()~`#+\-=|{}.!\\])', r'\\\1', str(value))

AUSTRIAN_CITIES = {
    "Wien": {"lat": 48.2082, "lon": 16.3738},
    "Graz": {"lat": 47.0707, "lon": 15.4395},
    "Linz": {"lat": 48.3069, "lon": 14.2858},
    "Salzburg": {"lat": 47.8095, "lon": 13.0550},
    "Innsbruck": {"lat": 47.2692, "lon": 11.4041},
    "Klagenfurt": {"lat": 46.6228, "lon": 14.3050},
    "Wels": {"lat": 48.1574, "lon": 14.0280},
    "St. Pölten": {"lat": 48.2047, "lon": 15.6256},
    "Dornbirn": {"lat": 47.4125, "lon": 9.7417},
    "Bregenz": {"lat": 47.5031, "lon": 9.7471},
    "Villach": {"lat": 46.6167, "lon": 13.8500},
    "Steyr": {"lat": 48.0397, "lon": 14.4208},
}

WMO_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Heavy freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def describe_wmo(code: int) -> str:
    return WMO_DESCRIPTIONS.get(code, f"Condition {code}")


def get_weather(city: str) -> dict:
    if city not in AUSTRIAN_CITIES:
        raise ValueError(f"Unknown city: {city}")

    now = time.monotonic()
    cached = _weather_cache.get(city)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]

    coords = AUSTRIAN_CITIES[city]
    params = {
        "latitude": coords["lat"],
        "longitude": coords["lon"],
        "hourly": [
            "temperature_2m",
            "apparent_temperature",
            "uv_index",
            "precipitation",
            "weathercode",
        ],
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "sunrise",
            "sunset",
            "uv_index_max",
            "wind_speed_10m_max",
        ],
        "timezone": "Europe/Vienna",
        "forecast_days": 2,
    }

    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params=params,
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    _weather_cache[city] = (time.monotonic(), data)
    return data


def make_caption(data: dict, city: str) -> str:
    hourly = data["hourly"]
    daily = data["daily"]

    temp_max = daily["temperature_2m_max"][0]
    temp_min = daily["temperature_2m_min"][0]
    uv_max = daily["uv_index_max"][0]
    wind_max = daily["wind_speed_10m_max"][0]
    sunrise = daily["sunrise"][0][11:16]
    sunset = daily["sunset"][0][11:16]

    noon_code = hourly["weathercode"][12]
    condition = describe_wmo(noon_code)

    max_rain = max(hourly["precipitation"][:24])

    if uv_max < 3:
        uv_level = "Low"
    elif uv_max < 6:
        uv_level = "Moderate"
    elif uv_max < 8:
        uv_level = "High"
    elif uv_max < 11:
        uv_level = "Very High"
    else:
        uv_level = "Extreme"

    date_str = hourly["time"][0][:10]
    date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %d %B %Y")

    return (
        f"*{_esc(city)}* — {_esc(date_display)}\n"
        f"_{_esc(condition)}_\n\n"
        f"🌡 Max *{_esc(f'{temp_max:.1f}')}°C* / Min *{_esc(f'{temp_min:.1f}')}°C*\n"
        f"🌧 Rain up to *{_esc(f'{max_rain:.1f}')}* mm/h\n"
        f"💨 Wind max: *{_esc(f'{wind_max:.0f}')}* km/h\n"
        f"☀️ UV max: *{_esc(f'{uv_max:.1f}')}* \\({_esc(uv_level)}\\)\n"
        f"🌅 {_esc(sunrise)} rise  🌇 {_esc(sunset)} set"
    )
