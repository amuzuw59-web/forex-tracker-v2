# Forex Signal Tracker

A Python Flask API for forex market data and technical signal analysis.

## Features
- XAUUSD market analysis
- EMA, RSI, and ATR indicators
- MetaApi market-data integration
- Flask API with a health endpoint
- Risk calculations and signal tracking

## Trading Safety
- Automatic trading is disabled by default.
- Order submission is disabled by default.
- Demo-account verification is required.
- Manual confirmation is required.

## Installation

Activate your virtual environment:

    source .venv/bin/activate

Install dependencies:

    pip install -r requirements.txt

## Environment Variables

Configure these variables locally in your .env file:

    METAAPI_TOKEN=your_metaapi_token
    METAAPI_ACCOUNT_ID=your_metaapi_account_id

For Google sign-in on the Render deployment, configure these environment variables in
Render (never commit their values):

    GOOGLE_CLIENT_ID
    GOOGLE_CLIENT_SECRET
    SESSION_SECRET
    AUTH_COOKIE_SECURE=true

Register this exact HTTPS redirect URI in Google Cloud Console:

    https://forex-tracker-v2.onrender.com/auth/google/callback

Never commit your actual credentials.

## Run Locally

    python -m backend.api

The local API normally listens on http://127.0.0.1:8080.

## API Endpoints

- GET / — Service information
- GET /health — Health check
- GET /login — Google sign-in page
- GET /auth/google — Start Google OpenID Connect
- GET /auth/google/callback — Google OAuth callback
- GET /auth/logout — Clear the authenticated session
- GET /dashboard — Protected read-only dashboard
- GET /api/me — Protected current-user session check
- GET /api/signal — Generate a market signal
- POST /api/demo/execute — Safety-gated demo execution

Market-data errors or stale candles may result in HTTP 503.

## Tests

Run:

    python -m unittest discover -s tests -v

## Render Deployment

The render.yaml file configures Gunicorn.

Set METAAPI_TOKEN and METAAPI_ACCOUNT_ID in Render's environment settings.
Do not put real credentials in render.yaml.

After deployment, test /health and /api/signal separately.
A healthy API does not guarantee that market data is fresh.

## Frontend Integration

Configure the frontend's API base URL to point to the deployed backend.
For Vite projects, VITE_API_BASE_URL is a common convention.

## Limitations

Passing tests does not guarantee current market data or profitable trades.
Keep automatic trading and order submission disabled during deployment and testing.
