import io
import pytest
from PIL import Image
from fastapi import HTTPException
from pydantic import ValidationError
from backend.main import clean_image,create_app
from backend.schemas import Incident
from backend.storage import PhotoStore

def test_photo_exif_removed_and_format_checked():
    photo=Image.new('RGB',(12,12))
    output=io.BytesIO()
    exif=Image.Exif()
    exif[270]='private metadata'
    photo.save(output,format='JPEG',exif=exif)
    result=clean_image(output.getvalue())
    with Image.open(io.BytesIO(result)) as image:
        assert not image.getexif()
        assert image.format=='JPEG'
    with pytest.raises(HTTPException):
        clean_image(b'not an image')
    with pytest.raises(HTTPException):
        clean_image(b'a'*3_000_001)

def test_private_store_rejects_traversal(tmp_path):
    store=PhotoStore(tmp_path/'private')
    key=store.put(b'test bytes')
    assert store.get(key)==b'test bytes'
    assert store.put(b'test bytes')==key
    with pytest.raises(ValueError):
        store.get('../secret')

def test_metadata_requires_client_uuid_and_location_permission():
    with pytest.raises(ValidationError):
        Incident(property_id='x')
    with pytest.raises(ValidationError):
        Incident(property_id='x',client_request_id='bad')
    with pytest.raises(ValidationError):
        Incident(property_id='x',client_request_id='86a0de74-5b4b-4263-98a1-b1b77d415d16',latitude=1,longitude=2,location_source='gps')

def test_postgres_required_and_openapi_multipart(tmp_path):
    with pytest.raises(ValueError):
        create_app(db_url='sqlite:///demo.db')
    app=create_app(db_url='postgresql://unused/unused',photo_dir=tmp_path)
    api=app.openapi()
    content=api['paths']['/v1/incidents']['post']['requestBody']['content']
    assert 'multipart/form-data' in content
    assert '/v1/auth/refresh' in api['paths']
