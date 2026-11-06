import asyncio
import os
import secrets
import time
from collections import OrderedDict
from fastapi import FastAPI, Depends, Header, HTTPException
import httpx
from .models import Location, Context, Envelope
from .providers import weather, hotspots, demo


def create_app(mode=None, api_key=None, firms_key=None, transport=None):
    mode = mode or os.getenv('DATA_MODE','live')
    if mode not in ('live','demo'):
        raise ValueError('DATA_MODE deve ser live ou demo')
    api_key = api_key or os.getenv('DATA_API_KEY','')
    firms_key = firms_key if firms_key is not None else os.getenv('FIRMS_MAP_KEY','')
    if len(api_key) < 24:
        raise ValueError('Configure DATA_API_KEY com pelo menos 24 caracteres')
    app = FastAPI(title='Guardiões do Fogo — Dados e Inputs',version='1.0.0')
    cache = OrderedDict()

    def authorize(x_api_key: str = Header(default='')):
        if not secrets.compare_digest(x_api_key, api_key):
            raise HTTPException(401,'Chave de serviço inválida')

    @app.get('/health')
    def health():
        return {'status':'ok','mode':mode,'schema_version':'1.0'}

    @app.post('/v1/context',response_model=Context,dependencies=[Depends(authorize)])
    async def context(q: Location):
        key = q.model_dump_json()
        cached = cache.get(key)
        if cached and time.monotonic()-cached[0] < 300:
            return cached[1]
        if mode == 'demo':
            w,h = demo(q)
        else:
            async with httpx.AsyncClient(timeout=10,transport=transport,follow_redirects=False) as client:
                w,h = await asyncio.gather(weather(client,q),hotspots(client,q,firms_key))
        out = Context(query=q,weather=w,hotspots=h,risk={
            'level':None,'method':None,'validated':False,
            'reason':'Índice de risco ainda não implementado; requer método validado. Não inferir risco pela contagem de focos.'})
        if w.status == 'ok' and h.status == 'ok':
            cache[key] = (time.monotonic(),out)
            if len(cache)>256:
                cache.popitem(last=False)
        return out

    @app.post('/v1/weather',response_model=Envelope,dependencies=[Depends(authorize)])
    async def only_weather(q: Location):
        return (await context(q)).weather

    @app.post('/v1/hotspots',response_model=Envelope,dependencies=[Depends(authorize)])
    async def only_hotspots(q: Location):
        return (await context(q)).hotspots
    return app
