"""Migrações SQL versionadas, transacionais e com checksum. Execute antes do app."""
import hashlib
from pathlib import Path
from .db import connect

def migrate(url=None):
    with connect(url) as db:
        # Impede dois processos de aplicar o esquema simultaneamente.
        db.execute('SELECT pg_advisory_xact_lock(71643001)')
        db.execute('''CREATE TABLE IF NOT EXISTS schema_migrations(
          version TEXT PRIMARY KEY, checksum TEXT NOT NULL,
          applied_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
        applied = {r['version']:r['checksum'] for r in db.execute('SELECT * FROM schema_migrations')}
        for file in sorted((Path(__file__).parent/'migrations').glob('*.sql')):
            source = file.read_text(encoding='utf-8')
            checksum = hashlib.sha256(source.encode()).hexdigest()
            if file.name in applied:
                if checksum != applied[file.name]:
                    raise RuntimeError(f'Migração aplicada foi alterada: {file.name}')
                continue
            db.execute(source)
            db.execute('INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)',(file.name,checksum))
    return 'Migrações aplicadas com sucesso'

if __name__=='__main__':
    print(migrate())
