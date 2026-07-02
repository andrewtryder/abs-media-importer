# Proxmox VE Deployment Guide

`abs-media-importer` can be deployed in a Proxmox VE environment as either a dedicated Virtual Machine (VM) running Debian or inside a Linux Container (LXC).

For complete interactive installer details, refer to the [Proxmox Installer Script README](../scripts/proxmox/README.md).

---

## 1. Deployment Modes

### A. Docker VM (Recommended)
This mode provisions a Debian 12 VM, installs Docker Engine, and starts the application stack via Docker Compose.

* **Advantages**: Simple updates, isolated dependencies, and clean sandboxing.
* **Volume Mapping**: You mount the network storage (e.g., NFS share) on the VM host at `/mnt/podcasts` and map it into the containers using the `.env` configuration.

### B. Native VM
This mode installs application dependencies directly on the guest Debian OS, managing the FastAPI web app and the RQ background worker as standard `systemd` services.

* **Advantages**: Minimal overhead.
* **Volume Mapping**: You mount the network storage directly into the VM OS (e.g. `/mnt/podcasts`) and point the application's `OUTPUT_ROOT` to it directly.

---

## 2. Setting Up Storage Mounts

### Mount NFS on the Proxmox Host (for LXC bind-mounts)
If deploying via LXC, mount the NFS share on your Proxmox VE host and bind-mount it into the container.

1. Add your mount to `/etc/fstab` on the Proxmox host:
   ```fstab
   nas.local:/volume1/podcasts  /mnt/podcasts  nfs  defaults,_netdev,nofail  0  0
   ```
2. Mount the share:
   ```bash
   mount -a
   ```
3. Bind-mount the host directory into your LXC container. Under the LXC container's **Resources** tab in the Proxmox UI, click **Add Mount Point**:
   * **Host Path**: `/mnt/podcasts`
   * **Mount Point (Path in container)**: `/mnt/podcasts`
   * Or configure via your container's configuration file `/etc/pve/lxc/<ID>.conf`:
     ```conf
     mp0: /mnt/podcasts,mp=/mnt/podcasts
     ```

---

## 3. Configuring the Application Paths

Instead of editing `docker-compose.yml` directly, configure your VM/container path variables in the `.env` file.

### For Docker VM Deployments
SSH into the guest VM, open `/opt/abs-media-importer/.env`, and configure:
```env
HOST_PODCASTS_DIR=/mnt/podcasts
CONTAINER_PODCASTS_DIR=/media/podcasts
OUTPUT_ROOT=/media/podcasts
```
Then restart the containers:
```bash
cd /opt/abs-media-importer
docker compose up -d
```

### For Native VM Deployments
In a native systemd deployment, open `/etc/abs-media-importer/.env` and update the output root directly:
```env
OUTPUT_ROOT=/mnt/podcasts
```
Then restart the services:
```bash
sudo systemctl restart abs-media-importer-app abs-media-importer-worker
```
