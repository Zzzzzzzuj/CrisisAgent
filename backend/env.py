from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"


def load_project_env(
    project_root: Path = PROJECT_ROOT,
    backend_dir: Path = BACKEND_DIR,
) -> None:
    """Load project defaults without overriding shell variables.

    Backend-local settings take precedence over root-level defaults, while
    variables explicitly supplied by the process environment remain authoritative.
    """
    load_dotenv(backend_dir / ".env", override=False)
    load_dotenv(project_root / ".env", override=False)
