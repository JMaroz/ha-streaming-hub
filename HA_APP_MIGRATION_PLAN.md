# Piano Architetturale: Home Assistant App "Streaming Hub"

Riferimento completo del piano per lo sviluppo del nuovo repository App (Add-on) per Home Assistant.

## Repository di partenza consigliati (Template GitHub)
- **[home-assistant/addons-example](https://github.com/home-assistant/addons-example)**: Template ufficiale di riferimento documentato da Home Assistant Core/Supervisor team.
- **[hassio-addons/addon-example](https://github.com/hassio-addons/addon-example)**: Template del team Home Assistant Community Add-ons con workflow CI/CD completi e build multi-arch.

---

## Sintesi Obiettivi dell'App
1. **Repository Standalone**: Dedicato all'App Store di Home Assistant (separato dall'attuale custom integration HACS).
2. **Container Docker con Ingress**: Web UI moderna in sidebar (griglia film/serie, ricerca, player video HLS, gestione captcha).
3. **Stream Proxy & FFmpeg**: Gestione isolata di DoH, VixCloud/StreamingCommunity, riscrittura HLS e streaming verso LAN.
4. **Cast Support**: Connessione con Home Assistant API via `SUPERVISOR_TOKEN` (`POST /core/api/services/media_player/play_media`) per pilotare Chromecast e Smart TV con `host_network: true` o porta 8099 esposta sulla LAN.
