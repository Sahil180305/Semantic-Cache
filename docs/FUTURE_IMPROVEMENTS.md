# Future Improvements

## Security & Authentication
- **Analytics Dashboards/APIs**: Ensure API keys/tokens are required for public analytics endpoints (`/api/v1/metrics/*` and `/ws/realtime`). Currently, they fetch without authentication.

## Architecture
- Consider storing real-time historical data utilizing the TimescaleDB extension properly in production.
- Refine clustering parameters for semantic insights based on real user workloads.
