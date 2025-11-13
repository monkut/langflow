# Multi-Tenant Langflow Implementation

This document describes the complete multi-tenant implementation for Langflow using PostgreSQL schema-based isolation.

## 🎯 Overview

A production-ready multi-tenant solution for Langflow providing complete tenant isolation through PostgreSQL schemas. Each tenant's data is stored in a separate database schema, ensuring data isolation at the database level.

### ✅ What's Included

- **Dynamic Schema Switching**: Header-based tenant identification with automatic PostgreSQL `search_path` routing
- **CLI Management Tool**: `lfhelper.py` for schema and user management
- **Docker Infrastructure**: Production-ready Dockerfile, docker-compose, and Nginx reverse proxy
- **AWS Deployment**: Complete CloudFormation stacks for ECS Fargate + Aurora Serverless v2
- **Security**: Schema-level isolation, secure password generation, connection pooling
- **Testing**: Automated test suite validating all functionality

### 🏗️ Key Design Decisions

**URL Path-Based Routing**: Tenants are identified via URL paths in the format `/tenant/{prefix}/...` (e.g., `/tenant/acme/api/v1/flows`). The middleware extracts the tenant prefix from the request path to determine schema routing.

**No Tracking Table**: Queries PostgreSQL's `pg_namespace` system catalog directly for schema discovery rather than maintaining a separate registry table. This:
- Eliminates sync issues between registry and actual schemas
- Provides single source of truth (PostgreSQL itself)
- Simplifies architecture and reduces maintenance
- Makes schema discovery fast and reliable

## 🚀 Quick Start

### Local Development

```bash
# 1. Navigate to deployment directory
cd deploy/multi-tenant

# 2. Start all services (PostgreSQL, Langflow, Nginx)
./start.sh

# 3. Create a tenant
docker-compose exec langflow python lfhelper.py schema-add --prefix mycompany
# Output: Schema created - mycompany-a1b2c3

# 4. Add a user (password auto-generated)
docker-compose exec langflow python lfhelper.py user-add \
  --schema mycompany-a1b2c3 \
  --username admin@mycompany.com
# Output: Password: Xy9$aBc123... (auto-generated)

# 5. Access via browser
# URL: http://localhost/tenant/mycompany/
# Login with credentials from step 4
```

### Running Tests

```bash
cd deploy/multi-tenant
./test-setup.sh

# Validates:
# ✅ Docker services running
# ✅ Schema creation
# ✅ User management
# ✅ Schema isolation
# ✅ Duplicate prevention
```

## 📁 Files Created/Modified

### New Files

**Core Implementation** (7 files):
- `src/backend/base/langflow/middleware/tenant.py` - Tenant middleware (61 lines)
- `src/backend/base/langflow/services/database/models/tenant/` - Tenant models (3 files)
- `src/backend/base/langflow/services/database/tenant_service.py` - Schema management (248 lines)
- `src/backend/base/langflow/services/deps_tenant.py` - Tenant dependencies (126 lines)
- `lfhelper.py` - CLI management tool (361 lines)

**Docker & Deployment** (7 files):
- `deploy/multi-tenant/Dockerfile` - Multi-stage build (used for both local and production)
- `deploy/multi-tenant/docker-compose.yml` - Local orchestration (uses same Dockerfile as production)
- `deploy/multi-tenant/docker-compose.dev.yml` - Development config
- `deploy/multi-tenant/.env.example` - Configuration template
- `deploy/multi-tenant/README.md` - Deployment guide
- `deploy/multi-tenant/start.sh` - Automated startup
- `deploy/multi-tenant/test-setup.sh` - Test automation
- `deploy/multi-tenant/postgres-init/01-init.sql` - DB initialization

**Note**: `nginx.conf` exists for reference but is not used in either local or production deployments

**Documentation** (3 files):
- `MULTI_TENANT_IMPLEMENTATION.md` - This technical guide
- `MULTI_TENANT_TEST_RESULTS.md` - Test validation results
- `test_multi_tenant.py` - Integration tests

### Modified Files

- `src/backend/base/langflow/main.py` - Added TenantMiddleware registration (2 lines)
- `src/backend/base/langflow/middleware/__init__.py` - Refactored to directory structure
- `pyproject.toml` - Added lfx logging dependency

