# Autonomous Multi-Agent System for Afforestation Site Discovery
## Project Brief & Feasibility Report

---

**Project codename:** *TerraScout* (working title)
**Document type:** Project proposal & feasibility analysis
**Context:** 24-hour hackathon submission targeting the "Multi-agent autonomy that ships real work, end-to-end" brief
**Status:** Pre-build feasibility review

---

## 1. Executive Summary

TerraScout is an autonomous multi-agent pipeline that discovers, evaluates, and recommends land parcels suitable for afforestation and ecological restoration. The system ingests a region of interest (district, state, or coordinate bounding box) and produces a ranked portfolio of candidate sites with site-specific restoration plans, multi-scenario species recommendations, projected carbon yields, economic models, and a continuous monitoring schedule.

The product is built for organisations that currently spend lakhs of rupees per site on consulting analyses: corporate ESG teams, carbon project developers, restoration NGOs, state forest departments, and rewilding nonprofits.

The core technical contribution is not the data — most underlying datasets are freely available — but the **agentic reasoning layer** that turns raw geospatial data into defensible, monitored, scenario-aware restoration decisions. This is work currently performed by human consultants and is not done by any existing automated system in India.

The project conforms strongly to the hackathon brief on usefulness, multi-agent architecture, autonomous execution, and tool use. The primary execution risk is the 24-hour time constraint combined with the setup overhead of geospatial pipelines.

---

## 2. Problem Statement

### 2.1 The real-world problem

India has committed to restoring 26 million hectares of degraded land by 2030 and creating an additional carbon sink of 2.5-3 billion tonnes of CO₂ equivalent. Approximately 55.76 million hectares of India — 16.96% of the country — is classified as wasteland. The financial flows behind restoration are significant: CAMPA funds, the Green India Mission, state forest department budgets, voluntary carbon markets (Verra, Gold Standard), and corporate Scope 3 commitments.

Despite this, **site selection for restoration projects is overwhelmingly manual, slow, expensive, and politically driven**. A typical site assessment by a consulting firm:

- Takes 4-8 weeks per site
- Costs ₹15-50 lakh
- Relies on the analyst's discretion for species selection
- Rarely projects climate suitability forward beyond 10 years
- Almost never includes a continuous monitoring loop after planting
- Frequently fails because community/conflict factors were not surfaced early

The result is that a meaningful fraction of restoration projects in India fail within 5-7 years due to species mismatch, climate drift, or social conflict that could have been predicted at the site-selection stage.

### 2.2 Why existing tools do not solve this

The NITI Aayog GROW portal (launched 2024) provides a static, district-level Agroforestry Suitability Index. It is a useful baseline but does not:

- Recommend specific parcels
- Generate restoration plans, species mixes, or budgets
- Reason adversarially across competing priorities
- Project climate trajectories forward
- Monitor outcomes after recommendations
- Match sites to funding programs or carbon methodologies

Commercial GIS platforms (ArcGIS, Google Earth Engine) provide raw data and computation but require human analysts to interpret. No autonomous, agentic system exists in this domain in India today.

### 2.3 Target users

| User segment | Pain point | Willingness to pay |
|---|---|---|
| Corporate ESG teams | Defensible site selection for net-zero commitments | High — currently pay consultants ₹50L+ per program |
| Carbon project developers | Pre-feasibility screening at scale | High — directly tied to revenue per project |
| Restoration NGOs | Limited analyst capacity, high project failure rates | Medium — budget-constrained but high need |
| State forest departments | Target hectares without rigorous site methodology | Medium — public procurement cycle |
| Carbon credit buyers | Independent verification of project siting quality | High — emerging market for audit-grade tooling |

---

## 3. System Architecture

### 3.1 Agent topology

TerraScout uses a layered multi-agent design. Agents are grouped by function but communicate through a shared workflow state and a message bus rather than rigid hierarchical handoffs.

