// State Management
let state = {
    watchlist: [],
    tiffFilms: [],
    matches: [],
    currentView: 'dashboard',
    activeFestivalFilter: 'all'
};

// DOM Elements
const views = {
    dashboard: document.getElementById('view-dashboard'),
    catalog: document.getElementById('view-catalog'),
    acrossFestivals: document.getElementById('view-across-festivals'),
    watchlist: document.getElementById('view-watchlist')
};

const navItems = {
    dashboard: document.getElementById('nav-dashboard'),
    catalog: document.getElementById('nav-catalog'),
    acrossFestivals: document.getElementById('nav-across-festivals'),
    watchlist: document.getElementById('nav-watchlist')
};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
    setupNavigation();
    setupEventListeners();
    loadInitialData();
});

// Setup Navigation & View Switching
function setupNavigation() {
    Object.keys(navItems).forEach(viewName => {
        navItems[viewName].addEventListener('click', (e) => {
            e.preventDefault();
            switchView(viewName);
        });
    });
    
    // Read hash if present
    let hash = window.location.hash.substring(1);
    if (hash === 'across-festivals') {
        hash = 'acrossFestivals';
    }
    if (views[hash]) {
        switchView(hash);
    }
}

function switchView(viewName) {
    state.currentView = viewName;
    const hash = viewName === 'acrossFestivals' ? 'across-festivals' : viewName;
    window.location.hash = hash;
    
    // Toggle active classes on Nav Items
    Object.keys(navItems).forEach(name => {
        if (name === viewName) {
            navItems[name].classList.add('active');
        } else {
            navItems[name].classList.remove('active');
        }
    });
    
    // Toggle d-none classes on Sections
    Object.keys(views).forEach(name => {
        if (name === viewName) {
            views[name].classList.remove('d-none');
        } else {
            views[name].classList.add('d-none');
        }
    });
    
    // Trigger view-specific loads
    if (viewName === 'catalog') {
        loadCatalog();
    } else if (viewName === 'acrossFestivals') {
        loadAcrossFestivals();
    } else if (viewName === 'watchlist') {
        loadWatchlist();
    }
}

// Setup Event Listeners for actions
function setupEventListeners() {
    // Add custom movie form
    const btnAddCustom = document.getElementById('btn-add-custom');
    if (btnAddCustom) {
        btnAddCustom.addEventListener('click', handleAddCustomMovie);
    }
    
    // Global sync button
    const btnGlobalSync = document.getElementById('btn-global-sync');
    if (btnGlobalSync) {
        btnGlobalSync.addEventListener('click', handleSyncSchedules);
    }
    
    // Search input
    const searchInput = document.getElementById('catalog-search-input');
    if (searchInput) {
        searchInput.addEventListener('input', handleCatalogSearch);
    }
}

// Load Initial Data from REST API
async function loadInitialData() {
    // Try loading matches from cache first
    const cachedMatches = localStorage.getItem('last_matches');
    if (cachedMatches) {
        state.matches = JSON.parse(cachedMatches);
    }
    
    await loadWatchlist();
    await loadCatalog();
    
    // Render the initial pruned matches
    renderMatches();
    
    const syncTime = localStorage.getItem('last_sync_time') || 'recently';
    const syncStatus = document.getElementById('sync-status');
    if (syncStatus) {
        syncStatus.textContent = `Last synced: ${syncTime}`;
    }
    const streamingSyncStatus = document.getElementById('streaming-sync-status');
    if (streamingSyncStatus) {
        streamingSyncStatus.textContent = `Last synced: ${syncTime}`;
    }
    
    // Check if a sync is already running in background
    await checkRunningSync();
}

// Watchlist API Calls
async function loadWatchlist() {
    try {
        const response = await fetch(`/api/watchlist?t=${Date.now()}`);
        state.watchlist = await response.json();
        
        // Instantly filter out matches of films no longer in the watchlist
        const watchlistTitles = new Set(state.watchlist.map(w => w.title.toLowerCase()));
        const originalLength = state.matches.length;
        state.matches = state.matches.filter(m => watchlistTitles.has(m.title.toLowerCase()));
        
        if (state.matches.length !== originalLength) {
            localStorage.setItem('last_matches', JSON.stringify(state.matches));
            renderMatches();
        }
        
        renderWatchlist();
        updateWatchlistCounts();
    } catch (error) {
        console.error("Error loading watchlist:", error);
        showToast("Error loading watchlist", "error");
    }
}

