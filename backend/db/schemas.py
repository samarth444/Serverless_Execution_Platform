from pydantic import BaseModel

class FunctionUpdate(BaseModel):
    code: str
