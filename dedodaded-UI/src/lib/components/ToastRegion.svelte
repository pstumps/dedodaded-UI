<script lang="ts">
	export interface ToastMessage {
		id: number;
		message: string;
		error: boolean;
	}

	interface Props {
		toasts: ToastMessage[];
	}

	let { toasts }: Props = $props();
</script>

<div class="toast-region" aria-live="polite">
	{#each toasts as toast (toast.id)}
		<div class="toast" class:is-error={toast.error}>
			<span class="toast-symbol" aria-hidden="true"
				>{toast.error ? "!" : "✓"}</span
			>
			<span>{toast.message}</span>
		</div>
	{/each}
</div>
