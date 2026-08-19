<script lang="ts">
	import { gameMeta, statusClass, statusLabel } from "../domain";
	import type { GameServer } from "../types";

	interface Props {
		servers: GameServer[];
		selectedId: string | null;
		oncreate: () => void;
		onselect: (serverId: string) => void;
	}

	let { servers, selectedId, oncreate, onselect }: Props = $props();
</script>

<div class="server-rail">
	<div class="section-heading compact-heading">
		<div>
			<p class="eyebrow">Fleet</p>
			<h2>Instances <span class="count-badge">{servers.length}</span></h2>
		</div>
		<button
			class="icon-button"
			type="button"
			onclick={oncreate}
			title="Add server"
			aria-label="Add server"
		>
			<span class="icon-glyph" aria-hidden="true">+</span>
		</button>
	</div>
	<div class="server-list">
		{#if servers.length === 0}
			<div class="empty-rail">No instances on this host.</div>
		{:else}
			{#each servers as server (server.id)}
				<button
					class="server-list-item"
					class:is-selected={server.id === selectedId}
					type="button"
					onclick={() => onselect(server.id)}
					aria-current={server.id === selectedId ? "true" : undefined}
				>
					<img
						class="server-thumb"
						src={gameMeta[server.game].image}
						alt=""
					/>
					<span class="server-list-copy">
						<strong>{server.name}</strong>
						<span>{gameMeta[server.game].label}</span>
					</span>
					<span
						class={`status-dot ${statusClass(server.runtime.state)}`}
						title={statusLabel(server.runtime.state)}
					></span>
				</button>
			{/each}
		{/if}
	</div>
</div>
