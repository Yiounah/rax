"""Operator-selected external perception, hosted outside the controller sandbox."""
from .gemini import GeminiRouter, load_key


def perception_router(config, *, key_file=None):
    if not config.external_perception:
        return None
    if config.external_perception_provider == 'basal-gemini-cli':
        from .basal_gemini_cli import BasalGeminiCliRouter
        return BasalGeminiCliRouter()
    if config.external_perception_provider == 'codex-account':
        from .codex_vision import CodexVisionRouter
        return CodexVisionRouter(config.root)
    key = load_key(key_file)
    return GeminiRouter(key) if key else None
