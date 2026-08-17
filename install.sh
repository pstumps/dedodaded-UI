#!/bin/sh

set -eu
umask 077

APP_DIR=/opt/dedodaded/app
DATA_DIR=/var/lib/dedodaded
SECRETS_DIR=$DATA_DIR/secrets
CADDY_DATA_DIR=$DATA_DIR/caddy/data
CADDY_CONFIG_DIR=$DATA_DIR/caddy/config
ENV_FILE=$APP_DIR/.env
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)

info() {
    printf '\n%s\n' "$*"
}

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

ask() {
    prompt=$1
    default=$2
    printf '%s [%s]: ' "$prompt" "$default" >&3
    IFS= read -r answer <&3 || fail "Input was closed"
    if [ -z "$answer" ]; then
        answer=$default
    fi
    REPLY=$answer
}

confirm() {
    prompt=$1
    default=${2:-n}
    if [ "$default" = y ]; then
        suffix='Y/n'
    else
        suffix='y/N'
    fi
    printf '%s [%s]: ' "$prompt" "$suffix" >&3
    IFS= read -r answer <&3 || fail "Input was closed"
    answer=${answer:-$default}
    case $answer in
        y|Y|yes|YES|Yes) return 0 ;;
        *) return 1 ;;
    esac
}

read_env_value() {
    key=$1
    if as_root test -f "$ENV_FILE"; then
        as_root sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1
    fi
}

restore_terminal() {
    stty echo <&3 2>/dev/null || true
}

abort_install() {
    exit 130
}

require_source_file() {
    [ -e "$SOURCE_DIR/$1" ] || fail "Run this installer from the Dedodaded repository (missing $1)"
}

install_docker() {
    if command -v docker >/dev/null 2>&1 && {
        docker compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1;
    }; then
        return
    fi

    info "Installing Docker and Compose from the operating system package repository..."
    if command -v apt-get >/dev/null 2>&1; then
        as_root apt-get update
        as_root apt-get install -y ca-certificates curl docker.io
        if ! docker compose version >/dev/null 2>&1; then
            as_root apt-get install -y docker-compose-v2 \
                || as_root apt-get install -y docker-compose-plugin \
                || as_root apt-get install -y docker-compose
        fi
    elif command -v dnf >/dev/null 2>&1; then
        as_root dnf install -y ca-certificates curl docker docker-compose-plugin \
            || as_root dnf install -y ca-certificates curl moby-engine docker-compose
    elif command -v pacman >/dev/null 2>&1; then
        as_root pacman -Sy --noconfirm ca-certificates curl docker docker-compose
    elif command -v apk >/dev/null 2>&1; then
        as_root apk add --no-cache ca-certificates curl docker docker-cli-compose
    else
        fail "Supported package managers are APT, DNF, Pacman, and APK"
    fi
}

start_docker() {
    if command -v systemctl >/dev/null 2>&1; then
        as_root systemctl enable --now docker
    elif command -v rc-update >/dev/null 2>&1; then
        as_root rc-update add docker default >/dev/null 2>&1 || true
        as_root rc-service docker start
    elif command -v service >/dev/null 2>&1; then
        as_root service docker start
    fi

    as_root docker info >/dev/null 2>&1 || fail "Docker is installed but its daemon is unavailable"
    if ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then
        fail "Docker Compose could not be installed from this system's repositories"
    fi
}

