<script lang="ts">
	import type { GameServer } from "../types";

	interface Props {
		open: boolean;
		server: GameServer | null;
		busy: boolean;
		error: string;
		onclose: () => void;
		onconfirm: (deleteData: boolean) => void;
	}

	let { open, server, busy, error, onclose, onconfirm }: Props = $props();
	let dialog: HTMLDialogElement;
	let deleteData = $state(false);

	$effect(() => {
		if (open && !dialog.open) {
			deleteData = false;
			dialog.showModal();
		} else if (!open && dialog.open) {
			dialog.close();
		}
	});

	function submit(event: SubmitEvent) {
		event.preventDefault();
		onconfirm(deleteData);
	}

	function handleNativeClose() {
		if (open) onclose();
	}
</script>

<dialog
	class="dialog dialog-small"
	bind:this={dialog}
	onclose={handleNativeClose}
>
	<form onsubmit={submit}>
		<div class="dialog-header">
			<div>
				<p class="eyebrow eyebrow-danger">Destructive action</p>
				<h2>Delete server?</h2>
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
			<p class="delete-copy">
				{server?.name ?? "This server"} will be stopped and its managed container
				removed.
			</p>
			<label class="check-row">
				<input bind:checked={deleteData} type="checkbox" />
				<span>
					<strong>Delete world and configuration data</strong>
					<small>Backups inside this instance are removed too.</small>
				</span>
			</label>
			<p class="form-error" role="alert">{error}</p>
		</div>
		<div class="dialog-footer dialog-footer-end">
			<button
				class="button button-secondary"
				type="button"
				onclick={onclose}>Cancel</button
			>
			<button class="button button-danger" type="submit" disabled={busy}>
				<span class="button-symbol" aria-hidden="true">×</span>
				<span>{busy ? "Deleting..." : "Delete server"}</span>
			</button>
		</div>
	</form>
</dialog>
