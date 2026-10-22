"""Validate Nexus Requests scheduler settings."""
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FIELDS = {
    'enabled', 'start_time', 'end_time', 'timezone',
    'advanced_enabled', 'advanced_days'
}
DAYS = (
    'monday', 'tuesday', 'wednesday', 'thursday',
    'friday', 'saturday', 'sunday'
)
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

    if 'advanced_enabled' in settings:
        if settings['advanced_enabled'] not in ('true', 'false'):
            raise ValueError('Invalid advanced scheduler enabled value')

    if 'advanced_days' in settings:
        import json
        try:
            days = json.loads(settings['advanced_days'])
        except (json.JSONDecodeError, TypeError):
            raise ValueError('Invalid advanced scheduler JSON')

        if not isinstance(days, dict) or set(days) != set(DAYS):
            raise ValueError('Advanced scheduler requires seven days')

        for day in DAYS:
            config = days[day]
            if not isinstance(config, dict) or set(config) != {
                'enabled', 'start', 'end'
            }:
                raise ValueError('Invalid daily scheduler configuration')

            if not isinstance(config['enabled'], bool):
                raise ValueError('Daily enabled value must be boolean')

            for field in ('start', 'end'):
                value = config[field]
                if not isinstance(value, str) or not TIME_PATTERN.fullmatch(value):
                    raise ValueError('Invalid daily scheduler time')

    if settings.get('advanced_enabled') == 'true' and 'advanced_days' not in settings:
        raise ValueError('Advanced scheduler days required')

    return settings
