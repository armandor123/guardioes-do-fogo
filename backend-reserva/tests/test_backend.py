import json
import uuid
import io
import time
import httpx
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from backend.main import create_app,passwords,digest
from backend.db import connect

@pytest.fixture
def system(tmp_path,pg_url):
    path=pg_url
    c=TestClient(create_app(path,photo_dir=tmp_path/'photos',data_transport=httpx.MockTransport(lambda r:httpx.Response(503))))
    with connect(path) as db:
        for coop in ('c1','c2'):
            db.execute('INSERT INTO cooperatives VALUES(%s,%s)',(coop,coop))
        for uid,coop,role in [('admin','c1','cooperative'),('farmer','c1','farmer'),('other','c1','farmer'),('outsider','c2','cooperative')]:
            db.execute('INSERT INTO users VALUES(%s,%s,%s,%s,%s,%s,FALSE)',(uid,coop,uid,uid,passwords.hash('initial-password-123'),role))
            db.execute('INSERT INTO sessions VALUES(%s,%s,%s,%s,%s,%s)',(uid,digest(uid),uid,time.time()+3600,digest('refresh-'+uid),time.time()+86400))
        db.execute('INSERT INTO properties(id,farmer_id,name,municipality,state,latitude,longitude,area_ha) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',('p1','farmer','Sitio','Campinas','SP',-22,-47,10))
    return c,path

def h(token):
    return {'Authorization':'Bearer '+token}

def photo():
    output=io.BytesIO()
    Image.new('RGB',(10,10),'green').save(output,format='PNG')
    return output.getvalue()

def send(c,raw=None,request_id=None,**fields):
    metadata={'client_request_id':request_id or str(uuid.uuid4()),'property_id':'p1',**fields}
    return c.post('/v1/incidents',headers=h('farmer'),data={'metadata':json.dumps(metadata)},
                  files={'photo':('image.png',raw if raw is not None else photo(),'image/png')})

def test_full_incident_review_flow_and_image(system):
    c,path=system
    r=send(c)
    assert r.status_code==201,r.text
    iid=r.json()['id']
    assert c.get(f'/v1/incidents/{iid}/photo',headers=h('farmer')).headers['content-type']=='image/jpeg'
    assert c.get(f'/v1/incidents/{iid}',headers=h('other')).status_code==404
    assert c.get(f'/v1/incidents/{iid}',headers=h('outsider')).status_code==404
    assert c.patch(f'/v1/incidents/{iid}/review',headers=h('admin'),json={'status':'verified','notes':'Ainda não permitido'}).status_code==409
    for status in ('under_review','verified','escalated'):
        r=c.patch(f'/v1/incidents/{iid}/review',headers=h('admin'),json={'status':status,'notes':'Avaliação humana de teste'})
        assert r.status_code==200,r.text
    item=c.get(f'/v1/incidents/{iid}',headers=h('admin')).json()
    assert len(item['reviews'])==3
    assert item['ai']['simulated'] is True
    assert c.get(f'/v1/incidents/{iid}/notification-draft',headers=h('admin')).json()['sent'] is False
    assert c.get('/v1/reports/summary',headers=h('admin')).json()['by_status']=={'escalated':1}

def test_farmer_temporary_password_and_revoke_sessions(system):
    c,path=system
    r=c.post('/v1/farmers',headers=h('admin'),json={'name':'Ana Silva','username':'ana.silva'})
    assert r.status_code==201
    temp=r.json()['temporary_password']
    login=c.post('/v1/auth/login',json={'username':'ana.silva','password':temp}).json()
    token=login['access_token']
    assert login['must_change_password'] is True
    assert c.get('/v1/properties',headers=h(token)).status_code==403
    assert c.post('/v1/auth/password',headers=h(token),json={'old_password':temp,'new_password':'new-strong-pass-123'}).status_code==200
    assert c.get('/v1/me',headers=h(token)).status_code==401
    new=c.post('/v1/auth/login',json={'username':'ana.silva','password':'new-strong-pass-123'}).json()['access_token']
    assert c.get('/v1/properties',headers=h(new)).status_code==200
    assert c.post('/v1/auth/logout',headers=h(new)).status_code==204
    assert c.get('/v1/me',headers=h(new)).status_code==401

def test_property_registration_and_cooperative_isolation(system):
    c,path=system
    body={'farmer_id':'farmer','municipality':'Campinas','state':'SP','latitude':-22,'longitude':-47,'area_ha':12}
    assert c.post('/v1/properties',headers=h('outsider'),json=body).status_code==404
    assert c.post('/v1/properties',headers=h('farmer'),json=body).status_code==403
    assert c.post('/v1/properties',headers=h('admin'),json=body).status_code==201
    assert c.get('/v1/reports/summary',headers=h('admin')).json()['registered_area_ha']==22
    assert c.get('/v1/properties',headers=h('outsider')).json()==[]
    assert c.get('/v1/reports/summary',headers=h('outsider')).json()['incidents']==0

