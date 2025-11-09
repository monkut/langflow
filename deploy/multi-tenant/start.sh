#!/bin/bash
# Startup script for Langflow Multi-Tenant deployment

set -e

echo "🚀 Starting Langflow Multi-Tenant Deployment"
echo "==========================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo "✅ Created .env file. Please edit it with your configuration."
    echo ""
    echo "Important: Set LANGFLOW_ADMIN_PASSWORD before continuing!"
    exit 1
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if Docker Compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Error: docker-compose is not installed."
    exit 1
fi

echo "📦 Building Docker images..."
docker-compose build

echo ""
echo "🔧 Starting services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Wait for PostgreSQL to be ready
echo "   Checking PostgreSQL..."
max_attempts=30
attempt=0
until docker-compose exec -T postgres pg_isready -U langflow > /dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ $attempt -eq $max_attempts ]; then
        echo "❌ Error: PostgreSQL failed to start after ${max_attempts} attempts"
        docker-compose logs postgres
        exit 1
    fi
    echo "   PostgreSQL not ready yet (attempt $attempt/$max_attempts)..."
    sleep 2
done
echo "   ✅ PostgreSQL is ready"

# Wait for Langflow to be ready
echo "   Checking Langflow..."
attempt=0
until curl -f http://localhost:7860/health > /dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ $attempt -eq $max_attempts ]; then
        echo "❌ Error: Langflow failed to start after ${max_attempts} attempts"
        docker-compose logs langflow
        exit 1
    fi
    echo "   Langflow not ready yet (attempt $attempt/$max_attempts)..."
    sleep 3
done
echo "   ✅ Langflow is ready"

echo ""
echo "✅ Deployment successful!"
echo ""
echo "📋 Service Status:"
docker-compose ps
echo ""

echo "🔗 Access Points:"
echo "   - Langflow (direct):  http://localhost:7860"
echo "   - Nginx (proxy):      http://localhost"
echo "   - Health Check:       http://localhost:7860/health"
echo ""

echo "📚 Next Steps:"
echo ""
echo "1. Create a tenant schema:"
echo "   docker-compose exec langflow python lfhelper.py schema-add --prefix mycompany"
echo ""
echo "2. Add a user to the schema:"
echo "   docker-compose exec langflow python lfhelper.py user-add --schema mycompany-XXXXXX --username admin@mycompany.com"
echo ""
echo "3. Access the tenant:"
echo "   http://localhost/tenant/mycompany/"
echo ""
echo "4. View logs:"
echo "   docker-compose logs -f langflow"
echo ""

echo "For more information, see README.md"
