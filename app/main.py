## APp entry point, Creates FastAPI app & registers UI routes
from fastapi import FastAPI
from app.modules.user_interface import router

app = FastAPI(
    title="Commercial Space Station Inventory and Resupply System",
    version="0.1.0",
    description="Initial API skeleton. Business operations are not implemented yet.",)

app.include_router(router)
