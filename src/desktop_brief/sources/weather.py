"""Weather via wttr.in (free, no auth, JSON format)."""
from __future__ import annotations

import logging

import httpx

from desktop_brief.config import INTERVALS, Config
from desktop_brief.sources.base import Source
from desktop_brief.state import write_source

logger = logging.getLogger(__name__)


_ICONS = {
    "Sunny": "☀", "Clear": "☀",
    "Partly cloudy": "⛅", "Cloudy": "☁", "Overcast": "☁",
    "Mist": "🌫", "Fog": "🌫",
    "Patchy rain": "🌦", "Light rain": "🌦", "Moderate rain": "🌧", "Heavy rain": "🌧",
    "Thundery": "⛈", "Snow": "❄",
}


def _icon_for(condition: str) -> str:
    for key, icon in _ICONS.items():
        if key.lower() in condition.lower():
            return icon
    return "🌡"


class WeatherSource(Source):
    name = "weather"

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self._query = cfg.weather_query

    @property
    def interval_s(self) -> int:
        return INTERVALS["weather"]

    async def run_once(self) -> None:
        url = f"https://wttr.in/{self._query}?format=j1"
        async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": "desktop-brief/0.1"}) as c:
            r = await c.get(url)
            r.raise_for_status()
            j = r.json()

        cur = j["current_condition"][0]
        today = j["weather"][0]
        astro = today["astronomy"][0]
        condition = cur["weatherDesc"][0]["value"]
        data = {
            "location": self._query,
            "current": {
                "temp_f": int(cur["temp_F"]),
                "feels_like_f": int(cur["FeelsLikeF"]),
                "condition": condition,
                "icon": _icon_for(condition),
                "humidity": int(cur["humidity"]),
                "wind_mph": int(cur["windspeedMiles"]),
                "wind_dir": cur["winddir16Point"],
            },
            "today": {
                "high_f": int(today["maxtempF"]),
                "low_f": int(today["mintempF"]),
                "precip_chance": max(int(h.get("chanceofrain", 0)) for h in today["hourly"]),
                "sunrise": astro["sunrise"],
                "sunset": astro["sunset"],
            },
            "hourly": [
                {
                    "time": f"{int(h['time']) // 100:02d}:00",
                    "temp_f": int(h["tempF"]),
                    "condition": h["weatherDesc"][0]["value"],
                }
                for h in today["hourly"]
            ],
        }
        write_source("weather", data)
