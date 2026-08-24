# Google Cloud + Gmail OAuth Setup (from zero)

Time: ~15 minutes. Cost: free. You need any Google account.

## 1. Create the project
1. Go to <https://console.cloud.google.com/> → project dropdown → **New Project**.
2. Name it `mailsweep` (or anything) → Create → select it in the dropdown.

## 2. Enable the Gmail API
1. ☰ Menu → **APIs & Services → Library**.
2. Search **Gmail API** → open it → **Enable**.
   *Why:* without this the OAuth token will be rejected with `access_denied`.

## 3. Configure the OAuth consent screen
1. **APIs & Services → OAuth consent screen** → choose **External** → Create.
2. Fill app name (`MailSweep AI`), your email as support/dev contact.
3. Scopes step: you may leave it empty; MailSweep requests scopes dynamically.
4. **Test users** step: **Add your own Gmail address.**
   *Why:* while the app is in *Testing*, ONLY added test users can sign in.
   This is exactly what we want for development.
5. Save. (Verification by Google is only needed for 100+ users / sensitive
   production launches — irrelevant for now.)

## 4. Create the OAuth client
1. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Application type: **Web application**.
3. **Authorized redirect URIs** → add EXACTLY:
   - Development: `http://localhost:8000/api/auth/google/callback`
   - Later, add your deployed URL: `https://<your-backend>/api/auth/google/callback`
   Trailing slashes and http/https must match byte-for-byte.
4. Create. Copy the **Client ID** and **Client secret**.

## 5. Put them into `.env`

```env
GOOGLE_CLIENT_ID=1234567890-abc.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxx
```

Do **not** paste these into chat, commits, or issues. `.env` is git-ignored.

## 6. Verify

```powershell
uvicorn app.main:app --reload
# browser → http://localhost:8000/api/auth/google/login?redirect_to=/dashboard
```

You should land on Google's consent screen listing *MailSweep AI* requesting
Gmail modify access, then be redirected back to `/auth/status` JSON showing
your account. If Google shows `Error 400: redirect_uri_mismatch`, the URI in
step 4 does not match `BASE_URL` + callback path exactly.
