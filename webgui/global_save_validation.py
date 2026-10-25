"""Validate Nexus Requests integrations before global save."""

from config_store import SERVICES

REQUIRED = ('seerr', 'qbittorrent')
OPTIONAL = ('radarr', 'sonarr')


def validate_global_save(configurations, store):
    if not isinstance(configurations, dict):
        raise ValueError('Invalid configuration')

    for service in REQUIRED + OPTIONAL:
        if service not in configurations:
            raise ValueError(f'Missing integration: {service}')

        submitted = configurations[service]
        if not isinstance(submitted, dict):
            raise ValueError(f'Invalid settings: {service}')

        saved = store.load_internal(service)

        if service in OPTIONAL:
            enabled = submitted.get('enabled', saved.get('enabled', 'false'))
            if enabled not in ('true', 'false'):
                raise ValueError(f'Invalid {service}.enabled')
            if enabled == 'false':
                continue

        fields = (
            ('url', 'api_key')
            if service in OPTIONAL
            else SERVICES[service]
        )

        for field in fields:
            value = submitted.get(field, saved.get(field, ''))
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'Missing {service}.{field}')

    return configurations
