"""Armazenamento privado local por conteúdo; não é uma pasta pública do servidor."""
import hashlib
import os
import re
import tempfile
from pathlib import Path

class PhotoStore:
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)

    def path(self,key):
        if not re.fullmatch(r'[0-9a-f]{64}\.jpg',key):
            raise ValueError('Chave de arquivo inválida')
        return self.root/key

    def put(self,data):
        key=hashlib.sha256(data).hexdigest()+'.jpg'
        destination=self.path(key)
        fd,name=tempfile.mkstemp(dir=self.root,prefix='.upload-')
        try:
            with os.fdopen(fd,'wb') as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(name,destination)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return key

    def get(self,key):
        return self.path(key).read_bytes()
