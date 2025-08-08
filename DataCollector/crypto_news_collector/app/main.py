from fastapi import FastAPI

app = FastAPI(title="Crypto News Collector")

@app.get("/")
def health_check():
    """
    Simple health endpoint.
    """
    return {"status": "ok", "message": "newscollector is running"}
