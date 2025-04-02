from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import docker
import psycopg2
import time
import logging

# Initialize FastAPI app
app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# PostgreSQL Database Connection
DB_CONFIG = {
    "dbname": "function_db",
    "user": "postgres",
    "password": "samu2003",
    "host": "localhost",
    "port": "5432"
}

def get_db_connection():
    """Establish a new database connection."""
    return psycopg2.connect(**DB_CONFIG)

# Ensure table exists
def create_table():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS functions (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            route TEXT NOT NULL,
            language TEXT NOT NULL,
            timeout INT NOT NULL,
            code TEXT NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

create_table()  # Ensure table is created on startup

# Docker Client
docker_client = docker.from_env()

# Request model for function registration
class FunctionRequest(BaseModel):
    name: str
    route: str
    language: str
    timeout: int
    code: str

@app.post("/functions/")
async def create_function(request: FunctionRequest):
    """Register a new function in the database."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO functions (name, route, language, timeout, code) 
            VALUES (%s, %s, %s, %s, %s)
        """, (request.name, request.route, request.language, request.timeout, request.code))
        conn.commit()
        cur.close()
        conn.close()
        return {"message": "Function created successfully", "data": request.dict()}
    except Exception as e:
        logger.error(f"Error creating function: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/functions/")
async def list_functions():
    """Retrieve the list of available functions."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM functions")
    functions = cur.fetchall()
    cur.close()
    conn.close()
    
    if not functions:
        raise HTTPException(status_code=404, detail="No functions available")
    
    return {"message": "Available functions", "data": [f[0] for f in functions]}

def run_function_in_container(language: str, code: str, timeout: int):
    """Execute function code inside a Docker container."""
    try:
        if language == "python":
            image = "python:3.9"
            safe_code = code.replace('"', '\\"')  # Correct escaping
            command = f'python -c "{safe_code}"'
        elif language == "javascript":
            image = "node:18"
            safe_code = code.replace('"', '\\"')
            command = f'node -e "{safe_code}"'
        else:
            return "Unsupported language"

        logger.info(f"Starting container for {language} function")
        container = docker_client.containers.run(
            image, command, remove=False, stdout=True, stderr=True, detach=True
        )

        try:
            container.wait(timeout=timeout)  # Wait for completion
        except docker.errors.ContainerError:
            container.kill()
            return "Execution timed out"

        logs = container.logs().decode("utf-8")
        container.remove()
        logger.info("Function executed successfully")
        return logs.strip()
    except Exception as e:
        logger.error(f"Execution error: {str(e)}")
        return f"Execution error: {str(e)}"


@app.post("/functions/execute")
async def execute_function(request: dict, background_tasks: BackgroundTasks):
    """Execute a function asynchronously from the database."""
    function_name = request.get("name")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT language, timeout, code FROM functions WHERE name = %s", (function_name,))
    function = cur.fetchone()
    cur.close()
    conn.close()

    if not function:
        raise HTTPException(status_code=404, detail="Function not found")

    language, timeout, code = function
    background_tasks.add_task(run_function_in_container, language, code, timeout)

    return {"message": f"Execution started for function '{function_name}'"}
