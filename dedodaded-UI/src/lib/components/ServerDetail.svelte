<script lang="ts">
	import { gameMeta, statusClass, statusLabel } from "../domain";
	import type { GameServer } from "../types";

	export type DetailTab = "overview" | "mods";

	interface Props {
		server: GameServer | null;
		detailTab: DetailTab;
		busyAction: string | null;
		onaction: (action: string) => void;
		oncreate: () => void;
		ondelete: () => void;
		onlogs: () => void;
		onmods: () => void;
		onremovemod: (sourceId: string) => void;
		ontab: (tab: DetailTab) => void;
	}

	let {
		server,
		detailTab,
		busyAction,
		onaction,
		oncreate,
		ondelete,
		onlogs,
		onmods,
		onremovemod,
		ontab,
	}: Props = $props();

	const hostname = window.location.hostname || "localhost";
</script>

<div class="server-detail">
	{#if !server}
		<div class="detail-empty">
			<div>
				<div class="empty-sigil" aria-hidden="true">
					<span class="empty-symbol">□</span>
				</div>
				<h2>No server selected</h2>
				<p>Provision an instance to begin.</p>
				<button
					class="button button-primary"
					type="button"
					onclick={oncreate}
				>
					<span class="button-symbol" aria-hidden="true">+</span>
					<span>New server</span>
				</button>
			</div>
		</div>
	{:else}
		{@const game = gameMeta[server.game]}
		{@const running = server.runtime.state === "running"}
		<div class="detail-hero">
			<img class="detail-art" src={game.image} alt={game.label} />
			<div class="detail-title">
				<p class="eyebrow">{game.label}</p>
				<h2>{server.name}</h2>
				<div class="detail-meta">
					<span class="status-label">
						<span
							class={`status-dot ${statusClass(server.runtime.state)}`}
						></span>
						{statusLabel(server.runtime.state)}
					</span>
					<span>{hostname}:{server.port}</span>
					<span>{server.max_players} slots</span>
				</div>
			</div>
			<div class="hero-actions">
				<button
					class={`button ${running ? "button-secondary" : "button-primary"}`}
					type="button"
					disabled={busyAction !== null}
					onclick={() => onaction(running ? "stop" : "start")}
				>
					<span class="button-symbol" aria-hidden="true"
						>{running ? "■" : "▶"}</span
					>
					<span
						>{busyAction === (running ? "stop" : "start")
							? "Working..."
							: running
								? "Stop"
								: "Start"}</span
					>
				</button>
				<button
					class="icon-button"
					type="button"
					disabled={busyAction !== null}
					onclick={() => onaction("restart")}
					title="Restart server"
					aria-label="Restart server"
				>
					<span class="icon-glyph" aria-hidden="true">↻</span>
				</button>
				<button
					class="icon-button"
					type="button"
					onclick={onlogs}
					title="View logs"
					aria-label="View logs"
				>
					<span class="icon-glyph icon-glyph-small" aria-hidden="true"
						>LOG</span
					>
				</button>
			</div>
		</div>

		<div class="detail-tabs" role="tablist">
			<button
				class="tab-button"
				class:is-active={detailTab === "overview"}
				type="button"
				role="tab"
				aria-selected={detailTab === "overview"}
				onclick={() => ontab("overview")}>Overview</button
			>
			<button
				class="tab-button"
				class:is-active={detailTab === "mods"}
				type="button"
				role="tab"
				aria-selected={detailTab === "mods"}
				onclick={() => ontab("mods")}
				>Mods <span class="count-badge">{server.mods.length}</span
				></button
			>
		</div>

		<div class="detail-body">
			{#if detailTab === "mods"}
				<div class="mod-header">
					<div>
						<h3>Installed mods</h3>
						<p>{game.source}</p>
					</div>
					<button
						class="button button-primary"
						type="button"
						onclick={onmods}
					>
						<span class="button-symbol" aria-hidden="true">+</span>
						<span>Add mod</span>
					</button>
				</div>
				<div class="mod-list">
					{#if server.mods.length === 0}
						<div class="empty-mods">
							<div>
								<span class="empty-symbol" aria-hidden="true"
									>◇</span
								>
								<p>No mods installed</p>
							</div>
						</div>
					{:else}
						{#each server.mods as mod (mod.source_id)}
							<div class="mod-row">
								<span class="mod-icon" aria-hidden="true"
									>◇</span
								>
								<span class="mod-copy">
									<strong>{mod.name}</strong>
									<span>{mod.mod_id || mod.source_id}</span>
								</span>
								<span class="mod-version"
									>{mod.version || ""}</span
								>
								<button
									class="icon-button"
									type="button"
									onclick={() => onremovemod(mod.source_id)}
									title={`Remove ${mod.name}`}
									aria-label={`Remove ${mod.name}`}
								>
									<span class="icon-glyph" aria-hidden="true"
										>×</span
									>
								</button>
							</div>
						{/each}
					{/if}
				</div>
			{:else}
				<div class="overview-grid">
					<div>
						<section class="subsection">
							<div class="subsection-heading">
								<h3>Runtime</h3>
							</div>
							<dl class="fact-list">
								<div class="fact-row">
									<dt>State</dt>
									<dd>{statusLabel(server.runtime.state)}</dd>
								</div>
								<div class="fact-row">
									<dt>Address</dt>
									<dd class="mono">
										{hostname}:{server.port}
									</dd>
								</div>
								<div class="fact-row">
									<dt>UDP range</dt>
									<dd class="mono">
										{server.port}–{server.port_end}
									</dd>
								</div>
								<div class="fact-row">
									<dt>Public</dt>
									<dd>
										{server.public ? "Listed" : "Private"}
									</dd>
								</div>
							</dl>
						</section>
						<section class="subsection">
							<div class="subsection-heading">
								<h3>Game configuration</h3>
							</div>
							<dl class="fact-list">
								<div class="fact-row">
									<dt>Game</dt>
									<dd>{game.label}</dd>
								</div>
								<div class="fact-row">
									<dt>World</dt>
									<dd>{server.world_name}</dd>
								</div>
								<div class="fact-row">
									<dt>Player slots</dt>
									<dd>{server.max_players}</dd>
								</div>
								<div class="fact-row">
									<dt>Mod source</dt>
									<dd>{game.source}</dd>
								</div>
							</dl>
						</section>
					</div>
					<aside>
						<section class="subsection">
							<div class="subsection-heading">
								<h3>Operations</h3>
							</div>
							<div class="action-stack">
								<button
									class="button button-secondary"
									type="button"
									disabled={busyAction !== null}
									onclick={() => onaction("update")}
								>
									<span
										class="button-symbol"
										aria-hidden="true">↥</span
									><span>Pull update and redeploy</span>
								</button>
								<button
									class="button button-secondary"
									type="button"
									onclick={onlogs}
								>
									<span
										class="button-symbol"
										aria-hidden="true">≡</span
									><span>Open container logs</span>
								</button>
								<button
									class="button button-secondary"
									type="button"
									onclick={onmods}
								>
									<span
										class="button-symbol"
										aria-hidden="true">◇</span
									><span>Add a mod</span>
								</button>
							</div>
						</section>
						<section class="danger-zone">
							<h3>Delete instance</h3>
							<p>
								The container can be removed while world data
								remains on disk.
							</p>
							<button
								class="button button-quiet"
								type="button"
								onclick={ondelete}
							>
								<span class="button-symbol" aria-hidden="true"
									>×</span
								><span>Delete server</span>
							</button>
						</section>
					</aside>
				</div>
			{/if}
		</div>
	{/if}
</div>
