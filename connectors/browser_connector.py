import os
import time
import requests

def browser_enabled() -> bool:
    return os.getenv("ENABLE_BROWSER", "false").lower() in ["true", "1", "yes"]

def run_browser_task(task: str) -> dict:
    if not browser_enabled():
        return {"status": "error", "message": "Browser access is disabled. To enable it, set ENABLE_BROWSER=true in your .env file."}
    
    host = os.getenv("BROWSER_API_HOST", "http://localhost:8000").rstrip("/")
    
    try:
        # Submit the task
        response = requests.post(f"{host}/task", json={"task": task})
        response.raise_for_status()
        data = response.json()
        task_id = data.get("task_id")
        
        if not task_id:
            return {"status": "error", "message": "Failed to get task_id from browser api."}
            
        # Poll for completion
        while True:
            time.sleep(2)  # Wait before polling
            status_response = requests.get(f"{host}/task/{task_id}")
            status_response.raise_for_status()
            status_data = status_response.json()
            
            status = status_data.get("status")
            if status == "completed":
                return {"status": "success", "result": status_data.get("result")}
            elif status == "failed":
                return {"status": "error", "error": status_data.get("error")}
            
            # If status is "pending" or "running", continue polling
            
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Network error communicating with Browser API: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
