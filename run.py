"""One-command launcher: python run.py  (then open http://127.0.0.1:8000)

Options: --pipeline   rebuild the database from the synthetic files (uses fixtures, or a live key if set)
"""
import sys

import uvicorn

import config
import pipeline

if __name__ == "__main__":
    if "--pipeline" in sys.argv or not config.DB_PATH.exists():
        pipeline.run()
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000)
