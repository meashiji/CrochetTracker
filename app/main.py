from fastapi import FastAPI

app = FastAPI(title="CrochetTracker")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    return {"message": "CrochetTracker is running"}
