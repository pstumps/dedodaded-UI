const APP_BASE_URL = new URL("./", document.baseURI);

function appUrl(path) {
    return new URL(path.replace(/^\/+/, ""), APP_BASE_URL).toString();
}

const GAME_META = {
    "project-zomboid": {
        label: "Project Zomboid",
        image: appUrl("assets/project-zomboid.png"),
        source: "Steam Workshop",
    },
    valheim: {
        label: "Valheim",
        image: appUrl("assets/valheim.png"),
        source: "Thunderstore",
    },
};

const state = {
    csrfToken: "",
    username: "",
    servers: [],
    selectedId: null,
    detailTab: "overview",
    currentPage: "servers",
    workshopItem: null,
    logsServerId: null,
    modSearchTimer: null,
    pollingTimer: null,
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
    Object.assign(elements, {
        loginView: document.querySelector("#login-view"),
        loginForm: document.querySelector("#login-form"),
        loginError: document.querySelector("#login-error"),
        appShell: document.querySelector("#app-shell"),
        serverList: document.querySelector("#server-list"),
        serverDetail: document.querySelector("#server-detail"),
        serverCount: document.querySelector("#server-count"),
        dockerHealth: document.querySelector("#docker-health"),
        userChip: document.querySelector("#user-chip"),
        pageTitle: document.querySelector("#page-title"),
        serversPage: document.querySelector("#servers-page"),
        activityPage: document.querySelector("#activity-page"),
        eventList: document.querySelector("#event-list"),
        createDialog: document.querySelector("#create-dialog"),
        createForm: document.querySelector("#create-form"),
        createError: document.querySelector("#create-error"),
        modDialog: document.querySelector("#mod-dialog"),
        modDialogTitle: document.querySelector("#mod-dialog-title"),
        modSourceLabel: document.querySelector("#mod-source-label"),
        modDialogBody: document.querySelector("#mod-dialog-body"),
        logsDialog: document.querySelector("#logs-dialog"),
        logsTitle: document.querySelector("#logs-title"),
        logsOutput: document.querySelector("#logs-output"),
        deleteDialog: document.querySelector("#delete-dialog"),
        deleteForm: document.querySelector("#delete-form"),
        deleteCopy: document.querySelector("#delete-copy"),
        toastRegion: document.querySelector("#toast-region"),
    });

    bindEvents();
    refreshIcons();
    restoreSession();
});

function bindEvents() {
    elements.loginForm.addEventListener("submit", login);
    elements.createForm.addEventListener("submit", createServer);
    elements.createForm.addEventListener("change", (event) => {
        if (event.target.name === "game") updateCreateGame();
        if (event.target.name === "port") updatePortSummary();
    });
    elements.createForm.addEventListener("input", (event) => {
        if (event.target.name === "port") updatePortSummary();
    });
    elements.deleteForm.addEventListener("submit", deleteServer);
    document.querySelector("#logout-button").addEventListener("click", logout);
    document.querySelector("#refresh-events").addEventListener("click", loadEvents);
    document.querySelector("#refresh-logs").addEventListener("click", loadLogs);

    document.addEventListener("click", async (event) => {
        const target = event.target.closest("button, [data-toggle-password]");
        if (!target) return;
        if (target.matches("[data-open-create]")) openCreateDialog();
        if (target.matches("[data-close-dialog]")) target.closest("dialog")?.close();
        if (target.dataset.togglePassword) togglePassword(target);
        if (target.dataset.page) setPage(target.dataset.page);
        if (target.dataset.serverId) selectServer(target.dataset.serverId);
        if (target.dataset.detailTab) {
            state.detailTab = target.dataset.detailTab;
            renderServerDetail();
        }
        if (target.dataset.serverAction) await runServerAction(target.dataset.serverAction, target);
        if (target.dataset.openMods) openModDialog();
        if (target.dataset.openLogs) openLogsDialog();
        if (target.dataset.openDelete) openDeleteDialog();
        if (target.dataset.removeMod) await removeMod(target.dataset.removeMod, target);
        if (target.dataset.installValheim) await installValheimMod(target.dataset.installValheim, target);
        if (target.dataset.lookupWorkshop) await lookupWorkshop(target);
    });

    document.addEventListener("submit", async (event) => {
        if (event.target.id === "zomboid-mod-form") {
            event.preventDefault();
            await installZomboidMod(event.target);
        }
    });

    document.addEventListener("input", (event) => {
        if (event.target.id === "valheim-mod-search") scheduleValheimSearch(event.target.value);
    });
}

