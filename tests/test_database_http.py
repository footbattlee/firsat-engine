from types import SimpleNamespace
from urllib.request import Request
from urllib.error import HTTPError
from unittest.mock import Mock
import pytest
from collectors import database_http as transport


def fixture(monkeypatch):
    session = Mock()
    session.request.return_value = SimpleNamespace(status_code=200,content=b'[]',headers={})
    monkeypatch.setattr(transport,'Session',lambda:session)
    original=Mock(return_value='fallback')
    module=SimpleNamespace(urlopen=original,SUPABASE_URL='https://database.test')
    transport.install(module)
    return module,session,original


def test_connection_reuse_preserves_method_headers_body_and_never_uses_store_proxy(monkeypatch):
    module,session,original=fixture(monkeypatch)
    request=Request('https://database.test/rest/v1/offers',data=b'{"price":5}',headers={'Authorization':'Bearer secret'},method='PATCH')
    for _ in range(2):
        with module.urlopen(request,timeout=17) as response: assert response.read()==b'[]'
    assert session.request.call_count==2
    assert session.request.call_args.args==('PATCH',request.full_url)
    assert session.request.call_args.kwargs['data']==request.data
    assert session.request.call_args.kwargs['headers']['Authorization']=='Bearer secret'
    assert session.trust_env is False
    original.assert_not_called()


def test_non_database_requests_keep_original_behavior(monkeypatch):
    module,session,original=fixture(monkeypatch)
    assert module.urlopen(Request('https://store.test/item'))=='fallback'
    session.request.assert_not_called()
    original.assert_called_once()


def test_database_error_keeps_urllib_error_contract_without_retry(monkeypatch):
    module,session,_=fixture(monkeypatch)
    session.request.return_value=SimpleNamespace(status_code=409,content=b'conflict',headers={})
    with pytest.raises(HTTPError) as error:module.urlopen(Request('https://database.test/rest/v1/offers'))
    assert error.value.read()==b'conflict'
    assert session.request.call_count==1
