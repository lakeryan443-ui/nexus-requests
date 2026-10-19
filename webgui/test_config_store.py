import os
import sqlite3
import tempfile
from pathlib import Path
from config_store import ConfigStore

with tempfile.TemporaryDirectory() as tmp:
    store = ConfigStore(Path(tmp) / 'data')
    store.save('seerr', {'url': 'http://localhost:5055', 'api_key': 'SENSITIVE_TEST_ONLY'})
    assert store.load_internal('seerr') == {'url': 'http://localhost:5055', 'api_key': 'SENSITIVE_TEST_ONLY'}
    print('Save and decrypt: PASS')
    raw = store.database.read_bytes()
    assert b'SENSITIVE_TEST_ONLY' not in raw
    print('Secret absent from raw database: PASS')
    assert (store.data_dir.stat().st_mode & 0o777) == 0o700
    assert (store.database.stat().st_mode & 0o777) == 0o600
    assert (store.key_file.stat().st_mode & 0o777) == 0o600
    print('Filesystem permissions: PASS')
    assert 'SENSITIVE_TEST_ONLY' not in str(store.public_status('seerr'))
    print('Public metadata redaction: PASS')
    store.save('seerr', {'url': 'http://localhost:5056'})
    assert store.load_internal('seerr')['api_key'] == 'SENSITIVE_TEST_ONLY'
    print('Partial update preserves credentials: PASS')
    try:
        store.save('seerr', {'invalid': 'x'})
    except ValueError:
        print('Unknown field rejected: PASS')
    else:
        raise AssertionError('Unknown field accepted')
print('Offline storage tests: PASS')