async function restoreSession() {
    try {
        const session = await api("/api/auth/session", {}, false);
        state.csrfToken = session.csrf_token;
        state.username = session.username;
        showApp();
        await Promise.all([loadServers(), checkHealth(), loadEvents()]);
        startPolling();
    } catch {
        showLogin();
    }
}

async function login(event) {
    event.preventDefault();
    const button = event.submitter;
    setBusy(button, true);
    elements.loginError.textContent = "";
    const data = Object.fromEntries(new FormData(elements.loginForm));
    try {
        const session = await api("/api/auth/login", { method: "POST", body: data }, false);
        state.csrfToken = session.csrf_token;
        state.username = session.username;
        elements.loginForm.reset();
        showApp();
        await Promise.all([loadServers(), checkHealth(), loadEvents()]);
        startPolling();
    } catch (error) {
        elements.loginError.textContent = error.message;
    } finally {
        setBusy(button, false);
    }
}

async function logout() {
    try {
        await api("/api/auth/logout", { method: "POST" });
    } catch {
        // Local sign-out still clears the panel state if the session has expired.
    }
    state.csrfToken = "";
    state.servers = [];
    state.selectedId = null;
    clearInterval(state.pollingTimer);
    showLogin();
}

function showApp() {
    elements.loginView.hidden = true;
    elements.appShell.hidden = false;
    elements.userChip.textContent = state.username;
    refreshIcons();
}

function showLogin() {
    elements.appShell.hidden = true;
    elements.loginView.hidden = false;
    requestAnimationFrame(() => elements.loginForm.elements.username.focus());
    refreshIcons();
}

function startPolling() {
    clearInterval(state.pollingTimer);
    state.pollingTimer = setInterval(() => {
        if (!document.hidden && !elements.appShell.hidden) loadServers(true);
    }, 8000);
}

async function checkHealth() {
    try {
        const health = await api("/api/health", {}, false);
        elements.dockerHealth.innerHTML = `<span class="status-dot ${health.docker ? "status-running" : "status-unavailable"}"></span><span>${health.docker ? "Docker connected" : "Docker unavailable"}</span>`;
    } catch {
        elements.dockerHealth.innerHTML = '<span class="status-dot status-unavailable"></span><span>Host unavailable</span>';
    }
}

async function loadServers(silent = false) {
    try {
        const servers = await api("/api/servers");
        state.servers = servers;
        if (state.selectedId && !servers.some((server) => server.id === state.selectedId)) state.selectedId = null;
        if (!state.selectedId && servers.length) state.selectedId = servers[0].id;
        renderServers();
    } catch (error) {
        if (!silent) showToast(error.message, true);
    }
}

function renderServers() {
    elements.serverCount.textContent = String(state.servers.length);
    if (!state.servers.length) {
        elements.serverList.innerHTML = '<div class="empty-rail">No instances on this host.</div>';
    } else {
        elements.serverList.innerHTML = state.servers.map((server) => {
            const game = GAME_META[server.game];
            const selected = server.id === state.selectedId;
            return `<button class="server-list-item ${selected ? "is-selected" : ""}" type="button" data-server-id="${escapeHtml(server.id)}" ${selected ? 'aria-current="true"' : ""}>
                <img class="server-thumb" src="${game.image}" alt="">
                <span class="server-list-copy"><strong>${escapeHtml(server.name)}</strong><span>${game.label}</span></span>
                <span class="status-dot ${statusClass(server.runtime.state)}" title="${escapeHtml(statusLabel(server.runtime.state))}"></span>
            </button>`;
        }).join("");
    }
    renderServerDetail();
    refreshIcons();
}

