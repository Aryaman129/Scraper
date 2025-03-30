#!/bin/bash

# This script helps deploy the SRM scraper to multiple platforms
# Usage: ./deploy-scrapers.sh [platform] [update-env]

# Set colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default environment variables (override with .env file)
SUPABASE_URL=${SUPABASE_URL:-"your-supabase-url"}
SUPABASE_KEY=${SUPABASE_KEY:-"your-supabase-key"}
JWT_SECRET=${JWT_SECRET:-"your-jwt-secret"}

# Load environment variables from .env file if it exists
if [ -f .env ]; then
    echo -e "${GREEN}Loading environment variables from .env file${NC}"
    source .env
fi

# Function to deploy to Railway
deploy_railway() {
    echo -e "${YELLOW}Deploying to Railway...${NC}"
    
    # Check if railway CLI is installed
    if ! command -v railway &> /dev/null; then
        echo -e "${RED}Railway CLI is not installed. Install it using:${NC}"
        echo "npm i -g @railway/cli"
        exit 1
    fi
    
    # Set environment variables
    railway variables set SUPABASE_URL="$SUPABASE_URL" SUPABASE_KEY="$SUPABASE_KEY" JWT_SECRET="$JWT_SECRET"
    
    # Deploy
    railway up
    
    echo -e "${GREEN}Railway deployment initiated!${NC}"
}

# Function to deploy to Render
deploy_render() {
    echo -e "${YELLOW}Deploying to Render...${NC}"
    
    # Check if render CLI is installed
    if ! command -v render &> /dev/null; then
        echo -e "${RED}Render CLI is not installed. Please deploy manually via the Render dashboard.${NC}"
        echo "Visit: https://dashboard.render.com/web/new"
        echo "Use the following configuration:"
        echo "- Environment: Docker"
        echo "- Dockerfile path: ./Dockerfile"
        echo "- Environment Variables: SUPABASE_URL, SUPABASE_KEY, JWT_SECRET"
        exit 1
    fi
    
    # Deploy using render CLI
    render deploy
    
    echo -e "${GREEN}Render deployment initiated!${NC}"
}

# Function to deploy to Fly.io
deploy_flyio() {
    echo -e "${YELLOW}Deploying to Fly.io...${NC}"
    
    # Check if flyctl is installed
    if ! command -v flyctl &> /dev/null; then
        echo -e "${RED}Fly.io CLI is not installed. Install it using:${NC}"
        echo "curl -L https://fly.io/install.sh | sh"
        exit 1
    fi
    
    # Set environment variables
    flyctl secrets set SUPABASE_URL="$SUPABASE_URL" SUPABASE_KEY="$SUPABASE_KEY" JWT_SECRET="$JWT_SECRET"
    
    # Deploy
    flyctl deploy
    
    echo -e "${GREEN}Fly.io deployment initiated!${NC}"
}

# Function to update API with new scraper URLs
update_api_env() {
    echo -e "${YELLOW}Updating API with new scraper URLs...${NC}"
    
    # Prompt for URLs
    read -p "Enter comma-separated scraper URLs (e.g., https://url1.com,https://url2.com): " SCRAPER_URLS
    
    # Update the .env file for the API
    if [ -f .env ]; then
        # Check if SCRAPER_URLS already exists in .env
        if grep -q "SCRAPER_URLS=" .env; then
            # Replace existing value
            sed -i "s|SCRAPER_URLS=.*|SCRAPER_URLS=$SCRAPER_URLS|" .env
        else
            # Add new value
            echo "SCRAPER_URLS=$SCRAPER_URLS" >> .env
        fi
    else
        # Create new .env file
        echo "SCRAPER_URLS=$SCRAPER_URLS" > .env
    fi
    
    echo -e "${GREEN}API environment updated with new scraper URLs!${NC}"
    echo -e "${YELLOW}Remember to redeploy your API to apply these changes.${NC}"
}

# Main execution
if [ "$1" = "railway" ]; then
    deploy_railway
elif [ "$1" = "render" ]; then
    deploy_render
elif [ "$1" = "flyio" ]; then
    deploy_flyio
elif [ "$1" = "update-env" ]; then
    update_api_env
else
    echo -e "${YELLOW}Usage:${NC}"
    echo "./deploy-scrapers.sh [platform] [update-env]"
    echo ""
    echo "Available platforms:"
    echo "  railway - Deploy to Railway"
    echo "  render  - Deploy to Render"
    echo "  flyio   - Deploy to Fly.io"
    echo ""
    echo "Other commands:"
    echo "  update-env - Update API environment with new scraper URLs"
fi

exit 0 