# Paths and Volumes Configuration

Understanding how directories map between the Docker host and the application containers is critical for proper setup. If paths are misconfigured, downloaded podcasts may not be visible to Audiobookshelf, or they may write to the container's temporary layer and be lost upon restart.

## The Path Model

When running under Docker, three paths must be configured:

1. **Host Path (`HOST_PODCASTS_DIR`)**: The directory path on your Docker host machine where podcasts are stored.
2. **Container Path (`CONTAINER_PODCASTS_DIR`)**: The mount path inside the Docker container (default is `/media/podcasts`). You typically do not need to change this.
3. **App Output Root (`OUTPUT_ROOT`)**: The path the application writes to.

> [!IMPORTANT]
> **Docker volume mounts must exist before the application can write to the share.**
> Ensure the directory specified in `HOST_PODCASTS_DIR` exists on your host machine and has the correct permissions (writable by the configured `PUID`/`PGID`, default 1000:1000).

---

## Scenario Mapping Table

| Scenario | Host Path (`HOST_PODCASTS_DIR`) | Container Path (`CONTAINER_PODCASTS_DIR`) | App Output Root (`OUTPUT_ROOT`) |
| :--- | :--- | :--- | :--- |
| **Mac Docker Test** | `/Volumes/Synology/Media/Podcasts` | `/media/podcasts` | `/media/podcasts` |
| **Proxmox/Linux Docker VM** | `/mnt/podcasts` | `/media/podcasts` | `/media/podcasts` |
| **Native Linux (No Docker)** | `/mnt/podcasts` | *n/a (Not Applicable)* | `/mnt/podcasts` |

---

## Settings Page Behavior

The application allows you to configure the `OUTPUT_ROOT` dynamically from the **Settings** page in the web interface.

* **How it works**: Saving a path on the Settings page writes to the configuration file `/data/settings.json`, which overrides the environment variables or YAML configuration.
* **Important Note for Docker Users**: The settings path must be a valid, writable path **inside the running container** (normally `/media/podcasts`), **NOT the host path**. Configuring a path outside the mounted volumes (such as using your host path `/Volumes/...` or `/mnt/...` in the Settings page) will cause the application to write to the container's ephemeral filesystem, meaning your downloads will be deleted when the container restarts.