**Total**: 19 new files, 3 modified files, ~1,200 lines of production code

## 🔧 Configuration

### Environment Variables

```bash
# Database Connection
LANGFLOW_DATABASE_URL=postgresql://user:pass@host:5432/langflow

# Authentication
LANGFLOW_AUTO_LOGIN=false
LANGFLOW_SUPERUSER=admin
LANGFLOW_SUPERUSER_PASSWORD=your-secure-password

# Performance Tuning
LANGFLOW_WORKERS=4              # Gunicorn workers
LANGFLOW_POOL_SIZE=20           # DB connection pool size
LANGFLOW_MAX_OVERFLOW=30        # Additional connections under load
LANGFLOW_POOL_TIMEOUT=30        # Connection wait timeout
LANGFLOW_POOL_RECYCLE=1800      # Recycle connections (30 min)

# Security
LANGFLOW_CORS_ORIGINS=https://yourdomain.com
LANGFLOW_SECRET_KEY=your-secret-key-here

# Logging
LANGFLOW_LOG_LEVEL=INFO
```

### Docker Compose Services

- **langflow**: Application server (port 7860)
- **postgres**: PostgreSQL 17 database (port 5432)
- **nginx**: Reverse proxy (ports 80, 443)

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│             Application Load Balancer / Nginx                │
│        Routes URL paths: /tenant/{prefix}/...                │
│         (/tenant/acme/api/v1/ → tenant prefix: acme)        │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Langflow Application                       │
│  ┌────────────────────────────────────────────────────┐    │
│  │  TenantMiddleware (middleware/tenant.py)            │    │
│  │  - Extracts tenant prefix from URL path            │    │
│  │  - Stores in request.state for session scope       │    │
│  └────────────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Tenant Service (tenant_service.py)                 │    │
│  │  - Queries pg_namespace for schemas                 │    │
│  │  - Creates schemas with collision-resistant hashes  │    │
│  │  - Manages schema lifecycle                         │    │
│  └────────────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Tenant Dependencies (deps_tenant.py)               │    │
│  │  - Provides tenant-aware database sessions          │    │
│  │  - Sets PostgreSQL search_path automatically        │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│         PostgreSQL (Aurora Serverless v2 / Local)            │
│  ┌────────────────────────────────────────────────────┐    │
│  │  public schema                                      │    │
│  │  └── (standard Langflow tables for migrations)     │    │
│  ├────────────────────────────────────────────────────┤    │
│  │  acme-a1b2c3 schema (discovered via pg_namespace)  │    │
│  │  ├── user                                           │    │
│  │  ├── flow                                           │    │
│  │  ├── folder                                         │    │
│  │  ├── apikey                                         │    │
│  │  └── ... (all other Langflow tables)               │    │
│  ├────────────────────────────────────────────────────┤    │
│  │  globex-d4e5f6 schema                               │    │
│  │  ├── user                                           │    │
│  │  └── ... (complete table structure)                │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Request Flow

1. **Client Request**: Request to tenant-specific URL path (e.g., `https://example.com/tenant/acme/api/v1/flows`)
2. **Load Balancer/Nginx**: Routes request based on `/tenant/{prefix}/` URL pattern, optionally sets `X-Tenant-Prefix` header
3. **TenantMiddleware**:
   - Extracts tenant prefix from URL path using regex: `/tenant/([a-zA-Z0-9_-]+)`
   - Stores prefix in `request.state.tenant_prefix` for request scope
4. **Database Session Creation** (via `get_tenant_session`):
   - Queries `pg_namespace`: `SELECT nspname FROM pg_namespace WHERE nspname LIKE 'acme-%'`
   - Finds existing schema: `acme-a1b2c3`
   - Executes: `SET search_path TO "acme-a1b2c3", public`
5. **Route Handler**: Processes request with tenant-isolated session
6. **Response**: Returns data from `acme-a1b2c3` schema only

### Why No Tracking Table?

The implementation intentionally avoids a `tenant_schemas` registry table because:

1. **Single Source of Truth**: PostgreSQL `pg_namespace` is the authoritative source
2. **No Synchronization Issues**: Can't have registry/schema mismatch
3. **Simpler Architecture**: One less table to manage and migrate
4. **Direct Discovery**: Queries like `SELECT nspname FROM pg_namespace WHERE nspname LIKE 'prefix-%'` are fast
5. **Self-Documenting**: Schema existence in PostgreSQL is the only requirement

