# Security Guidelines

Security is a primary consideration when self-hosting web applications. This guide describes the built-in security features of `abs-media-importer` and best practices for secure deployment.

## 1. Localhost Binding (Default)

By default, the `docker-compose.yml` file binds the web port only to localhost:

```yaml
    ports:
      - "127.0.0.1:8080:8080"
```

This prevents external machines on your local network (LAN) or the public internet from accessing the application until you explicitly choose to expose it.

---

## 2. Authentication Configuration

If you expose the application beyond your localhost (e.g. by changing the port binding to `"8080:8080"`), you must enable authentication.

To enable basic authentication:
1. Open `.env` and set `AUTH_ENABLED=true`.
2. Configure a strong `AUTH_USERNAME` and `AUTH_PASSWORD`.
3. Generate a secure, random `APP_SECRET_KEY` (do not leave it as the default example):
   ```bash
   # Generate a 32-byte hex secret key
   openssl rand -hex 32
   ```
4. Restart the containers.

> [!WARNING]
> Do not expose the application to the internet or your general LAN without enabling Basic Authentication and setting a strong password and secret key.

---

## 3. Reverse Proxy Routing

We strongly recommend routing all external/public traffic through a secure reverse proxy rather than exposing the application port directly to the internet.

Common reverse proxies include:
* **Caddy** / **Nginx** / **Traefik**
* **Cloudflare Tunnels** (highly recommended for simple, secure WAN access without opening router ports)

Ensure your reverse proxy is configured with valid SSL/TLS certificates (e.g. via Let's Encrypt) so that authentication credentials are encrypted in transit.

---

## 4. Path Traversal Protection

`abs-media-importer` contains built-in validation to prevent path traversal vulnerabilities.
* The application validates all destination folder paths and output filenames.
* Any request to write to a path outside the configured `OUTPUT_ROOT` directory will be rejected with an HTTP 400 bad request error.

---

## 5. Proxmox Scripts Warning

Our automated Proxmox VE installation script is provided as a convenience.

> [!CAUTION]
> **Do not run arbitrary scripts downloaded from the internet directly as `root` on your Proxmox VE hypervisor.**
> Always review the code of `proxmox-install.sh` and `guest-install.sh` in the repository before executing them on your host.
