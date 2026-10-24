"""Typed environment settings shared by the API and the worker (finding I-08).

Every field maps 1:1 to a variable of `.env.example` (same name, upper case). Variables that
only Docker Compose reads are listed in `COMPOSE_ONLY_VARIABLES`; a unit test fails when the
two sides drift apart.
"""

from fincontrol_config.settings import COMPOSE_ONLY_VARIABLES, Settings, get_settings

__all__ = ["COMPOSE_ONLY_VARIABLES", "Settings", "get_settings"]
