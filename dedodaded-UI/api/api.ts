import { appUrl } from "../src/lib/domain";
import type {
	ActivityEvent,
	CreateServerInput,
	GameServer,
	HealthStatus,
	SessionInfo,
	ThunderstorePackage,
	WorkshopItem,
} from "../src/lib/types";

interface ErrorPayload {
	detail?: string | Array<{ msg?: string }>;
}

interface RequestOptions {
	method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
	body?: unknown;
	csrf?: boolean;
}

let csrfToken = "";
let unauthorizedHandler: () => void = () => undefined;

export class ApiError extends Error {
	constructor(
		message: string,
		readonly status: number,
	) {
		super(message);
		this.name = "ApiError";
	}
}

export function setCsrfToken(token: string): void {
	csrfToken = token;
}

export function clearCsrfToken(): void {
	csrfToken = "";
}

export function setUnauthorizedHandler(handler: () => void): void {
	unauthorizedHandler = handler;
}

async function request<T>(
	path: string,
	options: RequestOptions = {},
): Promise<T> {
	const method = options.method ?? "GET";
	const headers: Record<string, string> = { Accept: "application/json" };
	const fetchOptions: RequestInit = {
		method,
		credentials: "same-origin",
		headers,
	};

	if (options.body !== undefined) {
		headers["Content-Type"] = "application/json";
		fetchOptions.body = JSON.stringify(options.body);
	}
	if (
		options.csrf !== false &&
		["POST", "PUT", "PATCH", "DELETE"].includes(method) &&
		csrfToken
	) {
		headers["X-CSRF-Token"] = csrfToken;
	}

	const response = await fetch(appUrl(path), fetchOptions);
	if (response.status === 204) return undefined as T;

	const contentType = response.headers.get("content-type") ?? "";
	const payload: unknown = contentType.includes("application/json")
		? await response.json()
		: { detail: await response.text() };

	if (!response.ok) {
		if (response.status === 401 && options.csrf !== false)
			unauthorizedHandler();
		throw new ApiError(
			errorMessage(payload as ErrorPayload),
			response.status,
		);
	}
	return payload as T;
}

function errorMessage(payload: ErrorPayload): string {
	if (typeof payload.detail === "string") return payload.detail;
	if (Array.isArray(payload.detail)) {
		return payload.detail
			.map((item) => item.msg ?? "Invalid value")
			.join(" · ");
	}
	return "The request could not be completed.";
}

export const panelApi = {
	session: () => request<SessionInfo>("api/auth/session", { csrf: false }),
	login: (username: string, password: string) =>
		request<SessionInfo>("api/auth/login", {
			method: "POST",
			body: { username, password },
			csrf: false,
		}),
	logout: () => request<void>("api/auth/logout", { method: "POST" }),
	health: () => request<HealthStatus>("api/health", { csrf: false }),
	servers: () => request<GameServer[]>("api/servers"),
	createServer: (body: CreateServerInput) =>
		request<GameServer>("api/servers", { method: "POST", body }),
	runServerAction: (serverId: string, action: string) =>
		request<Record<string, unknown>>(
			`api/servers/${encodeURIComponent(serverId)}/actions/${encodeURIComponent(action)}`,
			{ method: "POST" },
		),
	logs: (serverId: string) =>
		request<{ logs: string }>(
			`api/servers/${encodeURIComponent(serverId)}/logs?tail=300`,
		),
	deleteServer: (serverId: string, deleteData: boolean) =>
		request<void>(
			`api/servers/${encodeURIComponent(serverId)}?delete_data=${deleteData}`,
			{ method: "DELETE" },
		),
	events: () => request<ActivityEvent[]>("api/events"),
	searchValheimMods: (query: string) =>
		request<ThunderstorePackage[]>(
			`api/mods/valheim/search?q=${encodeURIComponent(query)}`,
		),
	installValheimMod: (serverId: string, packageId: string) =>
		request<GameServer>(
			`api/servers/${encodeURIComponent(serverId)}/mods/valheim`,
			{ method: "POST", body: { package_id: packageId } },
		),
	lookupWorkshopItem: (workshopId: string) =>
		request<WorkshopItem>("api/mods/project-zomboid/lookup", {
			method: "POST",
			body: { workshop_id: workshopId },
		}),
	installZomboidMod: (
		serverId: string,
		workshopId: string,
		name: string,
		modId: string,
	) =>
		request<GameServer>(
			`api/servers/${encodeURIComponent(serverId)}/mods/project-zomboid`,
			{
				method: "POST",
				body: { workshop_id: workshopId, name, mod_id: modId },
			},
		),
	removeMod: (serverId: string, sourceId: string) =>
		request<GameServer>(
			`api/servers/${encodeURIComponent(serverId)}/mods/${encodeURIComponent(sourceId)}`,
			{ method: "DELETE" },
		),
};
