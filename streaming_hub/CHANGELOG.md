# Changelog

## 1.2.3

### Bug Fixes & Resilience Improvements
- **Cast Mini-Player & UI Bar Crash Resolution**:
  - Fixed a `TypeError` in the frontend caused by accessing `state.selectedItem` after `closeModal()` had set it to `null`.
  - Caches title metadata (`poster_url`, `isTv`, `season`, `episode`, `seek_seconds`) before initiating playback, ensuring the Cast Control Bar appears reliably every time casting begins.
- **User-Friendly Device Names & Clean Notifications**:
  - Replaced technical entity identifiers (such as `media_player.tpm191e`) in toast alerts and device selectors with formatted friendly names (e.g. `Philips Smart TV (TPM191E)`).
  - Toast notifications updated to friendly messages: `Avvio riproduzione su <Dispositivo>...` and `In riproduzione su <Dispositivo>!`.
- **Genre Catalog Search & Cross-Catalog Merging**:
  - Implemented `get_movies_by_genre` on `CB01Client` and `get_by_genre` on `StreamingCommunityClient`.
  - Added SQLite title cache lookup (`get_titles_by_genre`) to merge locally stored titles with live scraper results for fast, reliable genre browsing for both movies and TV series.
- **Mobile App Background/Standby Recovery**:
  - Added lifecycle listeners (`visibilitychange`, `pageshow`, and `focus`) to detect when the Home Assistant Mobile App or browser tab wakes up from standby.
  - Automatically resets stuck loading states, reloads players, refreshes "Continue Watching", and reconnects active Cast playback tracking.
- **Cast Session Startup Grace Period**:
  - Extended TV receiver startup tolerance in backend Cast tracker to avoid premature session cancellation while TV apps boot.

## 1.2.2

### Nuova Funzionalità: Barra di Controllo e Riproduzione Cast (Mini-Player)
- **Barra di Riproduzione Cast Persistente a Fondo Schermo**:
  - Quando si avvia la riproduzione su un dispositivo Cast (Smart TV, Chromecast, Android TV), la scheda dei dettagli si chiude e compare immediatamente in basso una barra di controllo interattiva e fluttuante in stile Spotify/Netflix.
  - **Dati Media & Info Dispositivo**: Visualizzazione della miniatura/poster, titolo, badge episodio (es. `S3:E3`), nome del dispositivo TV ricevitore e stato real-time con dot animato (`In riproduzione`, `In pausa`, `Caricamento...`).
  - **Barra di Avanzamento & Seek Interattivo**: Barra temporale con minutaggio trascorso e durata totale (`mm:ss / mm:ss`), slider di seek scorrevole per avanzare o riavvolgere il flusso sulla TV in tempo reale.
  - **Pulsanti di Controllo Remoto**:
    - Tasto rapido **⏪ -10s** (indietro di 10 secondi)
    - Tasto centrale **⏯ Play / Pausa**
    - Tasto rapido **⏩ +30s** (avanti di 30 secondi)
    - Cursore e pulsante di gestione **Volume & Mute**
    - Pulsante **⏹ Stop** per interrompere immediatamente il casting sulla TV e rilasciare la sessione.
  - **Sincronizzazione Real-Time & Ripristino Sessione**:
    - Polling continuo con Home Assistant per allineare posizione e stato di riproduzione.
    - Se l'utente ricarica la pagina o riapre l'app mentre il Cast è in corso, la barra ricompare automaticamente ripristinando lo stato corrente.
    - Chiusura automatica della barra e aggiornamento della riga "Continua a guardare" quando la riproduzione giunge al termine o la TV entra in standby.

## 1.2.1

### Interfaccia & Pulizia UI
- **Rimozione Pulsanti Ridondanti dalla Navbar**:
  - Rimossi il pulsante `⚙ Sorgenti` e il badge `🟢 HA Connesso` dalla barra di navigazione in alto.
  - La configurazione delle sorgenti personalizzate (`custom_sources`), DNS, TMDb e porte è demandata interamente alla scheda nativa **Configurazione** dell'add-on in Home Assistant, eliminando duplicazioni e modali non necessarie dal frontend.
  - Ottimizzato lo spazio della barra di ricerca e la pulizia visiva complessiva su desktop e dispositivi mobili.

## 1.2.0

### Novità & Funzionalità
- **Sezione "Continua a Guardare" (Home Shelf)**:
  - Nuova sezione orizzontale in cima alla home page per film e serie TV interrotte.
  - Barra di avanzamento grafica al fondo della locandina, minutaggio rimanente e badge dinamico puntata (es. `S3:E3`).
  - Pulsante rapido di eliminazione `✕` per rimuovere un contenuto dalla cronologia.
- **Ripresa Intelligente Serie TV**:
  - Quando si apre una serie TV interrotta, l'app seleziona e apre automaticamente la stagione e la puntata corretta (es. Stagione 3, Episodio 3).
  - Tasto dinamico: **▶ Riprendi da mm:ss** per riprendere istantaneamente dal secondo esatto, con pulsante secondario **↺ Dall'inizio** per ripartire da zero.
  - Logica **Prossimo Episodio**: se un episodio è stato visto per oltre il 90%, la card continua a guardare propone automaticamente la puntata successiva (es. `Prossimo: S3:E4`).
- **Sincronizzazione Riproduzione Cast**:
  - Introdotto `CastTracker` in background su Home Assistant che interroga periodicamente l'entità TV (`media_position`, `media_duration`, `state`) salvando l'avanzamento su database SQLite anche a browser chiuso.
  - Supporto al comando di `media_seek` automatico all'avvio del Cast quando si riprende un contenuto interrotto.
- **Perfezionamento & Salvataggio TheMovieDB (TMDb)**:
  - Risolto il mancato salvataggio degli identificativi `tmdb_id` e `imdb_id` nel database.
  - Assegnazione prioritaria a locandine e sfondi ufficiali HD di TMDb rispetto ai thumbnail compressi dei siti di streaming.
  - Arricchimento puntate TV: interrogate le API TMDb per stagione per assegnare i titoli italiani effettivi, trame e still image per ogni singolo episodio.
  - Stato di configurazione TMDb esposto in `/api/status` e nelle impostazioni.

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
