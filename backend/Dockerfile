FROM python:3.11-slim

WORKDIR /app

# psycopg2-binary는 manylinux 휠이라 별도 빌드 툴체인이 필요 없다.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# SPEC.md: "컨테이너 시작 시 alembic upgrade head".
# 마이그레이션이 실패하면 기동도 실패해야 하므로 &&로 묶는다.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
