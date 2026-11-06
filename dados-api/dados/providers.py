"""Conectores de saída. Nenhuma falha de provedor vira dado simulado."""
import asyncio
import csv
import hashlib
import io
import math
from datetime import datetime, timezone
import httpx
from .models import Envelope, Hotspot, Weather

UTC = timezone.utc

def now():
    return datetime.now(UTC)

def distance(lat1, lon1, lat2, lon2):
    a,b = math.radians(lat1), math.radians(lat2)
    d = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(d)))

def unavailable(source, reason):
    return Envelope(source=source, simulated=False, status='unavailable', observed_at=None,
                    fetched_at=now(), data=None, warnings=[reason])

async def fetch(client, url, params=None):
    # Até duas tentativas, somente para timeout, 429 e erros de servidor.
    for attempt in range(2):
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            if attempt or (exc.response.status_code != 429 and exc.response.status_code < 500):
                raise
        except httpx.TransportError:
            if attempt:
                raise
        await asyncio.sleep(0.2)

async def weather(client, q):
    source = 'Open-Meteo'
    try:
        r = await fetch(client, 'https://api.open-meteo.com/v1/forecast', {
            'latitude': q.latitude, 'longitude': q.longitude,
            'current': 'temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation',
            'timezone': 'GMT', 'wind_speed_unit': 'kmh', 'temperature_unit': 'celsius',
            'precipitation_unit': 'mm'})
        c = r.json()['current']
        observed = datetime.fromisoformat(c['time']).replace(tzinfo=UTC)
        age = (now()-observed).total_seconds()
        if age < -3600:
            raise ValueError('future observation')
        stale = age > 3*3600
        return Envelope(source=source, simulated=False, status='stale' if stale else 'ok',
            observed_at=observed, fetched_at=now(),
            data=Weather(temperature_c=c['temperature_2m'], humidity_pct=c['relative_humidity_2m'],
                wind_kmh=c['wind_speed_10m'], wind_direction_deg=c['wind_direction_10m'],
                precipitation_mm=c['precipitation']),
            warnings=['Dados de modelo meteorológico; não são medição em sua propriedade.'] +
                     (['Referência meteorológica com mais de 3 horas.'] if stale else []))
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return unavailable(source, 'Falha de consulta ou resposta inválida do provedor.')

def parse_firms(text, q):
    reader = csv.DictReader(io.StringIO(text))
    required = {'latitude','longitude','acq_date','acq_time','confidence','frp'}
    if not required.issubset(set(reader.fieldnames or [])):
        raise ValueError('Cabeçalho FIRMS inválido')
    result = {}
    for row in reader:
        lat, lon = float(row['latitude']), float(row['longitude'])
        d = distance(q.latitude, q.longitude, lat, lon)
        observed = datetime.strptime(row['acq_date']+' '+row['acq_time'].zfill(4), '%Y-%m-%d %H%M').replace(tzinfo=UTC)
        # Valida também linhas fora do raio; não aceita CSV parcialmente corrompido.
        item = Hotspot(id=hashlib.sha256(f'VIIRS_SNPP_NRT|{lat}|{lon}|{observed}'.encode()).hexdigest()[:24],
            latitude=lat, longitude=lon, observed_at=observed,
            confidence={'l':'low','n':'nominal','h':'high'}[row['confidence'].lower()],
            frp_mw=float(row['frp']) if row['frp'] else None, distance_km=round(d,3))
        if d <= q.radius_km:
            result[item.id] = item
    return sorted(result.values(), key=lambda x:x.observed_at, reverse=True)

async def hotspots(client, q, key):
    source = 'NASA FIRMS / VIIRS_SNPP_NRT'
    if not key:
        return unavailable(source, 'FIRMS_MAP_KEY não configurada.')
    # Caixa conservadora; Haversine aplica o raio exato depois da consulta.
    delta_lat = q.radius_km / 110.0
    south, north = max(-90,q.latitude-delta_lat), min(90,q.latitude+delta_lat)
    cosine = math.cos(math.radians(max(abs(south),abs(north))))
    delta_lon = min(180,q.radius_km/(110*max(cosine,0.00001)))
    west, east = q.longitude-delta_lon, q.longitude+delta_lon
    if west < -180 or east > 180:
        return unavailable(source, 'Consulta cruzando o antimeridiano ainda não suportada.')
    bbox = f'{west},{south},{east},{north}'
    try:
        r = await fetch(client, f'https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/{bbox}/{q.days}')
        data = parse_firms(r.text, q)
        return Envelope(source=source, simulated=False, status='ok',
            observed_at=max((x.observed_at for x in data),default=None), fetched_at=now(), data=data,
            warnings=['Foco de calor não confirma incêndio nem representa área queimada.',
                      'Lista vazia não garante ausência de fogo; depende de passagem e cobertura do satélite.'])
    except (httpx.HTTPError, ValueError, KeyError, TypeError, csv.Error):
        # Não devolver URL/erro bruto: a chave FIRMS aparece na URL.
        return unavailable(source, 'Falha de consulta ou CSV inválido do provedor.')

def demo(q):
    t = datetime(2026,1,1,12,tzinfo=UTC)
    common = dict(simulated=True, status='ok', observed_at=t, fetched_at=now(),
                  warnings=['Cenário fixo fictício para demonstração; não indica condições atuais.'])
    w = Envelope(source='DEMO meteorologia', data=Weather(temperature_c=32,humidity_pct=25,
        wind_kmh=18,wind_direction_deg=90,precipitation_mm=0), **common)
    h = Envelope(source='DEMO satélite', data=[Hotspot(id='demo-1',latitude=q.latitude,
        longitude=q.longitude,observed_at=t,confidence='nominal',frp_mw=8,distance_km=0)], **common)
    return w,h
