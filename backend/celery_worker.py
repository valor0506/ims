#!/usr/bin/env python3
"""
celery_worker.py — Local Windows worker entrypoint.

The WindowsSelectorEventLoopPolicy fix is applied inside worker.py at
module level, so it automatically takes effect when celery_app is imported.

Run from backend/: python celery_worker.py
"""

import os
import sys

# Ensure backend/ is on sys.path for app.ims.* imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# This import triggers the SelectorEventLoopPolicy fix in worker.py
from app.ims.worker import celery_app

if __name__ == "__main__":
    celery_app.worker_main(argv=[
        'worker',
        '--loglevel=info',
        '--pool=solo',          # correct for Windows local dev
        '--concurrency=1',      # solo pool ignores concurrency, explicit for clarity
    ])