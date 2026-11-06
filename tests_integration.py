"""Execute na raiz: python -m pytest tests_integration.py -q"""
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'dados-api'))
sys.path.insert(0,str(Path(__file__).parent/'backend-reserva'))
import httpx
from fastapi.testclient import TestClient
from dados.main import create_app as create_data
from backend.main import create_app as create_backend, passwords, digest
from backend.db import connect

def test_backend_consumes_independent_data_service(tmp_path,pg_url):
    key='integration-key-with-24-characters'
    data=create_data(mode='demo',api_key=key)
    db_path=pg_url
    backend=create_backend(db_path,photo_dir=tmp_path/'photos',data_url='http://data',data_key=key,data_transport=httpx.ASGITransport(app=data))
    with connect(db_path) as db:
        db.execute('INSERT INTO cooperatives VALUES(%s,%s)',('coop','Teste'))
        db.execute('INSERT INTO users VALUES(%s,%s,%s,%s,%s,%s,FALSE)',('farmer','coop','Teste','teste',passwords.hash('not-used-password'),'farmer'))
        db.execute('INSERT INTO properties(id,farmer_id,name,municipality,state,latitude,longitude,area_ha) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',('property','farmer','Sitio','Campinas','SP',-22,-47,10))
        db.execute('INSERT INTO sessions VALUES(%s,%s,%s,%s,%s,%s)',('session',digest('test-token'),'farmer',time.time()+60,digest('refresh'),time.time()+3600))
    with TestClient(backend) as client:
        response=client.get('/v1/properties/property/environment',headers={'Authorization':'Bearer test-token'})
        assert response.status_code==200,response.text
        assert response.json()['weather']['simulated'] is True
        assert response.json()['query']['latitude']==-22
