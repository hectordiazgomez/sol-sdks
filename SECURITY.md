# Security

Please report security issues privately to hector@buildsol.ai. Do not post API keys, audio or customer data in public issues.

The SDKs are server-side clients. Keep SOL_API_KEY out of browsers, mobile bundles, logs and repositories. For browser live transcription, create single-use tokens on your authenticated backend and send only the short-lived session to your client.

Credentials are not included in errors or telemetry. HTTP redirects are disabled. HTTPS/WSS are required for remote endpoints. Explicitly setting a custom base URL sends the API key to that endpoint, so only configure a trusted origin. Live tokens are single-use and must never be automatically reconnected.
