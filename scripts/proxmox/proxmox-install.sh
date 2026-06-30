#!/bin/bash
# ============================================================
# proxmox-install.sh — Proxmox VE host installer
# ============================================================
set -euo pipefail

# Helper logging functions
log() {
    echo -e "[$(date +'%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    echo -e "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1" >&2
}

# 1. Environment & Privilege Validations
if [ "$(id -u)" -ne 0 ]; then
    error "This script must be run as root."
    exit 1
fi

if ! command -v pveversion &>/dev/null || [ ! -d "/etc/pve" ]; then
    error "This script must be run directly on a Proxmox VE host."
    exit 1
fi

# Initialize variables
MODE=""
VMID=""
HOSTNAME=""
STORAGE=""
BRIDGE=""
CORES=""
MEMORY=""
DISK=""
START_VM=""

# Helper to print usage instructions
usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --mode <docker-vm|native-vm>  Select app install mode"
    echo "  --vmid <id>                   Set VM ID (must be unused)"
    echo "  --hostname <name>             Set VM Hostname"
    echo "  --storage <storage>           PVE storage pool for VM disk"
    echo "  --bridge <bridge>             PVE network bridge (e.g. vmbr0)"
    echo "  --cores <n>                   Number of CPU cores"
    echo "  --memory <MiB>                Memory size in MiB"
    echo "  --disk <size>                 Disk size (e.g. 16G)"
    echo "  --start <true|false>          Whether to start VM after install"
    echo "  --help                        Show this message"
    echo ""
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --mode)
            MODE="$2"
            shift 2
            ;;
        --vmid)
            VMID="$2"
            shift 2
            ;;
        --hostname)
            HOSTNAME="$2"
            shift 2
            ;;
        --storage)
            STORAGE="$2"
            shift 2
            ;;
        --bridge)
            BRIDGE="$2"
            shift 2
            ;;
        --cores)
            CORES="$2"
            shift 2
            ;;
        --memory)
            MEMORY="$2"
            shift 2
            ;;
        --disk)
            DISK="$2"
            shift 2
            ;;
        --start)
            START_VM="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            error "Unknown argument: $1"
            usage
            exit 1
            ;;
    esac
done

# Interactive mode if arguments are missing
echo "============================================================"
echo "          yt-abs-importer Proxmox VM Installer              "
echo "============================================================"

if [ -z "$MODE" ]; then
    echo "Select Deployment Mode:"
    echo "  1) Docker VM (App runs inside Docker compose inside a VM)"
    echo "  2) Native VM (App runs as systemd services directly in a VM)"
    read -rp "Select mode [1-2]: " mode_choice
    if [ "$mode_choice" = "1" ]; then
        MODE="docker-vm"
    elif [ "$mode_choice" = "2" ]; then
        MODE="native-vm"
    else
        error "Invalid mode selection."
        exit 1
    fi
fi

if [ -z "$VMID" ]; then
    SUGGESTED_ID=$(pvesh get /cluster/nextid 2>/dev/null || echo "100")
    read -rp "Enter VM ID [default: $SUGGESTED_ID]: " input_vmid
    VMID="${input_vmid:-$SUGGESTED_ID}"
fi

if [ -z "$HOSTNAME" ]; then
    read -rp "Enter Hostname [default: yt-abs-importer]: " input_hostname
    HOSTNAME="${input_hostname:-yt-abs-importer}"
fi

if [ -z "$STORAGE" ]; then
    echo "Active storage pools:"
    pvesm status | grep -E "active" | awk '{print "  - " $1}'
    read -rp "Enter storage pool [default: local]: " input_storage
    STORAGE="${input_storage:-local}"
fi

if [ -z "$BRIDGE" ]; then
    read -rp "Enter network bridge [default: vmbr0]: " input_bridge
    BRIDGE="${input_bridge:-vmbr0}"
fi

if [ -z "$CORES" ]; then
    read -rp "Enter CPU cores [default: 2]: " input_cores
    CORES="${input_cores:-2}"
fi

if [ -z "$MEMORY" ]; then
    read -rp "Enter Memory in MiB [default: 2048]: " input_memory
    MEMORY="${input_memory:-2048}"
fi

