# Changelog

## 1.1.2

### Novità & Correzioni
- **Pulizia Dispositivi Cast & Rimozione Telecomandi TV**:
  - Filtraggio rigoroso delle entità `media_player`: rimosse tutte le entità di solo controllo remoto / telecomando TV (es. `philips_tv`, entità ambilight o CEC puro) che non supportano lo streaming video e generavano errori 500.
  - Vengono mantenuti unicamente i veri ricevitori di streaming e display abilitati (Google Cast, Chromecast, chassis TV Android/TPM, Shield, FireTV, AppleTV, Kodi, Roku).
  - Deduplicazione automatica per nome del dispositivo: se la TV espone più entità, viene selezionata automaticamente l'entità chassis Cast effettiva (`tpm191e`, `cast`).
  - Rimossa la confusione tra entità duplicate `(on)` e `(off)`: l'interfaccia mostra un unico selettore pulito con indicazione `(Standby)` per i dispositivi spenti, pronti ad essere svegliati dal comando Cast.

## 1.1.1

### Novità & Correzioni
- **Riproduzione Episodio Esatto**:
  - Risolto il bug per cui veniva riprodotto sempre l'episodio 1x01 invece di quello selezionato (es. 3x03): ora le sorgenti puntano direttamente all'iframe dell'episodio senza essere dirottate al default Inertia.
  - Nel frontend la selezione della sorgente e l'avvio del Play/Cast per le serie TV prendono categoricamente l'episodio attualmente selezionato.
  - Il pulsante Play e il comando Cast mostrano ora esplicitamente il numero di stagione ed episodio (es. `S3E3`).
- **Supporto Cast & Dispositivi HDMI/TV**:
  - Classificazione chiara nel selettore dispositivi tra `[Google Cast]` (ricevitore Cast abilitato allo streaming) e `[Controllo TV]` (telecomando HDMI).
  - Timeout di connessione esteso a 25s per consentire alle TV in standby (`off`) di accendersi e avviare il ricevitore Cast senza falsi errori 500.
  - Fallback automatico intelligente: se viene selezionata l'entità TV che non supporta lo streaming, il comando viene automaticamente girato al companion Cast receiver (es. `tpm191e`).
- **Supporto Metodo HTTP HEAD**:
  - Aggiunto supporto a richieste HTTP `HEAD` sulle rotte `/stream/{token}` e `/segment/{token}` richieste dai probe delle Smart TV (risolvendo gli errori `405 Method Not Allowed`).

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
