from fastapi import FastAPI

from cliova.api.errors import install_error_handlers
from cliova.api.router import router


def create_app() -> FastAPI:
    app = FastAPI(title="Cliova API", version="0.1.0")
    install_error_handlers(app)
    app.include_router(router)
    return app


app = create_app()
