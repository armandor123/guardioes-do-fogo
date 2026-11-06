from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid',allow_inf_nan=False,str_strip_whitespace=True)

class Login(Strict):
    username: str = Field(min_length=3,max_length=80)
    password: str = Field(min_length=1,max_length=128)
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=False)

class Password(Strict):
    old_password: str = Field(min_length=1,max_length=128)
    new_password: str = Field(min_length=12,max_length=128)
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=False)

class Farmer(Strict):
    name: str = Field(min_length=2,max_length=120)
    username: str = Field(pattern=r'^[a-zA-Z0-9_.-]{3,80}$')

class Property(Strict):
    farmer_id: str
    name: str = Field(default='',max_length=120)
    municipality: str = Field(min_length=2,max_length=120)
    state: str = Field(pattern=r'^(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)$')
    latitude: float = Field(ge=-90,le=90)
    longitude: float = Field(ge=-180,le=180)
    area_ha: float | None = Field(default=None,ge=0)

class Incident(Strict):
    client_request_id: UUID
    property_id: str
    description: str = Field(default='',max_length=2000)
    latitude: float | None = Field(default=None,ge=-90,le=90)
    longitude: float | None = Field(default=None,ge=-180,le=180)
    location_source: Literal['gps','manual','unavailable'] = 'unavailable'
    location_authorized: bool = False

    @model_validator(mode='after')
    def coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Informe ambas as coordenadas')
        if self.location_source == 'unavailable':
            if self.latitude is not None:
                raise ValueError('Coordenadas incompatíveis com localização indisponível')
        elif self.latitude is None or not self.location_authorized:
            raise ValueError('Localização exige coordenadas e autorização')
        return self

class Review(Strict):
    status: Literal['under_review','verified','rejected','escalated']
    notes: str = Field(min_length=5,max_length=2000)

class Refresh(Strict):
    refresh_token: str = Field(min_length=20,max_length=200)
