<script lang="ts">
	import { onMount } from "svelte";

	import {
		clearCsrfToken,
		panelApi,
		setCsrfToken,
		setUnauthorizedHandler,
	} from "../api/api";
	import ActivityView from "./lib/components/ActivityView.svelte";
	import CreateServerDialog from "./lib/components/CreateServerDialog.svelte";
	import DeleteServerDialog from "./lib/components/DeleteServerDialog.svelte";
	import LoginView from "./lib/components/LoginView.svelte";
	import LogsDialog from "./lib/components/LogsDialog.svelte";
	import ModDialog from "./lib/components/ModDialog.svelte";
	import ServerDetail, {
		type DetailTab,
	} from "./lib/components/ServerDetail.svelte";
	import ServerList from "./lib/components/ServerList.svelte";
	import ToastRegion, {
		type ToastMessage,
	} from "./lib/components/ToastRegion.svelte";
	import type {
		ActivityEvent,
		CreateServerInput,
		GameServer,
	} from "./lib/types";

	type AppView = "loading" | "login" | "app";
	type Page = "servers" | "activity";

	let view = $state<AppView>("loading");
	let username = $state("");
	let loginBusy = $state(false);
	let loginError = $state("");
	let servers = $state<GameServer[]>([]);
	let selectedId = $state<string | null>(null);
	let currentPage = $state<Page>("servers");
	let detailTab = $state<DetailTab>("overview");
	let healthLabel = $state("Checking host");
	let healthClass = $state("status-unknown");
	let events = $state<ActivityEvent[]>([]);
	let eventsLoading = $state(false);
	let busyAction = $state<string | null>(null);
	let createOpen = $state(false);
	let createBusy = $state(false);
	let createError = $state("");
	let modOpen = $state(false);
	let logsOpen = $state(false);
	let logs = $state("");
	let logsLoading = $state(false);
	let deleteOpen = $state(false);
	let deleteBusy = $state(false);
	let deleteError = $state("");
	let toasts = $state<ToastMessage[]>([]);
	let toastId = 0;

	let selectedServer = $derived(
		servers.find((server) => server.id === selectedId) ?? null,
	);

	onMount(() => {
		setUnauthorizedHandler(showLogin);
		restoreSession();
		const pollingTimer = window.setInterval(() => {
			if (!document.hidden && view === "app") loadServers(true);
		}, 8000);

		return () => {
			window.clearInterval(pollingTimer);
			setUnauthorizedHandler(() => undefined);
		};
	});

	async function restoreSession() {
		try {
			const session = await panelApi.session();
			establishSession(session.username, session.csrf_token);
			await Promise.all([loadServers(), checkHealth(), loadEvents()]);
		} catch {
			showLogin();
		}
	}

	async function login(loginUsername: string, password: string) {
		loginBusy = true;
		loginError = "";
		try {
			const session = await panelApi.login(loginUsername, password);
			establishSession(session.username, session.csrf_token);
			await Promise.all([loadServers(), checkHealth(), loadEvents()]);
		} catch (error) {
			loginError = messageFrom(error);
		} finally {
			loginBusy = false;
		}
	}

	async function logout() {
		try {
			await panelApi.logout();
		} catch {
			// Local state is still cleared if the server session has already expired.
		}
		showLogin();
	}

	function establishSession(sessionUsername: string, csrfToken: string) {
		username = sessionUsername;
		setCsrfToken(csrfToken);
		view = "app";
	}

	function showLogin() {
		clearCsrfToken();
		username = "";
		servers = [];
		selectedId = null;
		createOpen = false;
		modOpen = false;
		logsOpen = false;
		deleteOpen = false;
		view = "login";
	}

	async function checkHealth() {
		try {
			const health = await panelApi.health();
			healthLabel = health.docker
				? "Docker connected"
				: "Docker unavailable";
			healthClass = health.docker
				? "status-running"
				: "status-unavailable";
		} catch {
			healthLabel = "Host unavailable";
			healthClass = "status-unavailable";
		}
	}

	async function loadServers(silent = false) {
		try {
			const loadedServers = await panelApi.servers();
			servers = loadedServers;
			if (
				selectedId &&
				!loadedServers.some((server) => server.id === selectedId)
			) {
				selectedId = null;
			}
			if (!selectedId && loadedServers.length > 0)
				selectedId = loadedServers[0].id;
		} catch (error) {
			if (!silent) showToast(messageFrom(error), true);
		}
	}

	async function loadEvents() {
		eventsLoading = true;
		try {
			events = await panelApi.events();
		} catch (error) {
			showToast(messageFrom(error), true);
		} finally {
			eventsLoading = false;
		}
	}

	function setPage(page: Page) {
		currentPage = page;
		if (page === "activity") loadEvents();
	}

	function selectServer(serverId: string) {
		selectedId = serverId;
		detailTab = "overview";
		if (window.innerWidth <= 800) {
			requestAnimationFrame(() =>
				document.querySelector(".server-detail")?.scrollIntoView({
					behavior: "smooth",
					block: "start",
				}),
			);
		}
	}

	async function createServer(input: CreateServerInput) {
		createBusy = true;
		createError = "";
		try {
			const server = await panelApi.createServer(input);
			selectedId = server.id;
			detailTab = "overview";
			createOpen = false;
			showToast(`${server.name} is provisioning.`);
			await Promise.all([loadServers(), loadEvents()]);
		} catch (error) {
			createError = messageFrom(error);
		} finally {
			createBusy = false;
		}
	}

	async function runServerAction(action: string) {
		if (!selectedServer) return;
		const serverName = selectedServer.name;
		busyAction = action;
		try {
			await panelApi.runServerAction(selectedServer.id, action);
			showToast(`${serverName}: ${action} requested.`);
			await Promise.all([loadServers(), loadEvents()]);
		} catch (error) {
			showToast(messageFrom(error), true);
		} finally {
			busyAction = null;
		}
	}

	async function removeMod(sourceId: string) {
		if (!selectedServer) return;
		busyAction = `remove-${sourceId}`;
		try {
			const updated = await panelApi.removeMod(
				selectedServer.id,
				sourceId,
			);
			replaceServer(updated);
			showToast("Mod removed and server redeployed.");
			await loadEvents();
		} catch (error) {
			showToast(messageFrom(error), true);
		} finally {
			busyAction = null;
		}
	}

	function handleModChange(updated: GameServer, message: string) {
		replaceServer(updated);
		detailTab = "mods";
		showToast(message);
		loadEvents();
	}

	function replaceServer(updated: GameServer) {
		servers = servers.map((server) =>
			server.id === updated.id ? updated : server,
		);
	}

	function openLogs() {
		if (!selectedServer) return;
		logs = "";
		logsOpen = true;
		loadLogs();
	}

	async function loadLogs() {
		if (!selectedServer) return;
		logsLoading = true;
		try {
			const result = await panelApi.logs(selectedServer.id);
			logs = result.logs || "No output yet.";
		} catch (error) {
			logs = messageFrom(error);
		} finally {
			logsLoading = false;
		}
	}

	async function deleteServer(deleteData: boolean) {
		if (!selectedServer) return;
		const serverName = selectedServer.name;
		deleteBusy = true;
		deleteError = "";
		try {
			await panelApi.deleteServer(selectedServer.id, deleteData);
			selectedId = null;
			deleteOpen = false;
			showToast(`${serverName} deleted.`);
			await Promise.all([loadServers(), loadEvents()]);
		} catch (error) {
			deleteError = messageFrom(error);
		} finally {
			deleteBusy = false;
		}
	}

	function showToast(message: string, error = false) {
		const id = ++toastId;
		toasts = [...toasts, { id, message, error }];
		window.setTimeout(() => {
			toasts = toasts.filter((toast) => toast.id !== id);
		}, 4200);
	}

	function messageFrom(value: unknown): string {
		return value instanceof Error
			? value.message
			: "The request could not be completed.";
	}