function renderServerDetail() {
    const server = selectedServer();
    if (!server) {
        elements.serverDetail.innerHTML = `<div class="detail-empty"><div><div class="empty-sigil"><i data-lucide="server-off"></i></div><h2>No server selected</h2><p>Provision an instance to begin.</p><button class="button button-primary" type="button" data-open-create><i data-lucide="plus"></i><span>New server</span></button></div></div>`;
        refreshIcons();
        return;
    }
    const game = GAME_META[server.game];
    const running = server.runtime.state === "running";
    elements.serverDetail.innerHTML = `
        <div class="detail-hero">
            <img class="detail-art" src="${game.image}" alt="${game.label}">
            <div class="detail-title">
                <p class="eyebrow">${game.label}</p>
                <h2>${escapeHtml(server.name)}</h2>
                <div class="detail-meta">
                    <span class="status-label"><span class="status-dot ${statusClass(server.runtime.state)}"></span>${escapeHtml(statusLabel(server.runtime.state))}</span>
                    <span>${escapeHtml(window.location.hostname || "localhost")}:${server.port}</span>
                    <span>${server.max_players} slots</span>
                </div>
            </div>
            <div class="hero-actions">
                <button class="button ${running ? "button-secondary" : "button-primary"}" type="button" data-server-action="${running ? "stop" : "start"}"><i data-lucide="${running ? "square" : "play"}"></i><span>${running ? "Stop" : "Start"}</span></button>
                <button class="icon-button" type="button" data-server-action="restart" title="Restart server" aria-label="Restart server"><i data-lucide="rotate-cw"></i></button>
                <button class="icon-button" type="button" data-open-logs title="View logs" aria-label="View logs"><i data-lucide="scroll-text"></i></button>
            </div>
        </div>
        <div class="detail-tabs" role="tablist">
            <button class="tab-button ${state.detailTab === "overview" ? "is-active" : ""}" type="button" role="tab" aria-selected="${state.detailTab === "overview"}" data-detail-tab="overview">Overview</button>
            <button class="tab-button ${state.detailTab === "mods" ? "is-active" : ""}" type="button" role="tab" aria-selected="${state.detailTab === "mods"}" data-detail-tab="mods">Mods <span class="count-badge">${server.mods.length}</span></button>
        </div>
        <div class="detail-body">${state.detailTab === "mods" ? renderMods(server) : renderOverview(server)}</div>`;
    refreshIcons();
}

function renderOverview(server) {
    const game = GAME_META[server.game];
    return `<div class="overview-grid">
        <div>
            <section class="subsection">
                <div class="subsection-heading"><h3>Runtime</h3></div>
                <dl class="fact-list">
                    ${factRow("State", statusLabel(server.runtime.state))}
                    ${factRow("Address", `${window.location.hostname || "localhost"}:${server.port}`, true)}
                    ${factRow("UDP range", `${server.port}–${server.port_end}`, true)}
                    ${factRow("Public", server.public ? "Listed" : "Private")}
                </dl>
            </section>
            <section class="subsection">
                <div class="subsection-heading"><h3>Game configuration</h3></div>
                <dl class="fact-list">
                    ${factRow("Game", game.label)}
                    ${factRow("World", server.world_name)}
                    ${factRow("Player slots", String(server.max_players))}
                    ${factRow("Mod source", game.source)}
                </dl>
            </section>
        </div>
        <aside>
            <section class="subsection">
                <div class="subsection-heading"><h3>Operations</h3></div>
                <div class="action-stack">
                    <button class="button button-secondary" type="button" data-server-action="update"><i data-lucide="package-up"></i><span>Pull update and redeploy</span></button>
                    <button class="button button-secondary" type="button" data-open-logs><i data-lucide="scroll-text"></i><span>Open container logs</span></button>
                    <button class="button button-secondary" type="button" data-open-mods><i data-lucide="blocks"></i><span>Add a mod</span></button>
                </div>
            </section>
            <section class="danger-zone">
                <h3>Delete instance</h3>
                <p>The container can be removed while world data remains on disk.</p>
                <button class="button button-quiet" type="button" data-open-delete><i data-lucide="trash-2"></i><span>Delete server</span></button>
            </section>
        </aside>
    </div>`;
}

