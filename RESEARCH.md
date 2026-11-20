# BugSense — Research Background (Huawei)

**Project:** BugSense, an intelligent debugging and incident analysis platform
**Author:** Tanisha Sinha

BugSense is compared with research from **one company, Huawei**: the paper
GRLIA from Huawei Cloud, which matches BugSense's incident grouping.

| Paper | Huawei team | Venue | Matches BugSense part |
|---|---|---|---|
| GRLIA: Graph-based Incident Aggregation | Huawei Cloud (with CUHK) | IEEE/ACM ASE 2021 | Grouping errors into incidents (Phase 5) |

The pitch to Huawei (cost and workflow) is in [PITCH.md](PITCH.md).

---

## 1. Problem

When software fails in production, engineers face millions of log lines,
metrics and traces from many services. They need two things:

1. **Grouping:** which of these errors are the same problem?
2. **Explanation:** what probably caused it, and what should be done?

GRLIA addresses the first need at Huawei Cloud scale. BugSense addresses
both in one small tool: it groups failures into incidents, then finds the
probable cause (Phase 7).

---

## 2. Huawei as the company studied

Huawei runs one of the large public clouds (Huawei Cloud). Its operations
products are where a tool like BugSense would fit:

| Huawei Cloud product | What it does | Relevance to BugSense |
|---|---|---|
| **AOM** (Application Operations Management) | Monitoring, alarms, metrics | Accepts data over **OpenTelemetry**, the same protocol BugSense receives |
| **APM** (Application Performance Management) | Traces of requests across services | Compatible with the OpenTelemetry protocol; receives traces from OTel SDKs |
| **LTS** (Log Tank Service) | Stores and searches logs | Billed by volume (read/write, indexing, storage); 500 MB free per month |

