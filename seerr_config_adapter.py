"""Load Seerr connection settings from Nexus Requests WebGUI."""

import sys
from pathlib import Path


class SeerrConfigurationError(RuntimeError):
    """Seerr configuration is missing or invalid."""


def load_seerr_config():
    webgui_dir = Path(__file__).resolve().parent / "webgui"
    sys.path.insert(0, str(webgui_dir))

    try:
        from config_store import ConfigStore
        saved = ConfigStore().load_internal("seerr")
    except Exception as exc:
        raise SeerrConfigurationError(
            "Unable to load Seerr configuration"
        ) from exc
    finally:
        sys.path.remove(str(webgui_dir))

    url = saved.get("url", "").strip().rstrip("/")
    api_key = saved.get("api_key", "").strip()

    if not url or not api_key:
        raise SeerrConfigurationError(
            "Configure Seerr in the Nexus Requests WebGUI first"
        )

    if not url.startswith(("http://", "https://")):
        raise SeerrConfigurationError("Invalid Seerr URL")

    return {"url": url, "api_key": api_key}