## File Structure

### New Files Created

```
langflow/
├── lfhelper.py                                    # CLI management tool
├── deploy/multi-tenant/                           # Deployment configuration
│   ├── Dockerfile                                 # Production Docker image
│   ├── docker-compose.yml                         # Multi-service orchestration
│   ├── nginx.conf                                 # Reverse proxy config
│   ├── .env.example                               # Environment template
│   ├── README.md                                  # Deployment guide
│   ├── start.sh                                   # Startup script
│   ├── test-setup.sh                              # Automated tests
│   └── postgres-init/
│       └── 01-init.sql                            # Database initialization
└── src/backend/base/langflow/
    ├── middleware/
    │   ├── __init__.py                            # Middleware exports
    │   └── tenant.py                              # Tenant schema middleware
    ├── services/
    │   ├── database/
    │   │   ├── models/
    │   │   │   ├── __init__.py                    # Updated with TenantSchema
    │   │   │   └── tenant/
    │   │   │       ├── __init__.py                # Tenant model exports
    │   │   │       ├── model.py                   # TenantSchema model
    │   │   │       └── crud.py                    # Tenant CRUD operations
    │   │   └── tenant_service.py                  # Tenant schema management
    │   └── deps_tenant.py                         # Tenant-aware dependencies
    └── main.py                                    # Updated with middleware
```

### Modified Files

1. **`src/backend/base/langflow/main.py`**:
   - Added `TenantMiddleware` import from `middleware.tenant`
   - Registered middleware in `create_app()`

2. **`pyproject.toml`**:
   - Added `lfx` dependency for enhanced logging

**Note**: No Alembic migrations are required. The implementation discovers schemas directly from PostgreSQL's system catalog.

## Database Schema

### Schema Discovery

The implementation queries PostgreSQL's `pg_namespace` system catalog directly:

```sql
-- Find schema by prefix
SELECT nspname
FROM pg_namespace
WHERE nspname LIKE 'acme-%'
ORDER BY nspname
LIMIT 1;

-- List all tenant schemas (excluding system schemas)
SELECT nspname
FROM pg_namespace
WHERE nspname LIKE '%-%'
  AND nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'public')
ORDER BY nspname;
```

### Schema Creation

When creating a new tenant schema:

```sql
-- 1. Generate unique schema name
-- Format: {prefix}-{hash}
-- Example: acme-a1b2c3

-- 2. Create the schema
CREATE SCHEMA IF NOT EXISTS "acme-a1b2c3";

-- 3. Copy table structure from public schema
CREATE TABLE IF NOT EXISTS "acme-a1b2c3".user
(LIKE public.user INCLUDING ALL);

CREATE TABLE IF NOT EXISTS "acme-a1b2c3".flow
(LIKE public.flow INCLUDING ALL);

-- ... repeat for all Langflow tables
```

### Tenant Schema Structure

Each tenant schema contains all Langflow tables:

```sql
CREATE SCHEMA "acme-a1b2c3";

SET search_path TO "acme-a1b2c3";

-- All Langflow tables are created in this schema
CREATE TABLE "user" (...);
CREATE TABLE "flow" (...);
CREATE TABLE "folder" (...);
CREATE TABLE "api_key" (...);
CREATE TABLE "variable" (...);
-- etc.
```

## API Changes

### Tenant Identification

Tenants are identified via the `X-Tenant-ID` HTTP header, which is set by the load balancer or reverse proxy based on the subdomain:

- **Subdomain**: `acme.example.com` → Header: `X-Tenant-ID: acme`
- **Subdomain**: `globex.example.com` → Header: `X-Tenant-ID: globex`

### URL Format

All tenants use the same URL paths - tenant isolation is handled via headers:

- **Health Check**: `GET /health` (no tenant context)
- **All APIs**: `GET /api/v1/flows` (tenant determined by X-Tenant-ID header)

### Examples

