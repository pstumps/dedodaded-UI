# Dedodaded

Dedodaded is a self-hosted web control panel for creating and operating dedicated
Project Zomboid and Valheim servers on one Linux Docker host. It manages server
containers, persistent game data, logs, lifecycle actions, and game-specific mods.

## What it manages

- Project Zomboid and Valheim server creation
- Start, stop, restart, delete, status, and recent logs
- Steam Workshop metadata and mod configuration for Project Zomboid
- Thunderstore search, dependency resolution, and BepInEx installation for Valheim
- Encrypted server credentials and an authenticated administrator session
- Persistent game data outside the panel container

## VPS installation

Use a current Linux VPS with at least 4 GB of RAM, enough disk for the selected
games, and an account with `sudo` access. The installer supports APT, DNF, Pacman,
and APK based distributions.

```sh
git clone https://github.com/YOUR_ACCOUNT/Dedodaded-UI.git
cd Dedodaded-UI
sh install.sh
```

The script explains its privileged operations before requesting `sudo`. It can
install and start Docker, prompts for an access mode and the first administrator
account, then builds and starts the panel. Re-running it updates the application
while preserving the encryption key, administrator account, panel database, and
game data.

The installer offers two access modes. It does not offer direct public HTTP:

- `private` binds the panel to VPS loopback for access through an SSH tunnel.
- `https` publishes automatic, browser-trusted HTTPS on the VPS public IPv4
  address at `https://VPS_IP/dedodaded`.

The default `private` mode binds the panel to `127.0.0.1`. Connect from your own
computer with the tunnel printed by the installer:

```sh
ssh -L 8080:127.0.0.1:8080 YOUR_USER@YOUR_VPS
```

Then open `http://127.0.0.1:8080`. Keep the SSH session running while using the
panel. This loopback HTTP connection travels inside the encrypted SSH tunnel and
is never published to the network.

### Automatic public HTTPS

Choose `https` to have Dedodaded run Caddy and obtain a Let's Encrypt certificate
for the VPS public IPv4 address. The installer normally detects the address and
lets you confirm or replace it. It then waits until a trusted endpoint is available
before reporting success.

HTTPS mode publishes only TCP port `443`. Port `80` is not opened or used, and the
panel's port `8080` remains private on the Compose network. Allow inbound TCP `443`
in the VPS provider firewall or security group before installation. The installer
can also add a TCP `443` rule to UFW or an active firewalld configuration, but it
never enables an inactive firewall.

Let's Encrypt IP certificates are short-lived, lasting about six days. Caddy renews
them automatically over TLS-ALPN on TCP `443`; keep that port reachable and preserve
`/var/lib/dedodaded/caddy`. If the VPS public address changes, rerun the installer
and select the new address.

## Game networking

When creating a server, the selected base port reserves these host UDP ports:

| Game | Default base | Required UDP ports |
| --- | ---: | --- |
| Project Zomboid | `16261` | base and base + 1 |
| Valheim | `2456` | base, base + 1, and base + 2 |

Allow those UDP ranges in both the host firewall and the VPS provider firewall.
Each server on the same VPS needs a distinct, non-overlapping range. The panel
checks desired configurations for collisions, but infrastructure outside Docker
can still block traffic.

## Mods

For Project Zomboid, enter the numeric Steam Workshop item ID. Workshop metadata
is fetched before deployment, and the internal Project Zomboid mod ID is also
required by the server image.

For Valheim, search the Thunderstore catalog in the panel and install a package.
Required dependencies are resolved recursively. Plugin archives are downloaded
over HTTPS and checked for size, path traversal, symlinks, file count, and a valid
BepInEx plugin DLL before extraction. Restart the game server after changing mods.
All Valheim players normally need matching client-side mod versions.

## Operations

The production files are installed at `/opt/dedodaded/app`. Persistent state is
stored at `/var/lib/dedodaded`.

```sh
cd /opt/dedodaded/app
sudo docker compose ps
sudo docker compose logs --tail=200 panel
sudo docker compose logs --tail=200 caddy  # HTTPS mode only
sudo docker compose restart panel
sudo docker compose down
sudo docker compose up -d
```

The installed `.env` selects the private or HTTPS Compose override, so these
commands retain the access mode chosen during installation.

To update from a fresh repository checkout, pull the desired revision and run
`sudo sh install.sh` again. The installer rebuilds only the panel image; it does
not delete managed game containers or data.

### Backup and restore

Back up both of these locations together while the panel is stopped:

```text
/var/lib/dedodaded
/opt/dedodaded/app/.env
```

The `.env` file contains the Fernet key used to encrypt game credentials in the
SQLite database. Losing that key makes the encrypted fields unrecoverable. Treat
the backup as sensitive because it also contains the key and game credentials.

For a consistent manual backup:

```sh
cd /opt/dedodaded/app
sudo docker compose stop panel
sudo tar -C / -czf dedodaded-backup.tgz \
  var/lib/dedodaded opt/dedodaded/app/.env
sudo docker compose start panel
```

Restore those paths with their original ownership before starting the panel.
Game containers may write their own world files while running, so stop important
game servers before taking a full filesystem snapshot.

## Security model

- The panel runs as UID/GID `1000`, with a read-only root filesystem and
  `no-new-privileges`.
- Panel state and the one-time bootstrap secret live in host-mounted storage.
- Passwords use PBKDF2-SHA256; session tokens are stored as hashes.
- Authentication uses an `HttpOnly` cookie, a separate CSRF token, same-origin
  checks, and login throttling.
- Public mode uses a `Secure`, path-scoped session cookie and an exact HTTPS
  origin. Caddy terminates TLS and sends an HSTS header.
- Saved game passwords and administrator passwords are encrypted at rest.
- The bootstrap password file is removed after the first account is created.

The Docker socket is mounted into the panel so it can create game containers.
Access to that socket is effectively root-level access to the host. Only trusted
administrators should access the panel, and the panel should run on a dedicated
or appropriately isolated VPS.

## Local development

Python 3.12 or newer and a running Docker daemon are required.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
export PANEL_ENCRYPTION_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
mkdir -p data/secrets
printf '%s\n' 'replace-with-a-long-password' > data/secrets/bootstrap_admin_password
python -m dedodaded.main
```

Run the checks with:

```sh
python -m unittest discover -s tests -v
ruff check .
mypy dedodaded
```

## Current limitations

- One local administrator account is bootstrapped; there is no user-management or
  password-reset screen yet.
- The panel controls one local Docker daemon and does not orchestrate multiple VPSs.
- Automatic public HTTPS currently supports one public IPv4 address. DNS, provider
  firewall rules, and off-host backups remain operator-managed.
- Game server images and public mod catalogs are third-party dependencies.
- Removing a mod updates desired configuration, but compatibility and world-save
  migrations remain the game administrator's responsibility.