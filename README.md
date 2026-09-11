# ⚡ ECE Internship Discord Scraper & Radar

An automated, lightweight background scraper that monitors GitHub early-career repositories and company ATS job boards (Greenhouse, Lever) for **Electrical & Computer Engineering (ECE)** internships, co-ops, and student roles.

When a new matching position is discovered, it dispatches an instant, rich embed notification directly to your Discord channel via Webhook.

---

## 🌟 Key Features

- **🎯 ECE Specific Filtering**: Pre-configured with keywords across:
  - **Embedded & Firmware**: RTOS, C/C++, Microcontrollers, Device Drivers, ARM Cortex, STM32, ESP32, BSP
  - **Digital Logic & Silicon**: FPGA, ASIC, RTL, Verilog, SystemVerilog, VHDL, VLSI, SoC, Chip Design
  - **Computer Architecture**: CPU/GPU Architecture, RISC-V, DSP
  - **Hardware & PCB**: Altium, Schematics, Power Electronics, RF, Analog, Signal Integrity
  - **Validation & Robotics**: Silicon Validation, Post-Silicon, Board Bring-up, Mechatronics, Controls
- **🔄 Deduplication via SQLite**: Tracks seen jobs to guarantee you never receive duplicate notifications.
- **🚀 Multi-Source Aggregation**:
  - Curated GitHub internship tracking tables (SimplifyJobs, Opps, Tech Internships).
  - Direct public ATS API boards (SpaceX, Neuralink, Anduril, Skydio, SambaNova, Cerebras, Tenstorrent, Verkada, Joby, Palantir).
- **🐳 Docker & Home Server Ready**: Packaged for 24/7 low-resource background operation (`restart: unless-stopped`).
- **🛡️ Outbound Only**: Requires no open router ports or static public IPs.

---

## 🚀 Quick Start (Local)

### 1. Clone & Setup Environment

```bash
# Copy example environment configuration
cp .env.example .env

# Edit .env and paste your Discord Webhook URL
nano .env
```

### 2. Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Test Discord Webhook Connectivity

```bash
python -m src.main --test-webhook
```

### 4. Run a Dry-Run (View Matches Without Sending)

```bash
python -m src.main --dry-run
```

---

## 🏠 Home Server Deployment (Docker Compose)

The easiest way to run the scraper 24/7 on your home server:

### 1. Copy Files to Server

Clone this repository or copy the directory to your server (e.g., via `scp` or `git clone`).

```bash
ssh user@your-home-server
cd ~/discord-scraper
```

### 2. Configure `.env`

```bash
cp .env.example .env
nano .env
```

Set your Discord Webhook URL:

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN
```

### 3. Start with Docker Compose

```bash
docker compose up -d --build
```

### 4. View Live Logs

```bash
docker compose logs -f
```

To stop or restart:

```bash
docker compose down
docker compose restart
```

---

## ⚙️ Configuration & Customization (`config.yaml`)

You can modify `config.yaml` at any time without recompiling the Docker container (it is volume-mounted):

- **`scraper.interval_minutes`**: How often the scraper polls for new positions (default: `30` mins).
- **`filter.inclusion_keywords`**: Add or remove specialized subfield keywords.
- **`filter.exclusion_keywords`**: Filter out seniority levels or unrelated roles (e.g. `frontend`, `marketing`, `senior`).
- **`sources.github_repositories`**: Add new markdown repositories.
- **`sources.greenhouse_boards` / `lever_boards`**: Add new company ATS tokens.

---

## 🌐 Note on Custom Domains (`witchs.me`)

Because the scraper pushes notifications outbound to Discord's servers via HTTPS, **no inbound open ports or domain setup are required** for basic operation.

However, if you'd like to use your domain `witchs.me`:

1. **Custom Branding**: You can host an avatar icon on your domain (e.g. `https://witchs.me/assets/radar-icon.png`) and point `notification.avatar_url` in `config.yaml` to it.
2. **Future Web UI**: If you ever want a web dashboard to browse past jobs stored in SQLite, you can point a subdomain (e.g., `jobs.witchs.me`) to a lightweight web viewer running on your home server behind a reverse proxy (e.g., Caddy, Nginx, or Cloudflare Tunnel).

---

## 🧪 Running Tests

```bash
pytest tests/
```
