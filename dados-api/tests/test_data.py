import asyncio
from datetime import datetime, timezone
import httpx
import pytest
from fastapi.testclient import TestClient
from dados.main import create_app
from dados.models import Location
from dados.providers import parse_firms, weather, hotspots

KEY='test-key-with-at-least-24-characters'
Q={'latitude':-22.0,'longitude':-47.0}
CSV='latitude,longitude,acq_date,acq_time,confidence,frp\n-22,-47,2026-01-01,0150,n,8\n-22,-47,2026-01-01,0150,n,8\n-25,-50,2026-01-01,0150,l,1\n'

def test_demo_contract_auth_and_validation():
    c=TestClient(create_app('demo',KEY))
    assert c.post('/v1/context',json=Q).status_code==401
    r=c.post('/v1/context',json=Q,headers={'X-API-Key':KEY})
    assert r.status_code==200
    assert r.json()['weather']['simulated'] is True
    assert r.json()['risk']['level'] is None
    for invalid in ({**Q,'latitude':91},{**Q,'days':6},{**Q,'unexpected':1}):
        assert c.post('/v1/context',json=invalid,headers={'X-API-Key':KEY}).status_code==422

def test_firms_dedup_distance_and_utc():
    data=parse_firms(CSV,Location(**Q))
    assert len(data)==1
    assert data[0].distance_km==0
    assert data[0].observed_at.hour==1
    assert data[0].observed_at.tzinfo is not None
    with pytest.raises(ValueError):
        parse_firms('Invalid MAP_KEY',Location(**Q))

def test_real_provider_mapping():
    def handler(req):
        if 'open-meteo' in str(req.url):
            assert req.url.params['wind_speed_unit']=='kmh'
            return httpx.Response(200,json={'current':{'time':datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M'),
                'temperature_2m':30,'relative_humidity_2m':40,'wind_speed_10m':12,'wind_direction_10m':90,'precipitation':0}})
        assert '/VIIRS_SNPP_NRT/' in str(req.url)
        return httpx.Response(200,text=CSV)
    c=TestClient(create_app('live',KEY,'fake-key',httpx.MockTransport(handler)))
    data=c.post('/v1/context',json=Q,headers={'X-API-Key':KEY}).json()
    assert data['weather']['simulated'] is False
    assert data['weather']['data']['wind_kmh']==12
    assert len(data['hotspots']['data'])==1

def test_partial_unavailable_no_silent_mock():
    c=TestClient(create_app('live',KEY,'',httpx.MockTransport(lambda r:httpx.Response(503))))
    data=c.post('/v1/context',json=Q,headers={'X-API-Key':KEY}).json()
    assert data['weather']['status']=='unavailable'
    assert data['hotspots']['status']=='unavailable'
    assert data['weather']['data'] is None
    assert data['weather']['simulated'] is False

def test_old_weather_flagged_stale():
    def handler(req):
        return httpx.Response(200,json={'current':{'time':'2020-01-01T00:00','temperature_2m':30,
            'relative_humidity_2m':40,'wind_speed_10m':12,'wind_direction_10m':90,'precipitation':0}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result=await weather(client,Location(**Q))
            assert result.status=='stale'
    asyncio.run(run())

def test_empty_csv_is_not_provider_failure():
    assert parse_firms(CSV.splitlines()[0]+'\n',Location(**Q))==[]

def test_retry_transient_only():
    calls=[]
    def handler(req):
        calls.append(1)
        return httpx.Response(503 if len(calls)==1 else 200,text=CSV)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result=await hotspots(client,Location(**Q),'fake')
            assert result.status=='ok'
    asyncio.run(run())
    assert len(calls)==2
