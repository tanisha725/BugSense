# BugSense — Research Background and Comparison

**Project:** BugSense, an intelligent debugging and incident analysis platform
**Author:** Tanisha Sinha

BugSense is compared with **two IEEE research papers from companies**. Each
one matches a main part of BugSense:

| | Paper | Company | IEEE venue | Matches BugSense part |
|---|---|---|---|---|
| **Paper 1** | GRLIA: Graph-based Incident Aggregation | **Huawei Cloud** (with CUHK) | IEEE/ACM ASE 2021 | Grouping errors into incidents (Phase 5) |
| **Paper 2** | Recommending Root-Cause and Mitigation Steps for Cloud Incidents using LLMs | **Microsoft** (with UC Davis) | IEEE/ACM ICSE 2023 | AI diagnosis of incidents (Phase 7) |

For each paper: what they did, what BugSense does, and what is new in
BugSense.

---

## 1. Problem

When software fails in production, developers face thousands of log lines
from many services. They need two things:

1. **Grouping:** which of these errors are the same problem?
2. **Explanation:** what probably caused it, and how can it be fixed?

Paper 1 addresses the first need and Paper 2 the second. BugSense addresses
both, in one tool.

---

## 2. Paper 1 — GRLIA (Huawei Cloud, IEEE ASE 2021)

**Citation:** Z. Chen, J. Liu, Y. Su, H. Zhang, X. Wen, X. Ling, Y. Yang,
and M. R. Lyu, "Graph-based Incident Aggregation for Large-Scale Online
Service Systems," *Proc. 36th IEEE/ACM Int. Conf. Automated Software
Engineering (ASE)*, 2021, pp. 430–442, doi: 10.1109/ASE51524.2021.9678746.

### What they did

- **Problem:** in a large cloud, one failure spreads to many services, and
  each service raises its own incident. Engineers receive a flood of
  separate incidents that all have the same cause.
- **Method:** GRLIA learns how failures **cascade** from one service to
  another. It uses graph representation learning on a graph of past failures,
  plus detailed monitoring metrics (KPIs). Every type of incident becomes a
  vector, and incidents with close vectors are grouped together.
- **Data:** real incidents from Huawei Cloud.
- **Result:** the authors report it beats earlier methods and has been
  deployed in industry.

### Limits for a small team

- It needs a **history of past failures** and fine-grained **metrics** to
  learn from.
- The grouping comes from a learned model, so it **cannot say why** two
  incidents were grouped.
- It is an internal company system, not a tool a student or small team can
  run.

### What BugSense does instead (Phase 5)

| | GRLIA (Huawei) | BugSense |
|---|---|---|
| Input | Incidents + monitoring metrics + failure history | Raw logs only |
| How it groups | Learned graph model | Simple rule: problems within 10 minutes of each other are one incident |
| Training needed | Yes | No |
| Explains its decision | No (vector similarity) | Yes: the reason for each severity is shown, e.g. "errors in 3 services at the same time" |
| Where it runs | Huawei Cloud | A laptop |

### What is new in BugSense compared with Paper 1

1. **Explainable grouping:** published rules (CRITICAL, HIGH, MEDIUM and LOW
   thresholds), with the reason shown on every incident page.
2. **Works from raw logs alone,** with no history or training data, so it can
   be used from the first day.
3. **Process failures join the same incident.** BugSense's service monitor
   (Phase 6) records crashes, crash loops and failed health checks as logs.
   A crash and the errors it causes are therefore grouped together, which is
   the cascade GRLIA learns, captured here by time instead of a learned
   graph.

---

## 3. Paper 2 — LLMs for root cause (Microsoft, IEEE ICSE 2023)

**Citation:** T. Ahmed, S. Ghosh, C. Bansal, T. Zimmermann, X. Zhang, and
S. Rajmohan, "Recommending Root-Cause and Mitigation Steps for Cloud
Incidents using Large Language Models," *Proc. IEEE/ACM 45th Int. Conf.
Software Engineering (ICSE)*, 2023, pp. 1737–1749,
doi: 10.1109/ICSE48619.2023.00149.

### What they did

- **Problem:** finding the root cause of a cloud incident and deciding how
  to fix it takes engineers a lot of time.
- **Method:** large language models (GPT-3.x) receive the incident's
  **title and summary**, as written when the incident was created, and
  generate a likely root cause and mitigation steps. Zero-shot models
  (no extra training) are compared with fine-tuned ones.
- **Data:** more than **40,000 real incidents** from Microsoft.
- **Evaluation:** automatic text-similarity metrics, plus a human evaluation
  by the engineers who owned the incidents.

### Limits for a small team

- Fine-tuning needs **tens of thousands of past incidents**, which a small
  team does not have.
- The model sees only a short **text description**, not the actual error
  logs, so it can produce answers that sound right but are not backed by
  evidence.
- It uses Microsoft's internal incident data and systems.

### What BugSense will do (Phase 7, next)

| | Microsoft study | BugSense |
|---|---|---|
| What the AI receives | Incident title and summary (text) | The incident's **structured evidence**: severity, services involved, first errors, error types, stack traces, crash and health events |
| Training | Zero-shot and fine-tuned on 40,000+ incidents | No fine-tuning: a general model with a careful prompt |
| How the answer is worded | Generated root cause and steps | Must say "probable", list the evidence it used, and state its limits |
| Who decides | — | The developer; the AI's output is labelled as a suggestion |

