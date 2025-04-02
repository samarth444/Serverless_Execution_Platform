import docker
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import Function

router = APIRouter()
client = docker.from_env()  # Initialize Docker client

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/functions/")
def create_function(name: str, route: str, language: str, timeout: int, code: str, db: Session = Depends(get_db)):
    """ Store a function in the database """
    new_function = Function(name=name, route=route, language=language, timeout=timeout, code=code)
    db.add(new_function)
    db.commit()
    db.refresh(new_function)
    return new_function

@router.get("/functions/{id}")
def get_function(id: int, db: Session = Depends(get_db)):
    """ Retrieve function details by ID """
    function = db.query(Function).filter(Function.id == id).first()
    if not function:
        raise HTTPException(status_code=404, detail="Function not found")
    return function

@router.post("/execute/{id}")
def execute_function(id: int, db: Session = Depends(get_db)):
    """ Execute a stored function inside a Docker container """
    function = db.query(Function).filter(Function.id == id).first()
    if not function:
        raise HTTPException(status_code=404, detail="Function not found")

    # Define image and file path based on language
    if function.language.lower() == "python":
        image = "python:3.9"
        code_path = "/tmp/function.py"
        run_command = f"python {code_path}"
    elif function.language.lower() == "javascript":
        image = "node:18"
        code_path = "/tmp/function.js"
        run_command = f"node {code_path}"
    else:
        raise HTTPException(status_code=400, detail="Unsupported language")

    # Write the function code to a temporary file
    temp_filename = f"./temp/{function.name}_{function.id}.{'py' if function.language == 'python' else 'js'}"
    os.makedirs("./temp", exist_ok=True)
    
    with open(temp_filename, "w") as f:
        f.write(function.code)

    try:
        # Run function inside a Docker container
        container = client.containers.run(
            image,
            command=run_command,
            volumes={os.path.abspath("./temp"): {'bind': '/tmp', 'mode': 'rw'}},
            detach=True,
            remove=True
        )
        return {"message": "Function execution started", "container_id": container.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
