# 🔧 Internship Radar

An automated, lightweight background scraper that monitors GitHub early-career repositories and company ATS job boards (Greenhouse, Lever) for **Electrical & Computer Engineering (ECE)** internships, co-ops, and student roles.

Tuned for an EE student hunting **embedded / firmware** internships:

- **Tier 1 (🔧 embedded/firmware)**: instant Discord ping (drip-paced embed).
- **Tier 2 (🔌 hardware/FPGA/edge-ML)**: no ping; saved for the daily digest.
- SWE-only postings are no longer matched.
- Each alert shows tier, company type (defense, semiconductor, startup, ...), season, location, link.
- **Daily digest** at `digest.hour_local` (default 9, container `TZ`): every new posting from the last 24h in ONE message,
  ranked best-fit first with a one-line "why it fits" by Gemini when `GEMINI_API_KEY` is set, otherwise a plain list.
  Postings never repeat across digests; nothing is sent on empty days.

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
  - Curated GitHub internship lists (SimplifyJobs, IEEE at Cornell ECE, SpeedyApply, and more).
  - Direct public ATS boards for ~65 companies (Greenhouse, Lever, Ashby, SmartRecruiters, Workday), listed under `sources.companies` in `config.yaml`.
  - Keyword search via Adzuna and USAJobs (optional, free API keys in `.env`).
  - A page watcher that pings when the NVIDIA Ignite page changes.
- **🕑 Fresh only**: postings older than `scraper.max_age_days` (default 2) are ignored.
- **💧 Drip alerts**: new matches are queued and sent one by one (never dropped); a large backlog is spread over `drip_window_minutes`.
- **🐳 Docker & Home Server Ready**: Packaged for 24/7 low-resource background operation (`restart: unless-stopped`).
- **🛡️ Outbound Only**: Requires no open router ports or static public IPs.

---

## 🚀 Quick Start (Local)

### 1. Clone & Setup Environment

```bash
# Copy example environment configuration
cp .env.example .env

# Edit .env: DISCORD_WEBHOOK_URL (required), GEMINI_API_KEY / GEMINI_MODEL (optional), TZ
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

### 5. Daily Digest On Demand

```bash
python -m src.main --digest-now --dry-run   # print today's digest, send nothing, mark nothing
python -m src.main --digest-now             # send it now (marks those postings as digested)
# in Docker:
docker compose exec internship_radar python -m src.main --digest-now --dry-run
```

---

## 🏠 Home Server Deployment (Docker Compose)

The easiest way to run the scraper 24/7 on your home server:

### 1. Copy Files to Server

Clone this repository or copy the directory to your server (e.g., via `scp` or `git clone`).

```bash
ssh user@your-home-server
cd ~/find-a-job
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

- **`digest.hour_local`**: hour (0-23, container `TZ`) for the daily digest (default: `9`).
- **`scraper.interval_minutes`**: How often the scraper polls for new positions (default: `30` mins).
- **`filter.inclusion_keywords`**: Add or remove specialized subfield keywords.
- **`filter.exclusion_keywords`**: Filter out seniority levels or unrelated roles (e.g. `frontend`, `marketing`, `senior`).
- **`sources.github_repositories`**: Add new markdown repositories.
- **`sources.greenhouse_boards` / `lever_boards`**: Add new company ATS tokens.

---

## 🧪 Running Tests

```bash
pytest tests/
```
