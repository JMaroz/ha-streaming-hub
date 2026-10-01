# Changelog

## [2.3.0](https://github.com/JMaroz/streaming-hub-ha/compare/v2.2.1...v2.3.0) (2026-10-01)


### Features

* **player:** add smart subtitles, auto-next episode, failover and HA cinema events ([a1fad86](https://github.com/JMaroz/streaming-hub-ha/commit/a1fad8690f4a9a5b0a76044e491b496913c9f677))


### Bug Fixes

* **history:** restore watch progress tracking and continue watching shelf ([58cb3ea](https://github.com/JMaroz/streaming-hub-ha/commit/58cb3ea542db3cf91f66144d3ffe0ae8f107307e))

## [2.2.1](https://github.com/JMaroz/streaming-hub-ha/compare/v2.2.0...v2.2.1) (2026-09-30)


### Bug Fixes

* **rating:** prevent adult content leakage in kids profiles ([76c8fd5](https://github.com/JMaroz/streaming-hub-ha/commit/76c8fd52dded3fcd2e01e03e9017c95cb34e910a))

## [2.2.0](https://github.com/JMaroz/streaming-hub-ha/compare/v2.1.0...v2.2.0) (2026-09-30)


### Features

* **settings:** add TMDb API key validation and watch providers cache re-enrichment ([26f4a7d](https://github.com/JMaroz/streaming-hub-ha/commit/26f4a7d4dfdc70cc01fc714e84c27127c1b7097e))

## [2.1.0](https://github.com/JMaroz/streaming-hub-ha/compare/v2.0.0...v2.1.0) (2026-09-30)


### Features

* **streaming:** add geolocated streaming availability and overhaul content badges ([fdab78c](https://github.com/JMaroz/streaming-hub-ha/commit/fdab78c3f03172a77645ef8da029871f95aa9bac))

## [2.0.0](https://github.com/JMaroz/streaming-hub-ha/releases/tag/v2.0.0) (2026-09-29)

### Features & Refactoring

* **core:** introduce generic reactive and crawler streaming engines with automatic heuristic detection
* **db:** migrate SQLite models to generic source attributes with non-destructive fallback
* **proxy:** optimize HLS stream proxy with accurate HEAD probe lengths and MIME classification
* **cast:** full Google Cast and ExoPlayer compatibility with interactive floating control bar
* **profile:** multi-profile family accounts, strict PEGI ratings, and Trakt.tv synchronization
* **tools:** standalone playback debugger CLI script and comprehensive troubleshooting guides
