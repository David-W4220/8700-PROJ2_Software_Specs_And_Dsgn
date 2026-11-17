from fastapi import FastAPI
from app.modules.user_interface import router
from app.modules.local_data_storage import (initialize_database, seed_demo_data,)

app = FastAPI(title="Space Station Inventory and Resupply System",)

app.include_router(router)

@app.on_event("startup")
def startup():
    #initialize local storage and demo data when the application starts.
    initialize_database()
    seed_demo_data()
