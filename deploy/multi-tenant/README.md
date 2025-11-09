# Langflow Multi-Tenant Deployment

This directory contains the configuration for deploying Langflow with multi-tenant support using PostgreSQL schema-based isolation.

## Architecture Overview

- **Multi-Tenancy**: Each tenant gets its own PostgreSQL schema for complete data isolation
- **URL-Based Routing**: Tenants are accessed via `/tenant/{prefix}/...` URL paths
- **Scalable**: Designed for AWS Fargate with Aurora Serverless or similar cloud deployments
- **Secure**: Schema-level isolation with tenant-aware authentication

## Quick Start

### 1. Prerequisites

- Docker and Docker Compose installed
- At least 4GB RAM available
- Port 80, 443, 5432, and 7860 available

### 2. Initial Setup

```bash
# Copy environment configuration
cp .env.example .env

# Edit .env and set secure passwords
nano .env

# Build and start services
docker-compose up -d

# Wait for services to be healthy (check with)
docker-compose ps
```

### 3. Create Your First Tenant

```bash
# Access the Langflow container
docker-compose exec langflow bash

# Create a tenant schema
python lfhelper.py schema-add --prefix acme

# Expected output:
# ✅ Successfully created tenant schema:
#    Prefix: acme
#    Schema ID: acme-a1b2c3
#    Created: 2024-01-15 10:30:00

# Add a user to the tenant
python lfhelper.py user-add --schema acme-a1b2c3 --username john@acme.com

# Expected output:
# ✅ Successfully created user:
#    Schema: acme-a1b2c3
#    Username: john@acme.com
#    Password: XyZ123!@#abcDEF (auto-generated)
#    User ID: 550e8400-e29b-41d4-a716-446655440000
```

### 4. Access the Tenant

```bash
# The tenant can now access Langflow at:
http://localhost/tenant/acme/

# Or with nginx on port 80:
http://your-domain.com/tenant/acme/
```

## Helper Script Usage

The `lfhelper.py` script provides CLI commands for managing tenants and users.

### Schema Management

#### Create a New Schema

```bash
python lfhelper.py schema-add --prefix {PREFIX}
```

- Creates a new tenant schema with the given prefix
- Generates a unique schema ID: `{prefix}-{6-char-hash}`
- Raises an error if the prefix already exists

#### List All Schemas

```bash
python lfhelper.py schema-list
```

Output example:
```
Prefix               Schema ID                      Status     Created
------------------------------------------------------------------------------------------
acme                 acme-a1b2c3                    Active     2024-01-15 10:30
globex               globex-d4e5f6                  Active     2024-01-15 11:45

Total: 2 schema(s)
```

### User Management

#### Add a User

```bash
# With auto-generated password
python lfhelper.py user-add --schema {SCHEMA_ID} --username {USERNAME}

# With custom password
python lfhelper.py user-add --schema {SCHEMA_ID} --username {USERNAME} --password {PASSWORD}
```

Example:
```bash
python lfhelper.py user-add --schema acme-a1b2c3 --username admin@acme.com --password SecurePass123!
```

#### Reset User Password

```bash
# With auto-generated password
python lfhelper.py user-reset --schema {SCHEMA_ID} --username {USERNAME}

# With custom password
python lfhelper.py user-reset --schema {SCHEMA_ID} --username {USERNAME} --password {PASSWORD}
```

#### List Users in a Schema

```bash
python lfhelper.py user-list --schema {SCHEMA_ID}
```

Output example:
```
Users in schema 'acme-a1b2c3':
Username                       Active     Superuser    Last Login
------------------------------------------------------------------------------------------
admin@acme.com                 Yes        No           2024-01-15 14:30
user@acme.com                  Yes        No           Never

Total: 2 user(s)
```

## Architecture Details

### URL Routing

The multi-tenant setup uses URL path prefixes to identify tenants:

- **Public/Admin**: `http://your-domain.com/` (uses public schema)
- **Tenant Access**: `http://your-domain.com/tenant/{prefix}/` (uses tenant schema)

Example:
```
http://your-domain.com/tenant/acme/api/v1/flows
                              ^^^^
                              tenant prefix
```

### Database Schema Isolation

Each tenant has its own PostgreSQL schema:

```
langflow (database)
├── public (schema)
│   └── tenant_schemas (registry table)
├── acme-a1b2c3 (schema)
│   ├── user
│   ├── flow
│   ├── folder
│   └── ... (all other tables)
└── globex-d4e5f6 (schema)
    ├── user
    ├── flow
    └── ...
```

### How It Works

1. **Request arrives**: `GET /tenant/acme/api/v1/flows`
2. **Middleware extracts** tenant prefix: `acme`
3. **Database lookup**: Find schema for prefix `acme` → `acme-a1b2c3`
4. **Set search_path**: `SET search_path TO "acme-a1b2c3", public`
5. **Execute query**: All queries now run against tenant schema
6. **Reset search_path**: After request completes

## Production Deployment

### AWS Fargate + Aurora Serverless

1. **Build and push Docker image**:
   ```bash
   docker build -t your-registry/langflow-multi-tenant:latest -f Dockerfile ../..
   docker push your-registry/langflow-multi-tenant:latest
   ```

2. **Create Aurora Serverless PostgreSQL cluster**:
   - Engine: PostgreSQL 15+
   - Min capacity: 2 ACUs
   - Max capacity: 16 ACUs (adjust based on load)
   - Enable Data API for easy management