compose() {
    compose_override=${compose_file#*:}
    if docker compose version >/dev/null 2>&1; then
        as_root docker compose --env-file "$ENV_FILE" --project-directory "$APP_DIR" \
            -f "$APP_DIR/compose.yaml" -f "$APP_DIR/$compose_override" "$@"
    else
        as_root docker-compose --env-file "$ENV_FILE" --project-directory "$APP_DIR" \
            -f "$APP_DIR/compose.yaml" -f "$APP_DIR/$compose_override" "$@"
    fi
}

copy_application() {
    as_root mkdir -p "$APP_DIR"
    target_dir=$(CDPATH= cd -- "$APP_DIR" && pwd -P)
    if [ "$SOURCE_DIR" = "$target_dir" ]; then
        return
    fi

    as_root rm -rf "$APP_DIR/dedodaded"
    as_root cp -R "$SOURCE_DIR/dedodaded" "$APP_DIR/dedodaded"
    for file in Caddyfile Dockerfile compose.yaml compose.private.yaml compose.https.yaml \
        pyproject.toml README.md .dockerignore .gitattributes install.sh; do
        as_root cp "$SOURCE_DIR/$file" "$APP_DIR/$file"
    done
    as_root chmod 755 "$APP_DIR/install.sh"
}

write_environment() {
    temporary_file=$(mktemp)
    cat >"$temporary_file" <<EOF
COMPOSE_FILE=$compose_file
DOCKER_GID=$docker_gid
PANEL_HTTP_PORT=$panel_port
PANEL_DATA_DIR=$DATA_DIR
PANEL_SECRETS_DIR=$SECRETS_DIR
PANEL_CADDY_DATA_DIR=$CADDY_DATA_DIR
PANEL_CADDY_CONFIG_DIR=$CADDY_CONFIG_DIR
PANEL_ENCRYPTION_KEY=$encryption_key
PANEL_BOOTSTRAP_USERNAME=$admin_username
PANEL_COOKIE_SECURE=$cookie_secure
PANEL_ALLOWED_ORIGIN=$allowed_origin
PANEL_BASE_PATH=$base_path
PANEL_PUBLIC_IP=$public_ip
PANEL_FORWARDED_ALLOW_IPS=$forwarded_allow_ips
EOF
    as_root cp "$temporary_file" "$ENV_FILE"
    as_root chmod 600 "$ENV_FILE"
    as_root chown root:root "$ENV_FILE"
    rm -f "$temporary_file"
}

write_bootstrap_password() {
    temporary_file=$(mktemp)
    printf '%s\n' "$admin_password" >"$temporary_file"
    as_root cp "$temporary_file" "$SECRETS_DIR/bootstrap_admin_password"
    as_root chown 1000:1000 "$SECRETS_DIR/bootstrap_admin_password"
    as_root chmod 600 "$SECRETS_DIR/bootstrap_admin_password"
    rm -f "$temporary_file"
}

configure_firewall() {
    firewall_port=$1
    if command -v ufw >/dev/null 2>&1; then
        as_root ufw allow "$firewall_port/tcp" comment 'Dedodaded HTTPS'
        if ! as_root ufw status | grep -q '^Status: active'; then
            info "UFW is inactive. The rule was saved, but the installer did not enable UFW."
        fi
    elif command -v firewall-cmd >/dev/null 2>&1; then
        if as_root firewall-cmd --state >/dev/null 2>&1; then
            as_root firewall-cmd --permanent --add-port="$firewall_port/tcp"
            as_root firewall-cmd --reload
        else
            info "firewalld is installed but inactive; no rule was changed."
        fi
    else
        info "No UFW or firewalld installation was found; configure the VPS firewall manually."
    fi
}

install_curl() {
    command -v curl >/dev/null 2>&1 && return

    info "Installing curl for public-IP discovery and HTTPS verification..."
    if command -v apt-get >/dev/null 2>&1; then
        as_root apt-get update
        as_root apt-get install -y ca-certificates curl
    elif command -v dnf >/dev/null 2>&1; then
        as_root dnf install -y ca-certificates curl
    elif command -v pacman >/dev/null 2>&1; then
        as_root pacman -Sy --noconfirm ca-certificates curl
    elif command -v apk >/dev/null 2>&1; then
        as_root apk add --no-cache ca-certificates curl
    else
        fail "curl is required for automatic HTTPS verification"
    fi
}

normalize_ipv4() {
    printf '%s\n' "$1" | awk -F. '
        NF != 4 { exit 1 }
        {
            for (part = 1; part <= 4; part++) {
                if ($part !~ /^[0-9]+$/ || $part < 0 || $part > 255) {
                    exit 1
                }
            }
            printf "%d.%d.%d.%d\n", $1, $2, $3, $4
        }
    '
}

discover_public_ipv4() {
    detected_ip=$(curl -4fsS --max-time 10 https://api.ipify.org 2>/dev/null || true)
    normalize_ipv4 "$detected_ip" 2>/dev/null || true
}

wait_for_https() {
    endpoint="https://$public_ip/dedodaded/api/health"
    attempts=0
    while [ "$attempts" -lt 36 ]; do
        if curl -4fsS --connect-timeout 5 --max-time 10 \
            --resolve "$public_ip:443:127.0.0.1" "$endpoint" >/dev/null 2>&1; then
            return
        fi
        attempts=$((attempts + 1))
        sleep 5
    done

    compose logs --tail=100 caddy >&2 || true
    fail "Trusted HTTPS could not be established. Confirm that this VPS owns $public_ip and inbound TCP 443 is allowed by the provider firewall."
}

exec 3<>/dev/tty || fail "This installer must run from an interactive terminal"
trap restore_terminal EXIT
trap abort_install HUP INT TERM

for required_file in Caddyfile Dockerfile compose.yaml compose.private.yaml compose.https.yaml \
    pyproject.toml README.md dedodaded; do
    require_source_file "$required_file"
done

cat <<'EOF'
Dedodaded VPS installer

This installer needs administrator access to:
  - install and start Docker when necessary;
  - place the application under /opt/dedodaded;
  - store persistent state under /var/lib/dedodaded;
  - access the Docker socket to manage game-server containers;
    - optionally publish automatic HTTPS on TCP port 443.

Docker socket access is effectively root-level access to this host.
EOF

if [ "$(id -u)" -ne 0 ]; then
    command -v sudo >/dev/null 2>&1 || fail "sudo is required when not running as root"
    confirm "Continue and request sudo access?" y || fail "Installation cancelled"
    sudo -v
fi

existing_compose_file=$(read_env_value COMPOSE_FILE)
existing_bind=$(read_env_value PANEL_BIND_ADDRESS)
existing_public_ip=$(read_env_value PANEL_PUBLIC_IP)
if [ -n "$existing_public_ip" ] || [ "$existing_bind" = "0.0.0.0" ]; then
    access_default=https
else
    access_default=private
fi
case $existing_compose_file in
    *compose.https.yaml*) access_default=https ;;
    *compose.private.yaml*) access_default=private ;;
