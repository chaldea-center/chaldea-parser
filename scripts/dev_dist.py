import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


app = FastAPI(
    title="Chaldea Data",
    description="Test Data Server",
)
app.mount("/dist", StaticFiles(directory="data/dist"), name="dist")
app.add_middleware(CORSMiddleware, allow_origins=["*"])

if __name__ == "__main__":  # pragma: no cover
    # python -m scripts.dev_dist
    uvicorn.run(
        "scripts.dev_dist:app",
        host="127.0.0.1",
        port=8001,
        reload=False,
        log_level="debug",
    )
