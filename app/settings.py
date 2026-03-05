import os
from pydantic import BaseModel

class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "dev")

    allowed_origins: list[str] = [
        o.strip() for o in os.getenv(
            "ALLOWED_ORIGINS",
            "https://obearchitects.com,https://www.obearchitects.com,http://client.local:5500,http://localhost:5500"
        ).split(",") if o.strip()
    ]

    admin_api_key: str = os.getenv("ADMIN_API_KEY", "dev_key")

    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    postgres_dsn: str = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/postgres")
    sendgrid_api_key: str = os.getenv("SENDGRID_API_KEY", "")
    email_from: str = os.getenv("EMAIL_FROM", "")
    leads_notify_to: str = os.getenv("LEADS_NOTIFY_TO", "")
    handoff_notify_to: str = os.getenv("HANDOFF_NOTIFY_TO", "")

    ig_verify_token: str = os.getenv("IG_WEBHOOK_VERIFY_TOKEN", "")
    wa_verify_token: str = os.getenv("WHATSAPP_VERIFY_TOKEN", os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", ""))
    wa_app_secret: str = os.getenv("WHATSAPP_APP_SECRET", "")
    wa_access_token: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    wa_phone_number_id: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    wa_graph_version: str = os.getenv("WHATSAPP_GRAPH_VERSION", "v20.0")
    wa_mock_send: bool = os.getenv("WHATSAPP_MOCK_SEND", "").strip().lower() in {"1", "true", "yes", "on"}

    scrape_base_url: str = os.getenv("SCRAPE_BASE_URL", "https://obearchitects.com/obe/")
    scrape_start_url: str = os.getenv("SCRAPE_START_URL", "https://obearchitects.com/obe/index.php")
    scrape_rps: float = float(os.getenv("SCRAPE_RPS", "1.0"))
    scrape_max_pages: int = int(os.getenv("SCRAPE_MAX_PAGES", "2000"))
    scrape_output_dir: str = os.getenv("SCRAPE_OUTPUT_DIR", "data/ingestion")
    scrape_user_agent: str = os.getenv(
        "SCRAPE_USER_AGENT",
        "OBE-RAG-Ingestion/1.0 (+contact: info@obearchitects.com)",
    )
    scrape_allow_subdomains: bool = os.getenv("SCRAPE_ALLOW_SUBDOMAINS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    scrape_respect_robots: bool = os.getenv("SCRAPE_RESPECT_ROBOTS", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    scrape_path_prefix: str = os.getenv("SCRAPE_PATH_PREFIX", "/obe/")
    scrape_allowed_query_keys: list[str] = [
        k.strip()
        for k in os.getenv("SCRAPE_ALLOWED_QUERY_KEYS", "category,id").split(",")
        if k.strip()
    ]

    rag_enabled: bool = os.getenv("RAG_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    rag_public_enabled: bool = os.getenv("RAG_PUBLIC_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    rag_public_min_confidence: float = float(os.getenv("RAG_PUBLIC_MIN_CONFIDENCE", "0.55"))
    rag_public_top_k: int = int(os.getenv("RAG_PUBLIC_TOP_K", "5"))
    rag_public_max_context_chars: int = int(os.getenv("RAG_PUBLIC_MAX_CONTEXT_CHARS", "6000"))
    rag_llm_temperature: float = float(os.getenv("RAG_LLM_TEMPERATURE", "0.25"))
    rag_llm_top_p: float = float(os.getenv("RAG_LLM_TOP_P", "0.9"))
    rag_llm_repeat_penalty: float = float(os.getenv("RAG_LLM_REPEAT_PENALTY", "1.08"))
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_embed_model: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    ollama_chat_model: str = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b")
    rag_embed_dim: int = int(os.getenv("RAG_EMBED_DIM", "768"))
    rag_top_k: int = int(os.getenv("RAG_TOP_K", "6"))
    rag_min_score: float = float(os.getenv("RAG_MIN_SCORE", "0.0"))
    min_similarity_score_project: float = float(os.getenv("MIN_SIMILARITY_SCORE_PROJECT", "0.75"))
    min_similarity_score_category: float = float(os.getenv("MIN_SIMILARITY_SCORE_CATEGORY", "0.65"))
    min_similarity_score: float = float(os.getenv("MIN_SIMILARITY_SCORE", "0.75"))
    rag_max_context_chars: int = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "12000"))
    rag_chunks_path: str = os.getenv("RAG_CHUNKS_PATH", "data/ingestion/chunks/chunks.jsonl")
    rag_batch_size: int = int(os.getenv("RAG_BATCH_SIZE", "64"))

settings = Settings()


def validate_settings() -> None:
    if settings.app_env != "production":
        return

    missing = []

    def _req(name: str, value: str) -> None:
        if not (value or "").strip():
            missing.append(name)

    _req("POSTGRES_DSN", settings.postgres_dsn)
    _req("REDIS_URL", settings.redis_url)
    _req("ADMIN_API_KEY", settings.admin_api_key)
    _req("SENDGRID_API_KEY", settings.sendgrid_api_key)
    _req("EMAIL_FROM", settings.email_from)
    _req("LEADS_NOTIFY_TO", settings.leads_notify_to)

    # WhatsApp is optional, but if any WA config is set, require core vars.
    wa_any = any([
        (settings.wa_verify_token or "").strip(),
        (settings.wa_access_token or "").strip(),
        (settings.wa_phone_number_id or "").strip(),
    ])
    if wa_any:
        _req("WHATSAPP_VERIFY_TOKEN", settings.wa_verify_token)
        _req("WHATSAPP_ACCESS_TOKEN", settings.wa_access_token)
        _req("WHATSAPP_PHONE_NUMBER_ID", settings.wa_phone_number_id)

    if missing:
        raise RuntimeError(f"Missing required production env vars: {', '.join(missing)}")

    if settings.admin_api_key in {"dev_key", "change_me", "replace_with_long_random_admin_key"}:
        raise RuntimeError("ADMIN_API_KEY must be set to a strong non-default value in production")