async function handleAddCustomMovie() {
    const titleInput = document.getElementById('custom-movie-input');
    const directorInput = document.getElementById('custom-director-input');
    
    const title = titleInput.value.trim();
    const director = directorInput.value.trim();
    
    if (!title) {
        showToast("Please enter a film title", "error");
        return;
    }
    
    await addMovieToWatchlist(title, director);
    
    // Clear inputs
    titleInput.value = '';
    directorInput.value = '';
}

async function addMovieToWatchlist(title, director = null) {
    try {
        const response = await fetch('/api/watchlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title, director })
        });
        const result = await response.json();
        
        if (result.status === 'success') {
            showToast(`Added "${title}" to watchlist!`, "success");
            await loadWatchlist();
        } else {
            showToast(`"${title}" is already on watchlist.`, "info");
        }
    } catch (error) {
        console.error("Error adding movie:", error);
        showToast("Error adding film to watchlist", "error");
    }
}

async function deleteMovieFromWatchlist(title) {
    try {
        const response = await fetch(`/api/watchlist/${encodeURIComponent(title)}`, {
            method: 'DELETE'
        });
        const result = await response.json();
        
        if (result.status === 'success') {
            showToast(`Removed "${title}" from watchlist`, "success");
            await loadWatchlist();
        }
    } catch (error) {
        console.error("Error deleting movie:", error);
        showToast("Error removing film", "error");
    }
}

// Film Catalog API Calls with Filter Support
async function loadCatalog() {
    const container = document.getElementById('catalog-container');
    if (container) {
        container.innerHTML = `<div class="loading-state"><i class="fa-solid fa-spinner fa-spin"></i> Loading films...</div>`;
    }
    try {
        const filter = state.activeFestivalFilter || 'all';
        let url = '/api/films';
        const params = [];
        if (filter !== 'all' && filter !== 'awards') {
            params.push(`festival=${filter}`);
        }
        params.push(`t=${Date.now()}`);
        url += '?' + params.join('&');
        const response = await fetch(url);
        let films = await response.json();
        if (filter === 'awards') {
            films = films.filter(f => f.awards && f.awards.length > 0);
        }
        state.tiffFilms = films;
        renderCatalog(state.tiffFilms);
    } catch (error) {
        console.error("Error loading film catalog:", error);
        if (container) {
            container.innerHTML = `<div class="empty-state"><i class="fa-solid fa-triangle-exclamation"></i><p>Error loading film catalog.</p></div>`;
        }
    }
}

function filterCatalog(festival) {
    state.activeFestivalFilter = festival;
    
    // Update button styles
    const filters = ['all', 'tiff', 'cannes', 'berlinale', 'awards'];
    filters.forEach(f => {
        const btn = document.getElementById(`filter-btn-${f}`);
        if (btn) {
            if (f.toLowerCase() === festival.toLowerCase()) {
                btn.className = 'btn btn-primary';
                if (f === 'awards') {
                    btn.style.color = '#121212';
                    btn.style.backgroundColor = '#f5c518';
                    btn.style.borderColor = '#f5c518';
                }
            } else {
                btn.className = 'btn btn-secondary';
                if (f === 'awards') {
                    btn.style.color = '#f5c518';
                    btn.style.backgroundColor = 'transparent';
                    btn.style.borderColor = '#f5c518';
                } else {
                    btn.style.color = '';
                    btn.style.backgroundColor = '';
                    btn.style.borderColor = '';
                }
            }
        }
    });
    
    loadCatalog();
}

function selectFestivalInCatalog(festivalName) {
    // Switch the view to Film Catalog
    switchView('catalog');
    
    // Normalize festival name (e.g. 'TIFF' -> 'tiff', 'Cannes' -> 'cannes', 'Berlinale' -> 'berlinale')
    const key = festivalName.toLowerCase();
    
    // Filter the catalog
    filterCatalog(key);
}

// Festival Across Festivals API Calls & Rendering
async function loadAcrossFestivals() {
    const container = document.getElementById('across-festivals-container');
    if (container) {
        container.innerHTML = `<div class="loading-state"><i class="fa-solid fa-spinner fa-spin"></i> Loading films...</div>`;
    }
    try {
        const response = await fetch(`/api/films/intersections?t=${Date.now()}`);
        const intersections = await response.json();
        renderAcrossFestivals(intersections);
    } catch (error) {
        console.error("Error loading across festivals:", error);
        if (container) {
            container.innerHTML = `<div class="empty-state"><i class="fa-solid fa-triangle-exclamation"></i><p>Error loading films.</p></div>`;
        }
    }
}