### What is new in BugSense compared with Paper 2

1. **Grounded in evidence:** the AI receives facts that BugSense extracted and
   grouped itself (Phases 4–6), not just a free-text summary.
2. **No fine-tuning needed,** so it works without a history of past
   incidents.
3. **Honest about uncertainty:** the answer must use "probable" and list its
   limitations, and it never runs commands by itself.

---

## 4. Research gap

Both papers solve one step, using company-scale data:

- Paper 1 groups incidents, but needs metrics and failure history and does
  not explain itself.
- Paper 2 explains incidents, but needs tens of thousands of past incidents
  and sees only a text summary.

**Gap:** there is no open, lightweight tool that goes from **raw logs alone**
to **explained incidents** to an **evidence-based probable cause**, runs on a
laptop, and shows the reason for each decision.

---

## 5. What BugSense does (the whole pipeline)

```
Raw logs → Parsing → Grouping into incidents → AI diagnosis
           (Phase 4)  (Phase 5, vs Paper 1)    (Phase 7, vs Paper 2)
                ↑
   Service monitoring (Phase 6): crashes and health checks become logs
```

| Step | What BugSense does |
|---|---|
| Data | Six real datasets from Loghub (12,000 lines), plus a live demo shop |
| Parsing | Reads time, severity, service, error type, request ID and stack trace with rules |
| Grouping | Time-burst grouping with rule-based severity and visible reasons |
| Monitoring | Starts and watches three demo services: restarts, crash loops, health checks |
| AI diagnosis | Next phase: probable root cause from the structured evidence |

---

## 6. Evaluation so far

All numbers were measured on BugSense itself.

### 6.1 Parser accuracy on real data

The six datasets come from **Loghub**, a public research collection of real
system logs (J. Zhu *et al.*, IEEE ISSRE 2023, doi:
10.1109/ISSRE59848.2023.00071). Loghub also publishes a CSV in which the
researchers split every line into columns. BugSense parsed the raw files
without reading the CSVs; every line was then compared with the same CSV row.

| Check | Lines matching | Result |
|---|---|---|
| Message text | 12,000 / 12,000 | 100% |
| Clock time | 12,000 / 12,000 | 100% |
| Severity level (5 datasets with a Level column) | 10,000 / 10,000 | 100% |

### 6.2 Incident grouping on real data (compare Paper 1)

Number of incidents for different time gaps:

| Gap | Apache | OpenSSH | HDFS | ZooKeeper | Hadoop | OpenStack |
|---|---|---|---|---|---|---|
| 5 min | 59 | 10 | 0 | 2 | 1 | 1 |
| **10 min (chosen)** | **18** | **7** | **3** | **1** | **1** | **1** |
| 30 min | 13 | 1 | 3 | 5 | 1 | 1 |

The Hadoop dataset contains a real injected network failure. It becomes
**one CRITICAL incident** (152 errors across 8 services), the cascade
behaviour that GRLIA learns from data.

### 6.3 Scenarios with a known cause

| Scenario | Known cause | What BugSense produced |
|---|---|---|
| Checkout outage sample | Database shut down | 1 CRITICAL incident across 3 services, titled with the database error |
| Live: database goes down | shop-db stopped | shop-api reported unhealthy; 28 errors from 2 services became 1 incident |
| Live: crash loop | shop-api crashes at start | Crash loop declared at the 3rd crash, CRITICAL incident |
| Live: wrong configuration | Broken database address | "ConfigError" and "Startup failed", then a crash loop |

These four known causes will also be used to test Phase 7: does the AI name
the right probable cause?

---

## 7. Limitations and future work

- **Grouping by time** can join two unrelated problems that happen together.
  GRLIA avoids this by learning failure cascades, at the cost of training
  data.
- **No labelled incidents yet,** so there are no precision and recall
  figures.
- **AI diagnosis (Phase 7)** is the next step, measured on the four known
  scenarios.
- **Root cause ordering (Phase 8)** will use the request IDs shared across
  services to separate the first failure from the failures it caused.

---

## References

[1] Z. Chen, J. Liu, Y. Su, H. Zhang, X. Wen, X. Ling, Y. Yang, and
M. R. Lyu, "Graph-based Incident Aggregation for Large-Scale Online Service
Systems," in *Proc. 36th IEEE/ACM Int. Conf. Automated Software Engineering
(ASE)*, 2021, pp. 430–442, doi: 10.1109/ASE51524.2021.9678746.

[2] T. Ahmed, S. Ghosh, C. Bansal, T. Zimmermann, X. Zhang, and
S. Rajmohan, "Recommending Root-Cause and Mitigation Steps for Cloud
Incidents using Large Language Models," in *Proc. IEEE/ACM 45th Int. Conf.
Software Engineering (ICSE)*, 2023, pp. 1737–1749,
doi: 10.1109/ICSE48619.2023.00149.

Data source: J. Zhu, S. He, P. He, J. Liu, and M. R. Lyu, "Loghub: A Large
Collection of System Log Datasets for AI-driven Log Analytics," in *Proc.
IEEE 34th Int. Symp. Software Reliability Engineering (ISSRE)*, 2023,
pp. 355–366, doi: 10.1109/ISSRE59848.2023.00071.
