"""Validate required Nexus Requests integrations before global save."""

from config_store import SERVICES

REQUIRED = ('seerr', 'radarr', 'sonarr', 'qbittorrent')


def validate_global_save(configurations, store):
    if not isinstance(configurations, dict):
        raise ValueError('Invalid configuration')

    for service in REQUIRED:
        if service not in configurations:
            raise ValueError(f'Missing required integration: {service}')

        submitted = configurations[service]
        if not isinstance(submitted, dict):
            raise ValueError(f'Invalid settings: {service}')

        saved = store.load_internal(service)

        for field in SERVICES[service]:
            value = submitted.get(field, saved.get(field, ''))
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'Missing {service}.{field}')

    return configurations