function renderMods(server) {
    const rows = server.mods.length ? server.mods.map((mod) => `
        <div class="mod-row">
            <span class="mod-icon"><i data-lucide="puzzle"></i></span>
            <span class="mod-copy"><strong>${escapeHtml(mod.name)}</strong><span>${escapeHtml(mod.mod_id || mod.source_id)}</span></span>
            <span class="mod-version">${escapeHtml(mod.version || "")}</span>
            <button class="icon-button" type="button" data-remove-mod="${escapeHtml(mod.source_id)}" title="Remove ${escapeHtml(mod.name)}" aria-label="Remove ${escapeHtml(mod.name)}"><i data-lucide="trash-2"></i></button>
        </div>`).join("") : `<div class="empty-mods"><div><i data-lucide="blocks"></i><p>No mods installed</p></div></div>`;
    return `<div class="mod-header"><div><h3>Installed mods</h3><p>${GAME_META[server.game].source}</p></div><button class="button button-primary" type="button" data-open-mods><i data-lucide="plus"></i><span>Add mod</span></button></div><div class="mod-list">${rows}</div>`;
}

function factRow(label, value, mono = false) {
    return `<div class="fact-row"><dt>${label}</dt><dd class="${mono ? "mono" : ""}">${escapeHtml(value)}</dd></div>`;
}

function selectServer(id) {
    state.selectedId = id;
    state.detailTab = "overview";
    renderServers();
    if (window.innerWidth <= 800) elements.serverDetail.scrollIntoView({ behavior: "smooth", block: "start" });
}

function openCreateDialog() {
    elements.createForm.reset();
    elements.createForm.elements.game.value = "project-zomboid";
    elements.createForm.elements.world_name.value = "Knox";
    elements.createForm.elements.port.value = "16261";
    elements.createForm.elements.max_players.value = "16";
    elements.createForm.elements.public.checked = true;
    elements.createError.textContent = "";
    updateCreateGame();
    elements.createDialog.showModal();
    requestAnimationFrame(() => elements.createForm.elements.name.focus());
}

function updateCreateGame() {
    const game = elements.createForm.elements.game.value;
    document.querySelectorAll(".game-choice").forEach((choice) => choice.classList.toggle("is-selected", choice.querySelector("input").checked));
    const adminField = document.querySelector("#admin-password-field");
    const adminInput = elements.createForm.elements.admin_password;
    const playerInput = elements.createForm.elements.max_players;
    if (game === "valheim") {
        elements.createForm.elements.world_name.value = "Dedicated";
        elements.createForm.elements.port.value = "2456";
        playerInput.value = "10";
        playerInput.max = "10";
        adminField.hidden = true;
        adminInput.required = false;
        adminInput.value = "";
        elements.createForm.elements.password.minLength = 5;
    } else {
        elements.createForm.elements.world_name.value = "Knox";
        elements.createForm.elements.port.value = "16261";
        playerInput.value = "16";
        playerInput.max = "100";
        adminField.hidden = false;
        adminInput.required = true;
        elements.createForm.elements.password.minLength = 0;
    }
    updatePortSummary();
}

function updatePortSummary() {
    const game = elements.createForm.elements.game.value;
    const port = Number(elements.createForm.elements.port.value || 0);
    const end = port + (game === "valheim" ? 2 : 1);
    document.querySelector("#port-summary").textContent = port ? `UDP ${port}–${end}` : "UDP port range";
}

async function createServer(event) {
    event.preventDefault();
    if (!elements.createForm.reportValidity()) return;
    const button = event.submitter;
    const form = new FormData(elements.createForm);
    const body = {
        game: form.get("game"),
        name: form.get("name"),
        world_name: form.get("world_name"),
        password: form.get("password"),
        admin_password: form.get("admin_password") || "",
        port: Number(form.get("port")),
        max_players: Number(form.get("max_players")),
        public: form.get("public") === "on",
    };
    setBusy(button, true);
    elements.createError.textContent = "";
    try {
        const server = await api("/api/servers", { method: "POST", body });
        state.selectedId = server.id;
        state.detailTab = "overview";
        elements.createDialog.close();
        showToast(`${server.name} is provisioning.`);
        await Promise.all([loadServers(), loadEvents()]);
    } catch (error) {
        elements.createError.textContent = error.message;
    } finally {
        setBusy(button, false);
    }
}

