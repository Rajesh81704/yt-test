# Instagram Downloader Improvements

## Changes Made

### 1. **iPhone Safari Emulation** (Like YouTube)
- Added iPhone user agent: `Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1...)`
- Added full browser headers (Accept, Accept-Language, DNT, Sec-Fetch-*)
- Instagram is less aggressive with mobile browsers

### 2. **Multiple API Fallbacks**
```python
"extractor_args": {
    "instagram": {
        "api": ["graphql", "mobile", "web"]
    }
}
```
Tries GraphQL API → Mobile API → Web API in sequence

### 3. **Cookie Support**
- Auto-detects cookies from Firefox browser
- Falls back to `app/api/cookies.txt` file
- Logs which cookie source is being used

### 4. **Retry Logic with Embed URL**
- First tries the original URL
- If that fails, tries the embed version (`/p/{ID}/embed/`)
- Embed URLs sometimes bypass restrictions

### 5. **Better Error Messages**
Now provides specific guidance:
- Private account detection
- Deleted post detection
- Cookie expiration hints
- Rate limiting detection

## How It Works

1. **Request comes in** → Normalize Instagram URL
2. **Build options** → iPhone Safari headers + cookies + API fallbacks
3. **First attempt** → Try original URL with all settings
4. **Retry if failed** → Try embed URL
5. **Clear error** → Provide actionable error message if both fail

## Comparison with YouTube Implementation

| Feature | YouTube | Instagram (Updated) |
|---------|---------|-------------------|
| User Agent | Android Mobile | iPhone Safari |
| Player Client | `android_vr`, `web_safari` | N/A |
| API Fallbacks | Yes | Yes (graphql, mobile, web) |
| Cookies | File-based | Browser + File |
| Retry Logic | Proxy rotation | URL transformation |
| iPhone Emulation | ✅ | ✅ |

## Testing

Restart your server and try the Instagram endpoint again. The logs will now show:
```
[instagram] Using cookies from Firefox with iPhone Safari emulation
[instagram] Attempting to extract from: {url}
[instagram] Successfully extracted {n} formats
```

Or if it fails:
```
[instagram] First attempt failed: {error}
[instagram] Retrying with embed URL: {embed_url}
```

## Known Limitations

Instagram is actively fighting automation tools. Even with these improvements:
- Private posts from accounts you don't follow will fail
- Deleted posts will fail
- Instagram may still block requests during high-traffic times
- Some posts may require fresh cookies (re-login to Firefox)