**Discovery Layer**
- *Satellite Analysis Agent* — pulls multi-temporal Sentinel-2 and Landsat imagery via Google Earth Engine; computes NDVI/EVI trends over 5-10 years; identifies degraded and sparsely vegetated parcels
- *Land-Use Classification Agent* — cross-references candidates against ESA WorldCover, Dynamic World, and Bhuvan land-cover layers to filter out productive farmland, wetlands, and existing forest
- *Cadastral Context Agent* — queries state land-record portals (where available) and the GROW wasteland atlas to classify ownership type (government, community, private, contested)

**Suitability Layer**
- *Soil Agent* — queries SoilGrids 2.0 and NBSS&LUP data for pH, organic carbon, texture, depth, salinity
- *Hydrology Agent* — pulls CHIRPS rainfall, groundwater depth, watershed position; determines viability of passive vs assisted restoration
- *Climate Trajectory Agent* — projects 30-50 year climate conditions using downscaled CMIP6 models; flags sites where current species choices will fail under 2055 conditions
- *Biodiversity Context Agent* — checks proximity to protected areas, wildlife corridors, and remnant native forest fragments

**Adversarial Decision Layer** *(the multi-agent core)*
- *Native Species Advocate Agent* — argues for ecologically appropriate native species based on historical biome and remnant vegetation
- *Carbon Yield Advocate Agent* — argues for fast-growing species maximising sequestration and carbon credit revenue
- *Community Livelihoods Agent* — argues for agroforestry and NTFP-producing species benefiting nearby populations
- *Synthesis Agent* — produces three labelled scenarios (pure-native, mixed agroforestry, carbon-optimised) with explicit tradeoffs, rather than averaging into a false consensus

**Risk & Feasibility Layer**
- *Conflict Detection Agent* — runs targeted web searches across news archives, court records, and regional reports for land disputes, tribal claims, and protest history
- *Policy & Funding Agent* — checks eligibility for CAMPA, Green India Mission, state schemes, Verra, and Gold Standard methodologies
- *Economic Modeling Agent* — estimates establishment costs, 5-7 year maintenance, monitoring, carbon revenue, NTFP income, and break-even timelines

**Output & Monitoring Layer**
- *Report Generation Agent* — produces site dossiers, scenario comparisons, maps, and financial models
- *Monitoring Plan Agent* — designs post-planting verification: which Sentinel indices to track, ground-truth checks, intervention triggers

### 3.2 Workflow execution model

The orchestrator implements an event-driven, async workflow:

1. **Trigger** — REST endpoint or webhook receives `POST /scan` with region and constraints; returns a workflow ID immediately
2. **Plan** — Planner agent decomposes the region into analysis tiles and dispatches per-tile jobs to a queue (Celery/RQ/asyncio)
3. **Fan out** — Discovery and Suitability agents process tiles in parallel; results flow back to a shared state store
4. **Adversarial debate** — Once enough tiles complete, the three advocate agents debate, with reasoning streamed to the UI
5. **Synthesise & assess** — Synthesis, Conflict, Policy, and Economic agents complete the analysis
6. **Report** — Report Generation Agent produces deliverables; webhook fires to notify completion
7. **Monitor (long-running)** — Identified sites enter a monitoring registry; new Sentinel-2 imagery triggers re-analysis via webhook

### 3.3 Required capabilities mapped to the brief

| Brief requirement | How TerraScout satisfies it |
|---|---|
| Multi-Agent | 13 specialised agents with distinct responsibilities; adversarial layer ensures genuine multi-agent reasoning, not parallelised single-agent calls |
| Autonomy | End-to-end from region input to delivered dossier with no human steering |
| Long-Running | Tile-level analysis takes minutes; monitoring runs across months via cron + webhooks |
| Deep Reasoning | Adversarial species debate, climate trajectory projection, scenario synthesis |
| Tool Calling | Google Earth Engine, SoilGrids, CHIRPS, Bhuvan WMS, state land portals, code execution, PDF generation |
| Web Search | Live search for conflict detection, policy updates, species research |
| Webhooks | Region submission ingress; Sentinel imagery update triggers; completion notifications |
| Async Orchestration | Per-tile fan-out via job queue; advocate agents run in parallel; synthesis joins them |

---

## 4. Data Availability Analysis

The vast majority of required data is freely available, which makes the project tractable on a hackathon budget.

### 4.1 Tier 1: Free, immediately usable