Sources: Huawei Cloud documentation for AOM ("Ingesting Data to AOM Using
Open-Source APIs and Protocols"), APM (OpenTelemetry best practices) and LTS
billing. Prices and quotas change; check the Huawei Cloud price pages.

**Why Huawei fits BugSense:** Huawei Cloud's monitoring already speaks
OpenTelemetry, the protocol BugSense receives, and Huawei's own research
(GRLIA) works on the same problem as BugSense's grouping step.

---

## 3. The paper — GRLIA (Huawei Cloud, IEEE/ACM ASE 2021)

**Citation:** Z. Chen, J. Liu, Y. Su, H. Zhang, X. Wen, X. Ling, Y. Yang,
and M. R. Lyu, "Graph-based Incident Aggregation for Large-Scale Online
Service Systems," *Proc. 36th IEEE/ACM Int. Conf. Automated Software
Engineering (ASE)*, 2021, pp. 430–442, doi: 10.1109/ASE51524.2021.9678746.

### What they did

- **Problem:** in a large cloud, one failure spreads to many services, and
  each raises its own incident. Engineers get a flood of separate incidents
  with one cause.
- **Method:** GRLIA learns how failures **cascade** between services, using
  graph representation learning on past failures plus detailed monitoring
  metrics (KPIs). Incidents with close vectors are grouped together.
- **Data and result:** real incidents from Huawei Cloud; the authors report it
  beats earlier methods and is deployed.

### Limits for a small team

- Needs a **history of failures** and fine-grained **metrics** to learn from.
- A learned model **cannot say why** two incidents were grouped.

### What BugSense does instead (Phase 5)

| | GRLIA (Huawei Cloud) | BugSense |
|---|---|---|
| Input | Incidents + KPIs + failure history | Raw logs, plus OpenTelemetry traces and metrics when available |
| How it groups | Learned graph model | Rule: problems within 10 minutes of each other are one incident |
| Training | Yes | None |
| Explains itself | No | Yes: the reason for each severity is shown |
| Cascade | Learned from history | Seen directly: one OpenTelemetry **trace** shows web → api → db and which hop failed |

### What is new compared with GRLIA

1. **Explainable grouping** with published rules and visible reasons.
2. **Works from day one,** no history needed.
3. **The cascade is observed, not learned:** BugSense receives OpenTelemetry
   traces, so it can show the exact chain of calls and the failing hop.

---

## 4. Research gap

- GRLIA groups incidents, but needs failure history and metrics, does not
  explain its grouping, and is internal to Huawei Cloud.
- After grouping, finding the cause is still left to the engineers.

**Gap:** an open, lightweight tool that goes from **raw logs and standard
OpenTelemetry data** to **explained incidents** to an **evidence-backed
probable cause**, runs on a laptop with no training, and works even with no
AI model.

---

## 5. What BugSense does (the whole pipeline)

```
Logs ──────────────► Parsing ─► Grouping into incidents ─► Diagnosis
OpenTelemetry ─────► traces, metrics, alerts ─┘               │
(OTLP: /v1/traces, /v1/metrics, /v1/logs)                     ├─ root cause ordering (Phase 8)
                                                              ├─ AI agent + 10 tools
Process monitor ───► crashes, restarts, health ─┘             └─ or rule-based investigator
```

| Step | What BugSense does |
|---|---|
| Data | Six Loghub datasets (12,000 lines) plus a live three-service demo shop |
| Telemetry | Receives OpenTelemetry traces, metrics and logs; computes request rate, error rate, latency p50/p95/p99, CPU and memory; raises alerts |
| Grouping | Time-burst grouping with rule-based severity and visible reasons |
| Root cause ordering | Services ranked from probable origin to affected, from request IDs, trace IDs, named services, the earliest error and crashes; the chain of how the failure spread |
| Diagnosis | 10 investigation tools; an AI agent (free model) or the rules call them; answer with root service, confidence and evidence |

---

## 6. Evaluation

All numbers were measured on BugSense itself.

### 6.1 Parser accuracy on real data

BugSense parsed the six Loghub files without reading Loghub's CSVs, then every
line was compared with the CSV row (J. Zhu *et al.*, IEEE ISSRE 2023).

| Check | Lines matching | Result |
|---|---|---|
| Message text | 12,000 / 12,000 | 100% |
| Clock time | 12,000 / 12,000 | 100% |
| Severity level (5 datasets with a Level column) | 10,000 / 10,000 | 100% |

### 6.2 Incident grouping on real data (compare GRLIA)

| Gap | Apache | OpenSSH | HDFS | ZooKeeper | Hadoop | OpenStack |
|---|---|---|---|---|---|---|
| 5 min | 59 | 10 | 0 | 2 | 1 | 1 |
| **10 min (chosen)** | **18** | **7** | **3** | **1** | **1** | **1** |
| 30 min | 13 | 1 | 3 | 5 | 1 | 1 |

### 6.3 Diagnosis on the four live scenarios with a known cause

The demo shop was broken on purpose; telemetry, logs and process events were
real. The fault name is never written into the logs (and the monitor only
records a neutral "Stopped"), so the investigator has to find the cause from
the evidence. Both engines were run.

**Rules engine:**

| Scenario | Known cause | Root service found | Probable cause given | Confidence |
|---|---|---|---|---|
| Database goes down | shop-db stopped | **shop-db** ✔ | "shop-db is not running … services that depend on it cannot reach it" | high |
| Crash loop | shop-api crashes at start | **shop-api** ✔ | "crashes during start-up (RuntimeError: payment module failed to initialise: missing key 'currency')" | high |
| Wrong configuration | broken database address | **shop-api** ✔ | "refuses to start because of an invalid configuration: … got "postgres//127.0.0.1:9102"" | high |
| Slow API | shop-api hangs | **shop-api** ✔ | "responding too slowly (p95 latency 2277 ms), so the services calling it time out" | high |

4 of 4 correct. Each used 7 tool calls and took under 25 ms. The evidence
came from four kinds of data: logs, process status, an OpenTelemetry alert and
a trace (for example, "in a failed request the deepest failing step is shop-api
'shop-db SELECT' (connection refused)").

**AI engine** (`openai/gpt-oss-20b` on Groq's free tier, real runs):

| Scenario | Root service found | Probable cause given (shortened) | Confidence | Tokens | Time |
|---|---|---|---|---|---|
| Database goes down | **shop-db** ✔ | "shop-db stopped, causing shop-api to fail to connect and return 503 to shop-web" | high | 14,774 | 62.5 s |
| Crash loop | **shop-api** ✔ | "a missing configuration key ('currency') caused the payment module to raise a RuntimeError, crashing the service" | high | 6,559 | 5.7 s |
| Wrong configuration | **shop-api** ✔ | "SHOP_DB_URL was misconfigured (missing protocol prefix), so shop-api failed to start and entered a crash loop" | high | 9,247 | 15.5 s |
| Slow API | **shop-api** ✔ | "a latency spike (p95 ≈ 2.8 s) caused shop-web requests to time out" | medium | 16,697 | 70.4 s |

4 of 4 correct, on average **11,800 tokens** per diagnosis. Most of the time
is waiting for the free tier's limit of 8,000 tokens per minute (BugSense waits
and retries); the AI calls themselves take a few seconds.

**What changed the AI's results while building it** (useful lessons):

1. The first version gave the AI only the tools. Every step resent the whole
   conversation, so one diagnosis needed more tokens than the free tier
   allows per minute. BugSense now gathers a **case file** first (incident,
   first errors, which service failed first, process status, telemetry
   summary), and the AI only makes follow-up calls.
2. Without the telemetry summary in the case file, the AI blamed the slow API
   on a "crash" (it misread a planned restart). With the p95 latency in the
   case file, it named the slowness correctly.
3. Monitor events from an earlier problem misled the AI, so the status tool
   got a `since` parameter, and the diagnosis passes the incident's start time.

### 6.4 Diagnosis on real datasets, and evidence reduction

On the Loghub datasets there is no telemetry and no process monitor, so the
rules can only point at the earliest failure.

| Dataset (largest incident) | Raw log characters | Evidence characters | Reduction | Rules result |
|---|---|---|---|---|
| Hadoop MapReduce | 174,768 | 9,337 (rules), 5,395 (AI) | **18.7×** (rules), **32.4×** (AI) | earliest failure only (low confidence) |
| ZooKeeper | 151,806 | 7,747 | **19.6×** | earliest failure only |
| OpenSSH | 64,346 | 7,195 | **8.9×** | earliest failure only |
| Apache | 1,585 | 7,376 | 0.2× | small incident: evidence is larger than the logs |

Honest reading: the evidence size stays around 7–9 K characters whatever the
incident size, so the reduction grows with the incident. On Hadoop, which contains a known
injected network failure, the rules did **not** name the network as the cause.

**The AI on Hadoop** (10,941 tokens, 9.8 s): it searched the logs four times
and found that RMContainerAllocator logged "ERROR IN CONTACTING RM." 147 times
and that TaskAttemptListenerImpl hit `NoRouteToHostException`. Its answer:
"RMContainerAllocator repeatedly failed to contact the ResourceManager …
downstream services experience network errors". This finds the network
failure the rules missed. It is only **partly** right: it names the
ResourceManager as the root service, while the real cause was the network
between the machines, not the ResourceManager itself.

### 6.5 Root cause ordering (Phase 8)

Does the ranking put the true origin first? Live scenarios (no AI involved):

| Scenario | True origin | Ranked first | Score | Failure chain found | Confidence |
|---|---|---|---|---|---|
| Database goes down | shop-db (writes no logs) | **shop-db** ✔ | 95 | shop-db → shop-api (15×) → shop-web (14×) | high |
| Crash loop | shop-api | **shop-api** ✔ | 95 | shop-api → shop-web (19×) | high |
| Wrong configuration | shop-api | **shop-api** ✔ | 110 | shop-api → shop-web (14×) | high |
| Slow API | shop-api | **shop-api** ✔ | 58 (shop-web 42) | mixed: shop-web → shop-api (6×), shop-api → shop-web (4×) | medium |

4 of 4 ranked first; 3 with high confidence. The slow API is harder: the
caller (shop-web) gives up and logs its timeout **before** the slow service
finishes, so "who failed first" points the wrong way in about half the
requests. The errors that name shop-api ("did not answer") and the deepest
failing step in all 11 failed traces still put shop-api on top. Ordering by
time alone is weak for slowness; traces are what fix it. The database case matters most: shop-db is stopped and
writes nothing, yet it is ranked first, because it failed first in all 15
failed requests (named by shop-api's errors) and was the deepest failing step
in all 15 failed traces. This is the cascade that GRLIA learns from failure
history, found here from one incident's own evidence.

On the Loghub datasets without request IDs (Hadoop, Apache, OpenSSH) only the
earliest error is available, so the ranking says **low confidence** instead
of pretending to know more.

---

## 7. Limitations and future work

- **The AI's answers vary** from run to run (it is a language model); the
  results above are single runs. A fair accuracy figure needs repeated runs.
- **The free tier is slow under load:** 8,000 tokens per minute means a
  diagnosis can wait up to a minute or two when several run back to back.
- **Grouping by time** can join two unrelated problems that happen together.
- **Few labelled incidents** (four scenarios and one dataset failure), so no
  precision or recall yet.
- **Rules on unfamiliar systems** only find the earliest error.
- **Root cause ordering needs request IDs or traces** to be confident; with
  only timestamps it gives a low-confidence starting point.
- **Next:** a labelled set of incidents to compare rules, ranking and AI, a
  downloadable incident report, login, and deployment.

---

## References

[1] Z. Chen, J. Liu, Y. Su, H. Zhang, X. Wen, X. Ling, Y. Yang, and
M. R. Lyu, "Graph-based Incident Aggregation for Large-Scale Online Service
Systems," in *Proc. 36th IEEE/ACM ASE*, 2021, pp. 430–442,
doi: 10.1109/ASE51524.2021.9678746.

Data source: J. Zhu, S. He, P. He, J. Liu, and M. R. Lyu, "Loghub: A Large
Collection of System Log Datasets for AI-driven Log Analytics," in *Proc. IEEE
34th ISSRE*, 2023, pp. 355–366, doi: 10.1109/ISSRE59848.2023.00071.

Huawei Cloud documentation: AOM access overview and open-source protocol
ingestion (support.huaweicloud.com/usermanual-aom2), APM OpenTelemetry best
practices (support.huaweicloud.com/bestpractice-apm2), LTS billing
(support.huaweicloud.com/price-lts).
