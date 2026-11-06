from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Location(Strict):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_km: float = Field(default=10, ge=1, le=50)
    days: int = Field(default=1, ge=1, le=5)

class Weather(Strict):
    temperature_c: float = Field(ge=-100, le=70)
    humidity_pct: float = Field(ge=0, le=100)
    wind_kmh: float = Field(ge=0, le=500)
    wind_direction_deg: float = Field(ge=0, le=360)
    precipitation_mm: float = Field(ge=0)

class Hotspot(Strict):
    id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    observed_at: datetime
    confidence: Literal['low','nominal','high']
    frp_mw: float | None = Field(default=None, ge=0)
    distance_km: float = Field(ge=0)

class Envelope(Strict):
    schema_version: str = '1.0'
    source: str
    simulated: bool
    status: Literal['ok','unavailable','stale']
    observed_at: datetime | None
    fetched_at: datetime
    data: Weather | list[Hotspot] | None
    warnings: list[str] = []

class Context(Strict):
    query: Location
    weather: Envelope
    hotspots: Envelope
    risk: dict
