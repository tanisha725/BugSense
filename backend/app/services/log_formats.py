"""Known log formats from real systems.

Each format is a regular expression with named parts:
  ts   - the timestamp          sev - the severity level
  svc  - the service/component  msg - the message

The parser tries these formats in order. The first one that fits the line is
used. If none fits, the parser falls back to its general rules.
This is the same idea as "grok patterns" in tools such as Logstash.
"""

import re
from datetime import datetime


def short_service(component):
    """Turns a long component name into a short, readable service name.

    org.apache.hadoop.mapreduce.v2.app.MRAppMaster -> MRAppMaster
    dfs.DataNode$PacketResponder                   -> DataNode
    nova.osapi_compute.wsgi.server                 -> nova.osapi_compute
    """
    parts = component.split(".")
    last = parts[-1].split("$")[0]
    if last[:1].isupper():
        return last
    return ".".join(parts[:2])


def zookeeper_service(component):
    """QuorumPeer[myid=1]/0:0:0:0:0:0:0:0:2181:FastLeaderElection@774 -> FastLeaderElection"""
    match = re.search(r"(\w+)(?:\$\w+)?@\d+$", component)
    return match.group(1) if match else component[:100]


def syslog_time(text):
    """Syslog lines have no year (for example 'Dec 10 06:55:46').

    This year is assumed. If that date is still in the future, the log must be
    from last year.
    """
    now = datetime.now()
    moment = datetime.strptime(f"{now.year} {text}", "%Y %b %d %H:%M:%S")
    return moment.replace(year=now.year - 1) if moment > now else moment


FORMATS = [
    {
        # [Sun Dec 04 04:47:44 2005] [error] mod_jk child workerEnv in error state 6
        "name": "Apache",
        "pattern": re.compile(
            r"^\[(?P<ts>\w{3} \w{3} +\d{1,2} \d{2}:\d{2}:\d{2} \d{4})\] \[(?P<sev>\w+)\] (?P<msg>.*)"
        ),
        "time": lambda text: datetime.strptime(text, "%a %b %d %H:%M:%S %Y"),
    },
    {
        # Dec 10 06:55:46 LabSZ sshd[24200]: Invalid user webmaster from 173.234.31.186
        "name": "Syslog",
        "pattern": re.compile(
            r"^(?P<ts>\w{3} +\d{1,2} \d{2}:\d{2}:\d{2}) \S+ "
            r"(?P<svc>[\w.\-/]+)(?:\([^)]*\))?(?:\[\d+\])?: (?P<msg>.*)"
        ),
        "time": syslog_time,
        # Syslog has no level word. A line with no warning signs is normal activity.
        "default_severity": "INFO",
    },
    {
        # 081109 203615 148 INFO dfs.DataNode$PacketResponder: PacketResponder 1 terminating
        "name": "HDFS",
        "pattern": re.compile(
            r"^(?P<ts>\d{6} \d{6}) \d+ (?P<sev>[A-Z]+) (?P<svc>[\w.$]+): (?P<msg>.*)"
        ),
        "time": lambda text: datetime.strptime(text, "%y%m%d %H%M%S"),
        "service": short_service,
    },
    {
        # 2015-07-29 19:04:29,071 - WARN  [SendWorker:1889:QuorumCnxManager$SendWorker@688] - Send worker leaving
        "name": "Zookeeper",
        "pattern": re.compile(
            r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (?P<sev>[A-Z]+) +"
            r"\[(?P<svc>.*)\] - (?P<msg>.*)"
        ),
        "time": lambda text: datetime.strptime(text, "%Y-%m-%d %H:%M:%S,%f"),
        "service": zookeeper_service,
    },
    {
        # 2015-10-18 18:01:47,978 INFO [main] org.apache.hadoop.mapreduce.v2.app.MRAppMaster: Created MRAppMaster
        "name": "Hadoop",
        "pattern": re.compile(
            r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) (?P<sev>[A-Z]+) "
            r"\[.*?\] (?P<svc>[\w.$]+): (?P<msg>.*)"
        ),
        "time": lambda text: datetime.strptime(text, "%Y-%m-%d %H:%M:%S,%f"),
        "service": short_service,
    },
    {
        # nova-api.log.1 2017-05-16 00:00:00.008 25746 INFO nova.osapi_compute.wsgi.server [req-38101a0b-...] ...
        "name": "OpenStack",
        "pattern": re.compile(
            r"^(?:\S+\.log\S* )?(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+) \d+ "
            r"(?P<sev>[A-Z]+) (?P<svc>[\w.]+) (?P<msg>.*)"
        ),
        "time": lambda text: datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%f"),
        "service": short_service,
    },
]


def match_known_format(line):
    """Returns the fields of the first known format that fits, or None."""
    for log_format in FORMATS:
        match = log_format["pattern"].match(line)
        if not match:
            continue
        parts = match.groupdict()
        try:
            timestamp = log_format["time"](parts["ts"])
        except ValueError:
            timestamp = None
        service = parts.get("svc")
        if service and "service" in log_format:
            service = log_format["service"](service)
        return {
            "format": log_format["name"],
            "timestamp": timestamp,
            "severity": parts.get("sev"),
            "default_severity": log_format.get("default_severity"),
            "service": service[:100] if service else None,
            "message": parts["msg"].strip(),
        }
    return None
