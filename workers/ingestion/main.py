from __future__ import annotations

import logging

from app.core.config import get_settings
from app.modules.source_management.queue import INGESTION_QUEUE_NAME

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """Run an RQ worker that consumes ingestion jobs from Redis."""
    from redis import Redis
    from rq import Queue, Worker

    settings = get_settings()
    connection = Redis.from_url(settings.redis_url)
    queue = Queue(INGESTION_QUEUE_NAME, connection=connection)
    logger.info("SupportLens ingestion worker ready queue=%s redis=%s", INGESTION_QUEUE_NAME, settings.redis_url)
    worker = Worker([queue], connection=connection)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
