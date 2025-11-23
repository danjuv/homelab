from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
import os
import uvicorn

app = FastAPI()


@app.get("/", response_class=PlainTextResponse)
def hello() -> str:
    pod_name = os.environ.get("HOSTNAME", "unknown-pod")
    return f"Hello from Kubernetes! Served by pod: {pod_name}\n"


@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    return "ok\n"


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8685)),
        reload=True,
    )