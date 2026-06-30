# Proxmox VE VM Installer for yt-abs-importer

This installer allows you to provision a dedicated Virtual Machine (VM) running Debian 12 (stable) on your Proxmox VE host and install `yt-abs-importer` into it automatically. 

You can choose between two deployment modes:
1. **Docker VM (Recommended):** The VM installs Docker Engine and starts the application stack via Docker Compose.
2. **Native VM:** The VM runs the application dependencies directly on the guest OS, managing the web app and background worker using `systemd`.

---

## ⚠️ Security Warning

> [!WARNING]
> Running scripts fetched directly from the internet as `root` on your Proxmox VE host is a potential security risk.
> Always review the code of [proxmox-install.sh](proxmox-install.sh) and [guest-install.sh](guest-install.sh) before executing them.

---

## Prerequisites

- A running **Proxmox VE** instance.
- Internet connectivity on the Proxmox host (to download the Debian Cloud image and repository).
- A network bridge (typically `vmbr0`) with an active DHCP server on your LAN (so the guest VM gets assigned an IP address).

---

## Installation

### 1. One-Line Installer (Recommended)

SSH to your Proxmox VE host as `root` and run the following command:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/andrewtryder/yt-abs-importer/main/scripts/proxmox/proxmox-install.sh)"
```

### 2. Interactive Installation

If you run the script without any parameters, it will guide you interactively through the configuration, including:
- Deployment mode (Docker VM or Native VM)
- Next available VM ID (automatically queried from the cluster)
- Hostname
- Storage pool (lists active storages, defaults to `local`)
- Network bridge (defaults to `vmbr0`)
- VM Specs (cores, RAM, disk size)

### 3. Non-Interactive Command (Examples)

You can bypass interactive prompts by passing command-line flags.

#### Docker VM Deployment:
```bash
./proxmox-install.sh \
  --mode docker-vm \
  --vmid 105 \
  --hostname yt-abs-docker \
  --storage local \
  --bridge vmbr0 \
  --cores 2 \
  --memory 2048 \
  --disk 16G \
  --start true
```

#### Native VM Deployment:
```bash
./proxmox-install.sh \
  --mode native-vm \
  --vmid 106 \
  --hostname yt-abs-native \
  --storage local \
  --bridge vmbr0 \
  --cores 2 \
  --memory 2048 \
  --disk 16G \
  --start true
```

---

## Manual Installation Steps (Host Level)

If you prefer to configure the VM manually on your Proxmox host:

1. **Download the cloud-init template image:**
   ```bash
   wget -P /var/lib/vz/template/qemu/ https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2
   ```
2. **Create the VM:**
   ```bash
   qm create 999 --name yt-abs-importer --cores 2 --memory 2048 --net0 virtio,bridge=vmbr0 --scsihw virtio-scsi-pci --ostype l26
   ```
3. **Import and attach disk:**
   ```bash
   qm importdisk 999 /var/lib/vz/template/qemu/debian-12-genericcloud-amd64.qcow2 local
   qm set 999 --scsih0 local:vm-999-disk-0
   qm resize 999 scsih0 16G
   ```
4. **Configure cloudinit controller & boot:**
   ```bash
   qm set 999 --ide2 local:cloudinit
   qm set 999 --boot order=scsih0
   qm set 999 --serial0 socket --vga serial0
   qm set 999 --ipconfig0 ip=dhcp
   ```
5. **Add user data configuration:**
   Copy the `cloud-init-user-data.yml` template, customize it, copy to `/var/lib/vz/snippets/user-data-999.yml`, and link it:
   ```bash
   qm set 999 --cicustom "user=local:snippets/user-data-999.yml"
   ```
6. **Start VM:**
   ```bash
   qm start 999
   ```

---

## Configuration Instructions

After deployment, you must configure the application directory mounts and credentials.

1. Find the guest VM's IP:

   The interactive installer configures the VM with `qemu-guest-agent` enabled. Once the guest VM has finished booting and the agent starts, you can fetch its network interfaces (including IP address) using:
   ```bash
   qm guest cmd <VMID> network-get-interfaces
   ```
   *Alternative options if the agent is unreachable:*
   * Check the Proxmox VE Web UI under **VM Summary** -> **IPs**.
   * Inspect DHCP leases on your local router or network manager.
   * Access the VM's console in Proxmox and run `ip a`.

2. SSH to the guest VM:
   ```bash
   ssh debian@<GUEST_IP>
   ```
3. Configure settings:
   - **Docker VM:** Edit `/opt/yt-abs-importer/.env`.
   - **Native VM:** Edit `/etc/yt-abs-importer/.env`.

### Connecting Audiobookshelf Directories
To mount your Audiobookshelf podcasts directory (e.g. NFS share) inside the VM:
1. Open `/etc/fstab` in the VM and add your network mount:
   ```fstab
   nas.local:/volume1/podcasts  /mnt/podcasts  nfs  defaults,_netdev,nofail  0  0
   ```
2. Mount the share:
   ```bash
   sudo mkdir -p /mnt/podcasts
   sudo mount -a
   ```
3. Map the directory using environment variables (avoid editing `docker-compose.yml` directly):
   - **Docker VM:** In `/opt/yt-abs-importer/.env`, configure the paths. This maps the host share into the container using environment variables:
     ```env
     # Path on the VM host (where the NFS/SMB share is mounted)
     HOST_PODCASTS_DIR=/mnt/podcasts
     
     # Path inside the container (do not change)
     CONTAINER_PODCASTS_DIR=/media/podcasts
     
     # App output root inside the container (must match CONTAINER_PODCASTS_DIR)
     OUTPUT_ROOT=/media/podcasts
     ```
     *Advanced Note:* Direct modification of `docker-compose.yml` volume definitions is also possible but not recommended, as it makes application updates via `git pull` harder to merge.
     
     After editing `.env`, restart the stack:
     ```bash
     docker compose up -d
     ```
   - **Native VM:** In `/etc/yt-abs-importer/.env`, configure the output directory to point directly to the host mount:
     ```env
     OUTPUT_ROOT=/mnt/podcasts
     ```
     Then restart the systemd services:
     ```bash
     sudo systemctl restart yt-abs-importer-app yt-abs-importer-worker
     ```

---

## How to View Logs

### Docker VM
SSH into the VM and run:
```bash
cd /opt/yt-abs-importer
docker compose logs -f app     # Web server logs
docker compose logs -f worker  # RQ worker logs
```

### Native VM
SSH into the VM and run:
```bash
journalctl -u yt-abs-importer-app -f     # Web server logs
journalctl -u yt-abs-importer-worker -f  # RQ worker logs
```

---

## How to Update

### Docker VM
SSH into the VM and run:
```bash
cd /opt/yt-abs-importer
git pull
docker compose down
docker compose up --build -d
```

### Native VM
SSH into the VM and run:
```bash
cd /opt/yt-abs-importer
sudo git pull
sudo /opt/yt-abs-importer/.venv/bin/pip install -r requirements.txt
sudo systemctl restart yt-abs-importer-app yt-abs-importer-worker
```

---

## How to Uninstall

On the Proxmox host:
1. Stop the VM:
   ```bash
   qm stop <VMID>
   ```
2. Destroy the VM:
   ```bash
   qm destroy <VMID>
   ```
3. Remove user-data snippets:
   ```bash
   rm -f /var/lib/vz/snippets/user-data-<VMID>.yml
   ```
