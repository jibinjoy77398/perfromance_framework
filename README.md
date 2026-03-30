# ⚡ Performance Testing Framework

A Python + Playwright POM-based framework for comprehensive website performance testing.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Configure your target site
#    Edit config/sites.json

# 3. Run all tests
python run.py

# --- OR USE DOCKER ---
docker-compose up
```

## Configuration

### `config/sites.json`
```json
[
  {
    "name": "My App",
    "url": "https://example.com",
    "credentials": {
      "username": "user@example.com",
      "password": "secret123"
    }
  }
]
```
> `credentials` is optional — omit the key for public sites.

### `config/thresholds.json`
Edit any threshold to match your SLA. Default values follow Google Web Vitals.

| Metric | Default |
|---|---|
| LCP | 2500 ms |
| FCP | 1800 ms |
| TTFB | 800 ms |
| CLS | 0.1 |
| TBT | 300 ms |
| Load Time | 4000 ms |
| JS Heap | 50 MB |
| p95 Load | 6000 ms |
| StdDev | 800 ms |

## Test Modules

| Module | What it Tests |
|---|---|
| `test_page_load` | FCP, LCP, TTFB, load time, DCL |
| `test_interactions` | CLS, TBT |
| `test_network` | Failed & slow requests |
| `test_resources` | Request count & total page size |
| `test_memory` | JS heap usage |
| `test_baseline` ⭐ | N concurrent runs → p50/p95/stddev of all Core Web Vitals |
| `test_network_stress` ⭐ | Broadband / 4G / Fast 3G / Slow 3G |
| `test_breakpoint` ⭐ | Ramps 1→N users, finds exact failure point & reason |
| `test_resource_analysis` ⭐ | Grouped by type, top-10 slowest & heaviest requests |

## CLI Options

```
python run.py --help

--site "My App"          Run one site by name
--concurrent 10          Override baseline concurrency (default: 5)
--ramp 1,2,5,10,20,50   Override breakpoint ramp steps
--report-dir ./reports   Custom report output directory
--headful                Show browser window
--tests baseline,stress  Run only specific modules
```

## Reports

HTML reports are saved to `reports/<date>/<site_name>_report.html`.

Each report includes:
- **Grade (A–F)** based on overall pass rate
- **Metric cards** — color-coded PASS / WARN / FAIL
- **Baseline table** — p50, p95, stddev per metric
- **Network stress heatmap** — all 4 profiles side-by-side
- **Breakpoint chart** — ramp visualization with failure annotation
- **Resource breakdown** — by type + top-10 slowest/heaviest lists

## Project Structure

```
performanceframework/
├── config/              ← sites.json, thresholds.json (edit these)
├── core/                ← browser manager, metrics collector
├── pages/               ← POM base page
├── tests/               ← all test modules
├── reporters/           ← HTML report generator
├── utils/               ← threshold evaluator
└── run.py               ← entry point

## 🐳 Docker Support

This framework is fully containerized for consistent testing and easy deployment.

### Local Execution (Docker Compose)
The easiest way to run the dashboard and API is using Docker Compose:

```bash
docker-compose up
```
This starts the FastAPI server on [http://localhost:8000](http://localhost:8000). Your local `reports/`, `config/`, and `database/` directories are mapped to the container so data is persisted.

### Manual Docker Build & Run
```bash
# Build the image
docker build -t j1b1n/performance-framework .

# Run the server
docker run -p 8000:8000 --env-file .env j1b1n/performance-framework

# Run a specific test command
docker run j1b1n/performance-framework python run.py --site "My App"
```

### CI/CD Integration
A GitHub Action is included in `.github/workflows/docker-publish.yml` that automatically builds and pushes the image to Docker Hub on every push to `main`.

**Required GitHub Secrets:**
- `DOCKERHUB_USERNAME`: `j1b1n`
- `DOCKERHUB_TOKEN`: Your [Docker Hub Access Token](https://hub.docker.com/settings/security)
```
