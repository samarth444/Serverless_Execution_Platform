from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict
import io
import sys

app = FastAPI()

# In-memory storage for functions
functions_store: Dict[str, dict] = {}

class FunctionRequest(BaseModel):
    name: str
    route: str
    language: str
    timeout: int
    code: str

@app.post("/functions/")
async def create_function(request: FunctionRequest):
    if request.name in functions_store:
        raise HTTPException(status_code=400, detail="Function with this name already exists")

    # Store function data
    functions_store[request.name] = request.dict()
    return {"message": "Function created", "data": request.dict()}

@app.get("/functions/")
async def list_functions():
    if not functions_store:
        raise HTTPException(status_code=404, detail="No functions available")

    return {"message": "Available functions", "data": list(functions_store.keys())}

@app.post("/functions/execute")
async def execute_function(request: dict):
    function_name = request.get("name")
    if function_name not in functions_store:
        raise HTTPException(status_code=404, detail="Function not found")

    function_data = functions_store[function_name]
    
    if function_data["language"] == "python":
        try:
            # Capture print output
            output_buffer = io.StringIO()
            sys.stdout = output_buffer

            exec_globals = {}
            exec(function_data["code"], exec_globals)

            # Restore stdout and get captured output
            sys.stdout = sys.__stdout__
            output = output_buffer.getvalue().strip() or "Execution complete"
        except Exception as e:
            sys.stdout = sys.__stdout__
            raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")
    else:
        return {"message": "Execution not supported for this language"}

    return {"message": "Function executed", "output": output}
