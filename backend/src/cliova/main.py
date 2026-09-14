from fastapi import FastAPI

from cliova.api.router import router

app = FastAPI(title="Cliova API", version="0.0.0")
app.include_router(router)
