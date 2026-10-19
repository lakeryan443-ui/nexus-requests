"""Validate Nexus Requests scheduler settings."""
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FIELDS = {'enabled', 'start_time', 'end_time', 'timezone'}
TIME_PATTERN = re.compile(r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]$')


def validate_scheduler(settings):
    if not isinstance(settings, dict) or not settings:
        raise ValueError('Scheduler settings must be a nonempty object')

    if set(settings) - FIELDS:
        raise ValueError('Unknown scheduler setting')

    if any(not isinstance(value, str) for value in settings.values()):
        raise ValueError('Scheduler values must be strings')

    if 'enabled' in settings and settings['enabled'] not in ('true', 'false'):
        raise ValueError('Invalid enabled value')

    for field in ('start_time', 'end_time'):
        if field in settings and not TIME_PATTERN.fullmatch(settings[field]):
            raise ValueError('Invalid scheduler time')

    if 'timezone' in settings:
        try:
            ZoneInfo(settings['timezone'])
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            raise ValueError('Invalid scheduler timezone')

    return settings
