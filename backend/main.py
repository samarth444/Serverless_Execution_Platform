from fastapi import FastAPI
from api.functions import router as function_router

app = FastAPI()
app.include_router(function_router)

@app.get("/")
def root():
    return {"message": "Serverless Function Execution Platform"}
