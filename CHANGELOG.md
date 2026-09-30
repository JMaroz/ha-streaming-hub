# Changelog

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