if [ -z "$DISK" ]; then
    read -rp "Enter Disk size [default: 16G]: " input_disk
    DISK="${input_disk:-16G}"
fi

if [ -z "$START_VM" ]; then
    read -rp "Start VM automatically after creation? (y/n) [default: y]: " input_start
    if [[ "$input_start" =~ ^[nN] ]]; then
        START_VM="false"
    else
        START_VM="true"
    fi
fi

# 2. Input Validations
log "Validating configurations..."

# Validate VM ID
if ! [[ "$VMID" =~ ^[0-9]+$ ]]; then
    error "VMID '$VMID' must be a valid positive integer."
    exit 1
fi
if qm status "$VMID" &>/dev/null; then
    error "VM ID $VMID is already in use by another VM."
    exit 1
fi

# Validate Storage Pool
if ! pvesm status -storage "$STORAGE" &>/dev/null; then
    error "Storage pool '$STORAGE' does not exist or is inactive."
    exit 1
fi
if [ -f "/etc/pve/storage.cfg" ]; then
    if ! grep -A 10 "storage: $STORAGE" /etc/pve/storage.cfg | grep -q "content.*images"; then
        log "WARNING: Storage pool '$STORAGE' may not support virtual disk images (content: images)."
    fi
fi

# Validate Network Bridge
if ! ip link show "$BRIDGE" &>/dev/null; then
    error "Network bridge '$BRIDGE' does not exist on this host."
    exit 1
fi

# 3. Download VM cloud-init template image
IMAGE_DIR="/var/lib/vz/template/qemu"
mkdir -p "$IMAGE_DIR"
IMAGE_PATH="${IMAGE_DIR}/debian-12-genericcloud-amd64.qcow2"

if [ ! -f "$IMAGE_PATH" ]; then
    log "Downloading Debian 12 generic cloud image (approx 350MB)..."
    curl -L "https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2" -o "$IMAGE_PATH"
fi

# 4. Prepare Cloud-Init snippets
log "Configuring custom cloud-init user-data..."
mkdir -p /var/lib/vz/snippets
pvesm set local --content "images,vztmpl,iso,snippets" || true

SNIPPET_FILE="/var/lib/vz/snippets/user-data-${VMID}.yml"

# Generate VM-specific cloud-init configuration
cat <<EOF > "$SNIPPET_FILE"
#cloud-config
# Generated for yt-abs-importer VM ${VMID}
package_update: true
package_upgrade: false
packages:
  - git
  - curl
  - ca-certificates
  - qemu-guest-agent

users:
  - name: debian
    gecos: Debian User
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    lock_passwd: true
EOF

