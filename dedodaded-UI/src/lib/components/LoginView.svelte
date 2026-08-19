<script lang="ts">
	import { onMount } from "svelte";

	import { gameMeta } from "../domain";

	interface Props {
		busy: boolean;
		error: string;
		onlogin: (username: string, password: string) => void;
	}

	let { busy, error, onlogin }: Props = $props();
	let username = $state("");
	let password = $state("");
	let showPassword = $state(false);
	let usernameInput: HTMLInputElement;

	onMount(() => usernameInput.focus());

	function submit(event: SubmitEvent) {
		event.preventDefault();
		onlogin(username, password);
	}
</script>

<section class="login-view">
	<div class="login-art" aria-hidden="true">
		<img class="login-art-primary" src={gameMeta.valheim.image} alt="" />
		<img
			class="login-art-secondary"
			src={gameMeta["project-zomboid"].image}
			alt=""
		/>
		<div class="art-index">VPS / 01</div>
	</div>
	<div class="login-panel">
		<div class="brand brand-large">
			<span class="brand-mark" aria-hidden="true">D</span>
			<span>Dedodaded</span>
		</div>
		<div class="login-copy">
			<p class="eyebrow">Server control</p>
			<h1>Bring the world online.</h1>
			<p>Project Zomboid and Valheim, from one host.</p>
		</div>
		<form class="form-stack" onsubmit={submit}>
			<label class="field">
				<span>Username</span>
				<input
					name="username"
					autocomplete="username"
					required
					maxlength="80"
					bind:this={usernameInput}
					bind:value={username}
				/>
			</label>
			<div class="field">
				<label for="login-password">Password</label>
				<span class="password-field">
					<input
						id="login-password"
						name="password"
						type={showPassword ? "text" : "password"}
						autocomplete="current-password"
						required
						maxlength="256"
						bind:value={password}
					/>
					<button
						class="password-toggle"
						type="button"
						onclick={() => (showPassword = !showPassword)}
						aria-label={showPassword
							? "Hide password"
							: "Show password"}
					>
						{showPassword ? "Hide" : "Show"}
					</button>
				</span>
			</div>
			<p class="form-error" role="alert">{error}</p>
			<button
				class="button button-primary button-wide"
				type="submit"
				disabled={busy}
			>
				<span>{busy ? "Opening panel..." : "Open panel"}</span>
				<span class="button-symbol" aria-hidden="true">→</span>
			</button>
		</form>
		<p class="login-foot">
			<span class="pulse-dot"></span>
			Encrypted local control plane
		</p>
	</div>
</section>