esac
while :; do
    ask "Access mode (private/https)" "$access_default"
    case $REPLY in
        private|Private|p|P)
            access_mode=private
            compose_file=compose.yaml:compose.private.yaml
            existing_port=$(read_env_value PANEL_HTTP_PORT)
            case ${existing_port:-} in
                ''|*[!0-9]*) existing_port=8080 ;;
            esac
            ask "Private SSH tunnel port" "$existing_port"
            panel_port=$REPLY
            case $panel_port in
                ''|*[!0-9]*) fail "The tunnel port must be a number" ;;
            esac
            [ "$panel_port" -ge 1 ] && [ "$panel_port" -le 65535 ] \
                || fail "The tunnel port must be between 1 and 65535"
            cookie_secure=false
            allowed_origin=
            base_path=
            public_ip=
            forwarded_allow_ips=127.0.0.1
            break
            ;;
        https|HTTPS|h|H)
            access_mode=https
            compose_file=compose.yaml:compose.https.yaml
            panel_port=8080
            cookie_secure=true
            base_path=/dedodaded
            forwarded_allow_ips='*'
            break
            ;;
        *) info "Enter private or https." ;;
    esac
done

existing_username=$(read_env_value PANEL_BOOTSTRAP_USERNAME)
admin_username=dedodaded-admin
admin_password=
if as_root test -f "$DATA_DIR/panel.db"; then
    info "An existing panel database was found. Its administrator account will be preserved."