async function runServerAction(action, button) {
    const server = selectedServer();
    if (!server) return;
    setBusy(button, true);
    try {
        await api(`/api/servers/${encodeURIComponent(server.id)}/actions/${action}`, { method: "POST" });
        showToast(`${server.name}: ${action} requested.`);
        await Promise.all([loadServers(), loadEvents()]);
    } catch (error) {
        showToast(error.message, true);
    } finally {
        setBusy(button, false);
    }
}

function openModDialog() {
    const server = selectedServer();
    if (!server) return;
    elements.modDialogTitle.textContent = `Add to ${server.name}`;
    elements.modSourceLabel.textContent = GAME_META[server.game].source;
    if (server.game === "valheim") {
        elements.modDialogBody.innerHTML = `<label class="mod-search"><input id="valheim-mod-search" type="search" maxlength="100" placeholder="Search Thunderstore" autocomplete="off"><i data-lucide="search"></i></label><div id="valheim-search-results" class="search-results"><div class="loading-row">Popular packages load here</div></div>`;
        elements.modDialog.showModal();
        searchValheimMods("");
        requestAnimationFrame(() => document.querySelector("#valheim-mod-search").focus());
    } else {
        state.workshopItem = null;
        elements.modDialogBody.innerHTML = `<form id="zomboid-mod-form" class="workshop-form">
            <div class="lookup-row">
                <label class="field"><span>Steam Workshop ID</span><input name="workshop_id" inputmode="numeric" pattern="[0-9]+" maxlength="32" required placeholder="2169435993"></label>
                <button class="button button-secondary" type="button" data-lookup-workshop><i data-lucide="search"></i><span>Lookup</span></button>
            </div>
            <div id="workshop-preview"></div>
            <label class="field"><span>Internal mod ID</span><input name="mod_id" pattern="[A-Za-z0-9_.-]+" maxlength="160" required placeholder="modoptions"></label>
            <p id="zomboid-mod-error" class="form-error" role="alert"></p>
            <button class="button button-primary" type="submit" disabled><i data-lucide="plus"></i><span>Add and redeploy</span></button>
        </form>`;
        elements.modDialog.showModal();
        requestAnimationFrame(() => document.querySelector("#zomboid-mod-form [name=workshop_id]").focus());
    }
    refreshIcons();
}

function scheduleValheimSearch(query) {
    clearTimeout(state.modSearchTimer);
    state.modSearchTimer = setTimeout(() => searchValheimMods(query), 280);
}

async function searchValheimMods(query) {
    const results = document.querySelector("#valheim-search-results");
    if (!results) return;
    results.innerHTML = '<div class="loading-row"><i data-lucide="loader-circle"></i></div>';
    refreshIcons();
    try {
        const packages = await api(`/api/mods/valheim/search?q=${encodeURIComponent(query)}`);
        results.innerHTML = packages.length ? packages.map((item) => {
            const image = item.icon_url ? `<img src="${escapeHtml(item.icon_url)}" alt="">` : '<span class="result-placeholder"><i data-lucide="package"></i></span>';
            return `<div class="search-result">${image}<div class="search-result-copy"><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.owner)} · ${escapeHtml(item.version)} · ${formatNumber(item.downloads)} downloads</span><p>${escapeHtml(item.description || "")}</p></div><button class="button button-secondary button-small" type="button" data-install-valheim="${escapeHtml(item.package_id)}"><i data-lucide="plus"></i><span>Install</span></button></div>`;
        }).join("") : '<div class="loading-row">No packages found</div>';
    } catch (error) {
        results.innerHTML = `<div class="loading-row">${escapeHtml(error.message)}</div>`;
    }
    refreshIcons();
}

async function installValheimMod(packageId, button) {
    const server = selectedServer();
    if (!server) return;
    setBusy(button, true);
    try {
        await api(`/api/servers/${encodeURIComponent(server.id)}/mods/valheim`, { method: "POST", body: { package_id: packageId } });
        elements.modDialog.close();
        state.detailTab = "mods";
        showToast(`${packageId} installed with dependencies.`);
        await Promise.all([loadServers(), loadEvents()]);
    } catch (error) {
        showToast(error.message, true);
    } finally {
        setBusy(button, false);
    }
}