function renderAcrossFestivals(films) {
    const container = document.getElementById('across-festivals-container');
    if (!container) return;
    
    if (films.length === 0) {
        container.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <i class="fa-solid fa-circle-nodes"></i>
                <p>No films found that overlap across multiple festivals.</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = films.map(film => {
        const isTracked = state.watchlist.some(w => w.title.toLowerCase() === film.title.toLowerCase());
        const trackBtn = isTracked 
            ? `<button class="btn-card-link" disabled style="opacity: 0.6; cursor: not-allowed; background: rgba(255, 255, 255, 0.02); border-color: rgba(255, 255, 255, 0.05); color: var(--text-muted);"><i class="fa-solid fa-check"></i> Tracked</button>`
            : `<button class="btn-card-link btn-track" onclick="addMovieToWatchlist('${escapeHtml(film.title)}', '${escapeHtml(film.director)}')"><i class="fa-solid fa-plus"></i> Track</button>`;
            
        const festivalBadges = film.festivals.map(f => {
            if (f === 'TIFF') {
                return `
                    <span class="badge badge-tiff clickable-festival-badge" onclick="selectFestivalInCatalog('TIFF')" style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.25); padding: 4px 8px; border-radius: 12px; display: inline-flex; align-items: center; justify-content: center; height: 22px;">
                        <img src="images/tiff-logo.svg" style="height: 9px; width: auto;" alt="TIFF">
                    </span>
                `;
            } else if (f === 'Cannes') {
                return `
                    <span class="badge badge-cannes clickable-festival-badge" onclick="selectFestivalInCatalog('Cannes')" style="background: rgba(251, 191, 36, 0.12); border: 1px solid rgba(251, 191, 36, 0.25); padding: 4px 8px; border-radius: 12px; display: inline-flex; align-items: center; justify-content: center; height: 22px;">
                        <img src="images/cannes-logo.svg" style="height: 11px; width: auto;" alt="Cannes">
                    </span>
                `;
            } else if (f === 'Berlinale') {
                return `
                    <span class="badge badge-berlinale clickable-festival-badge" onclick="selectFestivalInCatalog('Berlinale')" style="background: rgba(227, 6, 19, 0.12); border: 1px solid rgba(227, 6, 19, 0.25); padding: 4px 8px; border-radius: 12px; display: inline-flex; align-items: center; justify-content: center; height: 22px;">
                        <img src="images/berlinale-logo.svg" style="height: 10px; width: auto;" alt="Berlinale">
                    </span>
                `;
            }
            return `<span class="badge clickable-festival-badge" onclick="selectFestivalInCatalog('${f}')" style="background: rgba(255, 255, 255, 0.05); color: var(--text-muted); font-size: 11px; padding: 2px 6px; border-radius: 4px;">${f}</span>`;
        }).join('');
        
        let awardBadgeHtml = '';
        if (film.awards && film.awards.length > 0) {
            film.awards.forEach(award => {
                awardBadgeHtml += `
                    <div class="award-badge" style="background: linear-gradient(135deg, rgba(245, 197, 24, 0.15) 0%, rgba(217, 119, 6, 0.15) 100%); border: 1px solid rgba(245, 197, 24, 0.3); color: #f5c518; font-size: 0.7rem; font-weight: 600; padding: 3px 8px; border-radius: 5px; display: inline-flex; align-items: center; gap: 5px; margin-bottom: 10px; width: fit-content; text-transform: uppercase; letter-spacing: 0.5px;">
                        <i class="fa-solid fa-trophy"></i> ${award}
                    </div>
                `;
            });
        }
        
        return `
            <div class="match-card glass-panel" style="margin-bottom: 0;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; gap: 15px;">
                    <h4 style="margin: 0; font-size: 18px; font-weight: 600; line-height: 1.3; max-width: 65%; color: #f3f4f6;">${film.title}</h4>
                    <div style="display: flex; gap: 6px; flex-shrink: 0; align-items: center;">
                        ${festivalBadges}
                    </div>
                </div>
                ${awardBadgeHtml}
                <p class="director" style="margin-bottom: 2px;">Directed by ${film.director || 'Unknown'}</p>
                <p class="director" style="margin-bottom: 12px;">Country: ${film.country || 'Unknown'}</p>
                
                <p class="director" style="font-size: 12px; line-height: 1.5; color: var(--text-muted); margin-bottom: 18px; flex-grow: 1; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;">${film.description}</p>
                
                <div class="card-footer">
                    <a href="https://www.imdb.com/find?q=${encodeURIComponent(film.title)}" target="_blank" class="btn-card-link">
                        <i class="fa-brands fa-imdb" style="color: #f5c518;"></i> IMDb
                    </a>
                    ${trackBtn}
                </div>
            </div>
        `;
    }).join('');
}

let syncPollInterval = null;

function startSyncPolling() {
    if (syncPollInterval) return; // Already polling
    
    const btnSync = document.getElementById('btn-global-sync');
    const syncStatus = document.getElementById('sync-status');
    const streamingSyncStatus = document.getElementById('streaming-sync-status');
    const syncIcon = btnSync ? btnSync.querySelector('i') : null;
    
    // UI state: loading
    if (syncIcon) syncIcon.classList.add('spinning');
    if (btnSync) btnSync.disabled = true;
    if (syncStatus) syncStatus.textContent = "Syncing in background...";
    if (streamingSyncStatus) streamingSyncStatus.textContent = "Syncing in background...";
    
    syncPollInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/sync/status?t=${Date.now()}`);
            const data = await response.json();
            
            if (data.status === 'success') {
                clearInterval(syncPollInterval);
                syncPollInterval = null;
                
                // UI state: success
                state.matches = data.matches;
                const syncTime = new Date().toLocaleTimeString();
                localStorage.setItem('last_matches', JSON.stringify(state.matches));
                localStorage.setItem('last_sync_time', syncTime);
                
                renderMatches();
                if (syncStatus) syncStatus.textContent = `Last synced: ${syncTime}`;
                if (streamingSyncStatus) streamingSyncStatus.textContent = `Last synced: ${syncTime}`;
                
                const cinemaCount = state.matches.filter(m => m.type !== 'streaming').length;
                const streamingCount = state.matches.filter(m => m.type === 'streaming').length;
                showToast(`Sync complete! Found ${cinemaCount} cinema matches and ${streamingCount} streaming matches.`, "success");
                
                if (syncIcon) syncIcon.classList.remove('spinning');
                if (btnSync) btnSync.disabled = false;
                
            } else if (data.status === 'failed') {
                clearInterval(syncPollInterval);
                syncPollInterval = null;
                
                if (syncStatus) syncStatus.textContent = "Sync failed";
                if (streamingSyncStatus) streamingSyncStatus.textContent = "Sync failed";
                showToast(`Sync failed: ${data.error || 'Unknown error'}`, "error");
                
                if (syncIcon) syncIcon.classList.remove('spinning');
                if (btnSync) btnSync.disabled = false;
            }
        } catch (error) {
            console.error("Error polling sync status:", error);
        }
    }, 1500);
}

async function checkRunningSync() {
    try {
        const response = await fetch(`/api/sync/status?t=${Date.now()}`);
        const data = await response.json();
        if (data.status === 'running') {
            startSyncPolling();
        }
    } catch (e) {
        console.error("Error checking sync status:", e);
    }
}

// Sync schedules API call
async function handleSyncSchedules() {
    const btnSync = document.getElementById('btn-global-sync');
    if (btnSync && btnSync.disabled) return;
    
    try {
        const response = await fetch('/api/sync', { method: 'POST' });
        const result = await response.json();
        
        if (result.status === 'accepted' || result.status === 'running') {
            showToast("Synchronization started in the background", "info");
            startSyncPolling();
        } else {
            showToast("Failed to start synchronization", "error");
        }
    } catch (error) {
        console.error("Error starting sync:", error);
        showToast("Error connecting to server", "error");
    }
}

// Search filtering logic
function handleCatalogSearch(e) {
    const query = e.target.value.toLowerCase().trim();
    if (!query) {
        renderCatalog(state.tiffFilms);
        return;
    }
    
    const filtered = state.tiffFilms.filter(film => {
        return (film.title && film.title.toLowerCase().includes(query)) ||
               (film.director && film.director.toLowerCase().includes(query)) ||
               (film.category && film.category.toLowerCase().includes(query));
    });
    
    renderCatalog(filtered);
}

// Rendering Functions
function renderWatchlist() {
    const tableBody = document.getElementById('watchlist-table-body');
    const summaryContainer = document.getElementById('watchlist-summary-container');
    
    // Render Watchlist Table
    if (tableBody) {
        if (state.watchlist.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="4" class="empty-text">Your watchlist is empty. Add films to track them!</td>
                </tr>
            `;
        } else {
            tableBody.innerHTML = state.watchlist.map(item => {
                const dateStr = item.added_at || 'Recently';
                const directorStr = item.director ? item.director : '<span class="text-muted">Not specified</span>';
                return `
                    <tr>
                        <td><span class="movie-title">${item.title}</span></td>
                        <td><span class="movie-dir">${directorStr}</span></td>
                        <td>${dateStr}</td>
                        <td>
                            <button class="btn-icon-delete" onclick="deleteMovieFromWatchlist('${escapeHtml(item.title)}')">
                                <i class="fa-solid fa-trash-can"></i>
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');
        }
    }
    
    // Render Sidebar/Dashboard Watchlist Summary
    if (summaryContainer) {
        if (state.watchlist.length === 0) {
            summaryContainer.innerHTML = `<li class="empty-text">No movies in watchlist yet.</li>`;
        } else {
            summaryContainer.innerHTML = state.watchlist.slice(0, 5).map(item => `
                <li>
                    <div>
                        <p class="title">${item.title}</p>
                        <p class="director">${item.director || 'Unknown Director'}</p>
                    </div>
                    <button class="btn-icon-delete btn-sm" style="padding:4px 8px; font-size:10px;" onclick="deleteMovieFromWatchlist('${escapeHtml(item.title)}')">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                </li>
            `).join('');
            
            if (state.watchlist.length > 5) {
                summaryContainer.innerHTML += `
                    <li class="empty-text">
                        <a href="#watchlist" class="card-link" onclick="switchView('watchlist')">And ${state.watchlist.length - 5} more...</a>
                    </li>
                `;
            }
        }
    }
}

function renderCatalog(films) {
    const container = document.getElementById('catalog-container');
    if (!container) return;
    
    if (films.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-magnifying-glass"></i>
                <p>No films found matching your search.</p>
            </div>
        `;
        return;
    }
    
    // Group films by selection category
    const grouped = {};
    films.forEach(film => {
        if (film.selections && film.selections.length > 0) {
            film.selections.forEach(sel => {
                // If we are filtering by a specific festival, skip selections from other festivals!
                if (state.activeFestivalFilter !== 'all' && state.activeFestivalFilter !== 'awards') {
                    if (sel.festival_id.toLowerCase() !== state.activeFestivalFilter.toLowerCase()) {
                        return;
                    }
                }
                
                // If we are filtering by awards, only include selections that actually won an award!
                if (state.activeFestivalFilter === 'awards') {
                    if (!sel.award) {
                        return;
                    }
                }
                
                const catName = sel.category.name || 'General';
                if (!grouped[catName]) {
                    grouped[catName] = {
                        festival_id: sel.festival_id,
                        films: []
                    };
                }
                
                // Avoid adding the exact same film to the exact same category twice
                const exists = grouped[catName].films.some(item => item.film.title.toLowerCase() === film.title.toLowerCase());
                if (!exists) {
                    grouped[catName].films.push({
                        film: film,
                        selection: sel
                    });
                }
            });
        }
    });
    
    // Generate HTML for each category section
    let html = '';
    Object.keys(grouped).sort().forEach(catName => {
        const group = grouped[catName];
        const catFilms = group.films;
        const festivalId = group.festival_id;
        
        // Build festival badge next to category title
        let festivalLogoHtml = '';
        if (festivalId === 'TIFF') {
            festivalLogoHtml = `
                <span class="badge badge-tiff" style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.25); padding: 4px 10px; border-radius: 20px; display: inline-flex; align-items: center; justify-content: center; margin-left: 10px; vertical-align: middle;">
                    <img src="images/tiff-logo.svg" style="height: 12px; width: auto;" alt="TIFF Logo">
                </span>
            `;
        } else if (festivalId === 'Cannes') {
            festivalLogoHtml = `
                <span class="badge badge-cannes" style="background: rgba(251, 191, 36, 0.12); border: 1px solid rgba(251, 191, 36, 0.25); padding: 4px 10px; border-radius: 20px; display: inline-flex; align-items: center; justify-content: center; margin-left: 10px; vertical-align: middle;">
                    <img src="images/cannes-logo.svg" style="height: 18px; width: auto;" alt="Cannes Logo">
                </span>
            `;
        } else if (festivalId === 'Berlinale') {
            festivalLogoHtml = `
                <span class="badge badge-berlinale" style="background: rgba(227, 6, 19, 0.12); border: 1px solid rgba(227, 6, 19, 0.25); padding: 4px 10px; border-radius: 20px; display: inline-flex; align-items: center; justify-content: center; margin-left: 10px; vertical-align: middle;">
                    <img src="images/berlinale-logo.svg" style="height: 14px; width: auto;" alt="Berlinale Logo">
                </span>
            `;
        }
        
        const cardsHtml = catFilms.map(item => {
            const film = item.film;
            const sel = item.selection;
            const isAdded = state.watchlist.some(w => w.title.toLowerCase() === film.title.toLowerCase());
            const actionButton = isAdded 
                ? `<button class="btn-card-link" disabled style="opacity: 0.6; cursor: not-allowed; background: rgba(255, 255, 255, 0.02); border-color: rgba(255, 255, 255, 0.05); color: var(--text-muted);"><i class="fa-solid fa-check"></i> Added</button>`
                : `<button class="btn-card-link btn-track" onclick="addMovieToWatchlist('${escapeHtml(film.title)}', '${escapeHtml(film.director)}')"><i class="fa-solid fa-plus"></i> Track</button>`;
                
            const cardFestivalBadges = Array.isArray(film.festivals)
                ? film.festivals.map(f => {
                    if (f === 'TIFF') {
                        return `
                            <span class="badge badge-tiff clickable-festival-badge" onclick="selectFestivalInCatalog('TIFF')" style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.25); padding: 2px 6px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; height: 16px; margin-left: 4px;">
                                <img src="images/tiff-logo.svg" style="height: 7px; width: auto;" alt="TIFF">
                            </span>
                        `;
                    } else if (f === 'Cannes') {
                        return `
                            <span class="badge badge-cannes clickable-festival-badge" onclick="selectFestivalInCatalog('Cannes')" style="background: rgba(251, 191, 36, 0.12); border: 1px solid rgba(251, 191, 36, 0.25); padding: 2px 6px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; height: 16px; margin-left: 4px;">
                                <img src="images/cannes-logo.svg" style="height: 9px; width: auto;" alt="Cannes">
                            </span>
                        `;
                    } else if (f === 'Berlinale') {
                        return `
                            <span class="badge badge-berlinale clickable-festival-badge" onclick="selectFestivalInCatalog('Berlinale')" style="background: rgba(227, 6, 19, 0.12); border: 1px solid rgba(227, 6, 19, 0.25); padding: 2px 6px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; height: 16px; margin-left: 4px;">
                                <img src="images/berlinale-logo.svg" style="height: 8px; width: auto;" alt="Berlinale">
                            </span>
                        `;
                    }
                    return '';
                }).join('')
                : '';

            let awardBadgeHtml = '';
            if (sel.award) {
                awardBadgeHtml = `
                    <div class="award-badge" style="background: linear-gradient(135deg, rgba(245, 197, 24, 0.15) 0%, rgba(217, 119, 6, 0.15) 100%); border: 1px solid rgba(245, 197, 24, 0.3); color: #f5c518; font-size: 0.72rem; font-weight: 600; padding: 4px 10px; border-radius: 6px; display: inline-flex; align-items: center; gap: 6px; margin-bottom: 10px; width: fit-content; text-transform: uppercase; letter-spacing: 0.5px;">
                        <i class="fa-solid fa-trophy"></i> ${sel.award}
                    </div>
                `;
            }
                
            return `
                <div class="catalog-card">
                    <div style="flex-grow: 1; display: flex; flex-direction: column;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <span class="cat-badge" style="margin-bottom: 0;">${sel.category.name}</span>
                            <div style="display: flex; align-items: center;">
                                ${cardFestivalBadges}
                            </div>
                        </div>
                        ${awardBadgeHtml}
                        <h4>${film.title}</h4>
                        <p class="movie-dir" style="margin-bottom: 2px;">Dir: ${film.director || 'Unknown'}</p>
                        <p class="movie-dir" style="margin-bottom: 4px;">Country: ${film.country && film.country !== 'Unknown' ? film.country : 'Unknown'}</p>
                        <p class="movie-duration" style="margin-bottom: 0; display: flex; align-items: center; gap: 6px;">
                            <i class="fa-regular fa-clock" style="color: #818cf8;"></i> ${film.duration || '90 min'}
                        </p>
                    </div>
                    <div class="card-footer" style="display: flex; gap: 10px; border-top: 1px solid rgba(255, 255, 255, 0.05); padding-top: 15px; margin-top: 15px;">
                        <a href="https://www.imdb.com/find?q=${encodeURIComponent(film.title)}" target="_blank" class="btn-card-link">
                            <i class="fa-brands fa-imdb" style="color: #f5c518;"></i> IMDb Details
                        </a>
                        ${actionButton}
                    </div>
                </div>
            `;
        }).join('');
        
        html += `
            <div class="catalog-category-section">
                <div class="category-header">
                    <h3 class="category-title-text">${catName}${festivalLogoHtml} <span class="category-film-count">${catFilms.length} films</span></h3>
                </div>
                <div class="catalog-grid">
                    ${cardsHtml}
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

function parseScreeningDate(dateStr) {
    if (!dateStr) return new Date(0);
    
    const str = dateStr.toLowerCase().trim();
    const today = new Date();
    today.setHours(0,0,0,0);
    
    if (str === 'azi' || str === 'today') {
        return today;
    }
    if (str === 'mâine' || str === 'maine' || str === 'tomorrow') {
        const tomorrow = new Date(today);
        tomorrow.setDate(today.getDate() + 1);
        return tomorrow;
    }
    
    // Check for ISO format YYYY-MM-DD
    if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
        return new Date(dateStr);
    }
    
    // Check for format containing dot: DD.MM (e.g. 28.06)
    const dotMatch = str.match(/(\d+)\.(\d+)/);
    if (dotMatch) {
        const day = parseInt(dotMatch[1], 10);
        const month = parseInt(dotMatch[2], 10) - 1;
        return new Date(2026, month, day);
    }
    
    // Check for Romanian written dates: "Duminică 28 Iunie" or "1 Iulie"
    const months = {
        'ianuarie': 0, 'februarie': 1, 'martie': 2, 'aprilie': 3, 'mai': 4, 'iunie': 5,
        'iulie': 6, 'august': 7, 'septembrie': 8, 'octombrie': 9, 'noiembrie': 10, 'decembrie': 11
    };
    
    const words = str.split(/\s+/);
    let day = null;
    let month = null;
    
    for (const word of words) {
        const num = parseInt(word, 10);
        if (!isNaN(num)) {
            day = num;
        } else if (months[word] !== undefined) {
            month = months[word];
        }
    }
    
    if (day !== null) {
        if (month === null) {
            month = day >= 27 ? 5 : 6; 
        }
        return new Date(2026, month, day);
    }
    
    return today;
}

function renderMatches() {
    const container = document.getElementById('matches-container');
    const streamingContainer = document.getElementById('streaming-matches-container');
    if (!container) return;
    
    // Split matches
    const cinemaMatches = state.matches.filter(m => m.type !== 'streaming');
    const streamingMatches = state.matches.filter(m => m.type === 'streaming');
    
    // 1. Render Cinema matches
    const sortedCinema = [...cinemaMatches].filter(match => {
        const sDate = parseScreeningDate(match.date);
        if (match.time) {
            const timeMatch = match.time.match(/(\d+)[:.](\d+)/);
            if (timeMatch) {
                sDate.setHours(parseInt(timeMatch[1], 10), parseInt(timeMatch[2], 10), 0, 0);
            }
        } else {
            sDate.setHours(23, 59, 59, 999);
        }
        return sDate.getTime() >= new Date().getTime();
    }).sort((a, b) => {
        const timeA = parseScreeningDate(a.date).getTime();
        const timeB = parseScreeningDate(b.date).getTime();
        if (timeA !== timeB) return timeA - timeB;
        if (a.time !== b.time) return a.time.localeCompare(b.time);
        return a.cinema.localeCompare(b.cinema);
    });

    if (sortedCinema.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-calendar-xmark"></i>
                <p>No upcoming screenings matched your watchlist.</p>
                <p style="font-size:12px; color:var(--text-muted); margin-top:5px;">Try adding more festival films to your watchlist and sync again.</p>
            </div>
        `;
    } else {
        container.innerHTML = sortedCinema.map(match => {
            const imdbUrl = match.imdb_url && match.imdb_url !== 'https://www.imdb.com/' && match.imdb_url !== 'https://www.imdb.com'
                ? match.imdb_url 
                : `https://www.imdb.com/find?q=${encodeURIComponent(match.title)}`;
                
            return `
                <div class="match-card">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; gap: 15px;">
                        <h4 style="margin: 0; font-size: 18px; font-weight: 600; line-height: 1.3; max-width: 65%; color: #f3f4f6;">${match.title}</h4>
                        <span class="card-badge" style="position: static; margin-bottom: 0; flex-shrink: 0;">Match Found</span>
                    </div>
                    <p class="director" style="margin-bottom: 2px;">Directed by ${match.director || 'Unknown'}</p>
                    <p class="director" style="margin-bottom: 15px;">Country: ${match.country && match.country !== 'Unknown' ? match.country : 'Unknown'}</p>
                    
                    <div class="screening-details">
                        <div class="detail-row">
                            <i class="fa-solid fa-building-columns"></i>
                            <span class="cinema-name">${match.cinema}</span>
                        </div>
                        <div class="detail-row">
                            <i class="fa-solid fa-calendar-days"></i>
                            <span>${match.date}</span>
                        </div>
                        <div class="detail-row">
                            <i class="fa-solid fa-clock"></i>
                            <span>${match.time}</span>
                        </div>
                    </div>
                    
                    <div class="card-footer">
                        <a href="${imdbUrl}" target="_blank" class="btn-card-link">
                            <i class="fa-brands fa-imdb" style="color: #f5c518;"></i> IMDb Details
                        </a>
                        <a href="${match.link || '#'}" target="_blank" class="btn-card-link btn-ticket"><i class="fa-solid fa-ticket"></i> Cinema tickets</a>
                    </div>
                </div>
            `;
        }).join('');
    }
    
    // 2. Render Streaming matches
    if (streamingContainer) {
        if (streamingMatches.length === 0) {
            streamingContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-tv-slash"></i>
                    <p>No streaming availability found on Netflix or TIFF Unlimited.</p>
                </div>
            `;
        } else {
            streamingContainer.innerHTML = streamingMatches.map(match => `
                <div class="match-card">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; gap: 15px;">
                        <h4 style="margin: 0; font-size: 18px; font-weight: 600; line-height: 1.3; max-width: 65%; color: #f3f4f6;">${match.title}</h4>
                        <span class="card-badge" style="position: static; margin-bottom: 0; flex-shrink: 0;">Streaming Available</span>
                    </div>
                    <p class="director" style="margin-bottom: 2px;">Directed by ${match.director || 'Unknown'}</p>
                    <p class="director" style="margin-bottom: 15px;">Country: ${match.country && match.country !== 'Unknown' ? match.country : 'Unknown'}</p>
                    
                    <div class="screening-details" style="margin-bottom: 18px;">
                        <div class="detail-row">
                            <i class="fa-solid fa-tv" style="color: #10b981;"></i>
                            <span class="cinema-name">${match.provider}</span>
                        </div>
                        <div class="detail-row">
                            <i class="fa-solid fa-circle-check" style="color: #10b981;"></i>
                            <span>Available to watch anytime</span>
                        </div>
                    </div>
                    
                    <div class="card-footer">
                        <a href="https://www.imdb.com/find?q=${encodeURIComponent(match.title)}" target="_blank" class="btn-card-link">
                            <i class="fa-brands fa-imdb" style="color: #f5c518;"></i> IMDb Details
                        </a>
                        <a href="${match.link}" target="_blank" class="btn-card-link" style="background: rgba(16, 185, 129, 0.15); color: #10b981; border-color: rgba(16, 185, 129, 0.3); transition: all 0.2s;" onmouseover="this.style.background='rgba(16, 185, 129, 0.25)'" onmouseout="this.style.background='rgba(16, 185, 129, 0.15)'">
                            <i class="fa-solid fa-circle-play"></i> Watch Now
                        </a>
                    </div>
                </div>
            `).join('');
        }
    }
}

function updateWatchlistCounts() {
    const countEl = document.getElementById('watchlist-count');
    if (countEl) {
        countEl.textContent = state.watchlist.length;
    }
}

// Toast Notifications
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let iconClass = 'fa-circle-info';
    if (type === 'success') iconClass = 'fa-circle-check';
    if (type === 'error') iconClass = 'fa-triangle-exclamation';
    
    toast.innerHTML = `
        <i class="fa-solid ${iconClass}"></i>
        <p>${message}</p>
    `;
    
    container.appendChild(toast);
    
    // Auto-remove after 3 seconds
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s reverse';
        setTimeout(() => {
            if (toast.parentNode === container) {
                container.removeChild(toast);
            }
        }, 300);
    }, 3000);
}

// Utility: Escape HTML strings to prevent XSS
function escapeHtml(str) {
    if (!str) return '';
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}


