import docker
import os
import shutil
import logging
import threading
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import Function
import time
from fastapi import Body

# Initialize router and Docker client
router = APIRouter()
client = docker.from_env()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory container pool
container_pool = {}
POOL_SIZE = 2  # Number of pre-warmed containers per language
MAX_CONTAINERS = 5  # Max containers per language before blocking new ones


def get_db():
    """ Dependency to get DB session """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def warm_up_containers():
    """ Pre-starts a pool of function containers. """
    languages = ["python", "javascript"]
    for lang in languages:
        container_pool[lang] = []
        for _ in range(POOL_SIZE):
            try:
                container = start_container(lang)
                if container:
                    container_pool[lang].append(container)
            except Exception as e:
                logger.error(f"Failed to pre-warm {lang} container: {e}")

# Function to start a new container
def start_container(language: str, runtime: str = "runc"):
    """ Starts a new container for the given language. """
    image_map = {"python": "python:3.9", "javascript": "node:18"}
    run_cmd_map = {"python": "tail -f /dev/null", "javascript": "tail -f /dev/null"}

    if language not in image_map:
        raise ValueError("Unsupported language")

    logger.info(f"Starting a new {language} container with runtime {runtime}...")
    container = client.containers.run(
        image_map[language],
        run_cmd_map[language],
        detach=True,
        stdin_open=True,
        tty=True,
        remove=False,
        runtime=runtime  # Specify runtime here (either runc or runsc)
    )
    return container

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
def execute_function(id: int, runtime: str = "runc", db: Session = Depends(get_db)):
    """ Execute a stored function inside a Docker container or gVisor (runtime). """
    function = db.query(Function).filter(Function.id == id).first()
    if not function:
        raise HTTPException(status_code=404, detail="Function not found")

    language = function.language.lower()
    if language not in container_pool:
        raise HTTPException(status_code=400, detail="Unsupported language")
    
    if not container_pool[language]:
        if len(container_pool[language]) < MAX_CONTAINERS:
            container_pool[language].append(start_container(language, runtime))
        else:
            raise HTTPException(status_code=503, detail="Too many requests, no available containers")

    container = container_pool[language].pop(0)  # Get a free container
    exec_result = execute_in_container(container, function.code, language, runtime)
    container_pool[language].append(container)  # Return container to pool
    return {"message": "Function executed successfully", "output": exec_result}      
                              
def execute_in_container(container, code: str, language: str, runtime: str):
    """ Executes function code inside an existing container. """
    try:
        exec_cmd = f'python -c "{code}"' if language == "python" else f'node -e "{code}"'

        exit_code, output = container.exec_run(exec_cmd)
        if exit_code != 0:
            raise Exception(f"Execution failed: {output.decode('utf-8')}")
        return output.decode("utf-8").strip()
    except Exception as e:
        logger.error(f"Execution error: {e}")
        return str(e)


from db.schemas import FunctionUpdate

@router.put("/functions/update/{name}")
def update_function_by_name(name: str, payload: FunctionUpdate, db: Session = Depends(get_db)):
    function = db.query(Function).filter(Function.name == name).first()
    if not function:
        raise HTTPException(status_code=404, detail="Function not found")

    function.code = payload.code
    db.commit()
    db.refresh(function)
    return {
        "message": f"Function '{name}' updated successfully",
        "function": {
            "id": function.id,
            "name": function.name,
            "route": function.route,
            "language": function.language,
            "timeout": function.timeout,
            "code": function.code
        }
    }

@router.delete("/functions/delete/{name}")
def delete_function_by_name(name: str, db: Session = Depends(get_db)):
    function = db.query(Function).filter(Function.name == name).first()
    if not function:
        raise HTTPException(status_code=404, detail="Function not found")

    db.delete(function)
    db.commit()
    return {"message": f"Function '{name}' deleted successfully"}

# Start container warm-up in a background thread
threading.Thread(target=warm_up_containers, daemon=True).start()
