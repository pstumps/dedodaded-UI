<script lang="ts">
  import { formatDate, statusClass } from '../domain'
  import type { ActivityEvent } from '../types'

  interface Props {
    events: ActivityEvent[]
    loading: boolean
    onrefresh: () => void
  }

  let { events, loading, onrefresh }: Props = $props()
</script>

<section class="page activity-page">
  <div class="section-heading">
    <div>
      <p class="eyebrow">Audit trail</p>
      <h2>Recent activity</h2>
    </div>
    <button
      class="icon-button"
      type="button"
      onclick={onrefresh}
      disabled={loading}
      title="Refresh activity"
      aria-label="Refresh activity"
    >
      <span class="icon-glyph" class:is-spinning={loading} aria-hidden="true">↻</span>
    </button>
  </div>
  <div class="event-list">
    {#if events.length === 0}
      <div class="loading-row">{loading ? 'Loading activity...' : 'No activity yet'}</div>
    {:else}
      {#each events as event (event.id)}
        <div class="event-row">
          <span class="event-level">
            <span class={`status-dot ${statusClass(event.level === 'error' ? 'error' : 'running')}`}></span>
            {event.level}
          </span>
          <span class="event-message">{event.message}</span>
          <time class="event-time" datetime={event.created_at}>{formatDate(event.created_at)}</time>
        </div>
      {/each}
    {/if}
  </div>
</section>
