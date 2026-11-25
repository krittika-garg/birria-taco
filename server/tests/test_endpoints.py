import server.endpoints as ep


TEST_CLIENT = ep.app.test_client()


def test_hello():
    resp = TEST_CLIENT.get(ep.HELLO_EP)
    resp_json = resp.get_json()
    assert ep.HELLO_RESP in resp_json


def test_health_ok(monkeypatch):
    from unittest.mock import MagicMock
    import data.db_connect as dbc

    monkeypatch.setattr(dbc, 'connect_db', MagicMock())
    monkeypatch.setenv('CLOUD_MONGO', dbc.CLOUD)
    resp = TEST_CLIENT.get(ep.HEALTH_EP)
    assert resp.status_code == 200
    assert resp.get_json() == {'db': 'ok', 'mode': 'cloud'}


def test_health_db_down(monkeypatch):
    from unittest.mock import MagicMock
    import pymongo.errors
    import data.db_connect as dbc

    client = MagicMock()
    client.admin.command.side_effect = (
        pymongo.errors.ServerSelectionTimeoutError())
    monkeypatch.setattr(dbc, 'connect_db', lambda: client)
    monkeypatch.delenv('CLOUD_MONGO', raising=False)
    resp = TEST_CLIENT.get(ep.HEALTH_EP)
    assert resp.status_code == 503
    assert resp.get_json() == {'db': 'unreachable', 'mode': 'local'}


def test_health_missing_cloud_uri(monkeypatch):
    import data.db_connect as dbc

    def no_uri():
        raise ValueError('no MONGO_URI')
    monkeypatch.setattr(dbc, 'connect_db', no_uri)
    resp = TEST_CLIENT.get(ep.HEALTH_EP)
    assert resp.status_code == 503


def test_create_app_initializes_indexes(monkeypatch):
    from unittest.mock import Mock
    import data.db_connect as dbc

    initialize = Mock()
    monkeypatch.setattr(dbc, 'initialize_indexes', initialize)

    assert ep.create_app() is ep.app
    initialize.assert_called_once_with()