async function lookupWorkshop(button) {
    const form = document.querySelector("#zomboid-mod-form");
    const input = form?.elements.workshop_id;
    if (!input || !input.reportValidity()) return;
    setBusy(button, true);
    const error = document.querySelector("#zomboid-mod-error");
    error.textContent = "";
    try {
        const item = await api("/api/mods/project-zomboid/lookup", { method: "POST", body: { workshop_id: input.value } });
        state.workshopItem = item;
        const image = item.preview_url ? `<img src="${escapeHtml(item.preview_url)}" alt="">` : '<span class="result-placeholder"><i data-lucide="image"></i></span>';
        document.querySelector("#workshop-preview").innerHTML = `<div class="workshop-preview">${image}<div class="workshop-preview-copy"><p class="eyebrow">Workshop ${escapeHtml(item.workshop_id)}</p><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.description)}</p></div></div>`;
        form.querySelector("button[type=submit]").disabled = false;
        refreshIcons();
    } catch (lookupError) {
        state.workshopItem = null;
        form.querySelector("button[type=submit]").disabled = true;
        error.textContent = lookupError.message;
    } finally {
        setBusy(button, false);
    }
}

async function installZomboidMod(form) {
    const server = selectedServer();
    if (!server || !state.workshopItem || !form.reportValidity()) return;
    const button = form.querySelector("button[type=submit]");
    const error = document.querySelector("#zomboid-mod-error");
    setBusy(button, true);
    error.textContent = "";
    try {
        await api(`/api/servers/${encodeURIComponent(server.id)}/mods/project-zomboid`, {
            method: "POST",
            body: {
                workshop_id: state.workshopItem.workshop_id,
                name: state.workshopItem.title,
                mod_id: form.elements.mod_id.value,
            },
        });
        elements.modDialog.close();
        state.detailTab = "mods";
        showToast(`${state.workshopItem.title} installed.`);
        await Promise.all([loadServers(), loadEvents()]);
    } catch (installError) {
        error.textContent = installError.message;
    } finally {
        setBusy(button, false);
    }
}

async function removeMod(sourceId, button) {
    const server = selectedServer();
    if (!server) return;
    setBusy(button, true);
    try {
        await api(`/api/servers/${encodeURIComponent(server.id)}/mods/${encodeURIComponent(sourceId)}`, { method: "DELETE" });
        showToast("Mod removed and server redeployed.");
        await Promise.all([loadServers(), loadEvents()]);
    } catch (error) {
        showToast(error.message, true);
    } finally {
        setBusy(button, false);
    }
}

function openLogsDialog() {
    const server = selectedServer();
    if (!server) return;
    state.logsServerId = server.id;
    elements.logsTitle.textContent = server.name;
    elements.logsOutput.textContent = "Loading…";
    elements.logsDialog.showModal();
    loadLogs();
}

async function loadLogs() {
    if (!state.logsServerId) return;
    elements.logsOutput.textContent = "Loading…";
    try {
        const result = await api(`/api/servers/${encodeURIComponent(state.logsServerId)}/logs?tail=300`);
        elements.logsOutput.textContent = result.logs || "No output yet.";
        elements.logsOutput.scrollTop = elements.logsOutput.scrollHeight;
    } catch (error) {
        elements.logsOutput.textContent = error.message;
    }
}

function openDeleteDialog() {
    const server = selectedServer();
    if (!server) return;
    elements.deleteForm.reset();
    elements.deleteCopy.textContent = `${server.name} will be stopped and its managed container removed.`;
    elements.deleteDialog.showModal();
}

async function deleteServer(event) {
    event.preventDefault();
    const server = selectedServer();
    if (!server) return;
    const button = event.submitter;
    const deleteData = new FormData(elements.deleteForm).get("delete_data") === "on";
    setBusy(button, true);
    try {
        await api(`/api/servers/${encodeURIComponent(server.id)}?delete_data=${deleteData}`, { method: "DELETE" });
        state.selectedId = null;
        elements.deleteDialog.close();
        showToast(`${server.name} deleted.`);
        await Promise.all([loadServers(), loadEvents()]);
    } catch (error) {
        showToast(error.message, true);
    } finally {
        setBusy(button, false);
    }
}

