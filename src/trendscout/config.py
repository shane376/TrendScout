import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    content_source: str = "reddit"
    client_id: str = field(default="", repr=False)
    client_secret: str = field(default="", repr=False)
    user_agent: str = ""
    output_dir: Path = Path("output")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            content_source=os.getenv("CONTENT_SOURCE", "reddit").strip(),
            client_id=os.getenv("REDDIT_CLIENT_ID", "").strip(),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET", "").strip(),
            user_agent=os.getenv("REDDIT_USER_AGENT", "").strip(),
            output_dir=Path(os.getenv("OUTPUT_DIR", "output")),
        )