| Source | What it provides | Access |
|---|---|---|
| Sentinel-2 / Landsat 8-9 | 10-30m optical imagery, vegetation indices | Google Earth Engine API |
| ESA WorldCover, Dynamic World | 10m global land cover | GEE |
| SoilGrids 2.0 | Global soil properties at 250m | REST API |
| CHIRPS, ERA5 | Daily rainfall, climate reanalysis | GEE / Copernicus |
| WorldClim, CMIP6 | Historical normals and future projections | Direct download |
| SRTM, ALOS PALSAR | DEMs at 30m / 12.5m | Free with registration |

### 4.2 Tier 2: Indian government data (free, registration required)

| Source | What it provides |
|---|---|
| Bhuvan (ISRO) | Wasteland atlas, LULC, soil, geomorphology, salt-affected lands |
| GROW Suitability Portal | District-level Agroforestry Suitability Index |
| NRSC Wasteland Atlas | 23-category wasteland classification at 1:50,000 |
| IMD | Gridded rainfall and temperature for India |

### 4.3 Tier 3: Complicated but workable

State land-record portals (Bhulekh, Apna Khata, Bhoomi, Dharani, etc.) are 95%+ digitised for textual records but only ~30% have ULPIN with geo-coordinates linking parcels to maps. For the hackathon scope, government-classified wasteland can be used without needing parcel-level cadastre.

### 4.4 Tier 4: Out of scope for MVP

High-resolution sub-meter imagery (Planet, Maxar), real-time community/social data, and ground-truth biomass measurements — all useful for production but not required for demo.

---

## 5. Feasibility Assessment

### 5.1 Alignment with hackathon evaluation axes

| Axis | Weight | Fit | Reasoning |
|---|---|---|---|
| Problem Relevance & Usefulness | 20% | Excellent | Real paying customers, large unsolved problem in India, defensibly novel |
| Autonomous Execution | 25% | Strong | Workflow runs end-to-end without human steering; natural branching and retry logic |
| Multi-Agent Workflow Quality | 20% | Excellent | Adversarial layer demonstrates genuine multi-agent reasoning, not parallel single-agent calls |
| Tooling & Integrations | 15% | Excellent | Multiple real APIs, code execution, file generation, webhook fan-in/out |
| Demo Video Quality | 10% | Moderate | Requires careful scoping to fit a 5-minute legible demo |
| Technical Architecture | 10% | Strong | Clean separation, async-first design, observable workflow state |

### 5.2 Risks

**High: 24-hour time pressure with geospatial setup overhead.** GEE authentication, projection handling, raster I/O, and cloud-masking edge cases typically consume 6-10 hours before the first useful agent runs. Mitigation: pre-cache satellite tiles and soil data for one chosen district before the hackathon clock starts where rules permit; pre-build the GEE Python client wrapper.

**High: demo legibility.** Five minutes is short and judges must see meaningful end-to-end execution. Watching Sentinel-2 tiles download is not compelling. Mitigation: hide long-running computation behind pre-cached results in the demo path; spend visible demo time on the adversarial debate and synthesis, which are the genuinely impressive multi-agent moments.

**Medium: scope creep.** The full architecture has 13 agents. A 24-hour build cannot ship all of them well. Mitigation: target 6-7 agents for MVP, with the adversarial trio as the centrepiece.

**Medium: GEE quota limits.** Free GEE accounts have computation quotas. Mitigation: pre-export the necessary rasters as Cloud Storage assets and query those directly during the demo.

**Low: webhook infrastructure.** ngrok or a free hosted endpoint (Cloudflare Tunnel, Render) suffices for demo purposes. Mitigation: simple FastAPI server with two endpoints.

### 5.3 De-risked MVP scope (recommended for hackathon)

Build seven agents, not thirteen:

1. Satellite Analysis Agent
2. Soil Agent
3. Climate Trajectory Agent
4. Native Species Advocate
5. Carbon Yield Advocate
6. Community Livelihoods Advocate
7. Synthesis & Report Generation Agent

Defer: cadastral, biodiversity context, conflict detection, policy/funding, economic modeling, monitoring loop (mention in writeup as roadmap).

