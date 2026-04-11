# pal_v4_main.py

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import os

# import your existing logic
#from pal_v4 import run_plan   # <-- adjust this
# from pal_v4 import run_plan, run_ingest
# --- FIX: use Mongo version ---
#from pal_v5_mongo import run_plan, run_ingest
from pal_v6_file_ingest import (
    load_events, run_plan, run_ingest, run_recurring_problems, 
    run_problem_locations, run_status_summary, run_delete
)
# --------------------------------

app = FastAPI()

# --- API AUTH 01 ---
API_KEY = os.getenv("PAL_API_KEY")

def check_api_key(x_api_key: str = Header(default="")):
    print(API_KEY)
    print(x_api_key)
    if not API_KEY or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

class Request(BaseModel):
    prompt: str

# --- API INGEST 02 ---
class EventRequest(BaseModel):
    entity: str
    event_type: str
    location: str
    status: str
    note: str
    timestamp: str | None = None


@app.get("/")
def root():
    return {"status": "ok"}

#If you want direct check>>> Add this endpoint (optional):
@app.get("/events")
def get_events():
    return load_events()


# --- API FIX 03 + AUTH ---
@app.post("/run")
def run(req: Request, x_api_key: str = Header(default="")):
    check_api_key(x_api_key)
    return run_plan(req.prompt)

# --- API INGEST 03 ---
@app.post("/ingest")
def ingest(req: EventRequest, x_api_key: str = Header(default="")):
    check_api_key(x_api_key)
    return run_ingest(req.model_dump(exclude_none=True))

# --- S2B 03 ---
@app.get("/recurring_problems")
def recurring_problems(x_api_key: str = Header(default="")):
    check_api_key(x_api_key)
    return run_recurring_problems()
# ----------------

# --- S2B 07 ---
@app.get("/problem_locations")
def problem_locations(x_api_key: str = Header(default="")):
    check_api_key(x_api_key)
    return run_problem_locations()


@app.get("/status_summary")
def status_summary(x_api_key: str = Header(default="")):
    check_api_key(x_api_key)
    return run_status_summary()
# ----------------

# --- S4 02 ---
class DeleteRequest(BaseModel):
    filter: dict

@app.post("/delete")
def delete(req: DeleteRequest, x_api_key: str = Header(default="")):
    check_api_key(x_api_key)
    return run_delete(req.filter)
# ----------------

