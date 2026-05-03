#!/usr/bin/env python3
"""
Standalone Celery worker starter.
Run: python celery_worker.py
"""

import os
import sys

# Add backend to path so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.ims.worker import celery_app

if __name__ == "__main__":
    celery_app.worker_main(argv=[
        'worker',
        '--loglevel=info',
        '--pool=solo',
    ])