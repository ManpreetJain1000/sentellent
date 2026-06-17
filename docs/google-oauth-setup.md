# Google OAuth setup (local dev)

If you see **Error 400: redirect_uri_mismatch**, the redirect URI your backend sends does not exactly match one registered in Google Cloud Console.

## Values this app uses (local)

| Setting | Value |
|--------|--------|
| **Authorized redirect URI** | `http://localhost:8000/api/v1/auth/google/callback` |
| **Authorized JavaScript origins** | `http://localhost:5173` |
| **Backend env** | `GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback` |

The redirect URI must match **character for character** (scheme, host, port, path). `localhost` and `127.0.0.1` are different to Google.

## Steps in Google Cloud Console

1. Open [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials).
2. Select your **OAuth 2.0 Client ID** (type must be **Web application**).
3. Under **Authorized redirect URIs**, click **Add URI** and paste:
   ```
   http://localhost:8000/api/v1/auth/google/callback
   ```
4. Under **Authorized JavaScript origins**, add:
   ```
   http://localhost:5173
   ```
5. Click **Save**. Changes can take a few minutes to propagate.
6. Restart the backend after changing `.env`:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

## Enable Gmail and Calendar APIs

Phase 2 requires Gmail and Calendar access for the agent tools.

1. Open [Google Cloud Console → APIs & Services → Library](https://console.cloud.google.com/apis/library).
2. Enable **Gmail API** and **Google Calendar API** for your project.
3. Ensure OAuth scopes in `backend/.env` include:
   ```
   openid email profile https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar
   ```
4. After changing scopes, users must **sign in again** so Google grants the new permissions.

## Fix `calendar_api_error` (403)

If chat returns **Unable to access Google Calendar** with status `403`, check these in order:

1. **Enable Google Calendar API**  
   [APIs & Services → Library](https://console.cloud.google.com/apis/library) → search **Google Calendar API** → **Enable**.

2. **Add Calendar scope to OAuth consent screen**  
   [OAuth consent screen → Scopes](https://console.cloud.google.com/apis/credentials/consent) → **Add or remove scopes** → add `.../auth/calendar` (See, edit, share, and permanently delete all calendars).

3. **Reconnect your Google account** (required after scope changes)  
   - Log out in the app, or open: `http://localhost:8000/api/v1/auth/google/reconnect`  
   - Approve **Calendar** on the Google consent screen (not just Gmail).

4. **Verify granted scopes**  
   `GET /api/v1/auth/workspace` should show:
   - `has_calendar_access: true`
   - `has_calendar_write_access: true`

If you signed in before Calendar was added, your stored token only has Gmail scopes — reconnecting fixes this.

## OAuth consent screen (Testing mode)

If the app is in **Testing**, only listed test users can sign in. Add:

- Your Google account (e.g. the email you use to sign in)
- `harisankar@sentellent.com` (required for Sentellent review)

Path: **APIs & Services → OAuth consent screen → Test users → Add users**.

## Verify

Open in the browser (should redirect to Google sign-in, not an error):

```
http://localhost:8000/api/v1/auth/google/start
```

## Production (later)

When deployed, add the production callback URL to the same OAuth client, for example:

```
https://<your-api-domain>/api/v1/auth/google/callback
```

Set `GOOGLE_OAUTH_REDIRECT_URI` and `FRONTEND_URL` in the backend environment to match production URLs.
