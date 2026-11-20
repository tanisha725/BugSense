# BugSense — Pitch to Huawei Cloud

**For:** Huawei Cloud operations (SRE) and AIOps teams
**One line:** BugSense turns OpenTelemetry data and logs into an explained
incident with an evidence-backed probable cause, in seconds, at near-zero cost,
with no training and no change to how services are instrumented.

Background research: [RESEARCH.md](RESEARCH.md).

---

## 1. The problem

In a large cloud, one failure spreads to many services, and each raises its
own alarms. Huawei Cloud's GRLIA paper (ASE 2021) groups these alarms into
incidents, but the engineer still has to find **why** it happened: searching
logs service by service, following request IDs, and checking metrics. Logs
are far too large to hand to an AI model as they are, and an answer without
checkable evidence is hard to trust during an outage.

## 2. What BugSense offers

| Need | BugSense |
|---|---|
| Group the flood of errors | Incidents from time bursts, severity with stated reasons |
| See the cascade | OpenTelemetry traces: web → api → db, with the failing hop |
| Where it started | Services ranked from probable origin to affected, with the failure chain (shop-db → shop-api → shop-web) |
| Probable cause | 10 investigation tools, used by an AI agent or by rules |
| Trust | Every answer lists its evidence and the tool each fact came from; every tool call is shown |
| Safety | Tools only read. BugSense never runs commands in production |

---

## 3. Workflow: how it fits Huawei Cloud

BugSense uses **OpenTelemetry (OTLP)**, the protocol Huawei Cloud AOM and APM
already accept. The same services that report to AOM/APM can also report to
BugSense: an OpenTelemetry Collector sends one copy to each. Nothing in the
services changes.

```
 Services (OTel SDK) ──► OpenTelemetry Collector ──┬──► Huawei AOM / APM  (dashboards, alarms, storage)
                                                    └──► BugSense /v1/*    (incidents + diagnosis)
 Logs (stdout / LTS export) ──────────────────────────► BugSense /logs
```

**An engineer's incident, before and after:**

| Step | Today (manual triage) | With BugSense |
|---|---|---|
| 1. Alarm fires | Open dashboards, guess which service | Incident already grouped, severity and reason shown |
| 2. Find where it started | Search logs service by service | `get_error_timeline`: which service failed first |
| 3. Follow the failure | Copy request IDs between log searches | One trace shows every hop and the failing one |
| 4. Form a hypothesis | Experience and luck | Probable cause, root service, confidence |
| 5. Check it | Re-run searches | Evidence list; re-run any tool on the Tools page |
| 6. Act | Engineer decides | Engineer decides (suggested fixes are only suggestions) |

The engineer stays in charge. BugSense removes steps 1–4 of searching and
hands over a hypothesis with the evidence to check it (step 5).

---

## 4. Cost-effectiveness

### 4.1 Where the cost comes from, and what BugSense does about it

| Cost driver | Typical AI approach | BugSense |
|---|---|---|
| Training | Fine-tuning on many past incidents, GPUs | **None.** Rules and a general, zero-shot model |
| AI input size | Grows with log volume | **Fixed by the tools.** Tool results are capped (3,500 characters each); measured evidence is 7–13 K characters per incident whatever the incident size |
| Every incident uses the AI | Yes | **No.** The rules engine handles clear cases for free; the AI is optional |
| Model price | Large commercial models | **A small, free model** (default: `openai/gpt-oss-20b` on Groq's free tier), swappable by configuration |
| Infrastructure | Cluster, vector stores | **One small process** (FastAPI + PostgreSQL); ran on a laptop for every result here |
| Log storage | Copies of full logs for analysis | Reads what is already collected; LTS is billed by volume, and BugSense adds no extra full copy for the AI |

### 4.2 Measured figures

| What | Measured value |
|---|---|
| Rule-based diagnosis, live scenarios | 4 of 4 correct root service, **under 25 ms**, 0 AI tokens, cost **0** |
| AI diagnosis, live scenarios | 4 of 4 correct root service, **6.6–16.7 K tokens** (average **11.8 K**), a few seconds of AI time |
| AI diagnosis, Hadoop (175 K characters of logs) | **10.9 K tokens**, 9.8 s; found the network failure the rules missed |
| Evidence vs raw logs, large real incidents | 175 K → 5–9 K characters (**18.7–32.4×**, Hadoop); 152 K → 8 K (**19.6×**, ZooKeeper) |
| AI input per diagnosis | Stays around **5–13 K characters**, so AI cost does not grow with log volume |

### 4.3 AI cost per diagnosis

BugSense records the real token use of every AI diagnosis (shown on the
incident page). Measured: **about 12 K tokens** per diagnosis on average.

- **Free tier (Groq):** measured limits are 8,000 tokens per minute and 1,000
  requests per day; the daily token limit was reported as 200,000 in October
  2026. That allows roughly **15 free AI diagnoses a day**, one every minute
  or two, plus unlimited rule-based ones. Limits change; check the provider.
- **Beyond the free tier:** a paid tier, or a model hosted inside Huawei Cloud
  (for example on ModelArts), removes the limit. The cost stays proportional
  to ~12 K tokens per incident, not to the size of the logs.

**How the token use was kept low:** the first version let the AI fetch
everything with tools, and each step resent the whole conversation, which
went over the free tier's per-minute limit. Now BugSense gathers a case file
first (incident, first errors, which service failed first, process status,
telemetry summary) and offers the AI only the follow-up tools relevant to the
incident.

---

## 5. Why Huawei specifically

1. **It continues Huawei's own research.** GRLIA groups incidents; BugSense
   groups them too (with stated reasons, no training) and then explains the
   probable cause, the step GRLIA leaves to engineers.
2. **Huawei Cloud already speaks OpenTelemetry** (AOM, APM), so the data path
   exists.
3. **Swappable model:** the AI is reached through a standard chat API, so a
   Huawei-hosted model can replace the free one with a configuration change,
   keeping incident data inside Huawei Cloud.

---

## 6. Honest limits

- The AI engine was measured on five incidents (single runs); its answers
  vary between runs, so a fair accuracy figure needs a larger labelled set.
- On the free tier, a diagnosis can wait a minute or two when several run
  back to back (8,000 tokens per minute).
- On unfamiliar systems with no telemetry, the rules only find the earliest
  error (on Hadoop they missed the known network failure; the AI found it,
  but named the unreachable ResourceManager instead of the network).
- Grouping by time can join two unrelated problems.
- Tested on one demo system and six public datasets, not on Huawei's scale.

## 7. Proposed pilot (4 weeks)

| Week | Step | Measure |
|---|---|---|
| 1 | Send one non-critical service's OTel data to BugSense via the Collector | Data arrives, no service change |
| 2 | Label 20 past incidents with their real cause | Labelled set |
| 3 | Run rules and AI on all 20 | Top-1 root-service accuracy; tokens and seconds per diagnosis |
| 4 | SREs use it on live incidents | Time to first hypothesis vs today; do engineers trust the evidence? |

Success: correct root service in most labelled incidents, a first hypothesis
in under a minute, and a cost per diagnosis that does not grow with log volume.