def test_bad_image_and_location_rejected(system):
    c,path=system
    assert send(c,raw=b'not an image').status_code==422
    assert send(c,latitude=-22).status_code==422
    assert send(c,latitude=-22,longitude=-47,location_source='gps').status_code==422
    assert send(c,latitude=-22,longitude=-47,location_source='manual',location_authorized=True).status_code==201

def test_auth_security_and_service_failure(system):
    c,path=system
    assert c.get('/v1/properties').status_code==401
    assert c.get('/v1/properties/p1/environment',headers=h('farmer')).status_code==503
    assert c.get('/v1/properties/p1/environment',headers=h('other')).status_code==404
    assert c.get('/v1/sos').json()['automatic_dispatch'] is False
    assert c.post('/v1/farmers',headers=h('admin'),json={'name':'Teste','username':'test','role':'cooperative'}).status_code==422
    for _ in range(5):
        assert c.post('/v1/auth/login',json={'username':'missing','password':'bad'}).status_code==401
    assert c.post('/v1/auth/login',json={'username':'missing','password':'bad'}).status_code==429

def test_sessions_persist_across_restart_and_expire(system):
    c,path=system
    second=TestClient(create_app(path))
    assert second.get('/v1/me',headers=h('farmer')).status_code==200
    with connect(path) as db:
        db.execute('UPDATE sessions SET expires=0 WHERE token_hash=%s',(digest('farmer'),))
    assert second.get('/v1/me',headers=h('farmer')).status_code==401

def test_postgis_distance_and_scope(system):
    c,path=system
    r=c.get('/v1/properties/nearby',params={'latitude':-22,'longitude':-47,'radius_m':100},headers=h('admin'))
    assert r.status_code==200,r.text
    assert r.json()[0]['distance_m']==0
    assert c.get('/v1/properties/nearby',params={'latitude':-22,'longitude':-47},headers=h('outsider')).json()==[]
    assert c.get('/v1/properties/nearby',params={'latitude':0,'longitude':0},headers=h('admin')).json()==[]
    assert c.get('/v1/properties/nearby',params={'latitude':-22,'longitude':-47},headers=h('farmer')).status_code==403
    with connect(path) as db:
        r=db.execute("SELECT ST_SRID(location::geometry) AS srid FROM properties WHERE id='p1'").fetchone()
        assert r['srid']==4326

def test_idempotent_retry_and_payload_conflict(system):
    c,path=system
    request_id=str(uuid.uuid4())
    first=send(c,request_id=request_id)
    again=send(c,request_id=request_id)
    assert first.status_code==again.status_code==201
    assert first.json()['id']==again.json()['id']
    assert again.json()['replayed'] is True
    assert send(c,request_id=request_id,description='Diferente').status_code==409
    assert c.get('/v1/reports/summary',headers=h('admin')).json()['incidents']==1

def test_refresh_rotation_replay_and_logout(system):
    c,path=system
    tokens=c.post('/v1/auth/login',json={'username':'farmer','password':'initial-password-123'}).json()
    rotated=c.post('/v1/auth/refresh',json={'refresh_token':tokens['refresh_token']})
    assert rotated.status_code==200,rotated.text
    fresh=rotated.json()
    assert c.get('/v1/me',headers=h(tokens['access_token'])).status_code==401
    assert c.get('/v1/me',headers=h(fresh['access_token'])).status_code==200
    assert c.post('/v1/auth/refresh',json={'refresh_token':tokens['refresh_token']}).status_code==401
    assert c.get('/v1/me',headers=h(fresh['access_token'])).status_code==401
    tokens=c.post('/v1/auth/login',json={'username':'farmer','password':'initial-password-123'}).json()
    assert c.post('/v1/auth/logout',headers=h(tokens['access_token'])).status_code==204
    assert c.post('/v1/auth/refresh',json={'refresh_token':tokens['refresh_token']}).status_code==401

def test_migration_reentrant(system):
    from backend.migrate import migrate
    c,url=system
    migrate(url)
    with connect(url) as db:
        assert db.execute('SELECT count(*) AS n FROM schema_migrations').fetchone()['n']==1

def test_concurrent_duplicate_upload(system):
    from concurrent.futures import ThreadPoolExecutor
    c,path=system
    request_id=str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:send(c,request_id=request_id),range(2)))
    assert all(r.status_code==201 for r in results)
    assert results[0].json()['id']==results[1].json()['id']

def test_refresh_survives_access_expiry(system):
    c,path=system
    tokens=c.post('/v1/auth/login',json={'username':'farmer','password':'initial-password-123'}).json()
    with connect(path) as db:
        db.execute('UPDATE sessions SET expires=0 WHERE token_hash=%s',(digest(tokens['access_token']),))
    assert c.get('/v1/me',headers=h(tokens['access_token'])).status_code==401
    assert c.post('/v1/auth/refresh',json={'refresh_token':tokens['refresh_token']}).status_code==200
