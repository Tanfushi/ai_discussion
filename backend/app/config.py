from functools import lru_cache
from pydantic import BaseModel
import os
from dotenv import load_dotenv


load_dotenv()


class Settings(BaseModel):
    app_env: str = os.getenv("APP_ENV", "dev")
    app_port: int = int(os.getenv("APP_PORT", "8000"))

    feishu_app_id: str = os.getenv("FEISHU_APP_ID", "")
    feishu_app_secret: str = os.getenv("FEISHU_APP_SECRET", "")
    feishu_verification_token: str = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
    feishu_encrypt_key: str = os.getenv("FEISHU_ENCRYPT_KEY", "")

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model_planner: str = os.getenv("OPENAI_MODEL_PLANNER", "gpt-4o-mini")
    openai_model_specialist: str = os.getenv("OPENAI_MODEL_SPECIALIST", "gpt-4o-mini")
    openai_model_judge: str = os.getenv("OPENAI_MODEL_JUDGE", "gpt-4o-mini")

    task_timeout_seconds: int = int(os.getenv("TASK_TIMEOUT_SECONDS", "60"))
    max_debate_rounds: int = int(os.getenv("MAX_DEBATE_ROUNDS", "2"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
