from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class MockSettings:
    host: str
    port: int
    database_path: Path
    admin_token: str
    callback_timeout: float
    ppp_callback_secret: str
    max_body_bytes: int

    @classmethod
    def from_env(cls) -> "MockSettings":
        load_dotenv(PROJECT_DIR / ".env")
        database_value = os.getenv("MOCK_DATABASE_PATH", "data/mock.db")
        database_path = Path(database_value)
        if not database_path.is_absolute():
            database_path = PROJECT_DIR / database_path
        return cls(
            host=os.getenv("MOCK_HOST", "0.0.0.0").strip(),
            port=int(os.getenv("MOCK_PORT", "18080")),
            database_path=database_path,
            admin_token=os.getenv("MOCK_ADMIN_TOKEN", "").strip(),
            callback_timeout=float(os.getenv("MOCK_CALLBACK_TIMEOUT", "10")),
            ppp_callback_secret=os.getenv("PPP_CALLBACK_SECRET", "").strip(),
            max_body_bytes=int(os.getenv("MOCK_MAX_BODY_BYTES", "1048576")),
        )

