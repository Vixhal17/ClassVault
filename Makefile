.PHONY: infra migrate api worker web test stop clean

infra:
	docker compose up -d

stop:
	docker compose down

migrate:
	cd backend && alembic upgrade head

api:
	cd backend && uvicorn app.main:app --reload --port 8000

worker:
	cd backend && arq app.worker.worker.WorkerSettings

web:
	cd frontend && npm run dev

test:
	cd backend && pytest -v

clean:
	docker compose down -v
