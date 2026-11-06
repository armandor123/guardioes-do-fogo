"""Acesso PostgreSQL com parâmetros vinculados; não há fallback SQLite."""
import os
from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row

def database_url(value=None):
    value = value or os.getenv('DATABASE_URL','')
    if not value.startswith(('postgresql://','postgres://')):
        raise ValueError('Configure DATABASE_URL com uma URL PostgreSQL')
    return value

@contextmanager
def connect(url=None):
    with psycopg.connect(database_url(url),row_factory=dict_row,connect_timeout=5) as db:
        yield db
