# SRM Scraper Deployment Guide

This guide explains how to deploy the SRM Selenium scraper across multiple free hosting platforms to distribute the load and provide failover capabilities.

## Architecture Overview

- **Backend API**: Deployed on Koyeb (noble-addy-personal129-4157b1c3.koyeb.app)
- **Scraper Services**: Deployed across multiple free platforms (Railway, Render, Fly.io)
- **Database**: Supabase for data storage

The API receives user credentials and forwards scraping requests to the most available scraper service. Data is stored in Supabase and then retrieved by the API to display to users.

## Prerequisites

- Accounts on the following platforms:
  - Railway
  - Render
  - Fly.io
- Supabase account with database set up
- Docker installed locally (for testing)

## Deployment Steps

### 1. Environment Setup

Create a `.env` file with the following variables:

```
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
JWT_SECRET=your_jwt_secret
```

### 2. Deploy to Multiple Platforms

#### Option 1: Use the deployment script

```bash
# Make the script executable
chmod +x deploy-scrapers.sh

# Deploy to Railway
./deploy-scrapers.sh railway

# Deploy to Render
./deploy-scrapers.sh render

# Deploy to Fly.io
./deploy-scrapers.sh flyio
```

#### Option 2: Manual Deployment

**Railway**:
1. Install Railway CLI: `npm i -g @railway/cli`
2. Login: `railway login`
3. Link project: `railway link`
4. Set environment variables: `railway variables set SUPABASE_URL=... SUPABASE_KEY=... JWT_SECRET=...`
5. Deploy: `railway up`

**Render**:
1. Push code to a GitHub repository
2. Create a new Web Service on Render dashboard
3. Select "Build and deploy from GitHub" 
4. Choose your repository
5. Select "Docker" as the environment
6. Set the environment variables
7. Deploy

**Fly.io**:
1. Install Flyctl: `curl -L https://fly.io/install.sh | sh`
2. Login: `flyctl auth login`
3. Launch app: `flyctl launch`
4. Set secrets: `flyctl secrets set SUPABASE_URL=... SUPABASE_KEY=... JWT_SECRET=...`
5. Deploy: `flyctl deploy`

### 3. Update API with Scraper URLs

After deploying all scrapers, update your API with the scraper URLs:

```bash
./deploy-scrapers.sh update-env
```

Enter the URLs of your deployed scrapers when prompted, separated by commas:
```
https://srm-scraper-railway.up.railway.app,https://srm-scraper.onrender.com,https://srm-scraper.fly.dev
```

Then redeploy your API to Koyeb to apply these changes.

## Testing

To test your setup:

1. Check health endpoints of each scraper:
   ```bash
   curl https://your-scraper-url/health
   ```

2. Test the API with your scrapers:
   ```bash
   curl -X POST https://noble-addy-personal129-4157b1c3.koyeb.app/api/scraper-health \
     -H "Authorization: Bearer YOUR_JWT_TOKEN"
   ```

## Troubleshooting

- **Memory Issues**: The Selenium scraper is memory-intensive. If you're experiencing crashes, try:
  - Reducing the number of concurrent scraper instances
  - Using the `/api/scrape` endpoint instead of `/api/scrape-all` to separate attendance and timetable scraping
  
- **Connection Timeouts**: If scrapers are timing out, check:
  - Network connectivity to SRM servers
  - VPN requirements (some hosting platforms might be blocked)
  - Increase timeout settings in the scraper code

- **Chrome Driver Issues**: If you see Chrome driver errors:
  - Ensure Chrome version matches driver version
  - Try using undetected-chromedriver for better stability

## Maintenance

- Regularly check the health of each scraper
- Monitor Supabase database for growth and potential cleanup
- Update the deployment when SRM portal changes

## Security Considerations

- Store passwords securely using environment variables
- Use HTTPS for all communications
- Regularly rotate API keys and tokens 