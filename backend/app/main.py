from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="btc-daily-web")
    app.router.redirect_slashes = False
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
