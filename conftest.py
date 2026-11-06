import os
import uuid
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import pytest

@pytest.fixture
def pg_url():
    from psycopg import sql
    from backend.db import connect
    from backend.migrate import migrate
    base=os.getenv('TEST_DATABASE_URL')
    if not base:
        pytest.skip('Defina TEST_DATABASE_URL apontando para banco PostgreSQL/PostGIS exclusivo de testes')
    schema='test_'+uuid.uuid4().hex
    with connect(base) as db:
        db.execute('CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public')
        db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    parts=urlsplit(base)
    params=dict(parse_qsl(parts.query))
    params['options']=f'-csearch_path={schema},public'
    url=urlunsplit(parts._replace(query=urlencode(params)))
    try:
        migrate(url)
        yield url
    finally:
        with connect(base) as db:
            db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
