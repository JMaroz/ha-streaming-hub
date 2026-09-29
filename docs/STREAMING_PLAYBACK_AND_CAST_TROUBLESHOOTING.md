# Streaming Playback & Google Cast Architecture & Troubleshooting Guide

## 1. Overview & Context

This document captures the technical discoveries, root cause analyses, and architectural solutions implemented to resolve playback failures in **Streaming Hub** (`streaming-hub-ha`). 

Failures were observed across two primary playback channels:
1. **Local Browser Playback (Web Player)** via Hls.js inside the Home Assistant Ingress web UI.
2. **Google Cast Playback** on Google TV, Chromecast, and Smart TV media players using ExoPlayer / Default Media Receiver.

Both failure modes exhibited distinct symptoms and network behaviors in add-on logs, ultimately stemming from upstream CDN token signature requirements and HTTP proxy header compliance.

---

## 2. Architecture: Stream Proxy & HLS Rewriter

Streaming Hub acts as an intelligent HTTP proxy and HLS playlist rewriter:
- **Upstream Sources**: Video streams are scraped and resolved from external reactive or crawler streaming engines that utilize host CDNs and third-party edge nodes.
- **Endpoint Structure**:
  - `/stream/{token}`: Fetches and rewrites master and sub-playlists (video renditions, audio languages, subtitles).
  - `/segment/{token}`: Proxies binary video/audio chunks (`.ts`, `.m4s`), subtitle tracks (`.vtt`), and decryption keys (`enc.key`).
- **Network Paths**:
  - **Local Ingress**: Proxied through Home Assistant Ingress (`/api/hassio_ingress/<token>/...`).
  - **LAN Cast**: Direct LAN IP and port (`http://<ha-host>:8099/stream/<token>`), accessible to local network devices without Ingress authentication cookies.

---

## 3. Investigation & Root Cause Analysis

### Issue A: Local Web Player 403 Forbidden Error

#### Symptoms
In the Home Assistant web interface, clicking "Guarda nel Browser" immediately showed `Errore di riproduzione video HLS` or `Impossibile avviare il video`. The log captured:
```text
INFO: 172.30.32.2:46812 - "POST /api/resolve HTTP/1.1" 200 OK
INFO: 172.30.32.2:57390 - "GET /stream/Ae2lEr6TsJM_zy1xAl2usQ HTTP/1.1" 403 Forbidden
```

#### Technical Root Cause
1. **Frontend Payload Misconfiguration**:
   In `streaming_hub/frontend/js/app.js`, `playInBrowser()` explicitly passed `prefer_fhd: false`, accompanied by the comment:
   ```javascript
   prefer_fhd: false, // 720p HD with embedded audio track for robust browser playback
   ```
2. **Upstream Token Signature Invalidation**:
   On reactive SPA player engines, when media assets support Full HD (`window.canPlayFHD = true`), the upstream token and expires timestamps generated in the player iframe are cryptographically bound to the query parameter `h=1`.
3. **Master Playlist vs. Rendition Misconception**:
   Omitting `h=1` was assumed to select a lower rendition (720p). In reality, the master playlist URL on upstream CDNs is **not** a rendition selector; it is the playlist-of-playlists containing all variant streams (1080p, 720p, 480p, audio tracks).
4. When `prefer_fhd` was `false`, `h=1` was omitted from the playlist request. The upstream server rejected the request with `HTTP 403 Forbidden`, causing `proxy.py` to forward 403 to the browser.

---

### Issue B: Google Cast / ExoPlayer Segment Probing & Idle Failure

