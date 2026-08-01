"""Entrypoint: `python -m worldtwin`"""
import uvicorn

from .server import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="info", access_log=False)
