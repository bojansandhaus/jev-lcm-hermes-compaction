"""Opt-in external Hermes context engine registration."""
from typing import Any
from .compressor import JevLCMContextCompressor
from .settings import Settings
from ._vendor.lcm.config import LCMConfig


def register(ctx: Any) -> None:
    from hermes_constants import get_hermes_home
    from hermes_cli.config_effective import load_user_config_effective
    config = load_user_config_effective()
    if config.get("context", {}).get("engine") != "jev-lcm":
        return
    settings = Settings(**config.get("jev_lcm", {}))
    engine = JevLCMContextCompressor(LCMConfig.from_env(), str(get_hermes_home()), settings)
    ctx.register_context_engine(engine)