3. **Create ECS Task Definition**:
   ```json
   {
     "family": "langflow-multi-tenant",
     "networkMode": "awsvpc",
     "requiresCompatibilities": ["FARGATE"],
     "cpu": "2048",
     "memory": "4096",
     "containerDefinitions": [{
       "name": "langflow",
       "image": "your-registry/langflow-multi-tenant:latest",
       "portMappings": [{"containerPort": 7860}],
       "environment": [
         {"name": "LANGFLOW_DATABASE_URL", "value": "postgresql://user:pass@aurora-cluster.region.rds.amazonaws.com:5432/langflow"},
         {"name": "LANGFLOW_WORKERS", "value": "4"}
       ]
     }]
   }
   ```

4. **Create ALB with path-based routing**:
   - Listener rule: `/tenant/*` → Target Group (Langflow)
   - Health check: `/health`
   - Sticky sessions: Enabled (for WebSocket support)

5. **Auto-scaling**:
   - Target tracking: CPU utilization 70%
   - Min tasks: 2
   - Max tasks: 10

### Environment Variables

Key environment variables for production:

```bash
# Database
LANGFLOW_DATABASE_URL=postgresql://user:pass@host:5432/dbname
LANGFLOW_DATABASE_CONNECTION_RETRY=true

# Authentication
LANGFLOW_AUTO_LOGIN=false
LANGFLOW_SUPERUSER=admin
LANGFLOW_SUPERUSER_PASSWORD=<secure-password>

# Performance
LANGFLOW_WORKERS=4
LANGFLOW_POOL_SIZE=20
LANGFLOW_MAX_OVERFLOW=30

# Security
LANGFLOW_CORS_ORIGINS=https://your-domain.com
LANGFLOW_CORS_ALLOW_CREDENTIALS=true

# Logging
LANGFLOW_LOG_LEVEL=warning
LANGFLOW_SENTRY_DSN=<your-sentry-dsn>
```

## Monitoring and Maintenance

### Health Checks

```bash
# Container health
curl http://localhost:7860/health

# Database health
docker-compose exec postgres pg_isready -U langflow
```

### Logs

```bash
# View logs
docker-compose logs -f langflow

# View specific tenant activity
docker-compose logs langflow | grep "acme-a1b2c3"
```

### Backups

```bash
# Backup entire database (all schemas)
docker-compose exec postgres pg_dump -U langflow langflow > backup.sql

# Backup specific schema
docker-compose exec postgres pg_dump -U langflow -n acme-a1b2c3 langflow > acme-backup.sql

# Restore
docker-compose exec -T postgres psql -U langflow langflow < backup.sql
```

### Database Maintenance

```bash
# Connect to database
docker-compose exec postgres psql -U langflow

# View all schemas
\dn

# View schema sizes
SELECT schema_name,
       pg_size_pretty(SUM(pg_total_relation_size(quote_ident(schemaname) || '.' || quote_ident(tablename)))::bigint) as size
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
GROUP BY schema_name
ORDER BY SUM(pg_total_relation_size(quote_ident(schemaname) || '.' || quote_ident(tablename))) DESC;

# List tenant schemas
SELECT * FROM public.tenant_schemas;
```

## Troubleshooting

### Schema Not Found

**Problem**: 404 error when accessing `/tenant/acme/`

**Solution**:
```bash
# Verify schema exists
python lfhelper.py schema-list

# Create if missing
python lfhelper.py schema-add --prefix acme
```

### Authentication Failed

**Problem**: User cannot log in

**Solution**:
```bash
# Verify user exists in correct schema
python lfhelper.py user-list --schema acme-a1b2c3

# Reset password
python lfhelper.py user-reset --schema acme-a1b2c3 --username user@acme.com
```

### Database Connection Issues

**Problem**: Cannot connect to database

**Solution**:
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check connection from container
docker-compose exec langflow psql $LANGFLOW_DATABASE_URL -c "SELECT 1"

# View PostgreSQL logs
docker-compose logs postgres
```

## Security Considerations

1. **Change Default Passwords**: Always set strong passwords in production
2. **Enable HTTPS**: Configure SSL certificates in nginx
3. **Rate Limiting**: Nginx config includes rate limiting (adjust as needed)
4. **Database Encryption**: Use RDS encryption at rest for Aurora
5. **Network Isolation**: Use VPC with private subnets for database
6. **API Key Management**: Rotate API keys regularly
7. **Audit Logging**: Enable CloudWatch logs for all services

## Performance Tuning

### PostgreSQL Settings

For high-load scenarios, adjust `docker-compose.yml` postgres command:

```yaml
command:
  - "postgres"
  - "-c"
  - "max_connections=200"      # Increase for more concurrent users
  - "-c"
  - "shared_buffers=512MB"     # 25% of available RAM
  - "-c"
  - "effective_cache_size=2GB" # 50-75% of available RAM
```

### Application Settings

```bash
# Increase worker processes (based on CPU cores)
LANGFLOW_WORKERS=8

# Increase connection pool
LANGFLOW_POOL_SIZE=30
LANGFLOW_MAX_OVERFLOW=50
```

## License

Same as Langflow main project.

## Support

For issues and questions:
- Langflow GitHub: https://github.com/langflow-ai/langflow
- Documentation: https://docs.langflow.org