# Inject host authorized_keys if available so user can SSH in immediately
if [ -f "/root/.ssh/authorized_keys" ]; then
    echo "    ssh_authorized_keys:" >> "$SNIPPET_FILE"
    while read -r key; do
        if [[ -n "$key" && ! "$key" =~ ^# ]]; then
            echo "      - \"$key\"" >> "$SNIPPET_FILE"
        fi
    done < "/root/.ssh/authorized_keys"
fi

# Append execution commands depending on Mode
cat <<EOF >> "$SNIPPET_FILE"

runcmd:
  - mkdir -p /opt
  - git clone https://github.com/andrewtryder/yt-abs-importer.git /opt/yt-abs-importer
  - systemctl enable qemu-guest-agent --now
EOF

if [ "$MODE" = "docker-vm" ]; then
    cat <<EOF >> "$SNIPPET_FILE"
  - echo "Installing Docker Engine..."
  - curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  - sh /tmp/get-docker.sh
  - systemctl enable docker --now
  - cd /opt/yt-abs-importer
  - cp .env.example .env
  - SECRET_KEY=\$(openssl rand -hex 32)
  - sed -i "s|^APP_SECRET_KEY=.*|APP_SECRET_KEY=\${SECRET_KEY}|" .env
  - sed -i "s|^REDIS_URL=.*|REDIS_URL=redis://redis:6379/0|" .env
  - sed -i "s|^DATABASE_URL=.*|DATABASE_URL=sqlite+aiosqlite:////data/app.db|" .env
  - echo "Starting Docker Compose stack..."
  - docker compose up -d
EOF
elif [ "$MODE" = "native-vm" ]; then
    cat <<EOF >> "$SNIPPET_FILE"
  - echo "Running guest-install.sh..."
  - bash /opt/yt-abs-importer/scripts/proxmox/guest-install.sh
EOF
fi

# 5. Create Proxmox Virtual Machine
log "Creating VM ${VMID} (${HOSTNAME})..."
qm create "$VMID" \
    --name "$HOSTNAME" \
    --cores "$CORES" \
    --memory "$MEMORY" \
    --net0 virtio,bridge="$BRIDGE" \
    --scsihw virtio-scsi-pci \
    --ostype l26 \
    --agent 1

log "Importing Debian disk image to storage ${STORAGE}..."
IMPORT_OUT=$(qm importdisk "$VMID" "$IMAGE_PATH" "$STORAGE" 2>&1)
DISK_VOL=$(echo "$IMPORT_OUT" | grep -oE "([a-zA-Z0-9_-]+:vm-${VMID}-disk-[0-9]+|[a-zA-Z0-9_-]+:[0-9]+/vm-${VMID}-disk-[0-9]+\.qcow2)" | head -n 1)

if [ -z "$DISK_VOL" ]; then
    log "Grep could not parse volume. Using default volume path..."
    DISK_VOL="${STORAGE}:vm-${VMID}-disk-0"
fi

log "Configuring imported disk as boot drive..."
qm set "$VMID" --scsih0 "$DISK_VOL"
qm resize "$VMID" scsih0 "$DISK"

# Configure cloud-init drives and configs
log "Setting up Cloud-Init controller..."
qm set "$VMID" --ide2 "$STORAGE":cloudinit
qm set "$VMID" --boot order=scsih0
qm set "$VMID" --serial0 socket --vga serial0
qm set "$VMID" --ipconfig0 ip=dhcp

log "Binding custom user-data cloud-init snippet..."
qm set "$VMID" --cicustom "user=local:snippets/user-data-${VMID}.yml"

# 6. Start the VM if requested
if [ "$START_VM" = "true" ]; then
    log "Starting VM ${VMID}..."
    qm start "$VMID"
fi

# 7. Print clear summary of changes
echo ""
echo "============================================================"
echo "          INSTALLATION SUMMARY & NEXT STEPS                 "
echo "============================================================"
echo "  VMID:            $VMID"
echo "  Hostname:        $HOSTNAME"
echo "  Selected Mode:   $MODE"
echo "  OS:              Debian 12 (stable)"
echo "  Storage Pool:    $STORAGE"
echo "  VCPU Cores:      $CORES"
echo "  Memory:          $MEMORY MiB"
echo "  Disk Size:       $DISK"
echo ""
echo "Getting the VM Guest IP address:"
echo "  - Wait 1-2 minutes for the VM to boot and obtain an IP via DHCP."
echo "  - Run the following command on this Proxmox host to fetch the IP:"
echo "      qm guest cmd $VMID network-get-interfaces"
echo "    Or check the Proxmox GUI or your router's DHCP leases."
echo ""
if [ "$MODE" = "docker-vm" ]; then
    echo "App Paths inside VM:"
    echo "  - App Repository:  /opt/yt-abs-importer"
    echo "  - Config File:     /opt/yt-abs-importer/.env"
    echo "  - SQLite DB / Work: /opt/yt-abs-importer/data"
    echo ""
    echo "Useful commands inside VM (SSH as 'debian'):"
    echo "  - Check Docker containers:   docker compose ps"
    echo "  - View Application Logs:     docker compose logs -f app"
    echo "  - View Worker Logs:          docker compose logs -f worker"
else
    echo "App Paths inside VM:"
    echo "  - App Repository:  /opt/yt-abs-importer"
    echo "  - Config File:     /etc/yt-abs-importer/.env"
    echo "  - SQLite DB / Work: /var/lib/yt-abs-importer"
    echo "  - Logs Directory:  /var/log/yt-abs-importer"
    echo ""
    echo "Useful commands inside VM (SSH as 'debian'):"
    echo "  - View Web Server Logs:      journalctl -u yt-abs-importer-app -f"
    echo "  - View Worker Logs:          journalctl -u yt-abs-importer-worker -f"
    echo "  - Restart Service:           sudo systemctl restart yt-abs-importer-app"
fi
echo "============================================================"
EOF
