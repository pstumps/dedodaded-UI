export type Game = "project-zomboid" | "valheim";

export interface SessionInfo {
	username: string;
	csrf_token: string;
}

export interface HealthStatus {
	status: string;
	docker: boolean;
}

export interface RuntimeStatus {
	state: string;
	[key: string]: unknown;
}

export interface ServerMod {
	source_id: string;
	name: string;
	mod_id: string | null;
	version: string | null;
}

export interface GameServer {
	id: string;
	game: Game;
	name: string;
	world_name: string;
	port: number;
	port_end: number;
	max_players: number;
	public: boolean;
	mods: ServerMod[];
	runtime: RuntimeStatus;
}

export interface CreateServerInput {
	game: Game;
	name: string;
	world_name: string;
	password: string;
	admin_password: string;
	port: number;
	max_players: number;
	public: boolean;
}

export interface ActivityEvent {
	id: number;
	server_id: string | null;
	level: string;
	message: string;
	created_at: string;
}

export interface ThunderstorePackage {
	package_id: string;
	name: string;
	owner: string;
	description: string;
	version: string;
	download_url: string;
	dependencies: string[];
	downloads: number;
	icon_url: string | null;
	website_url: string | null;
}

export interface WorkshopItem {
	workshop_id: string;
	title: string;
	description: string;
	preview_url: string | null;
}
