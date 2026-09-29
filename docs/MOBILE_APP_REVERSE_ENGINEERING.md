# Streaming Mobile App - Reverse Engineering & Architecture Analysis

## 1. Overview

This document summarizes the findings from reverse engineering the official mobile application package (branded as **Streamunity** / **DevShifters**) and compares its playback/casting mechanics with our Home Assistant Add-on (`streaming-hub-ha`).

---

## 2. Technical Stack & Core Architecture

* **Frontend Framework**: Flutter (Dart compiled AOT into `lib/arm64-v8a/libapp.so`).
* **Player Core**: `media_kit` (wrapping `libmpv.so`) alongside custom player controls (`package:player_video`).
* **Catalog & Metadata**: Direct client-side consumption of The Movie Database (TMDb) API (`https://api.themoviedb.org/3`), retrieving movie/show metadata, posters, cast, crew, and seasons without querying the streaming host for catalog data.
* **"Host Link" Architecture**: The application does not hardcode streaming mirror domains. Instead, it utilizes a user-configurable "Host Link" setting. The app dynamically couples TMDb identifiers with search/watch URLs on the active Host Link.

---

## 3. Stream Extraction Mechanism: App vs. Myth

### The "Private API" Myth
It was previously hypothesized that the mobile application called a private or proprietary REST API endpoint to retrieve direct `.m3u8` master playlists for video playback and casting.

### The Actual Implementation: Headless Android WebView (`HlsExtractor`)
Disassembly of `libapp.so` and the DEX bytecode (`classes.dex`, `classes4.dex`) revealed that **no private extraction API exists**. Instead, the app deploys an on-device headless browser crawler via a custom Android plugin:

1. **Flutter MethodChannel**:
   * Channel: `com.devshifters.hls_extractor/extractor`
   * Method: `extractFromUrl(url)` with `debugMode` option.

2. **Headless Android Activity (`HeadlessExtractionActivity`)**:
   * Spawns an invisible Android `WebView` (`headless_webview`).
   * Mutes audio playback (`AudioManager`).
   * Overrides the User-Agent to desktop Chrome:
     `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36`.
   * Loads the target title/episode streaming page or embedded iframe on the configured Host Link.

3. **Injected JavaScript Interceptor**:
   Upon page initialization (`onPageFinished` / `WebViewClient`), the following script is injected into the WebView runtime:
   ```javascript
   (function() {
       var origOpen = XMLHttpRequest.prototype.open;
       XMLHttpRequest.prototype.open = function() {
           console.log('XHR_REQUEST_URL:' + arguments[1]);
           origOpen.apply(this, arguments);
       };
       var origFetch = window.fetch;
       window.fetch = function(url, options) {
           console.log('FETCH_REQUEST_URL:' + url);
           return origFetch.apply(this, arguments);
       };
   })();
   ```

4. **Network & Console Snooping**:
   * `WebChromeClient.onConsoleMessage` filters log messages prefixed with `XHR_REQUEST_URL:` or `FETCH_REQUEST_URL:`.
   * `WebViewClient.shouldInterceptRequest` inspects network requests.
   * If a requested URL contains `.m3u8` or `playlist` (originating from upstream CDNs), the full URL along with required query tokens (`token`, `expires`, `h=1`) is captured.
   * A simulated clicker (`DebugActivity$d`) fires programmatic touch events at specified coordinates if user interaction is needed to trigger playback.
   * Once captured, the activity terminates and passes the resolved `.m3u8` URL back to Flutter.

---

## 4. Casting Mechanism

* **Protocol**: Open-source Flutter package `cast` (`package:cast/device.dart`, `package:cast/socket.dart`).
* **Implementation (`GoogleCastProvider`)**:
  * Connects over the local network to Chromecast devices via port 8009 (TLS).
  * Launches the Default Media Receiver (`CC1AD845`).
  * Sends standard Cast media commands:
    ```text
    Namespace: urn:x-cast:com.google.cast.media
    Type: LOAD
    ContentId: <extracted_m3u8_url>
    ContentType: application/x-mpegurl
    ```
* **Limitation of Direct Casting**:
  Chromecast default receivers cannot inject custom HTTP request headers (such as `Referer` required by CDNs). If CDNs enforce strict token/referer validation, direct Chromecast playback from client devices fails without an intermediary proxy.

---

## 5. Architectural Comparison with `streaming-hub-ha`

| Feature | Streamunity App (XAPK) | Streaming Hub Home Assistant Add-on |
| :--- | :--- | :--- |
| **Catalog Metadata** | TMDb API | Direct Inertia.js scraping + local SQLite caching |
| **Stream Extraction** | Headless Android WebView (`HeadlessExtractionActivity`) injecting JS | Native asynchronous Python scraping (`engine_reactive.py`) extracting `masterPlaylist` |
| **Resource Overhead** | High (full browser engine, WebViews, JS runtime) | Very Low (pure HTTP client + regex/AST parser) |
| **Cast Playback** | Direct URL to Google Cast | Managed LAN HLS Proxy (`/stream/{token}`, `/segment/{token}`) injecting headers |
| **DoH / Censorship Bypass** | System DNS or Private DNS provider | Integrated Cloudflare/Google DNS-over-HTTPS resolver |

---

## 6. Key Takeaways for Future Iterations

1. **Extraction Reliability**:
   * Our native Python extraction in [`backend/engine_reactive.py`](file:///Users/andrea/Repository/streaming-hub-ha/streaming_hub/backend/engine_reactive.py) is significantly faster than launching an invisible WebView, and it reliably yields HTTP 200 responses for playlist resolution.
   * If upstream CDNs ever change their obfuscation such that static parsing fails, an equivalent headless browser / DOM-interception approach (e.g. via Playwright or Pyppeteer) can serve as a robust fallback.

2. **Cast Proxy Robustness (`backend/proxy.py`)**:
   * Smart TVs (Philips, Android TV, Google TV) and Chromecasts frequently send HTTP `HEAD` probes before or during media segment downloads.
   * Ensure that `HEAD` responses on `/segment/{token}`:
     * Never return `Content-Type: text/html` when serving video/audio chunks (even if the CDN masks chunks as `.html`).
     * Forward the upstream `Content-Length` header on `HEAD` requests so players do not misinterpret segments as 0-byte files.
