import os
from unittest.mock import patch

import pytest

import states.load as ld

CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'raw_data',
                        'states.csv')
NUM_STATES = 52  # 50 states + DC + PR


def test_load_states():
    states = ld.load_states(CSV_PATH)
    assert len(states) == NUM_STATES
    abbrevs = {state['Abbrev'] for state in states}
    assert {'NY', 'DC', 'PR'} <= abbrevs


def test_load_states_coords_are_floats():
    for state in ld.load_states(CSV_PATH):
        assert isinstance(state['Latitude'], float)
        assert isinstance(state['Longitude'], float)


def test_load_states_bad_path():
    with pytest.raises(FileNotFoundError):
        ld.load_states('no_such_file.csv')


@patch('data.db_connect.upsert')
@patch('data.db_connect.connect_db')
def test_main(mock_connect, mock_upsert):
    with patch('sys.argv', ['load.py', CSV_PATH]):
        ld.main()
    mock_connect.assert_called_once()
    assert mock_upsert.call_count == NUM_STATES
    collection, filt, doc = mock_upsert.call_args[0]
    assert collection == 'states'
    assert filt == {'Abbrev': doc['Abbrev']}


def test_main_no_args():
    with patch('sys.argv', ['load.py']):
        with pytest.raises(SystemExit):
            ld.main()
