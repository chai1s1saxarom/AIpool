"""
Реестр поддерживаемых LLM-моделей с ценами.
В реальном проекте хранился бы в БД.
"""
from app.schemas import ModelInfo

MODELS: dict[str, ModelInfo] = {
    "openai_gpt-4o-mini": ModelInfo(
        model_id="openai_gpt-4o-mini",
        provider="openai",
        display_name="GPT-4o Mini",
        description="Быстрая и дешёвая модель от OpenAI",
        max_context_tokens=128000,
        max_output_tokens=16000,
        input_price_per_million=0.15,
        output_price_per_million=0.60,
        supports_structured_output=True,
    ),
    "openai_gpt-4o": ModelInfo(
        model_id="openai_gpt-4o",
        provider="openai",
        display_name="GPT-4o",
        description="Флагманская мультимодальная модель OpenAI",
        max_context_tokens=128000,
        max_output_tokens=16000,
        input_price_per_million=5.0,
        output_price_per_million=15.0,
        supports_structured_output=True,
    ),
    "google_gemini-1.5-flash": ModelInfo(
        model_id="google_gemini-1.5-flash",
        provider="google",
        display_name="Gemini 1.5 Flash",
        description="Быстрая модель Google с большим контекстом",
        max_context_tokens=1000000,
        max_output_tokens=8192,
        input_price_per_million=0.075,
        output_price_per_million=0.30,
        supports_structured_output=True,
    ),
    "google_gemini-1.5-pro": ModelInfo(
        model_id="google_gemini-1.5-pro",
        provider="google",
        display_name="Gemini 1.5 Pro",
        description="Продвинутая модель Google",
        max_context_tokens=2000000,
        max_output_tokens=8192,
        input_price_per_million=3.5,
        output_price_per_million=10.5,
        supports_structured_output=True,
    ),
    "anthropic_claude-3-haiku": ModelInfo(
        model_id="anthropic_claude-3-haiku",
        provider="anthropic",
        display_name="Claude 3 Haiku",
        description="Самая быстрая модель Anthropic",
        max_context_tokens=200000,
        max_output_tokens=4096,
        input_price_per_million=0.25,
        output_price_per_million=1.25,
        supports_structured_output=False,
    ),
}
