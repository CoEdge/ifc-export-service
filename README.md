# IFC Export Service

BIM DSL and intermediate mesh to IFC4 export service for V-CAD. Converts 3D building models into the Industry Foundation Classes (IFC) open standard for interoperability with BIM tools like Revit, ArchiCAD, and Tekla.

## API Reference

### Async Job-Based Endpoints (recommended)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/jobs/convert` | Create IFC conversion job from intermediate mesh |
| `POST` | `/api/v1/jobs/convert-from-dsl` | Create IFC conversion job from BIM DSL (via 3d-modeling-service) |
| `GET` | `/api/v1/jobs/{job_id}` | Get job status and progress |
| `GET` | `/api/v1/jobs/{job_id}/result` | Get job result metadata |
| `GET` | `/api/v1/jobs/{job_id}/download` | Download generated IFC file |
| `DELETE` | `/api/v1/jobs/{job_id}` | Cancel a running job |
| `GET` | `/api/v1/jobs/` | List all jobs |

### Synchronous Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/convert` | Direct mesh-to-IFC conversion (returns file) |
| `POST` | `/api/v1/convert-from-dsl` | Direct DSL-to-IFC conversion (returns file) |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health check |
| `GET` | `/` | Service info |

## Tech Stack

- **Framework**: FastAPI + Uvicorn
- **IFC Generation**: IfcOpenShell
- **Schema Validation**: Pydantic v2
- **Config**: pydantic-settings (env-based)
- **Environment**: Conda (Python 3.11)

## Quick Start

```bash
# Create conda environment
conda env create -f environment.yml
conda activate ifc-export-service

# Run the service
./start.sh
# or
make run
```

## Development

```bash
make test          # Run test suite
make test-cov      # Run tests with coverage
make lint          # Run linting checks
make clean         # Remove build artifacts
make help          # Show all available targets
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `ifc-export-service` | Service name |
| `APP_VERSION` | from `VERSION` file | Service version |
| `PORT` | `8004` | HTTP port |
| `MODELING_SERVICE_URL` | `http://localhost:8003` | 3D modeling service URL |
| `LOG_LEVEL` | `INFO` | Logging level |

## Docker

```bash
make build                              # Build image
docker run -p 8004:8004 ifc-export-service  # Run container
```

## Architecture

```
app/
├── api/
│   ├── v1/router.py          # Synchronous conversion endpoints
│   └── jobs_router.py        # Async job-based conversion endpoints
├── core/
│   ├── job_manager.py         # Canonical async job queue
│   ├── jobs_router.py         # Canonical generic job endpoints
│   ├── health.py              # Health check router
│   └── logging.py             # Structured logging
├── models/
│   └── schemas.py             # IFC export request/response schemas
├── services/
│   ├── ifc_builder.py         # Core IFC generation logic (IfcOpenShell)
│   ├── mesh_converter.py      # Mesh format conversion
│   ├── element_mapper.py      # BIM element to IFC element mapping
│   ├── property_mapper.py     # IFC property set mapping
│   ├── unit_converter.py      # Unit conversion utilities
│   └── job_manager.py         # Backward-compat shim → app.core
├── config.py                  # Service configuration (BaseSettings)
└── main.py                    # FastAPI application entry point
```

### Conversion Pipeline

1. **Mesh → IFC** (`/convert`): Accepts intermediate mesh format (vertices, faces, materials) from the 3d-modeling-service and produces IFC4 output using IfcOpenShell.

2. **DSL → IFC** (`/convert-from-dsl`): Accepts raw BIM DSL JSON, calls the 3d-modeling-service's `/api/v1/jobs/ifc-mesh` endpoint to get intermediate mesh data, then produces IFC4 output.

Both pipelines run CPU-bound IFC generation in a thread pool to avoid blocking the async event loop.
