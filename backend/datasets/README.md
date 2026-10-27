# Datasets

Real log files used by BugSense's **Datasets** page. Each file is the
2,000-line sample published by **Loghub**, a public collection of logs from
real systems that is widely used in log-analysis research.

- Source: https://github.com/logpai/loghub
- Paper: Jieming Zhu, Shilin He, Pinjia He, Jinyang Liu, Michael R. Lyu.
  *Loghub: A Large Collection of System Log Datasets for AI-driven Log
  Analytics.* IEEE ISSRE, 2023.
- The files are unchanged copies. Loghub shares them for research and
  academic use; see the repository for its terms.

Each dataset has two files, both downloaded unchanged from Loghub:

- `<name>_2k.log` - the raw log lines (what BugSense reads)
- `<name>_2k.log_structured.csv` - Loghub's official CSV of the same lines,
  already split into columns by the researchers

BugSense never reads the CSV to parse logs. It is used only to **check** the
parser: every line BugSense parses from the `.log` file is compared with the
same row of the CSV. All six datasets agree on all 2,000 lines.

| File | System | What it contains |
|---|---|---|
| `Apache_2k.log` | Apache web server | Notices and `mod_jk` connector errors |
| `OpenSSH_2k.log` | SSH server | Failed logins, invalid users, break-in attempts |
| `HDFS_2k.log` | Hadoop file system | Block operations on an Amazon EC2 cluster |
| `Zookeeper_2k.log` | ZooKeeper | Leader election and dropped connections |
| `Hadoop_2k.log` | Hadoop MapReduce | A job hit by an injected network failure |
| `OpenStack_2k.log` | OpenStack Nova | Cloud API requests with request IDs and HTTP codes |

The same collection is also mirrored on Kaggle, but downloading from Kaggle
needs an account and an API key, so the files are taken straight from the
Loghub repository instead.
