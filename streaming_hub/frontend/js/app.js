/**
 * Streaming Hub - Frontend Application Logic
 */

(function () {
  "use strict";

  // Application State
  const state = {
    activeProfileId: localStorage.getItem("streaming_hub_active_profile_id") || "default",
    profiles: [],
    favoritesSet: new Set(),
    activeType: "all",
    activeGenre: null,
    activeSource: "all",
    availableSources: [],
    searchQuery: "",
    catalogItems: [],
    selectedItem: null,
    selectedSeason: 1,
    selectedEpisode: null,
    selectedSource: null,
    selectedDevice: "browser",
    mediaPlayers: [],
    hls: null,
    ingressPath: "",
    resumeProgress: null,
    castSession: {
      active: false,
      entityId: null,
      deviceName: null,
      title: null,
      posterUrl: "",
      isTv: false,
      season: null,
      episode: null,
      state: "idle",
      position: 0,
      duration: 0,
      volume: 1,
      muted: false,
      isSeeking: false,
      pollTimer: null,
      localTimer: null,
      idleCount: 0,
    },
  };

  // DOM Elements
  const elements = {
    // Profile controls
    profileDropdownWrapper: document.getElementById("profile-dropdown-wrapper"),
    btnProfilePill: document.getElementById("btn-profile-pill"),
    navProfileAvatar: document.getElementById("nav-profile-avatar"),
    navProfileName: document.getElementById("nav-profile-name"),
    profileDropdownMenu: document.getElementById("profile-dropdown-menu"),
    profilesListMenu: document.getElementById("profiles-list-menu"),
    btnDropdownSwitch: document.getElementById("btn-dropdown-switch"),
    btnDropdownFavorites: document.getElementById("btn-dropdown-favorites"),
    btnDropdownWatched: document.getElementById("btn-dropdown-watched"),

    // Profile Picker Modal
    profilePickerModal: document.getElementById("profile-picker-modal"),
    profilePickerGrid: document.getElementById("profile-picker-grid"),

    // Carousels / Shelves
    continueSection: document.getElementById("continue-section"),
    continueRow: document.getElementById("continue-row"),
    continueCount: document.getElementById("continue-count"),
    favoritesSection: document.getElementById("favorites-section"),
    favoritesRow: document.getElementById("favorites-row"),
    favoritesCount: document.getElementById("favorites-count"),
    watchedSection: document.getElementById("watched-section"),
    watchedRow: document.getElementById("watched-row"),
    watchedCount: document.getElementById("watched-count"),

    btnRestartTrigger: document.getElementById("btn-restart-trigger"),
    brandLogo: document.getElementById("brand-logo"),
    navTabs: document.querySelectorAll(".nav-tab[data-type]"),
    btnGenresToggle: document.getElementById("btn-genres-toggle"),
    genresBar: document.getElementById("genres-bar"),
    genresList: document.getElementById("genres-list"),
    sourcesChips: document.getElementById("sources-chips"),
    searchInput: document.getElementById("search-input"),
    searchClear: document.getElementById("search-clear"),
    heroSection: document.getElementById("hero-section"),
    heroBackdrop: document.getElementById("hero-backdrop"),
    heroType: document.getElementById("hero-type"),
    heroRating: document.getElementById("hero-rating"),
    heroYear: document.getElementById("hero-year"),
    heroTitle: document.getElementById("hero-title"),
    heroDescription: document.getElementById("hero-description"),
    heroPlayBtn: document.getElementById("hero-play-btn"),
    heroFavoriteBtn: document.getElementById("hero-favorite-btn"),
    heroInfoBtn: document.getElementById("hero-info-btn"),
    sectionTitle: document.getElementById("section-title"),
    sectionCount: document.getElementById("section-count"),
    catalogGrid: document.getElementById("catalog-grid"),
    loadingSpinner: document.getElementById("loading-spinner"),
    emptyState: document.getElementById("empty-state"),
    detailsModal: document.getElementById("details-modal"),
    modalClose: document.getElementById("modal-close"),
    modalBackdropClose: document.getElementById("modal-backdrop-close"),
    modalBackdropImg: document.getElementById("modal-backdrop-img"),
    modalPoster: document.getElementById("modal-poster"),
    modalTitle: document.getElementById("modal-title"),
    modalYear: document.getElementById("modal-year"),
    modalDuration: document.getElementById("modal-duration"),
    modalRating: document.getElementById("modal-rating"),
    modalTypeBadge: document.getElementById("modal-type-badge"),
    modalGenres: document.getElementById("modal-genres"),
    modalPlot: document.getElementById("modal-plot"),
    modalCastSection: document.getElementById("modal-cast-section"),
    modalCastText: document.getElementById("modal-cast-text"),
    tvSeriesSection: document.getElementById("tv-series-section"),
    seasonsTabs: document.getElementById("seasons-tabs"),
    episodesList: document.getElementById("episodes-list"),
    sourcesSection: document.getElementById("sources-section"),
    sourceSelect: document.getElementById("source-select"),
    deviceSelect: document.getElementById("device-select"),
    btnPlayTrigger: document.getElementById("btn-play-trigger"),
    btnPlayText: document.getElementById("btn-play-text"),
    btnFavoriteTrigger: document.getElementById("btn-favorite-trigger"),
    playerModal: document.getElementById("player-modal"),
    playerCloseBtn: document.getElementById("player-close-btn"),
    playerFullscreenBtn: document.getElementById("player-fullscreen-btn"),
    playerTitle: document.getElementById("player-title"),
    videoElement: document.getElementById("video-element"),
    playerSpinner: document.getElementById("player-spinner"),
    toastContainer: document.getElementById("toast-container"),
    onboardingState: document.getElementById("onboarding-state"),

    // Cast Control Bar
    castBar: document.getElementById("cast-bar"),
    castBarPoster: document.getElementById("cast-bar-poster"),
    castBarTitle: document.getElementById("cast-bar-title"),
    castBarBadge: document.getElementById("cast-bar-badge"),
    castBarDevice: document.getElementById("cast-bar-device"),
    castBarStatusDot: document.getElementById("cast-bar-status-dot"),
    castBarStatus: document.getElementById("cast-bar-status"),
    castBarSeekBack: document.getElementById("cast-bar-seek-back"),
    castBarPlayPause: document.getElementById("cast-bar-play-pause"),
    castIconPlay: document.getElementById("cast-icon-play"),
    castIconPause: document.getElementById("cast-icon-pause"),
    castBarSeekForward: document.getElementById("cast-bar-seek-forward"),
    castBarCurTime: document.getElementById("cast-bar-cur-time"),
    castBarSlider: document.getElementById("cast-bar-slider"),
    castBarSliderFill: document.getElementById("cast-bar-slider-fill"),
    castBarTotalTime: document.getElementById("cast-bar-total-time"),
    castBarMute: document.getElementById("cast-bar-mute"),
    castIconVol: document.getElementById("cast-icon-vol"),
    castIconVolMute: document.getElementById("cast-icon-vol-mute"),
    castBarVolSlider: document.getElementById("cast-bar-vol-slider"),
    castBarStop: document.getElementById("cast-bar-stop"),
  };

  // Helper: Format base API URL respecting Ingress
  function apiUrl(endpoint) {
    const cleanEndpoint = endpoint.startsWith("/") ? endpoint.slice(1) : endpoint;
    let base = state.ingressPath;
    if (!base) {
      base = window.location.pathname || "/";
    }
    if (!base.endsWith("/")) {
      base += "/";
    }
    return `${base}${cleanEndpoint}`;
  }

  // Initialize
  async function init() {
    setupEventListeners();
    await checkStatus();
    await loadProfiles();
    loadPlayers();
    loadGenres();
    await loadSources();
    refreshAllShelves();
    loadCatalog();
    checkActiveCastSession();
  }

  // Status Check
  async function checkStatus() {
    try {
      const resp = await fetch(apiUrl("api/status"));
      if (resp.ok) {
        const data = await resp.json();
        if (data.ingress_path) {
          state.ingressPath = data.ingress_path;
        }
      }
    } catch (err) {
      console.warn("Could not check status:", err);
    }
  }

  // Event Listeners
  function setupEventListeners() {
    // Navigation Tabs
    elements.navTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        elements.navTabs.forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        state.activeType = tab.dataset.type;
        state.activeGenre = null;
        updateGenreChipsUI();
        loadCatalog();
      });
    });

    // Genres Toggle
    elements.btnGenresToggle.addEventListener("click", () => {
      elements.genresBar.classList.toggle("hidden");
    });

    // Search Input with Debounce
    let searchTimeout = null;
    elements.searchInput.addEventListener("input", (e) => {
      const val = e.target.value.trim();
      state.searchQuery = val;
      elements.searchClear.classList.toggle("hidden", !val);

      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        if (val.length > 0) {
          executeSearch(val);
        } else {
          loadCatalog();
        }
      }, 350);
    });

    elements.searchClear.addEventListener("click", () => {
      elements.searchInput.value = "";
      state.searchQuery = "";
      elements.searchClear.classList.add("hidden");
      loadCatalog();
    });

    // Logo Click
    elements.brandLogo.addEventListener("click", () => {
      state.activeType = "all";
      state.activeGenre = null;
      state.searchQuery = "";
      elements.searchInput.value = "";
      elements.searchClear.classList.add("hidden");
      elements.navTabs.forEach((t) => t.classList.toggle("active", t.dataset.type === "all"));
      updateGenreChipsUI();
      loadCatalog();
    });

    // Modal Close
    elements.modalClose.addEventListener("click", closeModal);
    elements.modalBackdropClose.addEventListener("click", closeModal);

    // Player Close & Fullscreen
    elements.playerCloseBtn.addEventListener("click", closePlayer);
    if (elements.playerFullscreenBtn) {
      elements.playerFullscreenBtn.addEventListener("click", toggleFullscreen);
    }
    if (elements.videoElement) {
      elements.videoElement.addEventListener("dblclick", toggleFullscreen);
    }

    // Play Button Trigger
    elements.btnPlayTrigger.addEventListener("click", handlePlayAction);

    // Favorite Modal Trigger
    if (elements.btnFavoriteTrigger) {
      elements.btnFavoriteTrigger.addEventListener("click", () => {
        if (state.selectedItem) {
          toggleFavoriteItem(state.selectedItem);
        }
      });
    }

    // Hero Favorite Button
    if (elements.heroFavoriteBtn) {
      elements.heroFavoriteBtn.addEventListener("click", () => {
        if (state.catalogItems && state.catalogItems.length > 0) {
          toggleFavoriteItem(state.catalogItems[0]);
        }
      });
    }

    // Restart Button Trigger (from 0:00)
    if (elements.btnRestartTrigger) {
      elements.btnRestartTrigger.addEventListener("click", () => {
        state.resumeProgress = null;
        elements.btnRestartTrigger.classList.add("hidden");
        updatePlayButtonText();
        handlePlayAction();
      });
    }

    // Device Select Change
    elements.deviceSelect.addEventListener("change", (e) => {
      state.selectedDevice = e.target.value;
      updatePlayButtonText();
    });

    // Profile Dropdown Toggle
    if (elements.btnProfilePill && elements.profileDropdownWrapper) {
      elements.btnProfilePill.addEventListener("click", (e) => {
        e.stopPropagation();
        elements.profileDropdownWrapper.classList.toggle("open");
        elements.profileDropdownMenu.classList.toggle("hidden");
      });

      document.addEventListener("click", (e) => {
        if (!elements.profileDropdownWrapper.contains(e.target)) {
          elements.profileDropdownWrapper.classList.remove("open");
          elements.profileDropdownMenu.classList.add("hidden");
        }
      });
    }

    // Dropdown Actions
    if (elements.btnDropdownSwitch) {
      elements.btnDropdownSwitch.addEventListener("click", () => {
        elements.profileDropdownWrapper.classList.remove("open");
        elements.profileDropdownMenu.classList.add("hidden");
        openProfilePickerModal();
      });
    }

    if (elements.btnDropdownFavorites) {
      elements.btnDropdownFavorites.addEventListener("click", () => {
        elements.profileDropdownWrapper.classList.remove("open");
        elements.profileDropdownMenu.classList.add("hidden");
        switchToTab("favorites");
      });
    }

    if (elements.btnDropdownWatched) {
      elements.btnDropdownWatched.addEventListener("click", () => {
        elements.profileDropdownWrapper.classList.remove("open");
        elements.profileDropdownMenu.classList.add("hidden");
        switchToTab("watched");
      });
    }

    // Cast Control Bar Listeners
    if (elements.castBarPlayPause) {
      elements.castBarPlayPause.addEventListener("click", toggleCastPlayPause);
    }
    if (elements.castBarSeekBack) {
      elements.castBarSeekBack.addEventListener("click", () => seekCastRelative(-10));
    }
    if (elements.castBarSeekForward) {
      elements.castBarSeekForward.addEventListener("click", () => seekCastRelative(30));
    }
    if (elements.castBarSlider) {
      elements.castBarSlider.addEventListener("input", handleCastSliderInput);
      elements.castBarSlider.addEventListener("change", handleCastSliderChange);
    }
    if (elements.castBarMute) {
      elements.castBarMute.addEventListener("click", toggleCastMute);
    }
    if (elements.castBarVolSlider) {
      elements.castBarVolSlider.addEventListener("input", handleCastVolumeChange);
    }
    if (elements.castBarStop) {
      elements.castBarStop.addEventListener("click", stopCastPlayback);
    }

    // Keyboard Esc
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (elements.profilePickerModal && !elements.profilePickerModal.classList.contains("hidden")) {
          // If a profile is already selected, allow closing picker
          if (state.activeProfileId) {
            elements.profilePickerModal.classList.add("hidden");
          }
        } else if (elements.playerModal && !elements.playerModal.classList.contains("hidden")) {
          closePlayer();
        } else if (elements.detailsModal && !elements.detailsModal.classList.contains("hidden")) {
          closeModal();
        }
      }
    });
  }

  // Switch active tab programmatically
  function switchToTab(type) {
    elements.navTabs.forEach((t) => {
      t.classList.toggle("active", t.dataset.type === type);
    });
    state.activeType = type;
    state.activeGenre = null;
    updateGenreChipsUI();
    loadCatalog();
  }

  // Profile Management
  function getAvatarClass(avatarIndex) {
    const idx = ((parseInt(avatarIndex, 10) || 1) - 1) % 6 + 1;
    return `avatar-bg-${idx}`;
  }

  async function loadProfiles() {
    try {
      const resp = await fetch(apiUrl("api/profiles"));
      if (resp.ok) {
        state.profiles = await resp.json();
      }
    } catch (err) {
      console.warn("Could not load profiles:", err);
      state.profiles = [
        { id: "default", name: "Principale", avatar: 1, rating_filter: "ALL" }
      ];
    }

    if (!state.profiles || state.profiles.length === 0) {
      state.profiles = [
        { id: "default", name: "Principale", avatar: 1, rating_filter: "ALL" }
      ];
    }

    // Check if active profile exists
    const storedId = localStorage.getItem("streaming_hub_active_profile_id");
    const active = state.profiles.find((p) => p.id === storedId) || state.profiles[0];
    state.activeProfileId = active.id;
    localStorage.setItem("streaming_hub_active_profile_id", active.id);

    renderActiveProfileHeader();
    renderProfileDropdown();

    // If first time visit or multiple profiles and user hasn't chosen in this browser session
    const hasChosenThisSession = sessionStorage.getItem("streaming_hub_profile_selected");
    if (!hasChosenThisSession && state.profiles.length > 1) {
      openProfilePickerModal();
    }
  }

  function getActiveProfile() {
    return state.profiles.find((p) => p.id === state.activeProfileId) || state.profiles[0] || {
      id: "default",
      name: "Principale",
      avatar: 1,
      rating_filter: "ALL"
    };
  }

  function renderActiveProfileHeader() {
    const profile = getActiveProfile();
    if (elements.navProfileAvatar) {
      elements.navProfileAvatar.className = `profile-avatar-thumb ${getAvatarClass(profile.avatar)}`;
      elements.navProfileAvatar.textContent = (profile.name || "P").charAt(0).toUpperCase();
    }
    if (elements.navProfileName) {
      elements.navProfileName.textContent = profile.name;
    }
  }

  function renderProfileDropdown() {
    if (!elements.profilesListMenu) return;
    elements.profilesListMenu.innerHTML = "";

    state.profiles.forEach((p) => {
      const isCurrent = p.id === state.activeProfileId;
      const row = document.createElement("div");
      row.className = `profile-item-row ${isCurrent ? "active" : ""}`;

      const avatarClass = getAvatarClass(p.avatar);
      const ratingBadge = p.rating_filter && p.rating_filter !== "ALL" ? ` (${p.rating_filter})` : "";

      row.innerHTML = `
        <div class="profile-item-left">
          <div class="profile-avatar-thumb ${avatarClass}">${(p.name || "P").charAt(0).toUpperCase()}</div>
          <div class="profile-name-col">
            <span class="profile-item-name">${escapeHtml(p.name)}</span>
            <span class="profile-rating-badge">${p.rating_filter || "Tutti"}${ratingBadge ? "" : " (Tutti i contenuti)"}</span>
          </div>
        </div>
        ${isCurrent ? '<svg style="width:16px;height:16px;color:var(--primary)" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>' : ""}
      `;

      row.addEventListener("click", () => {
        elements.profileDropdownWrapper.classList.remove("open");
        elements.profileDropdownMenu.classList.add("hidden");
        selectProfile(p.id);
      });

      elements.profilesListMenu.appendChild(row);
    });
  }

  function openProfilePickerModal() {
    if (!elements.profilePickerModal || !elements.profilePickerGrid) return;
    elements.profilePickerGrid.innerHTML = "";

    state.profiles.forEach((p) => {
      const card = document.createElement("div");
      const isCurrent = p.id === state.activeProfileId;
      card.className = `profile-picker-card ${isCurrent ? "active" : ""}`;

      const avatarClass = getAvatarClass(p.avatar);
      card.innerHTML = `
        <div class="profile-picker-avatar ${avatarClass}">
          ${(p.name || "P").charAt(0).toUpperCase()}
        </div>
        <span class="profile-picker-name">${escapeHtml(p.name)}</span>
        <span class="profile-picker-tag">${p.rating_filter || "ALL"}</span>
      `;

      card.addEventListener("click", () => {
        selectProfile(p.id);
        elements.profilePickerModal.classList.add("hidden");
      });

      elements.profilePickerGrid.appendChild(card);
    });

    elements.profilePickerModal.classList.remove("hidden");
  }

  async function selectProfile(profileId) {
    if (state.activeProfileId === profileId) {
      sessionStorage.setItem("streaming_hub_profile_selected", "1");
      return;
    }

    state.activeProfileId = profileId;
    localStorage.setItem("streaming_hub_active_profile_id", profileId);
    sessionStorage.setItem("streaming_hub_profile_selected", "1");

    renderActiveProfileHeader();
    renderProfileDropdown();

    const current = getActiveProfile();
    showToast(`Benvenuto, ${current.name}!`, "info");

    // Refresh all profile-scoped data
    refreshAllShelves();
    loadCatalog();
  }

  // Load Media Players from Home Assistant
  async function loadPlayers() {
    try {
      const resp = await fetch(apiUrl("api/players"));
      if (resp.ok) {
        state.mediaPlayers = await resp.json();
        renderPlayersSelect();
      }
    } catch (err) {
      console.warn("Could not load players:", err);
    }
  }

  // Helper: Format raw Home Assistant entity or device names into clean, friendly names
  function formatDeviceName(entityId, rawName) {
    if (rawName && rawName.trim() && !rawName.startsWith("media_player.") && !/tpm191e/i.test(rawName)) {
      return rawName.trim();
    }
    const clean = (rawName || entityId || "").replace(/^media_player\./, "");
    if (/tpm191e/i.test(clean)) {
      return "Philips Smart TV (TPM191E)";
    }
    const formatted = clean
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
    return formatted || "Dispositivo Cast";
  }

  function renderPlayersSelect() {
    elements.deviceSelect.innerHTML = '<option value="browser">💻 Browser Locale (Web Player)</option>';
    if (state.mediaPlayers && state.mediaPlayers.length > 0) {
      const group = document.createElement("optgroup");
      group.label = "📺 Schermi TV & Dispositivi Cast Disponibili";

      state.mediaPlayers.forEach((p) => {
        const opt = document.createElement("option");
        opt.value = p.entity_id;
        const stateNote = p.state === "off" ? " (Standby)" : "";
        const friendly = formatDeviceName(p.entity_id, p.name);
        opt.textContent = `📺 ${friendly}${stateNote}`;
        group.appendChild(opt);
      });

      elements.deviceSelect.appendChild(group);
    }
  }

  // Load Genres
  async function loadGenres() {
    try {
      const resp = await fetch(apiUrl("api/catalog/genres"));
      if (resp.ok) {
        const genres = await resp.json();
        elements.genresList.innerHTML = "";
        genres.forEach((g) => {
          const chip = document.createElement("button");
          chip.className = "genre-chip";
          chip.textContent = g;
          chip.addEventListener("click", () => {
            if (state.activeGenre === g) {
              state.activeGenre = null;
            } else {
              state.activeGenre = g;
            }
            updateGenreChipsUI();
            if (state.activeGenre) {
              loadByGenre(state.activeGenre);
            } else {
              loadCatalog();
            }
          });
          elements.genresList.appendChild(chip);
        });
      }
    } catch (err) {
      console.warn("Could not load genres:", err);
    }
  }

  function updateGenreChipsUI() {
    const chips = elements.genresList.querySelectorAll(".genre-chip");
    chips.forEach((c) => {
      c.classList.toggle("active", c.textContent === state.activeGenre);
    });
  }

  // Load Available Streaming Sources
  async function loadSources() {
    try {
      const resp = await fetch(apiUrl("api/sources"));
      if (resp.ok) {
        state.availableSources = await resp.json();
        renderSourcesChips();
      }
    } catch (err) {
      console.warn("Could not load sources:", err);
    }
  }

  function renderSourcesChips() {
    if (!elements.sourcesChips) return;
    elements.sourcesChips.innerHTML = "";

    // "Tutte" chip
    const allChip = document.createElement("button");
    allChip.className = `source-chip ${state.activeSource === "all" ? "active" : ""}`;
    allChip.innerHTML = `<span class="source-chip-dot"></span>Tutte`;
    allChip.addEventListener("click", () => {
      if (state.activeSource === "all") return;
      state.activeSource = "all";
      updateSourcesChipsUI();
      triggerCatalogRefresh();
    });
    elements.sourcesChips.appendChild(allChip);

    // Dynamic registered sources
    state.availableSources.forEach((src) => {
      const chip = document.createElement("button");
      chip.className = `source-chip ${state.activeSource === src.id ? "active" : ""}`;
      chip.innerHTML = `<span class="source-chip-dot"></span>${escapeHtml(src.name)}`;
      chip.addEventListener("click", () => {
        if (state.activeSource === src.id) return;
        state.activeSource = src.id;
        updateSourcesChipsUI();
        triggerCatalogRefresh();
      });
      elements.sourcesChips.appendChild(chip);
    });
  }

  function updateSourcesChipsUI() {
    if (!elements.sourcesChips) return;
    const chips = elements.sourcesChips.querySelectorAll(".source-chip");
    chips.forEach((c) => {
      const text = c.textContent.trim();
      if (text === "Tutte") {
        c.classList.toggle("active", state.activeSource === "all");
      } else {
        const found = state.availableSources.find((s) => s.name === text);
        if (found) {
          c.classList.toggle("active", state.activeSource === found.id);
        }
      }
    });
  }

  function triggerCatalogRefresh() {
    if (state.searchQuery && state.searchQuery.trim().length > 1) {
      executeSearch(state.searchQuery.trim());
    } else if (state.activeGenre) {
      loadByGenre(state.activeGenre);
    } else {
      loadCatalog();
    }
  }

  // Load Catalog Titles
  async function loadCatalog() {
    showLoading(true);
    elements.emptyState.classList.add("hidden");

    // Manage Carousel Shelves visibility: show carousels on "all", hide on specific tabs or search
    const isHome = state.activeType === "all" && !state.activeGenre && !state.searchQuery;
    if (!isHome) {
      if (elements.continueSection) elements.continueSection.classList.add("hidden");
      if (elements.favoritesSection) elements.favoritesSection.classList.add("hidden");
      if (elements.watchedSection) elements.watchedSection.classList.add("hidden");
    } else {
      if (elements.continueSection && elements.continueRow && elements.continueRow.children.length > 0) {
        elements.continueSection.classList.remove("hidden");
      }
      if (elements.favoritesSection && elements.favoritesRow && elements.favoritesRow.children.length > 0) {
        elements.favoritesSection.classList.remove("hidden");
      }
      if (elements.watchedSection && elements.watchedRow && elements.watchedRow.children.length > 0) {
        elements.watchedSection.classList.remove("hidden");
      }
    }

    // Tab "favorites"
    if (state.activeType === "favorites") {
      elements.sectionTitle.textContent = "I Tuoi Preferiti";
      elements.heroSection.classList.add("hidden");
      try {
        const resp = await fetch(apiUrl(`api/favorites?profile_id=${encodeURIComponent(state.activeProfileId)}`));
        if (!resp.ok) throw new Error("Favorites fetch failed");
        const favs = await resp.json();
        state.catalogItems = favs || [];
        renderGrid(state.catalogItems);
      } catch (err) {
        console.error("Error loading favorites tab:", err);
        showToast("Errore nel caricamento dei preferiti", "error");
      } finally {
        showLoading(false);
      }
      return;
    }

    // Tab "watched"
    if (state.activeType === "watched") {
      elements.sectionTitle.textContent = "Titoli Già Visti";
      elements.heroSection.classList.add("hidden");
      try {
        const resp = await fetch(apiUrl(`api/history/watched?profile_id=${encodeURIComponent(state.activeProfileId)}&limit=50`));
        if (!resp.ok) throw new Error("Watched fetch failed");
        const watched = await resp.json();
        // Normalize watched items to match catalog item structure
        state.catalogItems = (watched || []).map((w) => ({
          id: w.media_id,
          title: w.title,
          type: w.media_type,
          poster_url: w.poster_url,
          year: w.completed_at ? new Date(w.completed_at).getFullYear() : "",
          rating: "",
          genres: ["Visto"],
        }));
        renderGrid(state.catalogItems);
      } catch (err) {
        console.error("Error loading watched tab:", err);
        showToast("Errore nel caricamento della cronologia visti", "error");
      } finally {
        showLoading(false);
      }
      return;
    }

    if (!state.availableSources || state.availableSources.length === 0) {
      showLoading(false);
      elements.heroSection.classList.add("hidden");
      elements.catalogGrid.innerHTML = "";
      elements.emptyState.classList.add("hidden");
      elements.onboardingState.classList.remove("hidden");
      elements.sectionTitle.textContent = "Configura le tue Sorgenti";
      elements.sectionCount.textContent = "0 sorgenti";
      return;
    }
    elements.onboardingState.classList.add("hidden");

    let titleText = "Ultimi Arrivi";
    if (state.activeType === "movie") titleText = "Ultimi Film";
    if (state.activeType === "tv") titleText = "Ultime Serie TV";
    elements.sectionTitle.textContent = titleText;

    try {
      const url = apiUrl(`api/catalog/latest?type=${state.activeType}&source=${state.activeSource}&page=1&profile_id=${encodeURIComponent(state.activeProfileId)}`);
      const resp = await fetch(url);
      if (!resp.ok) throw new Error("Network response was not ok");
      const data = await resp.json();
      state.catalogItems = data.results || [];
      renderGrid(state.catalogItems);
      if (isHome && state.catalogItems.length > 0) {
        updateHero(state.catalogItems[0]);
      } else {
        elements.heroSection.classList.add("hidden");
      }
    } catch (err) {
      console.error("Error loading catalog:", err);
      showToast("Errore nel caricamento del catalogo", "error");
    } finally {
      showLoading(false);
    }
  }

  // Search
  async function executeSearch(query) {
    showLoading(true);
    elements.emptyState.classList.add("hidden");
    elements.heroSection.classList.add("hidden");
    if (elements.continueSection) elements.continueSection.classList.add("hidden");
    if (elements.favoritesSection) elements.favoritesSection.classList.add("hidden");
    if (elements.watchedSection) elements.watchedSection.classList.add("hidden");

    elements.sectionTitle.textContent = `Risultati per "${query}"`;

    try {
      const url = apiUrl(`api/catalog/search?q=${encodeURIComponent(query)}&type=${state.activeType}&source=${state.activeSource}&profile_id=${encodeURIComponent(state.activeProfileId)}`);
      const resp = await fetch(url);
      if (!resp.ok) throw new Error("Search failed");
      const data = await resp.json();
      state.catalogItems = data.results || [];
      renderGrid(state.catalogItems);
    } catch (err) {
      console.error("Error searching:", err);
      showToast("Errore durante la ricerca", "error");
    } finally {
      showLoading(false);
    }
  }

  // Load by Genre
  async function loadByGenre(genre) {
    showLoading(true);
    elements.emptyState.classList.add("hidden");
    elements.heroSection.classList.add("hidden");
    if (elements.continueSection) elements.continueSection.classList.add("hidden");
    if (elements.favoritesSection) elements.favoritesSection.classList.add("hidden");
    if (elements.watchedSection) elements.watchedSection.classList.add("hidden");

    elements.sectionTitle.textContent = `Genere: ${genre}`;

    try {
      const type = state.activeType === "tv" ? "tv" : "movie";
      const url = apiUrl(`api/catalog/genre/${encodeURIComponent(genre)}?type=${type}&source=${state.activeSource}&profile_id=${encodeURIComponent(state.activeProfileId)}`);
      const resp = await fetch(url);
      if (!resp.ok) throw new Error("Genre fetch failed");
      const data = await resp.json();
      state.catalogItems = data.results || [];
      renderGrid(state.catalogItems);
    } catch (err) {
      console.error("Error loading genre:", err);
      showToast("Errore durante il caricamento del genere", "error");
    } finally {
      showLoading(false);
    }
  }

  // Render Grid Cards
  function renderGrid(items) {
    elements.catalogGrid.innerHTML = "";
    elements.sectionCount.textContent = `${items.length} titoli`;

    if (!items || items.length === 0) {
      elements.emptyState.classList.remove("hidden");
      return;
    }

    elements.emptyState.classList.add("hidden");

    const fragment = document.createDocumentFragment();
    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = "media-card";

      const posterSrc = item.poster_url || "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='450' viewBox='0 0 300 450'%3E%3Crect width='300' height='450' fill='%23182030'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%2364748b' font-family='sans-serif' font-size='18'%3ELocandina%3C/text%3E%3C/svg%3E";

      const isTv = item.type === "tv" || !!item.seasons || (item.genres && item.genres.some((g) => g.toLowerCase().includes("serie")));
      const typeLabel = isTv ? "Serie TV" : "Film";
      const ratingLabel = item.rating ? `★ ${item.rating}` : "";

      // Determine catalog badges
      let catalogsList = [];
      if (item.catalogs && item.catalogs.length > 0) {
        catalogsList = item.catalogs;
      } else if (item.sources && item.sources.length > 0) {
        catalogsList = [...new Set(item.sources.map((s) => s.provider_id || s.provider_name))];
      } else if (item.id && item.id.startsWith("sc-")) {
        catalogsList = ["streamingcommunity"];
      } else if (item.id && (item.id.startsWith("cb-") || item.cb01_url)) {
        catalogsList = ["cb01"];
      }

      let catalogsHtml = "";
      if (catalogsList.length > 0) {
        catalogsHtml = `
          <div class="card-catalogs">
            ${catalogsList
              .map((cat) => {
                const lower = cat.toLowerCase();
                let badgeClass = "catalog-badge";
                let display = cat;
                if (lower.includes("streamingcommunity") || lower === "sc") {
                  badgeClass += " badge-streamingcommunity";
                  display = "SC";
                } else if (lower.includes("cb01") || lower === "cb") {
                  badgeClass += " badge-cb01";
                  display = "CB01";
                }
                return `<span class="${badgeClass}">${escapeHtml(display)}</span>`;
              })
              .join("")}
          </div>
        `;
      }

      card.innerHTML = `
        <div class="card-poster-wrap">
          <img class="card-poster" src="${posterSrc}" alt="${escapeHtml(item.title)}" loading="lazy">
          <div class="card-badges">
            <span class="card-badge-type">${typeLabel}</span>
            ${ratingLabel ? `<span class="card-badge-rating">${ratingLabel}</span>` : ""}
          </div>
        </div>
        <div class="card-info">
          <div class="card-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
          <div class="card-subtext">
            <span>${item.year || ""}</span>
            <span>${(item.genres && item.genres[0]) || ""}</span>
          </div>
          ${catalogsHtml}
        </div>
      `;

      card.addEventListener("click", () => openDetails(item));
      fragment.appendChild(card);
    });
    elements.catalogGrid.appendChild(fragment);
  }

  // Hero Banner Update
  function updateHero(item) {
    if (!item) {
      elements.heroSection.classList.add("hidden");
      return;
    }

    const backdrop = item.backdrop_url || item.poster_url;
    if (!backdrop) {
      elements.heroSection.classList.add("hidden");
      return;
    }

    elements.heroBackdrop.style.backgroundImage = `url("${backdrop}")`;
    const isTv = item.type === "tv" || !!item.seasons;
    elements.heroType.textContent = isTv ? "Serie TV" : "Film";
    elements.heroRating.textContent = item.rating ? `★ ${item.rating}` : "★ 7.5";
    elements.heroYear.textContent = item.year || "2026";
    elements.heroTitle.textContent = item.title;
    elements.heroDescription.textContent = item.description || "Nessuna descrizione disponibile.";

    elements.heroPlayBtn.onclick = () => openDetails(item);
    elements.heroInfoBtn.onclick = () => openDetails(item);

    elements.heroSection.classList.remove("hidden");
  }

  // Helper: Format seconds to M:SS or H:MM:SS
  function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return "0:00";
    const s = Math.floor(seconds);
    const m = Math.floor(s / 60);
    const remS = s % 60;
    const h = Math.floor(m / 60);
    const remM = m % 60;
    const pad = (n) => String(n).padStart(2, "0");
    if (h > 0) {
      return `${h}:${pad(remM)}:${pad(remS)}`;
    }
    return `${remM}:${pad(remS)}`;
  }

  // All Shelves Refresh
  function refreshAllShelves() {
    loadContinueWatching();
    loadFavoritesShelf();
    loadWatchedShelf();
  }

  // Favorites Shelf & Management
  async function loadFavoritesShelf() {
    if (!elements.favoritesSection || !elements.favoritesRow) return;
    try {
      const resp = await fetch(apiUrl(`api/favorites?profile_id=${encodeURIComponent(state.activeProfileId)}`));
      if (!resp.ok) return;
      const items = await resp.json();
      state.favoritesSet = new Set((items || []).map((i) => i.id));
      renderFavoritesShelf(items || []);
    } catch (err) {
      console.warn("Could not load favorites shelf:", err);
    }
  }

  function renderFavoritesShelf(items) {
    if (!elements.favoritesSection || !elements.favoritesRow) return;
    elements.favoritesRow.innerHTML = "";

    if (!items || items.length === 0) {
      elements.favoritesSection.classList.add("hidden");
      return;
    }

    // Only show on home tab ("all") when not searching
    if (state.activeType === "all" && !state.searchQuery && !state.activeGenre) {
      elements.favoritesSection.classList.remove("hidden");
    }

    if (elements.favoritesCount) {
      elements.favoritesCount.textContent = `${items.length} preferiti`;
    }

    const fragment = document.createDocumentFragment();
    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = "media-card";

      const posterSrc = item.poster_url || "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='450' viewBox='0 0 300 450'%3E%3Crect width='300' height='450' fill='%23182030'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%2364748b' font-family='sans-serif' font-size='18'%3ELocandina%3C/text%3E%3C/svg%3E";
      const isTv = item.type === "tv" || !!item.seasons;
      const typeLabel = isTv ? "Serie TV" : "Film";

      card.innerHTML = `
        <div class="card-poster-wrap">
          <img class="card-poster" src="${posterSrc}" alt="${escapeHtml(item.title)}" loading="lazy">
          <div class="card-badges">
            <span class="card-badge-type">${typeLabel}</span>
          </div>
        </div>
        <div class="card-info">
          <div class="card-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
        </div>
      `;

      card.addEventListener("click", () => openDetails(item));
      fragment.appendChild(card);
    });
    elements.favoritesRow.appendChild(fragment);
  }

  // Watched Shelf
  async function loadWatchedShelf() {
    if (!elements.watchedSection || !elements.watchedRow) return;
    try {
      const resp = await fetch(apiUrl(`api/history/watched?profile_id=${encodeURIComponent(state.activeProfileId)}&limit=15`));
      if (!resp.ok) return;
      const items = await resp.json();
      renderWatchedShelf(items || []);
    } catch (err) {
      console.warn("Could not load watched shelf:", err);
    }
  }

  function renderWatchedShelf(items) {
    if (!elements.watchedSection || !elements.watchedRow) return;
    elements.watchedRow.innerHTML = "";

    if (!items || items.length === 0) {
      elements.watchedSection.classList.add("hidden");
      return;
    }

    if (state.activeType === "all" && !state.searchQuery && !state.activeGenre) {
      elements.watchedSection.classList.remove("hidden");
    }

    if (elements.watchedCount) {
      elements.watchedCount.textContent = `${items.length} completati`;
    }

    const fragment = document.createDocumentFragment();
    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = "media-card";

      const posterSrc = item.poster_url || "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='450' viewBox='0 0 300 450'%3E%3Crect width='300' height='450' fill='%23182030'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%2364748b' font-family='sans-serif' font-size='18'%3ELocandina%3C/text%3E%3C/svg%3E";
      const isTv = item.media_type === "tv";
      const typeLabel = isTv ? "Serie TV" : "Film";

      card.innerHTML = `
        <div class="card-poster-wrap">
          <img class="card-poster" src="${posterSrc}" alt="${escapeHtml(item.title)}" loading="lazy">
          <div class="card-badges">
            <span class="card-badge-type">${typeLabel}</span>
            <span class="card-badge-rating">✓ Visto</span>
          </div>
        </div>
        <div class="card-info">
          <div class="card-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
        </div>
      `;

      card.addEventListener("click", () => {
        openDetails({
          id: item.media_id,
          title: item.title,
          type: item.media_type,
          poster_url: item.poster_url,
        });
      });
      fragment.appendChild(card);
    });
    elements.watchedRow.appendChild(fragment);
  }

  // Toggle Favorite
  async function toggleFavoriteItem(item) {
    if (!item || !item.id) return;
    const isTv = item.type === "tv" || !!item.seasons;

    try {
      const payload = {
        title_id: item.id,
        media_type: isTv ? "tv" : "movie",
        title: item.title,
        poster_url: item.poster_url || "",
        tmdb_id: item.tmdb_id || null,
        imdb_id: item.imdb_id || null,
        profile_id: state.activeProfileId,
      };

      const resp = await fetch(apiUrl("api/favorites/toggle"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) throw new Error("Toggle favorite failed");
      const data = await resp.json();
      const isFav = !!data.favorite;

      if (isFav) {
        state.favoritesSet.add(item.id);
        showToast(`"${item.title}" aggiunto ai Preferiti! ❤️`, "success");
      } else {
        state.favoritesSet.delete(item.id);
        showToast(`"${item.title}" rimosso dai Preferiti`, "info");
      }

      // Update button visual states
      updateFavoriteButtonUI(isFav);
      loadFavoritesShelf();

      // If on favorites tab, refresh the grid
      if (state.activeType === "favorites") {
        loadCatalog();
      }
    } catch (err) {
      console.error("Toggle favorite error:", err);
      showToast("Impossibile aggiornare i preferiti", "error");
    }
  }

  function updateFavoriteButtonUI(isFavorite) {
    if (elements.btnFavoriteTrigger) {
      elements.btnFavoriteTrigger.classList.toggle("active", isFavorite);
      elements.btnFavoriteTrigger.title = isFavorite ? "Rimuovi dai Preferiti" : "Aggiungi ai Preferiti";
    }
    if (elements.heroFavoriteBtn) {
      elements.heroFavoriteBtn.classList.toggle("active", isFavorite);
      elements.heroFavoriteBtn.title = isFavorite ? "Rimuovi dai Preferiti" : "Aggiungi ai Preferiti";
    }
  }

  // Continue Watching Section
  async function loadContinueWatching() {
    try {
      const resp = await fetch(apiUrl(`api/history/continue?profile_id=${encodeURIComponent(state.activeProfileId)}`));
      if (!resp.ok) return;
      const items = await resp.json();
      renderContinueWatching(items);
    } catch (err) {
      console.warn("Could not load continue watching list:", err);
    }
  }

  function renderContinueWatching(items) {
    if (!elements.continueSection || !elements.continueRow) return;
    elements.continueRow.innerHTML = "";

    if (!items || items.length === 0) {
      elements.continueSection.classList.add("hidden");
      return;
    }

    if (state.activeType === "all" && !state.searchQuery && !state.activeGenre) {
      elements.continueSection.classList.remove("hidden");
    }

    if (elements.continueCount) {
      elements.continueCount.textContent = `${items.length} in corso`;
    }

    const fragment = document.createDocumentFragment();
    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = "continue-card";

      const imgSrc = item.backdrop_url || item.poster_url || "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=500&auto=format&fit=crop&q=60";
      const isTv = item.media_type === "tv";

      let epBadgeText = "";
      if (isTv) {
        if (item.is_next_episode) {
          epBadgeText = `Prossimo: S${item.season_number}E${item.episode_number}`;
        } else {
          epBadgeText = `S${item.season_number}E${item.episode_number}`;
        }
      }

      let timeText = "";
      if (item.is_next_episode) {
        timeText = "Da iniziare";
      } else if (item.remaining_seconds > 0) {
        const remMin = Math.round(item.remaining_seconds / 60);
        timeText = remMin > 0 ? `${remMin} min rimanenti` : "Quasi terminato";
      } else {
        timeText = `${Math.round(item.progress_percent)}% completato`;
      }

      card.innerHTML = `
        <div class="continue-media-wrap">
          <img class="continue-media-img" src="${imgSrc}" alt="${escapeHtml(item.title)}" loading="lazy">
          <div class="continue-play-overlay">
            <div class="continue-play-icon">
              <svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            </div>
          </div>
          ${!item.is_next_episode ? `
            <div class="continue-progress-container">
              <div class="continue-progress-fill" style="width: ${Math.min(100, Math.max(0, item.progress_percent))}%;"></div>
            </div>
          ` : ""}
          <button class="continue-remove-btn" title="Rimuovi da Continua a guardare">✕</button>
        </div>
        <div class="continue-info">
          <div class="continue-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
          <div class="continue-subtitle">
            ${epBadgeText ? `<span class="continue-ep-badge">${epBadgeText}</span>` : `<span>Film</span>`}
            <span>${timeText}</span>
          </div>
        </div>
      `;

      // Remove button click
      const removeBtn = card.querySelector(".continue-remove-btn");
      removeBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        card.style.opacity = "0.3";
        card.style.transform = "scale(0.95)";
        try {
          await fetch(apiUrl(`api/history/${encodeURIComponent(item.media_id)}?profile_id=${encodeURIComponent(state.activeProfileId)}`), { method: "DELETE" });
          loadContinueWatching();
          showToast(`"${item.title}" rimosso da Continua a guardare`, "info");
        } catch (err) {
          console.warn("Delete history error:", err);
        }
      });

      // Card click: open modal with pre-selected season and episode
      card.addEventListener("click", () => {
        const dummyItem = {
          id: item.media_id,
          title: item.title,
          type: item.media_type,
          poster_url: item.poster_url,
          backdrop_url: item.backdrop_url,
        };
        openDetails(dummyItem, item.season_number, item.episode_number);
      });

      fragment.appendChild(card);
    });
    elements.continueRow.appendChild(fragment);
  }

  // Open Details Modal
  async function openDetails(item, targetSeason = null, targetEpisode = null) {
    state.selectedItem = item;
    state.selectedSeason = targetSeason || 1;
    state.selectedEpisode = null;
    state.selectedSource = null;
    state.resumeProgress = null;

    const mediaType = item.type === "tv" || !!item.seasons ? "tv" : "movie";

    // Show initial data
    elements.modalTitle.textContent = item.title;
    elements.modalYear.textContent = item.year || "";
    elements.modalDuration.textContent = item.duration ? `${item.duration} min` : "";
    elements.modalRating.textContent = item.rating ? `★ ${item.rating}` : "";
    elements.modalTypeBadge.textContent = mediaType === "tv" ? "Serie TV" : "Film";
    elements.modalPlot.textContent = item.description || "Caricamento trama arricchita...";

    const poster = item.poster_url || "";
    elements.modalPoster.src = poster;
    const backdrop = item.backdrop_url || poster;
    elements.modalBackdropImg.style.backgroundImage = backdrop ? `url("${backdrop}")` : "";

    // Set initial favorite UI from cached Set
    const isFav = state.favoritesSet.has(item.id) || !!item.is_favorite;
    updateFavoriteButtonUI(isFav);

    elements.modalGenres.innerHTML = "";
    if (item.genres) {
      item.genres.forEach((g) => {
        const tag = document.createElement("span");
        tag.className = "genre-tag";
        tag.textContent = g;
        elements.modalGenres.appendChild(tag);
      });
    }

    elements.detailsModal.classList.remove("hidden");
    document.body.style.overflow = "hidden";

    // Fetch full enriched details and watch progress concurrently
    try {
      const [detailsResp, progResp] = await Promise.all([
        fetch(apiUrl(`api/catalog/title/${mediaType}/${item.id}?profile_id=${encodeURIComponent(state.activeProfileId)}`)),
        fetch(apiUrl(`api/history/progress/${item.id}?profile_id=${encodeURIComponent(state.activeProfileId)}`)),
      ]);

      if (progResp.ok) {
        const progData = await progResp.json();
        if (progData.progress) {
          state.resumeProgress = progData.progress;
          if (mediaType === "tv" && !targetSeason && progData.progress.season_number) {
            state.selectedSeason = progData.progress.season_number;
          }
        }
      }

      if (detailsResp.ok) {
        const detailed = await detailsResp.json();
        state.selectedItem = detailed;
        if (detailed.is_favorite !== undefined) {
          if (detailed.is_favorite) state.favoritesSet.add(item.id);
          else state.favoritesSet.delete(item.id);
          updateFavoriteButtonUI(detailed.is_favorite);
        }
        updateModalWithDetails(detailed, targetEpisode || (state.resumeProgress && state.resumeProgress.episode_number));
      } else {
        updateModalWithDetails(item, targetEpisode);
      }
    } catch (err) {
      console.warn("Could not enrich item details:", err);
      updateModalWithDetails(item, targetEpisode);
    }
  }

  function updateModalWithDetails(item, targetEpisode = null) {
    if (item.description) elements.modalPlot.textContent = item.description;
    if (item.backdrop_url) elements.modalBackdropImg.style.backgroundImage = `url("${item.backdrop_url}")`;
    if (item.duration) elements.modalDuration.textContent = `${item.duration} min`;
    if (item.rating) elements.modalRating.textContent = `★ ${item.rating}`;

    // Cast section
    if (item.cast && item.cast.length > 0) {
      elements.modalCastText.textContent = item.cast.slice(0, 5).join(", ");
      if (item.director) elements.modalCastText.textContent += ` | Regia: ${item.director}`;
      elements.modalCastSection.classList.remove("hidden");
    } else {
      elements.modalCastSection.classList.add("hidden");
    }

    const isTv = item.type === "tv" || (item.seasons && item.seasons.length > 0);
    if (isTv) {
      elements.tvSeriesSection.classList.remove("hidden");
      renderSeasons(item.seasons || [], state.selectedSeason, targetEpisode);
    } else {
      elements.tvSeriesSection.classList.add("hidden");
      renderSources(item.sources || []);
    }

    updatePlayButtonText();
  }

  // Render TV Seasons & Episodes
  function renderSeasons(seasons, targetSeason = 1, targetEpisode = null) {
    elements.seasonsTabs.innerHTML = "";
    if (!seasons || seasons.length === 0) {
      elements.episodesList.innerHTML = "<p class='empty-state-text'>Nessuna stagione trovata.</p>";
      return;
    }

    const activeSeasonObj = seasons.find((s) => s.number === targetSeason) || seasons[0];
    state.selectedSeason = activeSeasonObj.number;

    seasons.forEach((season) => {
      const btn = document.createElement("button");
      btn.className = `season-btn ${season.number === state.selectedSeason ? "active" : ""}`;
      btn.textContent = `Stagione ${season.number}`;
      btn.addEventListener("click", () => {
        elements.seasonsTabs.querySelectorAll(".season-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        state.selectedSeason = season.number;
        activateSeason(season);
      });
      elements.seasonsTabs.appendChild(btn);
    });

    activateSeason(activeSeasonObj, targetEpisode);
  }

  async function activateSeason(season, targetEpisode = null) {
    if (season.episodes && season.episodes.length > 0) {
      renderEpisodes(season.episodes, targetEpisode);
      return;
    }

    elements.episodesList.innerHTML = `
      <div style="grid-column: 1 / -1; display: flex; align-items: center; justify-content: center; gap: 12px; padding: 30px; color: var(--text-muted);">
        <div class="spinner" style="width: 22px; height: 22px; margin: 0; border-width: 2px;"></div>
        <span>Caricamento episodi della Stagione ${season.number}...</span>
      </div>
    `;

    try {
      const seriesId = state.selectedItem ? state.selectedItem.id : "";
      const resp = await fetch(apiUrl(`api/catalog/seasons/${seriesId}/${season.number}`));
      if (resp.ok) {
        const data = await resp.json();
        season.episodes = data.episodes || [];
        renderEpisodes(season.episodes, targetEpisode);
      } else {
        elements.episodesList.innerHTML = "<p class='empty-state-text'>Nessun episodio caricato per questa stagione.</p>";
      }
    } catch (err) {
      console.warn("Failed to fetch season episodes:", err);
      elements.episodesList.innerHTML = `<p class='empty-state-text'>Errore nel recupero degli episodi: ${escapeHtml(err.message)}</p>`;
    }
  }

  function renderEpisodes(episodes, targetEpisode = null) {
    elements.episodesList.innerHTML = "";
    if (!episodes || episodes.length === 0) {
      elements.episodesList.innerHTML = "<p>Nessun episodio caricato per questa stagione.</p>";
      return;
    }

    let defaultEp = episodes[0];
    if (targetEpisode) {
      const found = episodes.find((e) => e.episode_number === targetEpisode);
      if (found) defaultEp = found;
    }

    state.selectedEpisode = defaultEp;
    renderSources(defaultEp.sources || []);
    updatePlayButtonText();

    episodes.forEach((ep) => {
      const isSelected = ep.episode_number === state.selectedEpisode.episode_number;
      const card = document.createElement("div");
      card.className = `episode-card ${isSelected ? "active" : ""}`;

      card.innerHTML = `
        <div class="ep-number">${ep.episode_number}</div>
        <div class="ep-title">${escapeHtml(ep.title || `Episodio ${ep.episode_number}`)}</div>
      `;

      card.addEventListener("click", () => {
        elements.episodesList.querySelectorAll(".episode-card").forEach((c) => c.classList.remove("active"));
        card.classList.add("active");
        state.selectedEpisode = ep;
        renderSources(ep.sources || []);
        updatePlayButtonText();
      });

      elements.episodesList.appendChild(card);
    });
  }

  // Render Sources Dropdown
  function renderSources(sources) {
    elements.sourceSelect.innerHTML = "";
    if (!sources || sources.length === 0) {
      elements.sourcesSection.classList.add("hidden");
      state.selectedSource = null;
      return;
    }

    elements.sourcesSection.classList.remove("hidden");
    sources.forEach((s, idx) => {
      const opt = document.createElement("option");
      opt.value = idx;
      opt.textContent = `${s.provider_name} [${s.quality || "HD"}]`;
      elements.sourceSelect.appendChild(opt);
    });

    state.selectedSource = sources[0];
    elements.sourceSelect.onchange = (e) => {
      state.selectedSource = sources[e.target.value];
    };
  }

  function updatePlayButtonText() {
    const isTv = state.selectedItem && (state.selectedItem.type === "tv" || !!state.selectedItem.seasons);
    const epPrefix = isTv && state.selectedEpisode ? `S${state.selectedSeason}E${state.selectedEpisode.episode_number} ` : "";

    const hasResume = state.resumeProgress && state.resumeProgress.progress_seconds > 15;
    const resumeTimeStr = hasResume ? `da ${formatTime(state.resumeProgress.progress_seconds)}` : "";

    if (elements.btnRestartTrigger) {
      elements.btnRestartTrigger.classList.toggle("hidden", !hasResume);
    }

    if (state.selectedDevice === "browser") {
      if (hasResume) {
        elements.btnPlayText.textContent = `▶ Riprendi ${epPrefix}${resumeTimeStr}`;
      } else {
        elements.btnPlayText.textContent = `Guarda ${epPrefix}nel Browser`;
      }
    } else {
      const dev = state.mediaPlayers.find((p) => p.entity_id === state.selectedDevice);
      const name = dev ? formatDeviceName(dev.entity_id, dev.name) : "Dispositivo Cast";
      if (hasResume) {
        elements.btnPlayText.textContent = `📺 Riprendi ${epPrefix}${resumeTimeStr} su ${name}`;
      } else {
        elements.btnPlayText.textContent = `Trasmetti ${epPrefix}su ${name}`;
      }
    }
  }

  // Handle Play / Cast Trigger
  async function handlePlayAction() {
    const item = state.selectedItem;
    if (!item) return;

    const isTv = item.type === "tv" || !!item.seasons;

    // Determine target source: for TV series, ALWAYS use the active episode's sources
    let source = null;
    if (isTv && state.selectedEpisode) {
      const epSources = state.selectedEpisode.sources || [];
      if (epSources.length > 0) {
        const match = epSources.find((s) => s.id === (state.selectedSource && state.selectedSource.id));
        source = match || epSources[0];
      }
    } else {
      source = state.selectedSource;
      if (!source && item.sources && item.sources.length > 0) {
        source = item.sources[0];
      }
    }

    if (!source || !source.page_url) {
      showToast("Nessuna sorgente video disponibile per questo contenuto", "error");
      return;
    }

    const title = (isTv && state.selectedEpisode)
      ? `${item.title} - S${state.selectedSeason}E${state.selectedEpisode.episode_number}${state.selectedEpisode.title ? ": " + state.selectedEpisode.title : ""}`
      : item.title;

    if (state.selectedDevice === "browser") {
      // Local Browser Playback
      await playInBrowser(source, title);
    } else {
      // Cast playback via Home Assistant
      await castToDevice(source, title, state.selectedDevice);
    }
  }

  // Local Browser Playback
  async function playInBrowser(source, title) {
    showToast("Risoluzione flusso HLS in corso...", "info");
    elements.btnPlayTrigger.disabled = true;

    try {
      const payload = {
        page_url: source.page_url,
        provider_id: source.provider_id,
        media_id: source.media_id,
        quality: source.quality,
        prefer_fhd: false, // 720p HD with embedded audio track for robust browser playback
      };

      const resp = await fetch(apiUrl("api/resolve"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Risoluzione stream fallita");
      }

      const streamData = await resp.json();
      closeModal();
      openPlayer(streamData.local_stream_url, title);
    } catch (err) {
      console.error("Play error:", err);
      showToast(err.message || "Impossibile avviare il video", "error");
    } finally {
      elements.btnPlayTrigger.disabled = false;
    }
  }

  // Cast to HA Device
  async function castToDevice(source, title, entityId) {
    const currentItem = state.selectedItem;
    const isTv = currentItem && (currentItem.type === "tv" || !!currentItem.seasons);
    const hasResume = state.resumeProgress && state.resumeProgress.progress_seconds > 15;
    const resumeSec = hasResume ? state.resumeProgress.progress_seconds : 0;
    const seasonNum = isTv ? state.selectedSeason : null;
    const epNum = (isTv && state.selectedEpisode) ? state.selectedEpisode.episode_number : null;
    const mediaId = currentItem ? currentItem.id : source.media_id;
    const posterUrl = currentItem ? (currentItem.backdrop_url || currentItem.poster_url || "") : "";

    const dev = state.mediaPlayers.find((p) => p.entity_id === entityId);
    const friendlyName = formatDeviceName(entityId, dev ? dev.name : "");

    showToast(`Avvio riproduzione su ${friendlyName}...`, "info");
    elements.btnPlayTrigger.disabled = true;

    try {
      const payload = {
        entity_id: entityId,
        page_url: source.page_url,
        title: title,
        poster_url: posterUrl,
        provider_id: source.provider_id,
        media_id: mediaId,
        quality: source.quality,
        media_type: isTv ? "tv" : "movie",
        season_number: seasonNum,
        episode_number: epNum,
        seek_seconds: resumeSec,
        profile_id: state.activeProfileId,
      };

      const resp = await fetch(apiUrl("api/cast"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || "Casting fallito");
      }

      const data = await resp.json();
      const actualEntity = data.entity_id || entityId;
      const actualDev = state.mediaPlayers.find((p) => p.entity_id === actualEntity);
      const actualDevName = formatDeviceName(actualEntity, actualDev ? actualDev.name : friendlyName);

      showToast(`In riproduzione su ${actualDevName}!`, "success");

      // Show persistent Cast Control Bar BEFORE closing modal so state is preserved
      showCastBar({
        entityId: actualEntity,
        deviceName: actualDevName,
        title: title,
        posterUrl: posterUrl,
        isTv: isTv,
        season: seasonNum,
        episode: epNum,
        seekSeconds: resumeSec,
      });

      closeModal();
      setTimeout(loadContinueWatching, 3000);
    } catch (err) {
      console.error("Cast error:", err);
      showToast(err.message || "Errore durante il casting", "error");
    } finally {
      elements.btnPlayTrigger.disabled = false;
    }
  }

  // Video Player Logic
  function openPlayer(streamUrl, title) {
    elements.playerTitle.textContent = title;
    elements.playerModal.classList.remove("hidden");
    elements.playerSpinner.classList.remove("hidden");

    const video = elements.videoElement;
    const hasResume = state.resumeProgress && state.resumeProgress.progress_seconds > 15;
    const seekSec = hasResume ? state.resumeProgress.progress_seconds : 0;

    if (window.Hls && Hls.isSupported()) {
      if (state.hls) {
        state.hls.destroy();
      }
      state.hls = new Hls({
        maxBufferLength: 30,
        enableWorker: true,
      });

      state.hls.loadSource(streamUrl);
      state.hls.attachMedia(video);

      state.hls.on(Hls.Events.MANIFEST_PARSED, () => {
        elements.playerSpinner.classList.add("hidden");
        if (seekSec > 0) {
          video.currentTime = seekSec;
        }
        video.play().catch((e) => console.log("Autoplay blocked:", e));
      });

      state.hls.on(Hls.Events.ERROR, (event, data) => {
        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              state.hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              state.hls.recoverMediaError();
              break;
            default:
              state.hls.destroy();
              showToast("Errore di riproduzione video HLS", "error");
              break;
          }
        }
      });
    } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
      // Native iOS / Safari HLS
      video.src = streamUrl;
      video.addEventListener("loadedmetadata", () => {
        elements.playerSpinner.classList.add("hidden");
        if (seekSec > 0) {
          video.currentTime = seekSec;
        }
        video.play();
      });
    } else {
      video.src = streamUrl;
      if (seekSec > 0) {
        video.currentTime = seekSec;
      }
      video.play();
    }

    video.ontimeupdate = () => reportWatchProgress(false);
    video.onpause = () => reportWatchProgress(true);
    video.onended = () => reportWatchProgress(true);
  }

  let lastProgressReportTime = 0;
  function reportWatchProgress(force = false) {
    const video = elements.videoElement;
    if (!video || !state.selectedItem || !video.currentTime) return;
    const now = Date.now();
    if (!force && now - lastProgressReportTime < 5000) return;
    lastProgressReportTime = now;

    const isTv = state.selectedItem.type === "tv" || !!state.selectedItem.seasons;
    const payload = {
      media_id: state.selectedItem.id,
      title: state.selectedItem.title,
      media_type: isTv ? "tv" : "movie",
      poster_url: state.selectedItem.poster_url,
      season_number: isTv ? state.selectedSeason : null,
      episode_number: (isTv && state.selectedEpisode) ? state.selectedEpisode.episode_number : null,
      progress_seconds: video.currentTime,
      duration_seconds: video.duration || 0,
      profile_id: state.activeProfileId,
    };
    fetch(apiUrl("api/history"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch(() => {});
  }

  function toggleFullscreen() {
    const isFull = !!(document.fullscreenElement || document.webkitFullscreenElement);
    if (!isFull) {
      const container = elements.playerModal || elements.videoElement;
      if (container.requestFullscreen) {
        container.requestFullscreen().catch(() => {
          if (elements.videoElement.requestFullscreen) elements.videoElement.requestFullscreen();
          else if (elements.videoElement.webkitRequestFullscreen) elements.videoElement.webkitRequestFullscreen();
        });
      } else if (container.webkitRequestFullscreen) {
        container.webkitRequestFullscreen();
      } else if (elements.videoElement.webkitEnterFullscreen) {
        elements.videoElement.webkitEnterFullscreen();
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      }
    }
  }

  function closePlayer() {
    reportWatchProgress(true);
    if (elements.videoElement) {
      elements.videoElement.ontimeupdate = null;
      elements.videoElement.onpause = null;
      elements.videoElement.onended = null;
    }
    if (document.fullscreenElement || document.webkitFullscreenElement) {
      if (document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
      }
    }
    if (state.hls) {
      state.hls.destroy();
      state.hls = null;
    }
    elements.videoElement.pause();
    elements.videoElement.removeAttribute("src");
    elements.videoElement.load();
    elements.playerModal.classList.add("hidden");
    loadContinueWatching();
  }

  function closeModal() {
    elements.detailsModal.classList.add("hidden");
    document.body.style.overflow = "";
    state.selectedItem = null;
  }

  function showLoading(show) {
    elements.loadingSpinner.classList.toggle("hidden", !show);
  }

  // Toast Notification
  function showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
    elements.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(40px)";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // ==========================================
  // Cast Playback Bar & Control Logic
  // ==========================================

  function showCastBar(initData) {
    if (!elements.castBar) return;

    state.castSession = {
      active: true,
      entityId: initData.entityId,
      deviceName: initData.deviceName || initData.entityId,
      title: initData.title || "In riproduzione",
      posterUrl: initData.posterUrl || "",
      isTv: !!initData.isTv,
      season: initData.season,
      episode: initData.episode,
      state: "playing",
      position: initData.seekSeconds || 0,
      duration: 0,
      volume: 1,
      muted: false,
      isSeeking: false,
      pollTimer: null,
      localTimer: null,
      idleCount: 0,
    };

    if (elements.castBarTitle) elements.castBarTitle.textContent = state.castSession.title;
    if (elements.castBarDevice) elements.castBarDevice.textContent = state.castSession.deviceName;
    if (elements.castBarPoster) {
      if (state.castSession.posterUrl) {
        elements.castBarPoster.src = state.castSession.posterUrl;
        elements.castBarPoster.classList.remove("hidden");
      } else {
        elements.castBarPoster.src = "";
      }
    }

    if (elements.castBarBadge) {
      if (state.castSession.isTv && state.castSession.season && state.castSession.episode) {
        elements.castBarBadge.textContent = `S${state.castSession.season}:E${state.castSession.episode}`;
        elements.castBarBadge.classList.remove("hidden");
      } else {
        elements.castBarBadge.classList.add("hidden");
      }
    }

    updateCastStatusUI("playing");
    renderCastProgressUI();

    elements.castBar.classList.remove("hidden");
    document.body.classList.add("cast-active");

    startCastPolling(initData.entityId);
  }

  function hideCastBar() {
    stopCastPolling();
    if (elements.castBar) {
      elements.castBar.classList.add("hidden");
    }
    document.body.classList.remove("cast-active");
    state.castSession.active = false;
    loadContinueWatching();
  }

  function updateCastStatusUI(playbackState) {
    const isPlaying = playbackState === "playing";
    const isBuffering = playbackState === "buffering";

    if (elements.castIconPlay && elements.castIconPause) {
      if (isPlaying) {
        elements.castIconPlay.classList.add("hidden");
        elements.castIconPause.classList.remove("hidden");
      } else {
        elements.castIconPlay.classList.remove("hidden");
        elements.castIconPause.classList.add("hidden");
      }
    }

    if (elements.castBarStatusDot) {
      elements.castBarStatusDot.className = "cast-bar-status-dot";
      if (!isPlaying && !isBuffering) {
        elements.castBarStatusDot.classList.add("paused");
      } else if (isBuffering) {
        elements.castBarStatusDot.classList.add("buffering");
      }
    }

    if (elements.castBarStatus) {
      if (isPlaying) {
        elements.castBarStatus.textContent = "In riproduzione";
      } else if (isBuffering) {
        elements.castBarStatus.textContent = "Caricamento...";
      } else if (playbackState === "paused") {
        elements.castBarStatus.textContent = "In pausa";
      } else {
        elements.castBarStatus.textContent = playbackState;
      }
    }
  }

  function startCastPolling(entityId) {
    stopCastPolling();

    // Fast local timer every 1s for smooth progress bar progression
    state.castSession.localTimer = setInterval(() => {
      if (state.castSession.active && state.castSession.state === "playing" && !state.castSession.isSeeking) {
        state.castSession.position += 1;
        if (state.castSession.duration > 0 && state.castSession.position > state.castSession.duration) {
          state.castSession.position = state.castSession.duration;
        }
        renderCastProgressUI();
      }
    }, 1000);

    // Initial immediate fetch
    pollCastStatus(entityId);

    // Periodic HA poll every 3 seconds
    state.castSession.pollTimer = setInterval(() => {
      pollCastStatus(entityId);
    }, 3000);
  }

  function stopCastPolling() {
    if (state.castSession.pollTimer) {
      clearInterval(state.castSession.pollTimer);
      state.castSession.pollTimer = null;
    }
    if (state.castSession.localTimer) {
      clearInterval(state.castSession.localTimer);
      state.castSession.localTimer = null;
    }
  }

  async function pollCastStatus(entityId) {
    try {
      const url = apiUrl(`api/cast/status?entity_id=${encodeURIComponent(entityId)}`);
      const resp = await fetch(url);
      if (!resp.ok) return;

      const data = await resp.json();
      if (!data) return;

      if (!data.active && data.state && ["off", "idle", "standby"].includes(data.state)) {
        state.castSession.idleCount = (state.castSession.idleCount || 0) + 1;
        if (state.castSession.idleCount >= 3) {
          hideCastBar();
          return;
        }
      } else if (data.active) {
        state.castSession.idleCount = 0;
      }

      state.castSession.state = data.state || "playing";
      if (!state.castSession.isSeeking) {
        state.castSession.position = data.media_position || state.castSession.position;
      }
      state.castSession.duration = data.media_duration || state.castSession.duration;
      state.castSession.volume = data.volume_level !== undefined ? data.volume_level : 1;
      state.castSession.muted = !!data.is_volume_muted;

      if (data.title && elements.castBarTitle) {
        elements.castBarTitle.textContent = data.title;
      }
      if (data.device_name && elements.castBarDevice) {
        elements.castBarDevice.textContent = data.device_name;
      }
      if (data.poster_url && elements.castBarPoster && !elements.castBarPoster.src) {
        elements.castBarPoster.src = data.poster_url;
      }

      updateCastStatusUI(state.castSession.state);
      renderCastProgressUI();
      renderCastVolumeUI();
    } catch (err) {
      console.debug("Cast poll error:", err);
    }
  }

  function renderCastProgressUI() {
    const curSec = Math.max(0, Math.floor(state.castSession.position || 0));
    const durSec = Math.max(0, Math.floor(state.castSession.duration || 0));

    if (elements.castBarCurTime) {
      elements.castBarCurTime.textContent = formatTime(curSec);
    }
    if (elements.castBarTotalTime) {
      elements.castBarTotalTime.textContent = durSec > 0 ? formatTime(durSec) : "--:--";
    }

    if (durSec > 0 && !state.castSession.isSeeking) {
      const pct = Math.min(100, Math.max(0, (curSec / durSec) * 100));
      if (elements.castBarSliderFill) {
        elements.castBarSliderFill.style.width = `${pct}%`;
      }
      if (elements.castBarSlider) {
        elements.castBarSlider.value = Math.round(pct * 10);
      }
    }
  }

  function renderCastVolumeUI() {
    if (elements.castBarVolSlider) {
      elements.castBarVolSlider.value = Math.round((state.castSession.volume || 1) * 100);
    }
    if (elements.castIconVol && elements.castIconVolMute) {
      if (state.castSession.muted || state.castSession.volume === 0) {
        elements.castIconVol.classList.add("hidden");
        elements.castIconVolMute.classList.remove("hidden");
      } else {
        elements.castIconVol.classList.remove("hidden");
        elements.castIconVolMute.classList.add("hidden");
      }
    }
  }

  async function sendCastControl(command, value = null) {
    if (!state.castSession.entityId) return false;
    try {
      const resp = await fetch(apiUrl("api/cast/control"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          entity_id: state.castSession.entityId,
          command: command,
          value: value,
        }),
      });
      return resp.ok;
    } catch (err) {
      console.warn(`Failed to send cast control ${command}:`, err);
      return false;
    }
  }

  async function toggleCastPlayPause() {
    const isCurrentlyPlaying = state.castSession.state === "playing";
    const newState = isCurrentlyPlaying ? "paused" : "playing";
    state.castSession.state = newState;
    updateCastStatusUI(newState);
    await sendCastControl("play_pause");
  }

  async function seekCastRelative(deltaSeconds) {
    const durSec = state.castSession.duration || 0;
    let target = (state.castSession.position || 0) + deltaSeconds;
    if (target < 0) target = 0;
    if (durSec > 0 && target > durSec) target = durSec;

    state.castSession.position = target;
    renderCastProgressUI();
    await sendCastControl("seek", target);
  }

  function handleCastSliderInput(e) {
    state.castSession.isSeeking = true;
    const durSec = state.castSession.duration || 0;
    const pct = parseInt(e.target.value, 10) / 10;
    if (elements.castBarSliderFill) {
      elements.castBarSliderFill.style.width = `${pct}%`;
    }
    if (durSec > 0 && elements.castBarCurTime) {
      const previewSec = Math.round((pct / 100) * durSec);
      elements.castBarCurTime.textContent = formatTime(previewSec);
    }
  }

  async function handleCastSliderChange(e) {
    const durSec = state.castSession.duration || 0;
    const pct = parseInt(e.target.value, 10) / 10;
    if (durSec > 0) {
      const targetSec = Math.round((pct / 100) * durSec);
      state.castSession.position = targetSec;
      await sendCastControl("seek", targetSec);
    }
    state.castSession.isSeeking = false;
  }

  async function toggleCastMute() {
    state.castSession.muted = !state.castSession.muted;
    renderCastVolumeUI();
    await sendCastControl("volume_mute", state.castSession.muted);
  }

  async function handleCastVolumeChange(e) {
    const vol = parseInt(e.target.value, 10) / 100;
    state.castSession.volume = vol;
    state.castSession.muted = vol === 0;
    renderCastVolumeUI();
    await sendCastControl("volume_set", vol);
  }

  async function stopCastPlayback() {
    showToast("Interruzione trasmissione Cast...", "info");
    await sendCastControl("stop");
    hideCastBar();
    showToast("Riproduzione interrotta", "success");
  }

  async function checkActiveCastSession() {
    try {
      const resp = await fetch(apiUrl("api/cast/status"));
      if (!resp.ok) return;
      const data = await resp.json();
      if (data && data.active && data.entity_id) {
        showCastBar({
          entityId: data.entity_id,
          deviceName: formatDeviceName(data.entity_id, data.device_name),
          title: data.title,
          posterUrl: data.poster_url,
          isTv: data.media_type === "tv",
          season: data.season_number,
          episode: data.episode_number,
          seekSeconds: data.media_position,
        });
      }
    } catch (err) {
      console.debug("Could not restore cast session:", err);
    }
  }

  // Handle Mobile App Standby / Background wake up with throttle
  let lastResumeTime = 0;
  function handleAppResume() {
    const now = Date.now();
    // Throttle: ignore resumes fired less than 15 seconds apart to avoid flooding HA / browser
    if (now - lastResumeTime < 15000) {
      return;
    }
    lastResumeTime = now;

    console.debug("[StreamingHub] Resuming from background/standby");
    // Clear stuck loading states or disabled buttons
    if (elements.btnPlayTrigger) {
      elements.btnPlayTrigger.disabled = false;
    }
    showLoading(false);

    // Refresh core states
    loadPlayers();
    refreshAllShelves();

    // Check or resume active cast polling
    if (state.castSession && state.castSession.active && state.castSession.entityId) {
      startCastPolling(state.castSession.entityId);
    } else {
      checkActiveCastSession();
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      handleAppResume();
    }
  });

  window.addEventListener("pageshow", () => {
    handleAppResume();
  });

  // Start app on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
