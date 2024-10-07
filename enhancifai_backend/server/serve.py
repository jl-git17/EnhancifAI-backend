import logging
import os
import uvicorn
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic
from apscheduler.schedulers.background import BackgroundScheduler

from enhancifai_backend.database.handlers.sys import SysDbCore
from enhancifai_backend.database.handlers.users import UsersDbCore
from enhancifai_backend.engine.rate_limit_manager import rate_limit_manager
from enhancifai_backend.integrations.monthly_billing import generate_monthly_invoices
from enhancifai_backend.server.jobs import delete_old_files, refresh_google_sheets_creds
from enhancifai_backend.server.routes.users_routes import router as router_users
from enhancifai_backend.server.routes.execution_routes import router as router_execution
from enhancifai_backend.server.routes.downloads_routes import router as router_downloads
from enhancifai_backend.server.routes.google_sheets_routes import router as router_sheets
from enhancifai_backend.server.routes.admin_routes import router as router_admin
from enhancifai_backend.server.routes.google_sheets_routes import router as router_google_sheets
from enhancifai_backend.server.routes.files_routes import router as router_files
from enhancifai_backend.server.routes.stripe_routes import router as router_stripe
from enhancifai_backend.server.utils import STATIC_FILES_DIRECTORY


# Environment variables
SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", 8000))

# Set global variables
APP_VERSION = "1.3.2"



app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.mount("/files", StaticFiles(directory=STATIC_FILES_DIRECTORY, html=True), name="files")
app.mount("/pages", StaticFiles(directory=STATIC_FILES_DIRECTORY, html=True), name="pages")
app.include_router(router_users)
app.include_router(router_execution)
app.include_router(router_downloads)
app.include_router(router_sheets)
app.include_router(router_admin)
app.include_router(router_google_sheets)
app.include_router(router_files)
app.include_router(router_stripe)

security = HTTPBasic()


@app.get("/")
async def root():
    server_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    msg = {
        "server": "EnhancifAI Backend",
        "status": "Online",
        "server_time": server_time
    }
    return JSONResponse(content=msg)


@app.get("/app-version", tags=["Utils"])
async def app_version():
    return {"version": APP_VERSION}

# Scheduler setup
scheduler = BackgroundScheduler()
scheduler.add_job(delete_old_files, 'interval', hours=1)
scheduler.add_job(SysDbCore.keep_db_alive, 'interval', seconds=21)
scheduler.add_job(UsersDbCore.cleanup_timed_out_jobs, 'interval', seconds=13)
scheduler.add_job(rate_limit_manager.clean_cancelled_jobs, 'interval', minutes=1)
#scheduler.add_job(generate_monthly_invoices, 'interval', minutes=5)
#scheduler.add_job(refresh_google_sheets_creds, 'interval', minutes=30) # TODO: check if it is corrupting existing creds
scheduler.start()
logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)


def run_server():
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)

if __name__ == "__main__":
    run_server()