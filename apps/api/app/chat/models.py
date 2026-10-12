"""Model factory (ADR-013): free OpenRouter chain default, OpenAI for paid
plans (configured per plan). Returns None when no key is configured — the
chat service then emits the not-ready/busy canned reply."""

from app.chat.providers import ChatModel, OpenAICompatibleModel
from app.core.config import Settings, get_settings


def model_from_settings(settings: Settings) -> ChatModel | None:
    if settings.chat_stub_model:
        from app.chat.providers import ExtractiveStubModel

        return ExtractiveStubModel()
    if settings.chat_openrouter_api_key is not None:
        chain = list(settings.chat_free_model_chain)
        if not chain:
            return None  # no configured model ids → not ready
        return OpenAICompatibleModel(
            base_url=settings.chat_openrouter_base_url,
            api_key=settings.chat_openrouter_api_key.get_secret_value(),
            model=chain[0],
            fallback_models=chain[1:],
            free_only=True,
            timeout_seconds=25.0,
            retries=2,
        )
    if settings.chat_openai_api_key is not None and settings.chat_openai_model:
        return OpenAICompatibleModel(
            base_url=settings.chat_openai_base_url,
            api_key=settings.chat_openai_api_key.get_secret_value(),
            model=settings.chat_openai_model,
            free_only=False,
            timeout_seconds=25.0,
            retries=2,
        )
    return None


def default_model() -> ChatModel | None:
    """Request-time model (built per call; construction is cheap)."""
    return model_from_settings(get_settings())