Scope to one district with good Bhuvan coverage — recommended candidates are Tumkur (Karnataka), Jaisalmer (Rajasthan), or Sehore (Madhya Pradesh).

### 5.4 Comparison with simpler alternatives

For a 24-hour timeline, simpler problem spaces (job application pipeline, competitive intelligence monitor, autonomous bug triage) are mechanically easier to demo. TerraScout trades demo-difficulty for problem-importance: it will score higher on usefulness and originality, lower-risk on autonomy and architecture, and moderate-risk on demo execution. Net expected score is higher for teams with at least one member comfortable with geospatial tooling.

---

## 6. Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| Agent framework | LangGraph or custom asyncio orchestrator | Native support for stateful, async, branching workflows |
| LLM | Claude Sonnet 4.5 or 4.6 for reasoning, Haiku for parallel low-cost tasks | Tool use, long context, adversarial reasoning quality |
| Geospatial compute | Google Earth Engine Python API | Free, scalable, hosts most required datasets |
| Web framework | FastAPI | Async-first, easy webhook endpoints, OpenAPI docs |
| Task queue | Celery + Redis, or pure asyncio with persistence | Fan-out per tile; survives demo restarts |
| Persistence | Postgres + PostGIS (or SQLite + GeoPackage for hackathon) | Workflow state, site registry, monitoring schedule |
| Frontend | Streamlit or Next.js + Mapbox | Live workflow visualisation; map overlay for results |
| Reports | WeasyPrint or ReportLab for PDF, with matplotlib/folium maps | Verifiable file output as side-effect |
| Observability | Omium SDK (bonus track) + structured logging | Causal trace graph across agents and webhooks |
| Hosting (demo) | Local with ngrok tunnel for webhook ingress | Sufficient for hackathon judging |

---

## 7. Demo Flow (5 minutes)

| Time | What happens | What judges see |
|---|---|---|
| 0:00 | `curl POST /scan` with Tumkur district + constraints | Workflow ID returned; status endpoint shows queued |
| 0:30 | Planner decomposes region; tile jobs dispatch to queue | Dashboard shows fan-out across N tiles |
| 1:00 | Satellite, Soil, Climate agents complete in parallel | Live tool calls visible; partial results on map |
| 2:00 | Adversarial debate begins | Three agents' reasoning streams; visible disagreement on species |
| 3:00 | Synthesis produces three scenarios | Map updates with site polygons; scenario comparison renders |
| 3:30 | Webhook fires from "new Sentinel imagery" simulator | Monitoring re-scan kicks off for a previously-stored site |
| 4:00 | Final PDF dossier generated and download link returned | Open the PDF in browser; show site recommendations, maps, plans |
| 4:30 | Q&A buffer / Omium trace dashboard tour | Trace graph shows full causal chain |

---

## 8. Deliverables

Per the hackathon brief:

1. **Source repository** — Git repo with README quickstart that produces a green demo run on a clean machine, including pre-cached district data
2. **Demo video** — 5-minute screen recording of the workflow above
3. **Writeup (3 pages)** — Problem, architecture, tool surface, what makes the workflow autonomous in practice
4. **Bonus: Omium trace** — Full causal coverage of one end-to-end run, dashboard URL submitted

---

## 9. Conclusion & Recommendation

TerraScout is a strong fit for the hackathon brief on every evaluation axis. The problem is genuinely real, the multi-agent architecture is non-trivial and well-motivated, and the autonomy, tool use, async orchestration, and webhook requirements all map naturally to the workflow rather than being bolted on.

The execution risk is concentrated in the 24-hour time constraint and the demo-legibility challenge of geospatial work. Both are manageable with disciplined scoping: build 7 agents not 13, pre-cache district data, and design the demo around the adversarial debate as the visible centrepiece.

**Recommendation: Proceed.** The expected score on this submission exceeds the expected score on safer-but-less-ambitious alternatives, conditional on the team including at least one member comfortable with Python geospatial tooling. If that skill is absent on the team, switch to one of the safer problem spaces (competitive intelligence, autonomous open-source maintainer, adversarial financial planner) and revisit TerraScout for a later, longer-runway build.

---

*Prepared for the project owner as a pre-build feasibility review.*