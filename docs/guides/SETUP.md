# Semantic Cache - Development Setup Guide

## Quick Start

### 1. Prerequisites
- Python 3.10+
- Docker & Docker Compose
- Git

### 2. Clone & Setup Environment

```bash
cd semantic-cache
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Start Services

```bash
# Start Redis, PostgreSQL, Prometheus, Grafana
docker-compose up -d

# Verify services
docker-compose ps
```

### 4. Run Tests

```bash
# Install test dependencies
pip install -e ".[dev]"

# Run all tests
pytest tests/

# Run with coverage
pytest --cov=src tests/
```

### 5. Start Development Server

```bash
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

API will be available at `http://localhost:8000`

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 6. Access Monitoring Stack

- **Prometheus:** http://localhost:9090
- **Grafana:** http://localhost:3000 (admin/admin)
- **Redis Commander:** (optional, can be added to docker-compose.yml)

## Project Structure

```
semantic-cache/
├── src/                    # Main source code
├── tests/                  # Test suites
├── config/                 # Configuration files
├── deployment/             # Deployment artifacts
├── docs/                   # Documentation
├── monitoring/             # Monitoring configs
└── scripts/                # Utility scripts
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# API
API_HOST=0.0.0.0
API_PORT=8000
API_DEBUG=false

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Database
DATABASE_URL=postgresql://semantic_cache:semantic_cache_dev@localhost/semantic_cache

# Embedding Model
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Logging
LOG_LEVEL=INFO
```

### Configuration Files

- **Default config:** `config/default.yaml`
- **Development:** `config/development.yaml` (create as needed)
- **Production:** `config/production.yaml` (create as needed)

## Development Workflow

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes with tests:**
   ```bash
   # Write code in src/
   # Write tests in tests/
   ```

3. **Run checks:**
   ```bash
   # Format code
   black src/ tests/
   
   # Check linting
   flake8 src/ tests/
   
   # Type checking
   mypy src/
   
   # Run tests
   pytest tests/
   ```

4. **Commit and push:**
   ```bash
   git add .
   git commit -m "feat: description of changes"
   git push origin feature/your-feature-name
   ```

## Troubleshooting

### Redis Connection Issues
```bash
# Check if Redis is running
docker-compose ps redis

# Test Redis connection
redis-cli ping  # Should respond with PONG
```

### PostgreSQL Connection Issues
```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# Connect to database
psql -U semantic_cache -h localhost -d semantic_cache
```

### Port Conflicts
If ports are already in use, modify `docker-compose.yml` or pass different ports:
```bash
docker-compose up -d -p custom_project_name
```

## Next Steps

1. Review [Architecture](../docs/architecture/)
2. Check [API Documentation](../docs/api/)
3. Run Phase 1 implementation tasks
