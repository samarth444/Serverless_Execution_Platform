from pydantic import BaseModel

class FunctionUpdate(BaseModel):
    code: str

class FunctionCreate(BaseModel):
    name: str
    route: str
    language: str
    timeout: int
    code: str