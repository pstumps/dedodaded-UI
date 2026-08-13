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
install and start Docker, prompts for panel access and the first administrator,
then builds and starts the panel. Re-running it updates the application while
preserving the encryption key, administrator account, panel database, and game
data.

The default `private` mode binds the panel to `127.0.0.1`. Connect from your own
computer with the tunnel printed by the installer:

```sh
ssh -L 8080:127.0.0.1:8080 YOUR_USER@YOUR_VPS
```

Then open `http://127.0.0.1:8080`. Keep the SSH session running while using the
panel.

### Public access and HTTPS

Public mode binds the selected TCP port to every host interface. Do not submit
credentials over public plain HTTP. Provide an `https://` origin during installation
and route that origin through a TLS reverse proxy such as Caddy, Nginx, or your VPS
provider's HTTPS proxy. The origin must be the exact browser origin, without a path
or trailing slash, for example `https://games.example.com`.

The installer can add the panel's TCP port to an active UFW or firewalld
configuration. It never enables an inactive firewall. Provider firewalls and
security groups must be configured separately.

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
sudo docker compose restart panel
sudo docker compose down
sudo docker compose up -d
```

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
- TLS, DNS, cloud firewall rules, and off-host backups remain operator-managed.
- Game server images and public mod catalogs are third-party dependencies.
- Removing a mod updates desired configuration, but compatibility and world-save
  migrations remain the game administrator's responsibility.