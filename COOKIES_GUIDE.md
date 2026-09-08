# Instagram Cookies Setup Guide

Instagram now requires authentication (cookies) to download some posts. Follow these steps:

## Option 1: Export Cookies from Browser (Recommended)

### Using Browser Extension:
1. Install a cookie extension:
   - **Chrome/Edge**: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
   - **Firefox**: [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

2. Go to Instagram.com and log in to your account

3. Click the extension icon and export cookies for instagram.com

4. Save the exported file as one of these locations:
   - `/home/rajeshh/Desktop/yt-downloader/app/api/cookies.txt`
   - OR `~/cookies.txt` (your home directory)

### Using yt-dlp directly:
```bash
# Export cookies from your browser automatically
./venv/bin/yt-dlp --cookies-from-browser firefox --cookies cookies.txt https://www.instagram.com/

# Or for Chrome:
./venv/bin/yt-dlp --cookies-from-browser chrome --cookies cookies.txt https://www.instagram.com/
```

## Option 2: Manual Cookie Export

1. Log in to Instagram in your browser
2. Open Developer Tools (F12)
3. Go to Application/Storage → Cookies → https://www.instagram.com
4. Export all cookies to a Netscape format cookies.txt file

## Cookie File Location

The app will automatically look for cookies in:
1. `/home/rajeshh/Desktop/yt-downloader/app/api/cookies.txt` (project directory)
2. `~/cookies.txt` (home directory)

## Verify It Works

After adding cookies, restart your API server and try the Instagram download again.

## Security Note

⚠️ **Keep your cookies.txt file private!** It contains your Instagram session. Add it to .gitignore:

```bash
echo "cookies.txt" >> .gitignore
echo "app/api/cookies.txt" >> .gitignore
```

## Troubleshooting

- If downloads still fail, regenerate your cookies (they expire)
- Make sure the cookies.txt file is in Netscape format
- Check that the file size is > 100 bytes (not empty)
