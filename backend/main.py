from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import docker
import psycopg2
import time
import logging
from threading import Lock
from api.functions import router
from api.metrics import router as metrics_router

# Initialize FastAPI app
app = FastAPI()
app.include_router(router)
app.include_router(metrics_router)

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

# Docker Client & Container Pool
docker_client = docker.from_env()
POOL_SIZE = 5  # Number of pre-warmed containers
container_pool = []
pool_lock = Lock()

# Function for warming up containers
def warm_up_containers():
    global container_pool
    with pool_lock:
        for _ in range(POOL_SIZE):
            container = docker_client.containers.run(
                "python:3.9",  # Default language
                command="sleep infinity",
                detach=True
            )
            container_pool.append(container)
            logger.info(f"Warmed-up container: {container.id}")

def get_available_container(runtime: str = "runc"):
    """Retrieve an available container from the pool, considering runtime."""
    with pool_lock:
        if container_pool:
            return container_pool.pop(0)
        else:
            raise HTTPException(status_code=503, detail="No available containers. Try again later.")

def return_container_to_pool(container):
    """Return a used container back to the pool."""
    with pool_lock:
        if len(container_pool) < POOL_SIZE:
            container_pool.append(container)

warm_up_containers()  # Initialize warm-up on startup

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

import tarfile
import io

@app.post("/functions/execute")
async def execute_function(request: dict):
    

    function_name = request.get("name")
    runtime = request.get("runtime", "runc")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT language, timeout, code FROM functions WHERE name = %s", (function_name,))
    function = cur.fetchone()
    cur.close()
    conn.close()

    if not function:
        raise HTTPException(status_code=404, detail="Function not found")

    language, timeout, code = function
    container = get_available_container(runtime)
    script_path = "/tmp/script.py"
    start_time = time.time()

    try:
        logger.info(f"Executing {function_name} in container {container.id} using runtime {runtime}")

        # Prepare and copy code
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            script_data = io.BytesIO(code.encode("utf-8"))
            tarinfo = tarfile.TarInfo(name="script.py")
            tarinfo.size = len(script_data.getvalue())
            tar.addfile(tarinfo, script_data)
        tar_stream.seek(0)
        container.put_archive("/tmp", tar_stream.read())

        # Run script
        exec_result = container.exec_run(f"python {script_path}", detach=False)
        exec_time = round(time.time() - start_time, 4)

        # Collect Docker stats
        stats = container.stats(stream=False)
        mem_usage = round(stats["memory_stats"]["usage"] / (1024 * 1024), 2)
        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
        cpu_percent = round((cpu_delta / system_delta) * len(stats["cpu_stats"]["cpu_usage"]["percpu_usage"]) * 100, 2) if system_delta > 0 else 0.0

        output = exec_result.output.decode("utf-8")
        success = exec_result.exit_code == 0

        # Store metrics
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO metrics (function_name, runtime, response_time, memory_usage_mb, cpu_percentage, success)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (function_name, runtime, exec_time, mem_usage, cpu_percent, success))
        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        logger.error(f"Execution error: {str(e)}")
        output = f"Execution error: {str(e)}"
        success = False
        exec_time = round(time.time() - start_time, 4)

        # Store failure metrics
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO metrics (function_name, runtime, response_time, memory_usage_mb, cpu_percentage, success)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (function_name, runtime, exec_time, 0.0, 0.0, False))
        conn.commit()
        cur.close()
        conn.close()

    finally:
        return_container_to_pool(container)

    return {
        "message": f"Execution completed for function '{function_name}'",
        "success": success,
        "runtime": runtime,
        "execution_time_sec": exec_time,
        "cpu_percent": cpu_percent,
        "memory_mb": mem_usage,
        "output": output
    }