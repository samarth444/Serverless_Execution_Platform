import docker
import os
import shutil
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import Function

# Initialize router and Docker client
router = APIRouter()
client = docker.from_env()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db():
    """ Dependency to get DB session """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/functions/")
def create_function(name: str, route: str, language: str, timeout: int, code: str, db: Session = Depends(get_db)):
    """ Store a function in the database """
    if db.query(Function).filter(Function.name == name).first():
        raise HTTPException(status_code=400, detail="Function with this name already exists")
    
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
    language_config = {
        "python": {
            "image": "python:3.9",
            "code_ext": "py",
            "run_command": "python /tmp/function.py"
        },
        "javascript": {
            "image": "node:18",
            "code_ext": "js",
            "run_command": "node /tmp/function.js"
        }
    }

    if function.language.lower() not in language_config:
        raise HTTPException(status_code=400, detail="Unsupported language")

    config = language_config[function.language.lower()]
    image = config["image"]
    code_ext = config["code_ext"]
    run_command = config["run_command"]

    # Prepare a unique temp directory for the function execution
    temp_dir = f"./temp/function_{function.id}"
    os.makedirs(temp_dir, exist_ok=True)
    temp_filename = os.path.join(temp_dir, f"function_{function.id}.{code_ext}")

    try:
        # Write function code to a temporary file
        with open(temp_filename, "w") as f:
            f.write(function.code)

        logger.info(f"Executing function {function.id} in a {function.language} environment.")

        # Run function inside a Docker container and capture logs
        try:
            container = client.containers.run(
                image,
                command=run_command,
                volumes={os.path.abspath(temp_dir): {'bind': '/tmp', 'mode': 'rw'}},
                detach=False,  # Run synchronously
                stdout=True,
                stderr=True
            )

            logger.info(f"Function {function.id} executed successfully. Output:\n{container}")

            return {"message": "Function executed successfully", "output": container}

        except docker.errors.ContainerError as e:
            logger.error(f"Execution failed for function {function.id}. Error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Function execution failed: {str(e)}")
        except docker.errors.APIError as e:
            logger.error(f"Docker API error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Docker API error: {str(e)}")
        except docker.errors.ImageNotFound:
            logger.error(f"Docker image {image} not found.")
            raise HTTPException(status_code=500, detail="Docker image not found")

    finally:
        # Cleanup: Remove only this function's temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)
