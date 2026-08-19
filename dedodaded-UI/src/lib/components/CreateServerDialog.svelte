<script lang="ts">
	import { gameMeta } from "../domain";
	import type { CreateServerInput, Game } from "../types";

	interface Props {
		open: boolean;
		busy: boolean;
		error: string;
		onclose: () => void;
		oncreate: (input: CreateServerInput) => void;
	}

	let { open, busy, error, onclose, oncreate }: Props = $props();
	let dialog: HTMLDialogElement;
	let nameInput: HTMLInputElement;
	let game = $state<Game>("project-zomboid");
	let name = $state("");
	let worldName = $state("Knox");
	let port = $state(16261);
	let maxPlayers = $state(16);
	let password = $state("");
	let adminPassword = $state("");
	let isPublic = $state(true);
	let showPassword = $state(false);
	let showAdminPassword = $state(false);
	let portEnd = $derived(port + (game === "valheim" ? 2 : 1));

	$effect(() => {
		if (open && !dialog.open) {
			reset();
			dialog.showModal();
			requestAnimationFrame(() => nameInput.focus());
		} else if (!open && dialog.open) {
			dialog.close();
		}
	});

	function reset() {
		game = "project-zomboid";
		name = "";
		worldName = "Knox";
		port = 16261;
		maxPlayers = 16;
		password = "";
		adminPassword = "";
		isPublic = true;
		showPassword = false;
		showAdminPassword = false;
	}

	function selectGame(selectedGame: Game) {
		game = selectedGame;
		if (selectedGame === "valheim") {
			worldName = "Dedicated";
			port = 2456;
			maxPlayers = 10;
			adminPassword = "";
		} else {
			worldName = "Knox";
			port = 16261;
			maxPlayers = 16;
		}
	}

	function submit(event: SubmitEvent) {
		event.preventDefault();
		oncreate({
			game,
			name,
			world_name: worldName,
			password,
			admin_password: adminPassword,
			port,
			max_players: maxPlayers,
			public: isPublic,
		});
	}

	function handleNativeClose() {
		if (open) onclose();
	}
</script>

<dialog
	class="dialog dialog-wide"
	bind:this={dialog}
	onclose={handleNativeClose}
>
	<form onsubmit={submit}>
		<div class="dialog-header">
			<div>
				<p class="eyebrow">Provision instance</p>
				<h2>New game server</h2>
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
		<div class="dialog-body">
			<fieldset class="game-picker">
				<legend>Game</legend>
				<label
					class="game-choice"
					class:is-selected={game === "project-zomboid"}
				>
					<input
						type="radio"
						name="game"
						value="project-zomboid"
						checked={game === "project-zomboid"}
						onchange={() => selectGame("project-zomboid")}
					/>
					<img src={gameMeta["project-zomboid"].image} alt="" />
					<span
						><strong>Project Zomboid</strong><small
							>Steam Workshop</small
						></span
					>
					<span class="choice-check" aria-hidden="true">✓</span>
				</label>
				<label
					class="game-choice"
					class:is-selected={game === "valheim"}
				>
					<input
						type="radio"
						name="game"
						value="valheim"
						checked={game === "valheim"}
						onchange={() => selectGame("valheim")}
					/>
					<img src={gameMeta.valheim.image} alt="" />
					<span
						><strong>Valheim</strong><small
							>Thunderstore + BepInEx</small
						></span
					>
					<span class="choice-check" aria-hidden="true">✓</span>
				</label>
			</fieldset>
			<div class="form-grid">
				<label class="field field-span-2">
					<span>Server name</span>
					<input
						bind:this={nameInput}
						bind:value={name}
						required
						minlength="3"
						maxlength="64"
						placeholder="Knox County Night Shift"
					/>
				</label>
				<label class="field">
					<span>World name</span>
					<input bind:value={worldName} required maxlength="64" />
				</label>
				<label class="field">
					<span>Base port</span>
					<input
						bind:value={port}
						type="number"
						required
						min="1024"
						max="65533"
					/>
				</label>
				<label class="field">
					<span>Player slots</span>
					<input
						bind:value={maxPlayers}
						type="number"
						required
						min="1"
						max={game === "valheim" ? 10 : 100}
					/>
				</label>
				<div class="field">
					<label for="server-password">Server password</label>
					<span class="password-field">
						<input
							id="server-password"
							bind:value={password}
							type={showPassword ? "text" : "password"}
							minlength={game === "valheim" ? 5 : 0}
							maxlength="64"
							autocomplete="new-password"
						/>
						<button
							class="password-toggle"
							type="button"
							onclick={() => (showPassword = !showPassword)}
						>
							{showPassword ? "Hide" : "Show"}
						</button>
					</span>
				</div>
				{#if game === "project-zomboid"}
					<div class="field field-span-2">
						<label for="admin-password">Admin password</label>
						<span class="password-field">
							<input
								id="admin-password"
								bind:value={adminPassword}
								type={showAdminPassword ? "text" : "password"}
								minlength="8"
								maxlength="64"
								pattern="[A-Za-z0-9]+"
								autocomplete="new-password"
								required
							/>
							<button
								class="password-toggle"
								type="button"
								onclick={() =>
									(showAdminPassword = !showAdminPassword)}
							>
								{showAdminPassword ? "Hide" : "Show"}
							</button>
						</span>
					</div>
				{/if}
				<label class="switch-row field-span-2">
					<span
						><strong>Public listing</strong><small
							>Advertise this server in the game browser</small
						></span
					>
					<input bind:checked={isPublic} type="checkbox" />
					<span class="switch" aria-hidden="true"></span>
				</label>
			</div>
			<p class="form-error" role="alert">{error}</p>
		</div>
		<div class="dialog-footer">
			<span class="port-summary">UDP {port}–{portEnd}</span>
			<div class="dialog-actions">
				<button
					class="button button-secondary"
					type="button"
					onclick={onclose}>Cancel</button
				>
				<button
					class="button button-primary"
					type="submit"
					disabled={busy}
				>
					<span class="button-symbol" aria-hidden="true">↑</span>
					<span>{busy ? "Provisioning..." : "Provision server"}</span>
				</button>
			</div>
		</div>
	</form>
</dialog>
