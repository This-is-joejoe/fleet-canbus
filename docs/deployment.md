# Public Deployment — Oracle Cloud Always Free (ARM)

Runbook for hosting the pipeline as a public, always-on demo with a live Grafana
URL over HTTPS. Uses the standalone `docker-compose.public.yml` (hardened: only
Caddy is internet-facing; Postgres/Prometheus/MQTT stay on the internal network;
Grafana is anonymous read-only behind Caddy).

**Target:** Oracle Cloud **Always Free** ARM Ampere A1 (free forever, persistent
disk — avoids the managed-TimescaleDB-free-tier reliability problem).

---

## 0. What a visitor will see

`https://<your-domain>` → Grafana, logged in automatically as an anonymous
**Viewer**, showing the *Fleet Overview* and *Pipeline Health* dashboards with
live data from a 6-device synthetic fleet. No login prompt, no edit rights.

---

## 1. Create the ARM instance

Oracle Cloud console → **Compute → Instances → Create instance**:

- **Image:** Canonical Ubuntu 22.04
- **Shape — two Always-Free options:**
  - `VM.Standard.A1.Flex` (Ampere **ARM**), **2 OCPU / 12 GB** — comfortable, but
    frequently capacity-blocked (see gotcha).
  - `VM.Standard.E2.1.Micro` (AMD **x86**), **1 OCPU / 1 GB** — almost always
    available and zero arch risk, but 1 GB is tight: **requires swap (step 3b)**
    and the trimmed 2-device fleet (already the default in the public compose).
- **SSH keys:** paste your public key (`~/.ssh/id_rsa.pub`).
- Keep the default VCN (it creates one with a public subnet).

> **Gotcha — "Out of host capacity":** free **A1** shapes are often unavailable in
> a given Availability Domain. Retry, switch **Availability Domain** (AD-1/2/3),
> shrink to 1 OCPU / 6 GB, or fall back to **E2.1.Micro** (x86, always available).
> This is the #1 friction point; it is not a mistake on your end.

Note the instance's **public IP** once it's running.

---

## 2. Open ports 80 + 443 (two layers — both required)

Oracle has **two** firewalls. Opening only one is the classic "port is open but
nothing connects" trap.

### 2a. VCN security list (cloud firewall)

Networking → your **VCN** → **Security Lists** → default list → **Add Ingress Rules**:

| Source CIDR | Protocol | Dest port |
|---|---|---|
| `0.0.0.0/0` | TCP | 80 |
| `0.0.0.0/0` | TCP | 443 |

(SSH 22 is already open by default. Optionally restrict it to your own IP.)

### 2b. Instance-local iptables (host firewall) — the Oracle Ubuntu gotcha

Oracle's Ubuntu image ships with restrictive `iptables` that block everything
except SSH, **even after** you open the VCN security list. SSH in and add
persistent ACCEPT rules for 80/443:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

(Insert at position 6 so the rules land *before* the default REJECT. Verify with
`sudo iptables -L INPUT --line-numbers`.)

---

## 3. Install Docker + Compose

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker    # or log out/in so group membership applies
docker compose version   # confirm the compose plugin is present
```

The convenience script installs the right build (arm64 or x86) automatically.

---

## 3b. Add swap (required on the 1 GB E2.1.Micro; skip on A1)

1 GB RAM is too little to run the full stack safely. A 2 GB swap file makes it
comfortable for this low-traffic demo:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab   # persist across reboots
free -h                                                       # confirm 2Gi swap
```

The public compose already trims the fleet to 2 simulators and caps Prometheus
retention at 3h for this box; bump `SIM_REPLICAS` in `.env` on a bigger instance.

---

## 4. Point a free domain at the box (DuckDNS)

Caddy needs a real hostname to get a TLS cert.

1. https://www.duckdns.org → sign in → create a subdomain, e.g. `yunan-fleet`.
2. Set its IP to the instance **public IP**. You now have
   `yunan-fleet.duckdns.org`.
3. Confirm it resolves: `ping yunan-fleet.duckdns.org` shows the right IP.

---

## 5. Clone + configure secrets

```bash
git clone https://github.com/This-is-joejoe/fleet-canbus.git
cd fleet-canbus

# Secrets live in .env (gitignored — never committed):
cat > .env <<'EOF'
SITE_ADDRESS=yunan-fleet.duckdns.org
GF_ADMIN_PASSWORD=<a long random password>
EOF
```

---

## 6. Launch

```bash
docker compose -f docker-compose.public.yml up -d --build
```

First run builds the simulator/subscriber images for arm64 and pulls the rest.
Caddy then requests a Let's Encrypt cert for `SITE_ADDRESS` (needs port 80
reachable + DNS correct — steps 2 and 4).

---

## 7. Verify

```bash
# all containers up; 6 simulator replicas
docker compose -f docker-compose.public.yml ps

# Caddy obtained a certificate (look for "certificate obtained successfully")
docker compose -f docker-compose.public.yml logs caddy | grep -i cert

# data is flowing
docker compose -f docker-compose.public.yml exec timescaledb \
  psql -U fleet -d fleet -c "SELECT count(DISTINCT device_id) FROM battery_telemetry;"
```

Then open **`https://<your-domain>`** in a browser → Grafana loads anonymously,
dashboards show live data.

### Security check (prove the hardening)

From your **laptop** (not the box), these must all **fail/refuse** — only 443
(and 80→redirect) should answer:

```bash
nc -vz <public-ip> 5432   # Postgres  — must be refused/filtered
nc -vz <public-ip> 9090   # Prometheus — must be refused/filtered
nc -vz <public-ip> 1883   # MQTT      — must be refused/filtered
nc -vz <public-ip> 443    # HTTPS     — must succeed
```

---

## Security notes

- **Postgres/Prometheus/MQTT** have no host ports in the public compose — reachable
  only on the internal Docker network. The `fleet/fleet` DB password is therefore
  never exposed; still, rotate it if you later publish any of these.
- **Grafana** is anonymous **Viewer** only; admin login is gated by the strong
  `GF_ADMIN_PASSWORD` from `.env`. Sign-up is disabled.
- **ntfy topic:** the overheat contact point in
  `config/grafana/provisioning/alerting/contact-points.yaml` is committed, so the
  topic name is public. The public fleet injects no faults, so it never fires; if
  you care, rotate the topic to an unguessable value and keep it in `.env`-driven
  config instead.
- **Cost:** Always Free A1 does not bill. Retention policies (raw 7d / 1min 30d /
  1hour 1y) keep disk bounded, so the demo is sustainable indefinitely.

---

## Updating the deployment

```bash
cd fleet-canbus && git pull
docker compose -f docker-compose.public.yml up -d --build
```
