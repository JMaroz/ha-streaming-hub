# Changelog

## 1.1.0

### Novità & Miglioramenti
- **Database persistente SQLite**: introdotto database locale in `/data/streaming_hub.db` per salvare metadati, trame, poster, stagioni, episodi, cronologia di riproduzione e preferiti.
- **Risoluzione Streaming HLS**:
  - Risolto il problema di buffering infinito causato dal mancato riconoscimento delle sotto-playlist Vixcloud senza estensione `.m3u8`.
  - Eliminato l'errore Uvicorn `RuntimeError: Response content longer than Content-Length` tramite corretta gestione degli header proxy decompressi.
- **Episodi Serie TV**:
  - Corretto il parsing dello slug canonico (`/it/titles/{id}-{slug}`) eliminando i ritorni 404 dai mirror.
  - Aggiunta l'estrazione immediata di `loadedSeason` (Stagione 1) dalla risposta Inertia.js.
  - Frontend con caricamento asincrono on-demand delle puntate (`activateSeason`).
- **Player & Schermo Intero**:
  - Aggiunto pulsante Fullscreen dedicato nell'header del player.
  - Supporto per il doppio click sul video per entrare/uscire dallo schermo intero.
  - Supporto HTML5 Fullscreen API reale per uscire dai limiti dell'iframe di Home Assistant Ingress.
