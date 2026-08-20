import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.runtime_tasks import get_rq_queue_name, get_redis_connection


def main() -> None:
    try:
        from rq import Queue, Worker
    except ImportError as exc:
        raise SystemExit("RQ worker requires the 'rq' package. Run: pip install -r requirements.txt") from exc

    connection = get_redis_connection()
    queue_name = get_rq_queue_name()
    queue = Queue(queue_name, connection=connection)
    print(f"Starting CrisisAgent RQ worker. queue={queue_name}")
    worker = Worker([queue], connection=connection)
    worker.work()


if __name__ == "__main__":
    main()
