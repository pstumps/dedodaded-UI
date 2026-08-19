<script lang="ts">
	import { panelApi } from "../../../api/api";
	import { formatNumber, gameMeta } from "../domain";
	import type {
		GameServer,
		ThunderstorePackage,
		WorkshopItem,
	} from "../types";

	interface Props {
		open: boolean;
		server: GameServer | null;
		onclose: () => void;
		onchange: (server: GameServer, message: string) => void;
	}

	let { open, server, onclose, onchange }: Props = $props();
	let dialog: HTMLDialogElement;
	let searchInput = $state<HTMLInputElement>();
	let workshopInput = $state<HTMLInputElement>();
	let query = $state("");
	let packages = $state<ThunderstorePackage[]>([]);
	let workshopId = $state("");
	let modId = $state("");
	let workshopItem = $state<WorkshopItem | null>(null);
	let loading = $state(false);
	let busyId = $state<string | null>(null);
	let error = $state("");
	let searchRequest = 0;

	$effect(() => {
		if (open && !dialog.open) {
			reset();
			dialog.showModal();
			requestAnimationFrame(() => {
				if (server?.game === "valheim") searchInput?.focus();
				else workshopInput?.focus();
			});
		} else if (!open && dialog.open) {
			dialog.close();
		}
	});

	$effect(() => {
		if (!open || server?.game !== "valheim") return;
		const currentQuery = query;
		const timer = window.setTimeout(() => searchValheim(currentQuery), 280);
		return () => window.clearTimeout(timer);
	});

	function reset() {
		query = "";
		packages = [];
		workshopId = "";
		modId = "";
		workshopItem = null;
		loading = false;
		busyId = null;
		error = "";
		searchRequest += 1;
	}

	async function searchValheim(searchQuery: string) {
		const requestId = ++searchRequest;
		loading = true;
		error = "";
		try {
			const results = await panelApi.searchValheimMods(searchQuery);
			if (requestId === searchRequest) packages = results;
		} catch (searchError) {
			if (requestId === searchRequest) error = messageFrom(searchError);
		} finally {
			if (requestId === searchRequest) loading = false;
		}
	}

	async function installValheim(packageId: string) {
		if (!server) return;
		busyId = packageId;
		error = "";
		try {
			const updated = await panelApi.installValheimMod(
				server.id,
				packageId,
			);
			onchange(updated, `${packageId} installed with dependencies.`);
			onclose();
		} catch (installError) {
			error = messageFrom(installError);
		} finally {
			busyId = null;
		}
	}

	async function lookupWorkshop() {
		if (!workshopInput?.reportValidity()) return;
		busyId = "lookup";
		error = "";
		workshopItem = null;
		try {
			workshopItem = await panelApi.lookupWorkshopItem(workshopId);
		} catch (lookupError) {
			error = messageFrom(lookupError);
		} finally {
			busyId = null;
		}
	}

	async function installZomboid(event: SubmitEvent) {
		event.preventDefault();
		if (!server || !workshopItem) return;
		busyId = "zomboid";
		error = "";
		try {
			const updated = await panelApi.installZomboidMod(
				server.id,
				workshopItem.workshop_id,
				workshopItem.title,
				modId,
			);
			onchange(updated, `${workshopItem.title} installed.`);
			onclose();
		} catch (installError) {
			error = messageFrom(installError);
		} finally {
			busyId = null;
		}
	}

	function handleNativeClose() {
		if (open) onclose();
	}

	function messageFrom(value: unknown): string {
		return value instanceof Error
			? value.message
			: "The request could not be completed.";
	}
</script>

<dialog
	class="dialog dialog-wide"
	bind:this={dialog}
	onclose={handleNativeClose}
>
	<div class="dialog-header">
		<div>
			<p class="eyebrow">
				{server ? gameMeta[server.game].source : "Mod source"}
			</p>
			<h2>Add to {server?.name ?? "server"}</h2>
		</div>
		<button
			class="icon-button"
			type="button"
			onclick={onclose}
			title="Close"
			aria-label="Close"
		>
			<span class="icon-glyph" aria-hidden="true">×</span>
		</button>
	</div>
	<div class="dialog-body mod-dialog-body">
		{#if server?.game === "valheim"}
			<label class="mod-search">
				<span class="sr-only">Search Thunderstore</span>
				<input
					bind:this={searchInput}
					bind:value={query}
					type="search"
					maxlength="100"
					placeholder="Search Thunderstore"
					autocomplete="off"
				/>
				<span class="search-glyph" aria-hidden="true">⌕</span>
			</label>
			<div class="search-results">
				{#if loading && packages.length === 0}
					<div class="loading-row">Loading packages...</div>
				{:else if packages.length === 0}
					<div class="loading-row">No packages found</div>
				{:else}
					{#each packages as item (item.package_id)}
						<div class="search-result">
							{#if item.icon_url}
								<img src={item.icon_url} alt="" />
							{:else}
								<span
									class="result-placeholder"
									aria-hidden="true">□</span
								>
							{/if}
							<div class="search-result-copy">
								<strong>{item.name}</strong>
								<span
									>{item.owner} · {item.version} · {formatNumber(
										item.downloads,
									)} downloads</span
								>
								<p>{item.description}</p>
							</div>
							<button
								class="button button-secondary button-small"
								type="button"
								disabled={busyId !== null}
								onclick={() => installValheim(item.package_id)}
							>
								<span class="button-symbol" aria-hidden="true"
									>+</span
								>
								<span
									>{busyId === item.package_id
										? "Installing..."
										: "Install"}</span
								>
							</button>
						</div>
					{/each}
				{/if}
			</div>
		{:else}
			<form class="workshop-form" onsubmit={installZomboid}>
				<div class="lookup-row">
					<label class="field">
						<span>Steam Workshop ID</span>
						<input
							bind:this={workshopInput}
							bind:value={workshopId}
							inputmode="numeric"
							pattern="[0-9]+"
							maxlength="32"
							required
							placeholder="2169435993"
						/>
					</label>
					<button
						class="button button-secondary"
						type="button"
						disabled={busyId !== null}
						onclick={lookupWorkshop}
					>
						<span
							>{busyId === "lookup"
								? "Looking up..."
								: "Lookup"}</span
						>
					</button>
				</div>
				{#if workshopItem}
					<div class="workshop-preview">
						{#if workshopItem.preview_url}
							<img src={workshopItem.preview_url} alt="" />
						{:else}
							<span class="result-placeholder" aria-hidden="true"
								>□</span
							>
						{/if}
						<div class="workshop-preview-copy">
							<p class="eyebrow">
								Workshop {workshopItem.workshop_id}
							</p>
							<h3>{workshopItem.title}</h3>
							<p>{workshopItem.description}</p>
						</div>
					</div>
				{/if}
				<label class="field">
					<span>Internal mod ID</span>
					<input
						bind:value={modId}
						pattern="[A-Za-z0-9_.-]+"
						maxlength="160"
						required
						placeholder="modoptions"
					/>
				</label>
				<button
					class="button button-primary"
					type="submit"
					disabled={!workshopItem || busyId !== null}
				>
					<span class="button-symbol" aria-hidden="true">+</span>
					<span
						>{busyId === "zomboid"
							? "Installing..."
							: "Add and redeploy"}</span
					>
				</button>
			</form>
		{/if}
		<p class="form-error" role="alert">{error}</p>
	</div>
</dialog>