else
    while :; do
        ask "Administrator username" "$admin_username"
        admin_username=$REPLY
        case $admin_username in
            ''|*[!A-Za-z0-9_.-]*)
                info "Use only letters, numbers, periods, underscores, and hyphens."
                ;;
            *) break ;;
        esac
    done

    while :; do
        printf 'Administrator password (12+ characters): ' >&3
        stty -echo <&3
        IFS= read -r admin_password <&3 || {
            stty echo <&3
            fail "Input was closed"
        }
        stty echo <&3
        printf '\nConfirm administrator password: ' >&3
        stty -echo <&3
        IFS= read -r password_confirmation <&3 || {
            stty echo <&3
            fail "Input was closed"
        }
        stty echo <&3
        printf '\n' >&3
        if [ "${#admin_password}" -lt 12 ]; then
            info "The password must contain at least 12 characters."
        elif [ "$admin_password" != "$password_confirmation" ]; then
            info "The passwords did not match."
        else
            break
        fi
    done
fi

install_docker
start_docker

if [ "$access_mode" = https ]; then
    install_curl
    detected_public_ip=$(discover_public_ipv4)
    public_ip_default=${existing_public_ip:-$detected_public_ip}
    while :; do
        ask "Public IPv4 address for HTTPS" "$public_ip_default"
        if public_ip=$(normalize_ipv4 "$REPLY" 2>/dev/null); then
            break
        fi
        info "Enter a valid IPv4 address assigned to this VPS."
    done
    allowed_origin="https://$public_ip"
    info "Automatic HTTPS will publish only TCP 443. Port 80 is not used."
    info "Ensure the VPS provider firewall also allows inbound TCP 443."
fi

require_source_file .dockerignore
require_source_file .gitattributes
require_source_file install.sh
copy_application

as_root mkdir -p "$DATA_DIR/instances" "$SECRETS_DIR"
as_root chown 1000:1000 "$DATA_DIR" "$DATA_DIR/instances" "$SECRETS_DIR"
as_root chmod 750 "$DATA_DIR" "$DATA_DIR/instances"
as_root chmod 700 "$SECRETS_DIR"
if [ "$access_mode" = https ]; then
    as_root mkdir -p "$CADDY_DATA_DIR" "$CADDY_CONFIG_DIR"
    as_root chmod 700 "$DATA_DIR/caddy" "$CADDY_DATA_DIR" "$CADDY_CONFIG_DIR"
fi

encryption_key=$(read_env_value PANEL_ENCRYPTION_KEY)
if [ -z "$encryption_key" ]; then
    if as_root test -f "$DATA_DIR/panel.db"; then
        fail "The existing database has no matching encryption key in $ENV_FILE"
    fi
    encryption_key=$(dd if=/dev/urandom bs=32 count=1 2>/dev/null \
        | base64 | tr '+/' '-_' | tr -d '\n')
fi

[ -S /var/run/docker.sock ] || fail "Docker started without creating /var/run/docker.sock"
if docker_gid=$(as_root stat -c '%g' /var/run/docker.sock 2>/dev/null); then
    :
elif docker_gid=$(as_root stat -f '%g' /var/run/docker.sock 2>/dev/null); then
    :
else
    fail "Could not determine the Docker socket group ID"
fi
case $docker_gid in
    ''|*[!0-9]*) fail "Docker socket group ID must be numeric" ;;
esac
write_environment
if [ -n "$admin_password" ]; then
    write_bootstrap_password
fi

if [ "$access_mode" = https ] && confirm "Allow inbound HTTPS on TCP 443 in UFW/firewalld?" y; then
    configure_firewall 443
fi

info "Building and starting the panel..."
compose up -d --build --remove-orphans

if [ "$access_mode" = https ]; then
    info "Waiting for Let's Encrypt to issue and verify the IP certificate..."
    wait_for_https
fi

compose ps

if [ "$access_mode" = private ]; then
    cat <<EOF

Installation complete. From your computer, open an SSH tunnel:

  ssh -L $panel_port:127.0.0.1:$panel_port YOUR_USER@YOUR_VPS

Then browse to http://127.0.0.1:$panel_port
EOF
else
    printf '\nInstallation complete. Browse to https://%s/dedodaded\n' "$public_ip"
fi

printf 'Application: %s\nPersistent data: %s\n' "$APP_DIR" "$DATA_DIR"