</script>

<svelte:head>
	<title>Dedodaded</title>
	<meta name="color-scheme" content="light" />
	<meta name="theme-color" content="#191a18" />
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link
		rel="preconnect"
		href="https://fonts.gstatic.com"
		crossorigin="anonymous"
	/>
	<link
		href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&amp;family=IBM+Plex+Mono:wght@400;500;600&amp;display=swap"
		rel="stylesheet"
	/>
</svelte:head>

<div class="noise" aria-hidden="true"></div>
<ToastRegion {toasts} />

{#if view === "loading"}
	<main class="startup-view" aria-live="polite">
		<div class="brand brand-large">
			<span class="brand-mark" aria-hidden="true">D</span>
			<span>Dedodaded</span>
		</div>
		<p>Opening control plane...</p>
	</main>
{:else if view === "login"}
	<LoginView busy={loginBusy} error={loginError} onlogin={login} />
{:else}
	<div class="app-shell">
		<aside class="sidebar">
			<div class="brand brand-sidebar">
				<span class="brand-mark" aria-hidden="true">D</span>
				<span class="brand-word">Dedodaded</span>
			</div>
			<nav class="primary-nav" aria-label="Primary navigation">
				<button
					class="nav-button"
					class:is-active={currentPage === "servers"}
					type="button"
					onclick={() => setPage("servers")}
					aria-current={currentPage === "servers"
						? "page"
						: undefined}
				>
					<span class="nav-symbol" aria-hidden="true">▤</span><span
						>Servers</span
					>
				</button>
				<button
					class="nav-button"
					class:is-active={currentPage === "activity"}
					type="button"
					onclick={() => setPage("activity")}
					aria-current={currentPage === "activity"
						? "page"
						: undefined}
				>
					<span class="nav-symbol" aria-hidden="true">⌁</span><span
						>Activity</span
					>
				</button>
			</nav>
			<div class="sidebar-foot">
				<div class="host-health">
					<span class={`status-dot ${healthClass}`}></span><span
						>{healthLabel}</span
					>
				</div>
				<button class="nav-button" type="button" onclick={logout}>
					<span class="nav-symbol" aria-hidden="true">↪</span><span
						>Sign out</span
					>
				</button>
			</div>
		</aside>

		<header class="topbar">
			<div>
				<p class="eyebrow">Control plane</p>
				<h1>{currentPage === "activity" ? "Activity" : "Servers"}</h1>
			</div>
			<div class="topbar-actions">
				<span class="user-chip">{username}</span>
				<button
					class="button button-primary"
					type="button"
					onclick={() => (createOpen = true)}
				>
					<span class="button-symbol" aria-hidden="true">+</span><span
						>New server</span
					>
				</button>
			</div>
		</header>

		<main class="main-content">
			{#if currentPage === "servers"}
				<section class="page servers-page">
					<ServerList
						{servers}
						{selectedId}
						oncreate={() => (createOpen = true)}
						onselect={selectServer}
					/>
					<ServerDetail
						server={selectedServer}
						{detailTab}
						{busyAction}
						onaction={runServerAction}
						oncreate={() => (createOpen = true)}
						ondelete={() => (deleteOpen = true)}
						onlogs={openLogs}
						onmods={() => (modOpen = true)}
						onremovemod={removeMod}
						ontab={(tab) => (detailTab = tab)}
					/>
				</section>
			{:else}
				<ActivityView
					{events}
					loading={eventsLoading}
					onrefresh={loadEvents}
				/>
			{/if}
		</main>
	</div>

	<CreateServerDialog
		open={createOpen}
		busy={createBusy}
		error={createError}
		onclose={() => (createOpen = false)}
		oncreate={createServer}
	/>
	<ModDialog
		open={modOpen}
		server={selectedServer}
		onclose={() => (modOpen = false)}
		onchange={handleModChange}
	/>
	<LogsDialog
		open={logsOpen}
		serverName={selectedServer?.name ?? ""}
		{logs}
		loading={logsLoading}
		onclose={() => (logsOpen = false)}
		onrefresh={loadLogs}
	/>
	<DeleteServerDialog
		open={deleteOpen}
		server={selectedServer}
		busy={deleteBusy}
		error={deleteError}
		onclose={() => (deleteOpen = false)}
		onconfirm={deleteServer}
	/>
{/if}
