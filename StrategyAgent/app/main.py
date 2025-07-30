from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from app.models import MarketRequest, GPTResponse
from app.services import execute_analysis

app = FastAPI()


@app.post("/analyze-gpt", response_model=GPTResponse)
def analyze_gpt(request: MarketRequest):
    try:
        result = execute_analysis(symbol=request.symbol, analysis_mode=request.mode)
        return GPTResponse(message=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# @app.post("/analyze-gpt-stream", response_class=StreamingResponse)
# def analyze_gpt_stream(request: MarketRequest):
#     try:
#         result = execute_analysis(symbol=request.symbol)
#         return StreamingResponse(result, media_type="text/plain")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
