"""Backend independente de reserva: MVP local, sem acionamento de autoridades."""
import hashlib
import io
import json
import os
import secrets
import psycopg
import time
import uuid
import warnings
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import httpx
from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import ValidationError
from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool
from fastapi.responses import Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from PIL import Image, UnidentifiedImageError
from pwdlib import PasswordHash
from .db import connect, database_url
from .storage import PhotoStore
from .schemas import Login, Password, Farmer, Property, Incident, Review, Refresh

passwords = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)

def uid():
    return str(uuid.uuid4())

def timestamp():
    return datetime.now(timezone.utc).isoformat()

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def clean_image(raw):
    try:
        if len(raw)>3_000_000:
            raise ValueError()
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as img:
                if img.format not in ('JPEG','PNG') or img.width*img.height>12_000_000:
                    raise ValueError()
                img.load()
                output = io.BytesIO()
                # Reencodificação remove EXIF, inclusive GPS que não tenha sido autorizado.
                img.convert('RGB').save(output,format='JPEG',quality=85)
                return output.getvalue()
    except (ValueError,UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise HTTPException(422,'Foto inválida: envie JPEG/PNG, até 3 MB e 12 megapixels')

def create_app(db_url=None, data_url=None, data_key=None, data_transport=None, photo_dir=None):
    db_url = database_url(db_url)
    store = PhotoStore(photo_dir or os.getenv('PHOTO_DIR','./data/photos'))
    data_url = (data_url or os.getenv('DATA_API_URL','http://127.0.0.1:8001')).rstrip('/')
    data_key = data_key or os.getenv('DATA_API_KEY','')
    app = FastAPI(title='Guardiões do Fogo — Backend reserva',version='2.0.0')
    dummy_hash = passwords.hash(secrets.token_urlsafe(24))
    login_attempts = {}

    @app.middleware('http')
    async def body_limit(request, call_next):
        # Limita também corpos chunked. É um MVP; proxy deve impor o mesmo limite.
        total = 0
        pieces = []
        async for chunk in request.stream():
            total += len(chunk)
            if total > 4_100_000:
                return Response('Corpo excede 4,1 MB',status_code=413)
            pieces.append(chunk)
        request._body = b''.join(pieces)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    def current(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if not credentials:
            raise HTTPException(401,'Autenticação necessária')
        with connect(db_url) as db:
            row = db.execute('''SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id
                WHERE s.token_hash=%s AND s.expires>%s''',(digest(credentials.credentials),time.time())).fetchone()
        if not row:
            raise HTTPException(401,'Sessão inválida ou expirada')
        return dict(row)

    def ready(user=Depends(current)):
        if user['must_change']:
            raise HTTPException(403,'Troque a senha temporária antes de continuar')
        return user

    def cooperative(user=Depends(ready)):
        if user['role'] != 'cooperative':
            raise HTTPException(403,'Acesso exclusivo da cooperativa')
        return user

    def property_access(db, property_id, user):
        row = db.execute('''SELECT p.*,u.coop_id FROM properties p JOIN users u ON u.id=p.farmer_id
                            WHERE p.id=%s''',(property_id,)).fetchone()
        if not row or row['coop_id'] != user['coop_id'] or (user['role']=='farmer' and row['farmer_id'] != user['id']):
            raise HTTPException(404,'Propriedade não encontrada')
        return dict(row)

    def incident_access(db, incident_id,user, lock=False):
        row = db.execute('SELECT * FROM incidents WHERE id=%s'+(' FOR UPDATE' if lock else ''),(incident_id,)).fetchone()
        if not row:
            raise HTTPException(404,'Ocorrência não encontrada')
        property_access(db,row['property_id'],user)
        return dict(row)

    def public_incident(row):
        row = dict(row)
        row.pop('photo_key',None)
        row.pop('request_hash',None)
        row['ai'] = row.pop('ai_json')
        row['photo_url'] = f"/v1/incidents/{row['id']}/photo"
        row['location_verified'] = False
        return row

    @app.get('/health')
    def health():
        with connect(db_url) as db:
            version = db.execute('SELECT PostGIS_Version() AS version').fetchone()['version']
        return {'status':'ok','storage':'postgresql','postgis':version,'scope':'MVP mobile'}

    @app.post('/v1/auth/login')
    def login(body: Login):
        t = time.monotonic()
        key = body.username
        attempts = [x for x in login_attempts.get(key,[]) if t-x<60]
        if len(attempts)>=5:
            raise HTTPException(429,'Aguarde um minuto antes de tentar novamente')
        if len(login_attempts)>10000:
            login_attempts.clear()
        login_attempts[key] = attempts+[t]
        with connect(db_url) as db:
            row = db.execute('SELECT * FROM users WHERE username=%s FOR UPDATE',(body.username,)).fetchone()
            valid = passwords.verify(body.password,row['password_hash'] if row else dummy_hash)
            if not row or not valid:
                raise HTTPException(401,'Usuário ou senha incorretos')
            tokens = issue_session(db,row['id'])
        login_attempts.pop(key,None)
        return {**tokens,'role':row['role'],'must_change_password':bool(row['must_change'])}

    def issue_session(db,user_id):
        access,refresh = secrets.token_urlsafe(32),secrets.token_urlsafe(48)
        db.execute('DELETE FROM sessions WHERE refresh_expires<=%s',(time.time(),))
        db.execute('INSERT INTO sessions(id,token_hash,user_id,expires,refresh_hash,refresh_expires) VALUES(%s,%s,%s,%s,%s,%s)',
                   (uid(),digest(access),user_id,time.time()+900,digest(refresh),time.time()+30*86400))
        return {'access_token':access,'refresh_token':refresh,'token_type':'bearer','expires_in':900,'refresh_expires_in':30*86400}

    @app.post('/v1/auth/refresh')
    def refresh(body: Refresh):
        hashed = digest(body.refresh_token)
        result = None
        with connect(db_url) as db:
            # A primeira leitura localiza a família, inclusive tokens já usados.
            candidate=db.execute("""SELECT user_id,id FROM sessions WHERE refresh_hash=%s
                UNION SELECT s.user_id,s.id FROM sessions s JOIN refresh_history h ON h.session_id=s.id
                WHERE h.token_hash=%s""",(hashed,hashed)).fetchone()
            if candidate:
                # Ordem de locks: usuário, depois sessão; igual à troca de senha/login.
                db.execute('SELECT id FROM users WHERE id=%s FOR UPDATE',(candidate['user_id'],))
                session=db.execute('SELECT * FROM sessions WHERE id=%s FOR UPDATE',(candidate['id'],)).fetchone()
                if session and session['refresh_hash']==hashed and session['refresh_expires']>time.time():
                    access,new_refresh=secrets.token_urlsafe(32),secrets.token_urlsafe(48)
                    db.execute('INSERT INTO refresh_history VALUES(%s,%s)',(hashed,session['id']))
                    db.execute('UPDATE sessions SET token_hash=%s,expires=%s,refresh_hash=%s WHERE id=%s',
                               (digest(access),time.time()+900,digest(new_refresh),session['id']))
                    result={'access_token':access,'refresh_token':new_refresh,'token_type':'bearer',
                            'expires_in':900,'refresh_expires_in':max(0,int(session['refresh_expires']-time.time()))}
                elif session:
                    # Reuso do refresh antigo revoga a família; commit antes do 401.
                    db.execute('DELETE FROM sessions WHERE id=%s',(session['id'],))
        if result is None:
            raise HTTPException(401,'Refresh inválido, expirado ou reutilizado. Faça login novamente.')
        return result

    @app.get('/v1/me')
    def me(user=Depends(current)):
        return {k:user[k] for k in ('id','name','username','role','coop_id','must_change')}

    @app.post('/v1/auth/password')
    def password(body: Password,user=Depends(current)):
        if body.new_password == body.old_password:
            raise HTTPException(422,'Escolha uma senha diferente')
        with connect(db_url) as db:
            row=db.execute('SELECT password_hash FROM users WHERE id=%s FOR UPDATE',(user['id'],)).fetchone()
            if not passwords.verify(body.old_password,row['password_hash']):
                raise HTTPException(400,'Senha atual incorreta')
            db.execute('UPDATE users SET password_hash=%s,must_change=FALSE WHERE id=%s',(passwords.hash(body.new_password),user['id']))
            db.execute('DELETE FROM sessions WHERE user_id=%s',(user['id'],))
        return {'message':'Senha alterada. Faça login novamente.'}

    @app.post('/v1/auth/logout',status_code=204)
    def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer),user=Depends(current)):
        with connect(db_url) as db:
            db.execute('DELETE FROM sessions WHERE token_hash=%s',(digest(credentials.credentials),))

    @app.post('/v1/farmers',status_code=201)
    def farmer(body: Farmer,user=Depends(cooperative)):
        farmer_id,temp = uid(),secrets.token_urlsafe(16)
        try:
            with connect(db_url) as db:
                db.execute('INSERT INTO users VALUES(%s,%s,%s,%s,%s,%s,TRUE)',
                    (farmer_id,user['coop_id'],body.name,body.username,passwords.hash(temp),'farmer'))
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409,'Nome de usuário já utilizado')
        return {'id':farmer_id,'username':body.username,'temporary_password':temp,'must_change_password':True}

    @app.get('/v1/farmers')
    def farmers(user=Depends(cooperative)):
        with connect(db_url) as db:
            return [dict(r) for r in db.execute("SELECT id,name,username FROM users WHERE coop_id=%s AND role='farmer'",(user['coop_id'],))]

    @app.post('/v1/properties',status_code=201)
    def add_property(body: Property,user=Depends(cooperative)):
        with connect(db_url) as db:
            farmer = db.execute("SELECT id FROM users WHERE id=%s AND coop_id=%s AND role='farmer'",(body.farmer_id,user['coop_id'])).fetchone()
            if not farmer:
                raise HTTPException(404,'Agricultor não encontrado')
            prop_id = uid()
            db.execute('INSERT INTO properties(id,farmer_id,name,municipality,state,latitude,longitude,area_ha) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                (prop_id,body.farmer_id,body.name,body.municipality,body.state,body.latitude,body.longitude,body.area_ha))
        return {'id':prop_id,**body.model_dump()}

    @app.get('/v1/properties')
    def properties(user=Depends(ready)):
        with connect(db_url) as db:
            rows = db.execute('SELECT p.* FROM properties p JOIN users u ON u.id=p.farmer_id WHERE u.coop_id=%s',(user['coop_id'],))
            return [{k:v for k,v in dict(r).items() if k!='location'} for r in rows if user['role']=='cooperative' or r['farmer_id']==user['id']]

    @app.get('/v1/properties/nearby')
    def nearby(latitude: float=Query(ge=-90,le=90),longitude: float=Query(ge=-180,le=180),
               radius_m: float=Query(10000,ge=1,le=50000),user=Depends(cooperative)):
        with connect(db_url) as db:
            rows=db.execute("""SELECT p.id,p.name,p.latitude,p.longitude,
                ST_Distance(p.location,ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography) AS distance_m
                FROM properties p JOIN users u ON u.id=p.farmer_id
                WHERE u.coop_id=%s AND ST_DWithin(p.location,
                ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s)
                ORDER BY distance_m LIMIT 200""",(longitude,latitude,user['coop_id'],longitude,latitude,radius_m))
            return list(rows)

    @app.get('/v1/properties/{property_id}/environment')
    async def environment(property_id: str,user=Depends(ready)):
        def load_property():
            with connect(db_url) as db:
                return property_access(db,property_id,user)
        prop=await run_in_threadpool(load_property)
        try:
            async with httpx.AsyncClient(timeout=25,transport=data_transport) as client:
                r = await client.post(data_url+'/v1/context',json={'latitude':prop['latitude'],'longitude':prop['longitude']},
                    headers={'X-API-Key':data_key})
                r.raise_for_status()
                payload = r.json()
                if payload.get('weather') is None or payload.get('hotspots') is None:
                    raise ValueError()
                return payload
        except (httpx.HTTPError,ValueError):
            raise HTTPException(503,'Serviço de dados indisponível; não há leitura atual confirmada')

    @app.post('/v1/incidents',status_code=201)
    def add_incident(metadata: str = Form(...,max_length=10000),photo: UploadFile = File(...),user=Depends(ready)):
        if user['role'] != 'farmer':
            raise HTTPException(403,'Envio disponível para agricultores')
        try:
            body=Incident.model_validate_json(metadata)
        except ValidationError:
            raise HTTPException(422,'metadata inválido: verifique UUID, campos, coordenadas e autorização')
        # UploadFile já está limitado pelo middleware; limite do arquivo é separado.
        raw=photo.file.read(3_000_001)
        image=clean_image(raw)
        fingerprint=hashlib.sha256((body.model_dump_json()+hashlib.sha256(raw).hexdigest()).encode()).hexdigest()
        with connect(db_url) as db:
            property_access(db,body.property_id,user)
            # Serializa requisições com a mesma chave para tratar reenvios simultâneos.
            lock_key=user['id']+':'+str(body.client_request_id)
            db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(lock_key,))
            existing=db.execute('SELECT id,request_hash FROM incidents WHERE farmer_id=%s AND client_request_id=%s',
                                (user['id'],body.client_request_id)).fetchone()
            if existing:
                if existing['request_hash']!=fingerprint:
                    raise HTTPException(409,'client_request_id já utilizado com outro conteúdo')
                return {'id':existing['id'],'replayed':True}
            incident_id=uid()
            photo_key=store.put(image)
            ai={'status':'simulated','simulated':True,'classification':'inconclusive','confidence':None,
                'warning':'Nenhum modelo de IA foi executado; revisão humana necessária.'}
            db.execute("""INSERT INTO incidents(id,property_id,farmer_id,description,latitude,longitude,
                location_source,location_authorized,created_at,status,photo_key,photo_type,ai_json,client_request_id,request_hash)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (incident_id,body.property_id,user['id'],body.description,body.latitude,body.longitude,
                 body.location_source,body.location_authorized,timestamp(),'submitted',photo_key,'image/jpeg',Jsonb(ai),
                 body.client_request_id,fingerprint))
        return {'id':incident_id,'replayed':False}

    @app.get('/v1/incidents')
    def incidents(limit: int=Query(50,ge=1,le=200),offset: int=Query(0,ge=0),user=Depends(ready)):
        with connect(db_url) as db:
            rows = db.execute('''SELECT i.* FROM incidents i JOIN users u ON u.id=i.farmer_id
                WHERE u.coop_id=%s AND (%s='cooperative' OR i.farmer_id=%s) ORDER BY i.created_at DESC LIMIT %s OFFSET %s''',
                (user['coop_id'],user['role'],user['id'],limit,offset))
            return [public_incident(r) for r in rows]

    @app.get('/v1/incidents/{incident_id}')
    def incident(incident_id: str,user=Depends(ready)):
        with connect(db_url) as db:
            result = public_incident(incident_access(db,incident_id,user))
            result['reviews'] = [dict(r) for r in db.execute('SELECT * FROM reviews WHERE incident_id=%s ORDER BY id',(incident_id,))]
            return result

    @app.get('/v1/incidents/{incident_id}/photo')
    def photo(incident_id: str,user=Depends(ready)):
        with connect(db_url) as db:
            row = incident_access(db,incident_id,user)
            try:
                content=store.get(row['photo_key'])
            except FileNotFoundError:
                raise HTTPException(503,'Arquivo da foto indisponível')
            return Response(content,media_type=row['photo_type'])

    @app.patch('/v1/incidents/{incident_id}/review')
    def review(incident_id: str,body: Review,user=Depends(cooperative)):
        transitions = {'submitted':{'under_review'},'under_review':{'verified','rejected'},
                       'verified':{'escalated'},'rejected':set(),'escalated':set()}
        with connect(db_url) as db:
            row = incident_access(db,incident_id,user,lock=True)
            if body.status not in transitions[row['status']]:
                raise HTTPException(409,'Transição de status não permitida')
            db.execute('UPDATE incidents SET status=%s WHERE id=%s',(body.status,incident_id))
            db.execute('INSERT INTO reviews(incident_id,reviewer_id,old_status,new_status,notes,created_at) VALUES(%s,%s,%s,%s,%s,%s)',
                (incident_id,user['id'],row['status'],body.status,body.notes,timestamp()))
        return {'id':incident_id,'status':body.status,'authorities_contacted':False}

    @app.get('/v1/incidents/{incident_id}/notification-draft')
    def draft(incident_id: str,user=Depends(cooperative)):
        with connect(db_url) as db:
            row = incident_access(db,incident_id,user)
        return {'draft':True,'sent':False,'text':f"MINUTA PARA REVISÃO — Ocorrência {incident_id}, registrada em {row['created_at']}. "
            f"Status interno: {row['status']}. Relato do agricultor: {row['description']}. "
            'A classificação de IA é simulada. Verifique as evidências antes de qualquer comunicação.'}

    @app.get('/v1/reports/summary')
    def summary(user=Depends(cooperative)):
        with connect(db_url) as db:
            farmers = db.execute("SELECT COUNT(*) AS count FROM users WHERE coop_id=%s AND role='farmer'",(user['coop_id'],)).fetchone()['count']
            props = db.execute('SELECT p.area_ha FROM properties p JOIN users u ON u.id=p.farmer_id WHERE u.coop_id=%s',(user['coop_id'],)).fetchall()
            rows = db.execute('SELECT i.status FROM incidents i JOIN users u ON u.id=i.farmer_id WHERE u.coop_id=%s',(user['coop_id'],)).fetchall()
        counts = dict(Counter(r['status'] for r in rows))
        return {'farmers':farmers,'properties':len(props),'registered_area_ha':sum(r['area_ha'] or 0 for r in props),
            'properties_without_area':sum(r['area_ha'] is None for r in props),'incidents':len(rows),
            'by_status':counts,'awaiting_review':counts.get('submitted',0)+counts.get('under_review',0),
            'burned_area_ha':None,'note':'Área cadastrada não é área queimada. verified é avaliação humana interna.'}

    @app.get('/v1/sos')
    def sos():
        return {'phone':'193','dial_uri':'tel:193','automatic_dispatch':False,
                'message':'O aplicativo não aciona equipes. Use o telefone para solicitar atendimento.'}
    return app
