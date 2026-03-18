.PHONY: help install dev test lint format clean docker-build docker-up docker-down docs

help:
	@echo "Semantic Cache - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install dependencies"
	@echo "  make dev              Setup development environment"
	@echo ""
	@echo "Development:"
	@echo "  make run              Run development server"
	@echo "  make test             Run tests"
	@echo "  make test-cov         Run tests with coverage"
	@echo "  make lint             Run linting checks"
	@echo "  make format           Format code"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build     Build Docker image"
	@echo "  make docker-up        Start services with docker-compose"
	@echo "  make docker-down      Stop services"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean            Remove build artifacts and cache"

install:
	pip install -r requirements.txt

dev:
	pip install -e ".[dev]"

run:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term

lint:
	black --check src/ tests/
	flake8 src/ tests/
	mypy src/
	isort --check-only src/ tests/

format:
	black src/ tests/
	isort src/ tests/

docker-build:
	docker build -t semantic-cache:latest .

docker-up:
	docker-compose up -d
	@echo "Services starting..."
	@echo "API: http://localhost:8000"
	@echo "Swagger: http://localhost:8000/docs"
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3000"

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".coverage" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ *.egg-info/

requirements-freeze:
	pip freeze > requirements-frozen.txt

notebook:
	jupyter notebook --ip=0.0.0.0 --port=8888 --no-browser

.PHONY: docs
docs:
	@echo "Documentation is in docs/ directory"
	@echo "Visit docs/guides/SETUP.md to get started"