function setPage(page) {
    state.currentPage = page;
    document.querySelectorAll("[data-page]").forEach((button) => {
        const active = button.dataset.page === page;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-current", active ? "page" : "false");
    });
    elements.serversPage.hidden = page !== "servers";
    elements.activityPage.hidden = page !== "activity";
    elements.pageTitle.textContent = page === "activity" ? "Activity" : "Servers";
    if (page === "activity") loadEvents();
}

async function loadEvents() {
    try {
        const events = await api("/api/events");
        elements.eventList.innerHTML = events.length ? events.map((event) => `<div class="event-row"><span class="event-level"><span class="status-dot ${event.level === "error" ? "status-error" : "status-running"}"></span>${escapeHtml(event.level)}</span><span class="event-message">${escapeHtml(event.message)}</span><time class="event-time" datetime="${escapeHtml(event.created_at)}">${formatDate(event.created_at)}</time></div>`).join("") : '<div class="loading-row">No activity yet</div>';
    } catch (error) {
        elements.eventList.innerHTML = `<div class="loading-row">${escapeHtml(error.message)}</div>`;
    }
}

function selectedServer() {
    return state.servers.find((server) => server.id === state.selectedId) || null;
}

async function api(path, options = {}, includeSession = true) {
    const fetchOptions = { method: options.method || "GET", credentials: "same-origin", headers: { Accept: "application/json", ...(options.headers || {}) } };
    if (options.body !== undefined) {
        fetchOptions.headers["Content-Type"] = "application/json";
        fetchOptions.body = JSON.stringify(options.body);
    }
    if (["POST", "PUT", "PATCH", "DELETE"].includes(fetchOptions.method) && includeSession && state.csrfToken) {
        fetchOptions.headers["X-CSRF-Token"] = state.csrfToken;
    }
    const response = await fetch(appUrl(path), fetchOptions);
    if (response.status === 204) return null;
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : { detail: await response.text() };
    if (!response.ok) {
        if (response.status === 401 && includeSession) {
            state.csrfToken = "";
            showLogin();
        }
        throw new Error(errorMessage(payload));
    }
    return payload;
}

function errorMessage(payload) {
    if (typeof payload.detail === "string") return payload.detail;
    if (Array.isArray(payload.detail)) return payload.detail.map((item) => item.msg).join(" · ");
    return "The request could not be completed.";
}

function statusClass(status) {
    if (status === "running") return "status-running";
    if (["exited", "created", "paused", "not-created"].includes(status)) return "status-stopped";
    if (["error", "dead"].includes(status)) return "status-error";
    if (status === "unavailable") return "status-unavailable";
    return "status-unknown";
}

function statusLabel(status) {
    const labels = { running: "Online", exited: "Stopped", created: "Created", paused: "Paused", "not-created": "Not deployed", unavailable: "Host unavailable", dead: "Failed", error: "Error" };
    return labels[status] || status || "Unknown";
}

function togglePassword(button) {
    const input = document.getElementById(button.dataset.togglePassword);
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    button.title = show ? "Hide password" : "Show password";
    button.setAttribute("aria-label", button.title);
    button.innerHTML = `<i data-lucide="${show ? "eye-off" : "eye"}"></i>`;
    refreshIcons();
}

function setBusy(button, busy) {
    if (!button) return;
    button.disabled = busy;
    button.classList.toggle("is-busy", busy);
}

function showToast(message, isError = false) {
    const toast = document.createElement("div");
    toast.className = `toast ${isError ? "is-error" : ""}`;
    toast.innerHTML = `<i data-lucide="${isError ? "circle-alert" : "circle-check"}"></i><span>${escapeHtml(message)}</span>`;
    elements.toastRegion.append(toast);
    refreshIcons();
    setTimeout(() => toast.remove(), 4200);
}

function refreshIcons() {
    if (window.lucide) window.lucide.createIcons({ attrs: { "aria-hidden": "true" } });
}

function formatDate(value) {
    try {
        return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
    } catch {
        return value;
    }
}

function formatNumber(value) {
    return new Intl.NumberFormat(undefined, { notation: "compact" }).format(Number(value || 0));
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
}