"""Weather without the LLM or an API key (Open-Meteo): instant, works for 'weather in X',
'will it rain tomorrow', 'do I need an umbrella'. Your home city is remembered ('my city is Pune')."""
import re

import requests

from Backend import Settings

_GEO = "https://geocoding-api.open-meteo.com/v1/search"
_API = "https://api.open-meteo.com/v1/forecast"
_UNITS_F = ("fahrenheit",)          # set Settings "units" to "fahrenheit" for degrees F

_CODES = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy",
          51: "drizzling lightly", 53: "drizzling", 55: "drizzling heavily", 61: "lightly raining", 63: "raining",
          65: "raining heavily", 66: "freezing rain", 67: "freezing rain", 71: "lightly snowing", 73: "snowing",
          75: "snowing heavily", 77: "snowing", 80: "showery", 81: "showery", 82: "pouring", 85: "snow showers",
          86: "snow showers", 95: "stormy", 96: "stormy with hail", 99: "stormy with hail"}
_CODES_DAY = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy",
              51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
              66: "freezing rain", 67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow",
              80: "rain showers", 81: "rain showers", 82: "heavy showers", 85: "snow showers", 86: "snow showers",
              95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail"}

_CITY_SET = re.compile(r"^(?:my (?:city|location|home|town) is|i live in|i'm in|i am in|set (?:my )?(?:city|location) to|"
                       r"change (?:my )?(?:city|location) to)\s+(.+)$")
_PLACE = re.compile(r"\b(?:in|at|for|of)\s+([a-z][a-z .'-]{1,40}?)(?:\s+(?:today|tomorrow|tonight|right now|now|this|next)\b|[?.!,]*$)")


def parse_city_command(text):
    """'my city is Pune' -> 'Pune' (used by the router), else None."""
    m = _CITY_SET.match(text.lower().strip(" .!?"))
    return m.group(1).strip().title() if m else None


def set_home_city(city):
    place = _find(city)
    if not place:
        return f"I couldn't find a place called {city}. Try the city's full name?"
    Settings.set("city", place["name"])
    Settings.set("lat", place["latitude"])
    Settings.set("lon", place["longitude"])
    return f"Got it, I'll use {place['name']} as your home city."


def _find(name):
    r = requests.get(_GEO, params={"name": name, "count": 1, "language": "en"}, timeout=6)
    r.raise_for_status()
    res = r.json().get("results") or []
    return res[0] if res else None


def _deg(c, f_units):
    return round(c * 9 / 5 + 32) if f_units else round(c)


def answer(text):
    """One spoken-style weather answer for the request."""
    low = text.lower()
    f_units = (Settings.get("units") or "").lower() in _UNITS_F
    try:
        m = _PLACE.search(low)
        place_name = m.group(1).strip().title() if m else None
        if place_name and place_name.lower() in ("the", "my", "here", "today", "me", "weather", "forecast"):
            place_name = None
        if place_name:
            place = _find(place_name)
            if not place:
                return f"I couldn't find a place called {place_name}."
            name, lat, lon = place["name"], place["latitude"], place["longitude"]
        elif Settings.get("city") and Settings.get("lat") is not None:
            name, lat, lon = Settings.get("city"), Settings.get("lat"), Settings.get("lon")
        else:
            return "Which city? Tell me, like, my city is Delhi, and I'll remember it. Or ask, what's the weather in Delhi?"

        r = requests.get(_API, params={
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 3,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"}, timeout=8)
        r.raise_for_status()
        d = r.json()
    except requests.RequestException:
        return "I couldn't reach the weather service. Check your connection and ask me again."

    cur, day = d["current"], d["daily"]
    idx = 1 if "tomorrow" in low else 0
    hi, lo = _deg(day["temperature_2m_max"][idx], f_units), _deg(day["temperature_2m_min"][idx], f_units)
    rain = day["precipitation_probability_max"][idx] or 0
    sky = _CODES_DAY.get(day["weather_code"][idx], "mixed")
    when = "tomorrow" if idx else "today"

    if re.search(r"\b(?:umbrella|rain|raining|rainy|snow|shower)\b", low):
        verdict = ("Yes, take one" if rain >= 50 else "Maybe pack one" if rain >= 25 else "Probably not") \
            if "umbrella" in low else ("Looks likely" if rain >= 50 else "Possibly" if rain >= 25 else "Unlikely")
        return f"{verdict}... it's a {rain} percent chance of rain in {name} {when}. Expect {sky}."

    if idx:
        return f"Tomorrow in {name}: {sky}, between {lo} and {hi} degrees" + (f", with a {rain} percent chance of rain." if rain >= 10 else ".")
    now_t = _deg(cur["temperature_2m"], f_units)
    feels = _deg(cur["apparent_temperature"], f_units)
    now_sky = _CODES.get(cur["weather_code"], "fine")
    feels_part = f", feels like {feels}" if abs(feels - now_t) >= 2 else ""
    rain_part = f" There's a {rain} percent chance of rain today." if rain >= 20 else ""
    return (f"Right now in {name} it's {now_t} degrees{feels_part} and {now_sky}. "
            f"Today's high is {hi}, low {lo}.{rain_part}")


if __name__ == "__main__":
    print(answer("what's the weather in Delhi"))
