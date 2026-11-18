import server.endpoints as ep


TEST_CLIENT = ep.app.test_client()


def test_hello():
    resp = TEST_CLIENT.get(ep.HELLO_EP)
    resp_json = resp.get_json()
    assert ep.HELLO_RESP in resp_json


def test_create_app_initializes_indexes(monkeypatch):
    from unittest.mock import Mock
    import data.db_connect as dbc

    initialize = Mock()
    monkeypatch.setattr(dbc, 'initialize_indexes', initialize)

    assert ep.create_app() is ep.app
    initialize.assert_called_once_with()
