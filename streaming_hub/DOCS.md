# Home Assistant App: Streaming Hub

**Streaming Hub** è un'applicazione multimediale neutrale per Home Assistant (Add-on / App) che permette di aggregare e deserializzare cataloghi multimediali personalizzati inseriti dall'utente, guardarli direttamente dalla barra laterale di Home Assistant (tramite Ingress) oppure trasmetterli con un click a qualsiasi dispositivo **Google Cast**, **Android TV** o **Smart TV** presente nella rete locale.

> [!NOTE]
> **Architettura BYOS (Bring Your Own Sources)**: Streaming Hub non ospita, non distribuisce e non include alcun link, mirror o flusso multimediale predefinito. L'utente ha la piena facoltà e responsabilità di configurare i propri indirizzi web personali tramite le impostazioni dell'Add-on.

---

## Caratteristiche Principali

- **Architettura BYOS & Auto-Discriminazione**: Inserisci i tuoi indirizzi web; Streaming Hub identifica automaticamente il motore compatibile (es. StreamingCommunity, CB01 o motori personalizzati) analizzando il markup HTML e i tag fingerprint.
- **Interfaccia Ingress Moderna**: UI reattiva in stile streaming (dark mode, locandine HD, trame, filtro per genere e ricerca istantanea).
- **Player HLS Integrato**: Riproduzione fluida direttamente nel browser o nell'app mobile Home Assistant senza plugin aggiuntivi.
- **Supporto Google Cast & Smart TV**: Integrazione diretta con le entità `media_player` di Home Assistant tramite `SUPERVISOR_TOKEN`.
- **HLS Stream Proxy & Remuxing**: Riscrittura automatica delle playlist M3U8 e gestione trasparente di intestazioni (`Referer`, `Origin`, `User-Agent`) per consentire la riproduzione anche sui dispositivi che non supportano header personalizzati.
- **Risoluzione DoH (DNS-over-HTTPS)**: Supporto opzionale a Cloudflare, Google e Quad9 per garantire la corretta risoluzione DNS.
- **Arricchimento Metadati**: Integrazione con TMDb (e fallback pubblico Cinemeta/TVmaze) per sinossi accurate, locandine e sfondi in alta definizione.

---

## Installazione

1. Aggiungi questo repository all'App Store di Home Assistant:
   - Apri Home Assistant e vai su **Impostazioni** -> **Componenti aggiuntivi (App)** -> **App Store**.
   - Clicca sul menu a tre puntini in alto a destra e seleziona **Repository**.
   - Inserisci l'URL del repository: `https://github.com/JMaroz/ha-streaming-hub` e clicca **Aggiungi**.
2. Trova e clicca su **Streaming Hub** nella lista.
3. Clicca **Installa**.
4. Apri la scheda **Configurazione** dell'Add-on per inserire gli URL delle tue sorgenti (vedi sezione successiva).
5. Clicca su **Avvia** e attiva l'opzione **Mostra nella barra laterale**.
6. Clicca su **Streaming Hub** nella barra laterale per aprire l'interfaccia.

---

## Configurazione

Esempio di configurazione nelle impostazioni dell'Add-on:

```yaml
log_level: info
custom_sources:
  - url: "https://tuo-indirizzo-sorgente.esempio"
    type: "auto"
custom_dns: cloudflare
tmdb_api_key: ""
stream_port: 8099
```

### Opzioni

| Opzione | Tipo | Predefinito | Descrizione |
|---|---|---|---|
| `log_level` | list | `info` | Livello di log dell'app (`trace`, `debug`, `info`, `warning`, `error`). |
| `custom_sources` | list | `[]` | Elenco di oggetti o URL delle sorgenti web personali. Il tipo può essere `auto`, `streamingcommunity` o `cb01`. |
| `custom_dns` | list | `cloudflare` | Provider DNS-over-HTTPS (`cloudflare`, `google`, `quad9`, `system`). |
| `tmdb_api_key` | string | `""` | Chiave API TMDb opzionale per locandine e dettagli arricchiti. |
| `stream_port` | port | `8099` | Porta HTTP del proxy HLS per la rete locale. |

---

## Come Usare il Cast

1. Clicca sul titolo di un film o di una serie TV per aprire la scheda di dettaglio.
2. In basso, seleziona il dispositivo di destinazione dal menu a tendina:
   - **Local Web Player**: riproduce il contenuto direttamente nel browser/app HA.
   - **Dispositivo Cast (es. TV Salotto, Chromecast Cucina)**: trasmette il flusso proxato al dispositivo fisico.
3. Clicca su **Riproduci**: Home Assistant invierà il comando di riproduzione al dispositivo sulla rete locale.
