"""Verify the Hospital API adapter selection contract."""
from app.services.hospital_api import get_adapter
from app.services.hospital_api.base import HospitalApiAdapter
from app.services.hospital_api.http_adapter import HttpHospitalApiAdapter
from app.services.hospital_api.null_adapter import NullHospitalApiAdapter
from app.config import settings


def test_adapter_is_null_when_url_unset(monkeypatch):
    monkeypatch.setattr(settings, "HOSPITAL_API_URL", "", raising=False)
    get_adapter.cache_clear()
    adapter = get_adapter()
    assert isinstance(adapter, NullHospitalApiAdapter)
    assert isinstance(adapter, HospitalApiAdapter)
    assert adapter.name == "null"


def test_adapter_is_http_stub_when_url_set(monkeypatch):
    monkeypatch.setattr(settings, "HOSPITAL_API_URL", "https://example.invalid/api", raising=False)
    monkeypatch.setattr(settings, "HOSPITAL_API_KEY", "test-key", raising=False)
    get_adapter.cache_clear()
    adapter = get_adapter()
    assert isinstance(adapter, HttpHospitalApiAdapter)
    assert adapter.name == "http"
    get_adapter.cache_clear()
