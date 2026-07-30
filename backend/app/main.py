from fastapi import FastAPI

from app.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="btc-daily-web")
    app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
