"""One-command launcher: python run.py  (then open http://127.0.0.1:8000)

Each browser gets its own sandbox database, created on first visit. Honors PORT and HOST for hosting.
"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.main:app", host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