#### Symptoms
Casting to `media_player.google_tv` (or Philips Smart TV `media_player.tpm191e`) initialized the Cast receiver and downloaded the master and media playlists. However, after requesting initial segments, the device unexpectedly switched audio/video tracks, stopped downloading, and went into `idle` state without playing any media:
```text
GET /stream/O1YkOSfEm3vQ3oLnkfRk_g HTTP/1.1 200 OK
GET /stream/O1YkOSfEm3vQ3oLnkfRk_g?url=...video...rendition=720p HTTP/1.1 200 OK
GET /stream/O1YkOSfEm3vQ3oLnkfRk_g?url=...audio...rendition=ita HTTP/1.1 200 OK
HEAD /segment/O1YkOSfEm3vQ3oLnkfRk_g?url=.../audio/ita/0000-0181.html HTTP/1.1 200 OK
GET /segment/O1YkOSfEm3vQ3oLnkfRk_g?url=.../video/720p/0000-0876.html HTTP/1.1 200 OK
GET /segment/O1YkOSfEm3vQ3oLnkfRk_g?url=https://upstream-cdn/storage/enc.key HTTP/1.1 200 OK
HEAD /segment/O1YkOSfEm3vQ3oLnkfRk_g?url=.../video/720p/0000-0876.html HTTP/1.1 200 OK
GET /stream/...video...rendition=480p HTTP/1.1 200 OK
GET /stream/...audio...rendition=eng HTTP/1.1 200 OK
HEAD /segment/...audio/eng/0000-0180.html HTTP/1.1 200 OK
HEAD /segment/...video/480p/0000-0438.html HTTP/1.1 200 OK
Cast device media_player.google_tv is idle, stopping tracker.
```

#### Technical Root Cause
1. **ExoPlayer HEAD Probing Protocol**:
   ExoPlayer (the underlying media playback engine in Google Cast receiver applications and Android TV) issues HTTP `HEAD` requests on media segments before feeding them to its demuxing pipeline. It verifies two essential attributes:
   - The media container format via `Content-Type`.
   - The chunk boundary/size via `Content-Length`.
2. **`Content-Length: 0` on HEAD Responses**:
   In `streaming_hub/backend/proxy.py`, `get_segment_response` handled `HEAD` by returning an empty `Response(status_code=status_code, headers=out_headers)`. Because `Content-Length` was omitted from `out_headers`, Starlette's response handler measured `len(self.body) == 0` and automatically injected `Content-Length: 0`.
   ExoPlayer interpreted all chunks as zero bytes and flagged the streams as corrupted.
3. **MIME Masking by Upstream CDNs (`text/html`)**:
   Upstream CDNs frequently mask MPEG-TS chunks by appending `.html` (e.g. `0000-0876.html`) and serving them with `Content-Type: text/html`.
   While `proxy.py` previously corrected `Content-Type` for `GET` responses, for `HEAD` responses it returned immediately before the correction block, sending `Content-Type: text/html`. ExoPlayer rejected the chunk as non-media.
4. **AES-128 Encryption Key Misclassification**:
   When ExoPlayer downloaded the decryption key (`enc.key`), the proxy treated it as a media segment and assigned `Content-Type: video/MP2T` instead of `application/octet-stream`.
5. **Fallback Cascade**:
   When 720p video and Italian audio failed format and length probing, ExoPlayer fell back to English audio and 480p video. When those also failed HEAD probing, playback was aborted.

---

## 4. Implemented Solutions

### 1. Enforcing Master Playlist Authorization (`h=1`)
- **Frontend (`streaming_hub/frontend/js/app.js`)**:
  Updated `playInBrowser()` to set `prefer_fhd: true`. Modern desktop and mobile browsers running Hls.js handle multi-rendition HLS streams and separate audio demuxing natively.
- **Backend Reactive Engine (`streaming_hub/backend/engine_reactive.py`)**:
  Modified `build_master_playlist_url()` and the fallback regex extractor to unconditionally inject `params["h"] = "1"` whenever `can_play_fhd` is detected. This prevents upstream 403 Forbidden errors across all clients.

### 2. Comprehensive Media & Header Classification in `proxy.py`
In `streaming_hub/backend/proxy.py`, `get_segment_response()` was refactored:

```python
# Classify content type according to segment format
if lower_url.endswith(".key") or "/enc.key" in lower_url or ".key?" in lower_url:
    content_type = "application/octet-stream"
elif lower_url.endswith(".vtt") or ".vtt?" in lower_url or "subs-" in lower_url:
    content_type = "text/vtt"
elif ".m4s" in lower_url or ".mp4" in lower_url:
    content_type = "video/mp4"
elif raw_content_type.lower().startswith("text/") or not raw_content_type:
    # CDN disguised media chunk (e.g. video/audio chunk disguised as .html)
    content_type = "video/MP2T"
else:
    content_type = raw_content_type
```

