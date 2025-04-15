from fastapi import APIRouter, HTTPException
from psycopg2.extras import RealDictCursor
import psycopg2
from config import DB_CONFIG


router = APIRouter()

def get_db():
    return psycopg2.connect(**DB_CONFIG)

@router.get("/metrics/{function_name}")
def get_metrics(function_name: str):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT 
                AVG(response_time) AS avg_time,
                AVG(cpu_percentage) AS avg_cpu,
                AVG(memory_usage_mb) AS avg_mem,
                COUNT(*) FILTER (WHERE success) AS success_count,
                COUNT(*) FILTER (WHERE NOT success) AS failure_count
            FROM metrics
            WHERE function_name = %s
        """, (function_name,))
        metrics = cur.fetchone()
        cur.close()
        conn.close()

        if not metrics:
            raise HTTPException(status_code=404, detail="No metrics found")

        return {"function": function_name, "metrics": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
