import type { Game } from "./types";

const appBaseUrl = new URL("./", document.baseURI);

export function appUrl(path: string): string {
	return new URL(path.replace(/^\/+/, ""), appBaseUrl).toString();
}

export const gameMeta: Record<
	Game,
	{ label: string; image: string; source: string }
> = {
	"project-zomboid": {
		label: "Project Zomboid",
		image: appUrl("assets/project-zomboid.png"),
		source: "Steam Workshop",
	},
	valheim: {
		label: "Valheim",
		image: appUrl("assets/valheim.png"),
		source: "Thunderstore",
	},
};

export function statusClass(status: string): string {
	if (status === "running") return "status-running";
	if (["exited", "created", "paused", "not-created"].includes(status)) {
		return "status-stopped";
	}
	if (["error", "dead"].includes(status)) return "status-error";
	if (status === "unavailable") return "status-unavailable";
	return "status-unknown";
}

export function statusLabel(status: string): string {
	const labels: Record<string, string> = {
		running: "Online",
		exited: "Stopped",
		created: "Created",
		paused: "Paused",
		"not-created": "Not deployed",
		unavailable: "Host unavailable",
		dead: "Failed",
		error: "Error",
	};
	return labels[status] ?? (status || "Unknown");
}

export function formatDate(value: string): string {
	try {
		return new Intl.DateTimeFormat(undefined, {
			dateStyle: "medium",
			timeStyle: "short",
		}).format(new Date(value));
	} catch {
		return value;
	}
}

export function formatNumber(value: number): string {
	return new Intl.NumberFormat(undefined, { notation: "compact" }).format(
		value,
	);
}
