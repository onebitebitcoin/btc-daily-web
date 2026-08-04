from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="btc-daily-web")
    app.router.redirect_slashes = False
    # 에디션 JSON이 한 건에 50KB고 세로 피드는 날짜를 연달아 받는다. gzip이면
    # 13KB로 떨어진다. 1KB 미만은 압축해봐야 헤더값도 못 건지므로 제외.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
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
