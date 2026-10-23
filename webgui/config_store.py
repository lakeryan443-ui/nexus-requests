"""Encrypted local integration settings for Nexus Requests WebGUI.

Storage only: no network calls or HTTP routes. Never return secrets to browser clients.
"""
import os
import sqlite3
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

SERVICES = {
    'seerr': ('url', 'api_key'),
    'qbittorrent': ('url', 'username', 'password'),
    'radarr': ('url', 'api_key'),
    'sonarr': ('url', 'api_key'),
    'scheduler': ('enabled', 'start_time', 'end_time', 'timezone', 'advanced_enabled', 'advanced_days'),
    'discord': ('bot_token', 'guild_id', 'channel_id', 'owner_id'),
}
SECRET_FIELDS = {'api_key', 'password', 'bot_token'}


class ConfigStore:
    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir is not None else Path(__file__).resolve().parent / 'data'
        self.database = self.data_dir / 'integrations.db'
        self.key_file = self.data_dir / 'integrations.key'

    def _prepare_dir(self):
        if self.data_dir.is_symlink():
            raise RuntimeError('Configuration directory cannot be a symlink')
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.data_dir.is_symlink():
            raise RuntimeError('Configuration directory cannot be a symlink')
        os.chmod(self.data_dir, 0o700)

    def _cipher(self):
        self._prepare_dir()
        if self.key_file.is_symlink():
            raise RuntimeError('Encryption key cannot be a symlink')
        if not self.key_file.exists():
            # Write a complete key to a private temporary file, then publish
            # it atomically without overwriting another process's key.
            fd, temporary = tempfile.mkstemp(prefix='.integrations-key-', dir=self.data_dir)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(Fernet.generate_key())
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary, self.key_file, follow_symlinks=False)
                except FileExistsError:
                    pass
            finally:
                os.unlink(temporary)
        if self.key_file.is_symlink():
            raise RuntimeError('Encryption key cannot be a symlink')
        if self.key_file.stat().st_mode & 0o077:
            raise RuntimeError('Encryption key permissions are too broad')
        return Fernet(self.key_file.read_bytes())

    def _connect(self):
        self._prepare_dir()
        if self.database.is_symlink():
            raise RuntimeError('Configuration database cannot be a symlink')
        # Create the SQLite file with private permissions before opening it.
        try:
            fd = os.open(self.database, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        if self.database.is_symlink():
            raise RuntimeError('Configuration database cannot be a symlink')
        if self.database.stat().st_mode & 0o077:
            raise RuntimeError('Configuration database permissions are too broad')
        db = sqlite3.connect(self.database, timeout=10)
        db.execute('''CREATE TABLE IF NOT EXISTS integration_settings (
            service TEXT NOT NULL,
            field TEXT NOT NULL,
            value BLOB NOT NULL,
            encrypted INTEGER NOT NULL,
            PRIMARY KEY(service, field)
        )''')
        db.commit()
        return db

    def save(self, service, settings):
        """Explicitly replace supplied fields; omitted fields remain unchanged."""
        if service not in SERVICES:
            raise ValueError('Unknown integration')
        if not isinstance(settings, dict) or not settings or set(settings) - set(SERVICES[service]):
            raise ValueError('Invalid integration fields')
        if any(not isinstance(value, str) for value in settings.values()):
            raise ValueError('Integration values must be strings')
        cipher = self._cipher()
        with self._connect() as db:
            for field, value in settings.items():
                secret = field in SECRET_FIELDS
                stored = cipher.encrypt(value.encode('utf-8')) if secret else value.encode('utf-8')
                db.execute('''INSERT INTO integration_settings(service, field, value, encrypted)
                    VALUES (?, ?, ?, ?) ON CONFLICT(service, field)
                    DO UPDATE SET value=excluded.value, encrypted=excluded.encrypted''',
                    (service, field, stored, int(secret)))

    def load_internal(self, service):
        """For trusted backend callers only; NEVER serialize into an API response."""
        if service not in SERVICES:
            raise ValueError('Unknown integration')
        cipher = self._cipher()
        with self._connect() as db:
            rows = db.execute('SELECT field, value, encrypted FROM integration_settings WHERE service=?',
                              (service,)).fetchall()
        return {field: (cipher.decrypt(value) if encrypted else value).decode('utf-8')
                for field, value, encrypted in rows}

    def public_status(self, service):
        """Safe metadata only, with no saved values returned."""
        if service not in SERVICES:
            raise ValueError('Unknown integration')
        with self._connect() as db:
            fields = {row[0] for row in db.execute(
                'SELECT field FROM integration_settings WHERE service=?', (service,))}
        return {'service': service, 'configured_fields': sorted(fields),
                'has_credentials': any(f in fields for f in SECRET_FIELDS)}


    def save_all(self, configurations):
        """Atomically save multiple integrations."""
        if not isinstance(configurations, dict) or not configurations:
            raise ValueError('Invalid configuration')

        for service, settings in configurations.items():
            if service not in SERVICES:
                raise ValueError('Unknown integration')
            if not isinstance(settings, dict):
                raise ValueError('Invalid settings')
            if set(settings) - set(SERVICES[service]):
                raise ValueError('Invalid integration fields')
            if any(not isinstance(v, str) for v in settings.values()):
                raise ValueError('Integration values must be strings')

        cipher = self._cipher()
        with self._connect() as db:
            for service, settings in configurations.items():
                for field, value in settings.items():
                    secret = field in SECRET_FIELDS
                    stored = (
                        cipher.encrypt(value.encode())
                        if secret else value.encode()
                    )
                    db.execute(
                        'INSERT INTO integration_settings '
                        '(service, field, value, encrypted) '
                        'VALUES (?, ?, ?, ?) '
                        'ON CONFLICT(service, field) DO UPDATE SET '
                        'value=excluded.value, '
                        'encrypted=excluded.encrypted',
                        (service, field, stored, int(secret))
                    )
