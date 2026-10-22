"""Model factory (ADR-013): free OpenRouter chain default, OpenAI for paid
plans (configured per plan). Returns None when no key is configured — the
chat service then emits the not-ready/busy canned reply."""

from app.chat.providers import ChatModel, OpenAICompatibleModel
from app.core.config import Settings, get_settings
from app.db.models import Bot


def model_from_settings(settings: Settings, bot: Bot | None = None) -> ChatModel | None:
    if settings.chat_stub_model:
        from app.chat.providers import ExtractiveStubModel

        return ExtractiveStubModel()
    provider = (
        bot.generation_provider
        if bot is not None
        else ("openrouter" if settings.chat_openrouter_api_key else "openai")
    )
    override = bot.generation_model if bot is not None else None
    if provider == "openrouter" and settings.chat_openrouter_api_key is not None:
        chain = [override] if override else list(settings.chat_free_model_chain)
        if not chain:
            return None  # no configured model ids → not ready
        return OpenAICompatibleModel(
            base_url=settings.chat_openrouter_base_url,
            api_key=settings.chat_openrouter_api_key.get_secret_value(),
            model=chain[0],
            fallback_models=chain[1:],
            free_only=True,
            timeout_seconds=25.0,
            retries=0,
        )
    if (
        provider == "openai"
        and settings.chat_openai_api_key is not None
        and (override or settings.chat_openai_model)
    ):
        return OpenAICompatibleModel(
            base_url=settings.chat_openai_base_url,
            api_key=settings.chat_openai_api_key.get_secret_value(),
            model=override or settings.chat_openai_model,
            free_only=False,
            timeout_seconds=25.0,
            retries=0,
        )
    return None


def tier_targets(settings: Settings) -> dict[str, dict[str, str | None]]:
    """What each tier maps to, for staff display (ADR-013).

    Read-only: the patch endpoint keeps writing provider/model itself and the
    answering pipeline is unchanged. Standard shows the first model of the
    free OpenRouter chain; Premium the configured OpenAI model."""
    chain = list(settings.chat_free_model_chain)
    return {
        "standard": {
            "provider": "openrouter",
            "model": chain[0] if chain else None,
        },
        "premium": {
            "provider": "openai",
            "model": settings.chat_openai_model or None,
        },
    }


def default_model(bot: Bot | None = None) -> ChatModel | None:
    """Request-time model (built per call; construction is cheap)."""
    return model_from_settings(get_settings(), bot)