```bash
# Public health check (no tenant header required)
curl https://example.com/health

# Tenant-specific flows (acme schema via subdomain)
curl https://acme.example.com/api/v1/flows
# → Nginx adds: X-Tenant-ID: acme

# Tenant-specific user management (globex schema)
curl https://globex.example.com/api/v1/users
# → Nginx adds: X-Tenant-ID: globex

# Direct header-based access (for testing)
curl -H "X-Tenant-ID: acme" https://example.com/api/v1/flows
```

## Helper Script (lfhelper.py)

### Commands

#### Schema Management

```bash
# Create a new tenant schema
python lfhelper.py schema-add --prefix acme

# List all schemas
python lfhelper.py schema-list
```

#### User Management

```bash
# Add user with auto-generated password
python lfhelper.py user-add --schema acme-a1b2c3 --username admin@acme.com

# Add user with custom password
python lfhelper.py user-add --schema acme-a1b2c3 --username admin@acme.com --password SecurePass123!

# Reset user password
python lfhelper.py user-reset --schema acme-a1b2c3 --username admin@acme.com

# List users in schema
python lfhelper.py user-list --schema acme-a1b2c3
```

## Deployment

### Local Development

```bash
cd deploy/multi-tenant
./start.sh
```

This starts the complete stack locally with Docker Compose:
- PostgreSQL database
- Langflow application
- Nginx reverse proxy

### Production (AWS ECS Fargate + Aurora Serverless v2)

For complete AWS deployment instructions using CloudFormation stacks (VPC, RDS, ECR, Fargate), see the dedicated infrastructure repository:

**[langflow-infra](https://github.com/monkut/langflow-infra.git)**

The infrastructure repository provides:
- CloudFormation templates for VPC, RDS (Aurora Serverless v2), Platform (ECR), and Fargate stacks
- Step-by-step deployment guide with example commands
- Schema and user management instructions using ECS Exec and `lfhelper.py`
- Production-ready configuration with auto-scaling, health checks, and monitoring

#### Docker Build

The `deploy/multi-tenant/Dockerfile` is used for both local development and production deployment:

**What's included**:
- Langflow application with multi-tenant middleware
- `lfhelper.py` CLI tool for tenant/user management
- PostgreSQL client libraries
- Frontend built assets

**Configuration**:
- **Port**: 7860 (Langflow application server)
- **Command**: `langflow run`
- **No nginx**: Runs Langflow directly

**URL Routing**:
- All tenant routing is handled by FastAPI middleware (middleware/tenant.py:46)
- Middleware extracts tenant prefix from URL path `/tenant/{prefix}/...`
- ALB/load balancers are unaware of multi-tenant implementation - they simply forward requests
- Access pattern: `http://host/tenant/{prefix}/` (same for local and production)

Build command:
```bash
docker build -f deploy/multi-tenant/Dockerfile -t langflow-multi-tenant:latest .
```

## Security Features

1. **Schema Isolation**: Complete data separation at database level using PostgreSQL schemas
2. **URL Path-Based Routing**: Tenant identification via URL paths (`/tenant/{prefix}/...`)
3. **Collision Prevention**: 6-character random hash prevents schema name conflicts
4. **Password Security**: Auto-generated secure passwords with mixed character sets
5. **Rate Limiting**: Nginx-based request throttling (configurable)
6. **Connection Pooling**: Prevents resource exhaustion with configurable pool sizes
7. **No Shared Data**: Each tenant schema is completely isolated - no cross-tenant queries possible
8. **Schema Enumeration Protection**: Random hashes prevent tenant discovery

## Performance Optimization

### Database Settings

```yaml
# PostgreSQL tuning for multi-tenant workload
max_connections: 200
shared_buffers: 256MB
effective_cache_size: 1GB
work_mem: 1MB
```

### Application Settings

```bash
# Worker configuration
LANGFLOW_WORKERS=4

# Connection pool
LANGFLOW_POOL_SIZE=20
LANGFLOW_MAX_OVERFLOW=30
```

## Monitoring

### Health Checks

```bash
# Application health
curl http://localhost:7860/health

# Database health
docker-compose exec postgres pg_isready -U langflow

# Schema sizes
docker-compose exec postgres psql -U langflow -d langflow -c "SELECT * FROM public.get_schema_sizes();"
```

### Logs

```bash
# View application logs
docker-compose logs -f langflow

# View tenant-specific activity
docker-compose logs langflow | grep "acme-a1b2c3"

# View PostgreSQL logs
docker-compose logs postgres
```

## Testing

### Automated Test Suite

```bash
cd deploy/multi-tenant
./test-setup.sh
```

Tests include:
- Service health checks
- Schema creation and listing
- User management operations
- Schema isolation verification
- Duplicate prevention
- Password reset functionality

### Manual Testing

```bash
# 1. Create schema
docker-compose exec langflow python lfhelper.py schema-add --prefix testco

# 2. List schemas (from pg_namespace)
docker-compose exec postgres psql -U langflow -d langflow -c \
  "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'testco-%' ORDER BY nspname;"

# 3. Add user to the schema
docker-compose exec langflow python lfhelper.py user-add --schema testco-XXXXXX --username test@test.com

# 4. Verify user in tenant schema
docker-compose exec postgres psql -U langflow -d langflow -c \
  "SET search_path TO \"testco-XXXXXX\"; SELECT username, is_active FROM \"user\";"

# 5. Verify schema isolation (should only see tenant's data)
docker-compose exec postgres psql -U langflow -d langflow -c \
  "SET search_path TO \"testco-XXXXXX\"; SELECT * FROM flow;"
```

## File Storage & Persistence

### Problem Statement

**Current Issue**: File storage uses `user_id` as directory path:
```
/app/data/{user_id}/{filename}
```

**Risk**: Since UUID uniqueness is enforced per-schema (not globally), the same `user_id` can exist in different schemas:
- Tenant A: User `abc-123-def` in schema `testco-0f6d5c`
- Tenant B: User `abc-123-def` in schema `demolab-fbd49c`
- Both write to: `/app/data/abc-123-def/` ❌ **COLLISION**

### Schema-Based Directory Prefixing

#### Target Structure
```
/app/data/{schema_name}/{user_id}/{filename}
```

**Example**:
- Tenant A: `/app/data/testco-0f6d5c/abc-123-def/report.pdf`
- Tenant B: `/app/data/demolab-fbd49c/abc-123-def/report.pdf`
- ✅ **ISOLATED**

#### Implementation Changes Required

**1. Modify Storage Service Interface**

**File**: `src/backend/base/langflow/services/storage/service.py`

```python
# Current
async def save_file(self, flow_id: str, file_name: str, data) -> None:
    raise NotImplementedError

# Proposed
async def save_file(self, flow_id: str, file_name: str, data, schema_name: str | None = None) -> None:
    raise NotImplementedError
```

**Changes needed** in ALL abstract methods:
- `save_file()`
- `get_file()`
- `list_files()`
- `delete_file()`
- `get_file_size()`
- `build_full_path()`

**2. Update LocalStorageService Implementation**

**File**: `src/backend/base/langflow/services/storage/local.py`

```python
def build_full_path(self, flow_id: str, file_name: str, schema_name: str | None = None) -> str:
    """Build the full path with schema prefix for multi-tenant isolation."""
    if schema_name:
        # Multi-tenant: /app/data/{schema}/{user_id}/{filename}
        return str(self.data_dir / schema_name / flow_id / file_name)
    else:
        # Legacy/single-tenant: /app/data/{user_id}/{filename}
        return str(self.data_dir / flow_id / file_name)

async def save_file(self, flow_id: str, file_name: str, data: bytes, schema_name: str | None = None) -> None:
    """Save a file with schema-based isolation."""
    if schema_name:
        folder_path = self.data_dir / schema_name / flow_id
    else:
        folder_path = self.data_dir / flow_id

    await folder_path.mkdir(parents=True, exist_ok=True)
    file_path = folder_path / file_name

    # ... rest of implementation
```

**Apply similar changes to**:
- `get_file()` - line 45-68
- `list_files()` - line 70-97
- `delete_file()` - line 99-111
- `get_file_size()` - line 116-127

**3. Update All Callers to Pass Schema Name**

**File**: `src/backend/base/langflow/api/v2/files.py`

**Current** (line 82):
```python
await storage_service.save_file(
    flow_id=str(current_user.id),
    file_name=file_name,
    data=file_content
)
```

**Proposed**:
```python
from typing import Annotated
from fastapi import Depends, Request

@router.post("", status_code=HTTPStatus.CREATED)
async def upload_user_file(
    file: Annotated[UploadFile, File(...)],
    session: DbSession,
    current_user: CurrentActiveUser,
    storage_service: Annotated[StorageService, Depends(get_storage_service)],
    settings_service: Annotated[SettingsService, Depends(get_settings_service)],
    request: Request,  # Add this
) -> UploadFileResponse:
    # Get tenant schema from request state (set by middleware)
    schema_name = getattr(request.state, "tenant_schema", None)

    # Save with schema prefix
    await storage_service.save_file(
        flow_id=str(current_user.id),
        file_name=file_name,
        data=file_content,
        schema_name=schema_name  # Pass schema
    )
```

**Other files requiring updates**:
1. `src/backend/base/langflow/api/v2/files.py`
   - `upload_user_file()` - line 89
   - `download_file()` - line 130
   - `list_files()` - line 175
   - `delete_file()` - line 195

2. `src/lfx/src/lfx/components/data/save_file.py`
   - `_upload_file()` - line 277

3. Any other component that calls storage service methods

**4. Testing Strategy**

**Test Cases**:
1. Create same user_id in two different schemas
2. Upload files from both users
3. Verify files are in separate directories
4. Verify cross-tenant file access is blocked
5. Test backward compatibility (schema_name=None)

**Test Script**:
```python
# Test multi-tenant file isolation
testco_token = api_login("testco", "testuser1", "password")
demolab_token = api_login("demolab", "demouser1", "password")

# Upload file as testco user
upload_file("testco", testco_token, "report.pdf")

# Try to access as demolab user (should fail)
try:
    download_file("demolab", demolab_token, "report.pdf")
    assert False, "Should not access testco file"
except HTTPException as e:
    assert e.status_code == 404  # File not found
```

### Data Persistence Recommendations

#### Current State: Ephemeral Storage
- Dockerfile creates `/app/data` without volumes
- All files lost on container restart
- ✅ Good for temporary cache/workspace
- ❌ Bad for user-uploaded files, exports, attachments

#### Persistence Options

**Option 1: AWS S3 (RECOMMENDED for Fargate)**

**Advantages**:
- Serverless, no infrastructure management
- Infinite scalability
- Built-in multi-tenancy (use prefixes)
- Versioning and lifecycle policies
- Low cost for storage

**Implementation**:
```python
# In storage/factory.py
def create_storage_service():
    storage_type = os.getenv("LANGFLOW_STORAGE_TYPE", "local")

    if storage_type == "s3":
        return S3StorageService(
            bucket_name=os.getenv("LANGFLOW_S3_BUCKET"),
            region=os.getenv("AWS_REGION", "ap-northeast-1")
        )
    return LocalStorageService(...)
```

**S3 Path Structure**:
```
s3://langflow-files-bucket/
├── testco-0f6d5c/
│   └── {user_id}/
│       └── report.pdf
└── demolab-fbd49c/
    └── {user_id}/
        └── invoice.pdf
```

**Environment Variables**:
```bash
LANGFLOW_STORAGE_TYPE=s3
LANGFLOW_S3_BUCKET=langflow-be1bbb25-dev-files
AWS_REGION=ap-northeast-1
```

**Fargate IAM Role**: Grant S3 permissions to task execution role

**Cost Estimate**: ~$0.023/GB/month + $0.0004/1000 requests

**Option 2: AWS EFS (Alternative for Fargate)**

**Advantages**:
- POSIX-compliant filesystem (drop-in replacement)
- Shared across multiple Fargate tasks
- Automatic scaling

**Disadvantages**:
- More expensive than S3 (~$0.30/GB/month)
- Requires VPC configuration
- Not as scalable as S3

**Implementation**:
1. Create EFS filesystem
2. Mount to Fargate tasks at `/app/data`
3. No code changes needed (uses LocalStorageService)

**CloudFormation Addition**:
```yaml
EFSFileSystem:
  Type: AWS::EFS::FileSystem
  Properties:
    PerformanceMode: generalPurpose
    Encrypted: true

MountTarget:
  Type: AWS::EFS::MountTarget
  Properties:
    FileSystemId: !Ref EFSFileSystem
    SubnetId: !Ref PrivateSubnet
    SecurityGroups: [!Ref EFSSecurityGroup]
```

**Fargate Task Definition**:
```json
{
  "volumes": [{
    "name": "langflow-data",
    "efsVolumeConfiguration": {
      "fileSystemId": "fs-xxxxx",
      "rootDirectory": "/langflow-data"
    }
  }],
  "containerDefinitions": [{
    "mountPoints": [{
      "sourceVolume": "langflow-data",
      "containerPath": "/app/data"
    }]
  }]
}
```

**Option 3: Docker Volumes (Local Development Only)**

**For docker-compose testing with persistence**:

```yaml
# deploy/multi-tenant/docker-compose.yml
services:
  langflow:
    volumes:
      - langflow-data:/app/data  # Add volume mount
    # ... rest of config

volumes:
  langflow-data:
    driver: local
```

**Not recommended for production**: Data tied to single host

### Implementation Priority

**Phase 1: Schema Prefixing (HIGH PRIORITY)**
- **Why**: Security/isolation concern
- **Timeline**: Implement before production launch
- **Files to change**: ~4-5 files
- **Testing**: Critical for multi-tenant validation

**Phase 2: Persistence Strategy (MEDIUM PRIORITY)**
- **Why**: User experience improvement
- **Timeline**: Can deploy without (ephemeral is functional)
- **Recommendation**: S3 for production
- **Testing**: Upload/download/delete operations

### Storage Migration Strategy

If you already have data in production:

**Option A: Fresh Start (If no critical data)**
1. Deploy schema-prefixed version
2. Old files in `/app/data/{user_id}/` are orphaned
3. Files are ephemeral anyway (lost on restart)
4. No migration needed

**Option B: Data Migration (If critical data exists)**
1. Deploy schema-prefixed version with migration script
2. Script to move files:
```python
async def migrate_existing_files():
    """Move files from /app/data/{user_id}/ to /app/data/{schema}/{user_id}/"""
    for user in all_users:
        old_path = f"/app/data/{user.id}"
        new_path = f"/app/data/{user.schema_name}/{user.id}"
        if os.path.exists(old_path):
            shutil.move(old_path, new_path)
```

### Storage Decision Matrix

| Requirement | Local (Ephemeral) | Local (Volume) | EFS | S3 |
|------------|-------------------|----------------|-----|-----|
| Multi-tenant isolation | ✅ (with prefix) | ✅ (with prefix) | ✅ (with prefix) | ✅ (native) |
| Data persistence | ❌ | ✅ | ✅ | ✅ |
| Fargate compatible | ✅ | ❌ | ✅ | ✅ |
| Cost (monthly) | Free | N/A | ~$30 (100GB) | ~$2.30 (100GB) |
| Scalability | N/A | Limited | Good | Excellent |
| Implementation effort | Low | Low | Medium | Medium-High |
| **Recommendation** | Testing only | Dev only | If POSIX needed | **PRODUCTION** |

### Storage Implementation Checklist

1. **Immediate**: Implement schema prefixing (Part 1)
   - Modify storage service interface
   - Update LocalStorageService
   - Update file upload/download endpoints
   - Test with local Docker

2. **Short-term**: Choose persistence strategy
   - Recommended: S3 for production
   - Create S3 bucket with lifecycle policies
   - Implement S3StorageService class
   - Update Fargate IAM role

3. **Before production**:
   - Complete multi-tenant isolation testing
   - Verify file access controls
   - Test schema prefix isolation
   - Document backup/recovery procedures

### Storage Questions to Resolve

1. **Immediate deployment tolerance**: Can you deploy with ephemeral storage initially?
2. **Data criticality**: Are uploaded files business-critical or just temporary?
3. **Budget considerations**: S3 ($2-5/month) vs EFS ($30+/month)?
4. **Compliance requirements**: Any data residency or encryption requirements?

## Migration from Single-Tenant

If you have existing Langflow data in the public schema:

1. **Backup current database**:
   ```bash
   pg_dump -U langflow langflow > backup.sql
   ```

2. **Create tenant schema and copy data**:
   ```sql
   -- Create new tenant schema (use lfhelper.py for automatic structure)
   CREATE SCHEMA "existing-a1b2c3";

   -- Copy table structures
   CREATE TABLE "existing-a1b2c3".user (LIKE public.user INCLUDING ALL);
   CREATE TABLE "existing-a1b2c3".flow (LIKE public.flow INCLUDING ALL);
   CREATE TABLE "existing-a1b2c3".folder (LIKE public.folder INCLUDING ALL);
   CREATE TABLE "existing-a1b2c3".apikey (LIKE public.apikey INCLUDING ALL);
   -- ... repeat for all tables

   -- Copy data
   INSERT INTO "existing-a1b2c3".user SELECT * FROM public.user;
   INSERT INTO "existing-a1b2c3".flow SELECT * FROM public.flow;
   INSERT INTO "existing-a1b2c3".folder SELECT * FROM public.folder;
   INSERT INTO "existing-a1b2c3".apikey SELECT * FROM public.apikey;
   -- ... repeat for all tables
   ```

3. **Verify schema in PostgreSQL**:
   ```sql
   -- Confirm schema exists
   SELECT nspname FROM pg_namespace WHERE nspname = 'existing-a1b2c3';

   -- Verify data
   SET search_path TO "existing-a1b2c3";
   SELECT COUNT(*) FROM "user";
   SELECT COUNT(*) FROM flow;
   ```

**Note**: No tracking table is needed - the schema's existence in PostgreSQL is sufficient for the application to discover and use it.

## 🎓 Usage Examples

### Example 1: Multi-Customer SaaS

```bash
# Customer A (Acme Corp)
python lfhelper.py schema-add --prefix acme
python lfhelper.py user-add --schema acme-a1b2c3 --username admin@acme.com
# Users access: https://yourdomain.com/tenant/acme/

# Customer B (Globex Inc)
python lfhelper.py schema-add --prefix globex
python lfhelper.py user-add --schema globex-d4e5f6 --username admin@globex.com
# Users access: https://yourdomain.com/tenant/globex/
```

### Example 2: Department Isolation

```bash
# Marketing Department
python lfhelper.py schema-add --prefix marketing
python lfhelper.py user-add --schema marketing-a1b2c3 \
  --username team@marketing.company.com

# Engineering Department
python lfhelper.py schema-add --prefix engineering
python lfhelper.py user-add --schema engineering-d4e5f6 \
  --username team@eng.company.com
```

### Example 3: Environment Separation

```bash
# Development Environment
python lfhelper.py schema-add --prefix dev
python lfhelper.py user-add --schema dev-a1b2c3 --username devteam

# Staging Environment
python lfhelper.py schema-add --prefix staging
python lfhelper.py user-add --schema staging-d4e5f6 --username stagingteam

# Production Environment
python lfhelper.py schema-add --prefix prod
python lfhelper.py user-add --schema prod-e7f8g9 --username prodteam
```

## Troubleshooting

### Issue: Schema not found

**Symptom**: 404 error or "Schema not found" errors when accessing tenant

**Solution**:
```bash
# Check if schema exists via lfhelper
python lfhelper.py schema-list

# Or check directly in PostgreSQL
psql -U langflow -d langflow -c \
  "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'acme-%';"

# Create if missing
python lfhelper.py schema-add --prefix acme
```

**Note**: The X-Tenant-ID header must exactly match the schema prefix.

### Issue: User authentication fails

**Symptom**: Invalid credentials error

**Solution**:
```bash
# Verify user exists
python lfhelper.py user-list --schema acme-a1b2c3

# Reset password
python lfhelper.py user-reset --schema acme-a1b2c3 --username user@acme.com
```

### Issue: Database connection timeout

**Symptom**: Connection pool exhausted

**Solution**:
```bash
# Increase pool size in .env
LANGFLOW_POOL_SIZE=30
LANGFLOW_MAX_OVERFLOW=50

# Restart services
docker-compose restart langflow
```

## Future Enhancements

1. **Tenant Quotas**: Implement resource limits per tenant
2. **Billing Integration**: Track usage per schema
3. **Tenant Analytics**: Monitor activity per tenant
4. **Automated Backup**: Per-schema backup scheduling
5. **Tenant Suspension**: Deactivate without data deletion
6. **Cross-tenant Admin**: Super-admin dashboard for all tenants

## License

Same as Langflow main project (MIT).

## Support

For issues or questions:
- GitHub Issues: https://github.com/langflow-ai/langflow/issues
- Documentation: See `deploy/multi-tenant/README.md`