### 3. Accurate HEAD Response Propagation
For `HEAD` requests:
- Forward upstream `Content-Length` so media players receive the actual byte size.
- Send the sanitized `Content-Type` (`video/MP2T`, `video/mp4`, `application/octet-stream`).

```python
if method.upper() == "HEAD":
    upstream_resp.close()
    if "Content-Length" in upstream_resp.headers:
        out_headers["Content-Length"] = upstream_resp.headers["Content-Length"]
    return Response(
        status_code=status_code,
        headers=out_headers,
        media_type=content_type,
    )
```

### 4. Subtitle Playlist Delegation in `rewrite_m3u8`
Extended the playlist detection regex and routing in `rewrite_m3u8` and `get_segment_response` to include `type=subtitle` and `type=subtitles`, preventing subtitle playlists from being prematurely handled as binary chunks.

---

## 5. Verification Matrix

| Playback Target | Stream Type | Probing Method | Result |
| :--- | :--- | :--- | :--- |
| **Web Player (Hls.js)** | HLS Master Playlist | GET `/stream/<token>` | `200 OK` (Authorized with `h=1`) |
| **Web Player (Hls.js)** | AES-128 Key (`enc.key`) | GET `/segment/<token>` | `200 OK` (`application/octet-stream`, 16 bytes) |
| **Web Player (Hls.js)** | Subtitles (`.vtt`) | GET `/segment/<token>` | `200 OK` (`text/vtt`) |
| **Google Cast (ExoPlayer)** | Video/Audio Chunks (`.html`) | HEAD `/segment/<token>` | `200 OK` (`video/MP2T`, length > 0) |
| **Google Cast (ExoPlayer)** | Video/Audio Chunks (`.html`) | GET `/segment/<token>` | `200 OK` (`video/MP2T`, streaming bytes) |
| **Google Cast (ExoPlayer)** | Decryption Key (`enc.key`) | GET `/segment/<token>` | `200 OK` (`application/octet-stream`) |

---

## 6. Future References & Architectural Guidelines

1. **Never suppress `h=1` on token-signed streams**: Omitting `h=1` breaks the token signature on any asset flagged with `canPlayFHD`.
2. **Preserve upstream Content-Length on HEAD**: Never let ASGI/Starlette default `Content-Length` to 0 on probing requests.
3. **Respect content typing**: Cryptographic keys (`.key`) and subtitle files (`.vtt`) must never be defaulted to `video/MP2T`.

---

## 7. Playback Debugger Script

A standalone Python CLI tool (`script/debug_playback`) has been added to diagnose stream extraction and playback issues locally, without needing to run the full Home Assistant Add-on. 

### Features
* **DNS & Reachability**: Verifies if the target URL and CDN are reachable or blocked.
* **Stream Resolution & Token Extraction**: Validates whether the parser can successfully locate the player `masterPlaylist` and its corresponding tokens (e.g., `h=1`, `expires`).
* **Probe Simulation**: Simulates the exact `GET` and `HEAD` requests performed by ExoPlayer (Google Cast) for master playlists, segment playlists, and AES decryption keys.
* **Known Errors Knowledge-base**: Automatically flags known failure causes (e.g., missing `Referer`, CORS blocks, expired tokens).

### Usage
From the root of the repository, execute:
```bash
uv run ./script/debug_playback <URL_OR_ID>
```

### Tracing Errors in Home Assistant
When running inside Home Assistant, all standard `logging` output from the proxy and extraction components (`backend/proxy.py`, `backend/engine_reactive.py`) is forwarded to the Supervisor. You can monitor stream extraction failures directly from **Settings > Add-ons > Streaming Hub > Logs**. The debugger script's methodology has been natively integrated into these components, meaning any known issues (e.g. expired tokens, CORS blocks, missing Referers on Cast) will generate a clear, localized diagnostic `[ERROR]` entry in your Home Assistant logs.
