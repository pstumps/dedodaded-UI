<script lang="ts">
	interface Props {
		open: boolean;
		serverName: string;
		logs: string;
		loading: boolean;
		onclose: () => void;
		onrefresh: () => void;
	}

	let { open, serverName, logs, loading, onclose, onrefresh }: Props =
		$props();
	let dialog: HTMLDialogElement;

	$effect(() => {
		if (open && !dialog.open) dialog.showModal();
		else if (!open && dialog.open) dialog.close();
	});

	function handleNativeClose() {
		if (open) onclose();
	}
</script>

<dialog
	class="dialog dialog-terminal"
	bind:this={dialog}
	onclose={handleNativeClose}
>
	<div class="dialog-header terminal-header">
		<div>
			<p class="eyebrow">Container output</p>
			<h2>{serverName || "Server logs"}</h2>
		</div>
		<div class="dialog-header-actions">
			<button
				class="icon-button icon-button-inverse"
				type="button"
				onclick={onrefresh}
				disabled={loading}
				title="Refresh logs"
				aria-label="Refresh logs"
			>
				<span
					class="icon-glyph"
					class:is-spinning={loading}
					aria-hidden="true">↻</span
				>
			</button>
			<button
				class="icon-button icon-button-inverse"
				type="button"
				onclick={onclose}
				title="Close"
				aria-label="Close"
			>
				<span class="icon-glyph" aria-hidden="true">×</span>
			</button>
		</div>
	</div>
	<pre
		class="logs-output"
		aria-live="polite"
		aria-label="Server log output">{loading
			? "Loading..."
			: logs || "No output yet."}</pre>
</dialog>
