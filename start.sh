#!/bin/bash

# IFC Export Service - Start Script
# This script activates the conda environment and starts the FastAPI service with hot-reload

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting IFC Export Service...${NC}"

# Set conda path
CONDA_BASE="/opt/miniconda3"
CONDA_EXE="${CONDA_BASE}/bin/conda"

# Check if conda is available
if [ ! -f "$CONDA_EXE" ]; then
    echo -e "${RED}Error: conda is not installed at ${CONDA_BASE}${NC}"
    exit 1
fi

# Check if environment exists
if ! $CONDA_EXE env list | grep -q "ifc-export-service"; then
    echo -e "${YELLOW}Conda environment 'ifc-export-service' not found.${NC}"
    echo -e "${YELLOW}Creating environment from environment.yml...${NC}"
    $CONDA_EXE env create -f environment.yml
fi

# Source conda.sh to enable conda activate
source "$CONDA_BASE/etc/profile.d/conda.sh"

# Activate environment
echo -e "${GREEN}Activating conda environment 'ifc-export-service'...${NC}"
conda activate ifc-export-service

# Set default environment variables
export PORT=${PORT:-8004}
export HOST=${HOST:-0.0.0.0}
export DEBUG=${DEBUG:-True}

# Start the service with hot-reload
echo -e "${GREEN}Starting uvicorn server with hot-reload...${NC}"
echo -e "${GREEN}API will be available at: http://${HOST}:${PORT}${NC}"
echo -e "${GREEN}API documentation at: http://${HOST}:${PORT}/docs${NC}"
echo -e "${YELLOW}Hot-reload enabled - files will be watched for changes${NC}"
echo ""

# Run uvicorn with reload for development
uvicorn app.main:app --reload --host ${HOST} --port ${PORT}
