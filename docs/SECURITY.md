# Security

## Secrets

API keys are stored as `SecretStr` in `Settings` and never logged. Use environment variables or `.env` file.

## WebSocket

The WebSocket endpoint has no authentication. Deploy behind a reverse proxy with authentication in production.

## Emergency Stop

The emergency stop endpoint requires no authentication by default. Restrict access in production.
