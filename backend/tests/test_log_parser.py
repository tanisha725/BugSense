from datetime import datetime, timezone

from app.services.log_parser import parse_log, split_into_entries


def test_full_line():
    log = parse_log(
        "2026-10-08 10:15:03 ERROR [checkout-api] OperationalError: refused request_id=req-9f31"
    )

    assert log["timestamp"] == datetime(2026, 10, 8, 10, 15, 3)
    assert log["severity"] == "ERROR"
    assert log["service"] == "checkout-api"
    assert log["error_type"] == "OperationalError"
    assert log["request_id"] == "req-9f31"
    assert log["message"] == "OperationalError: refused request_id=req-9f31"
    assert log["stack_trace"] is None


def test_iso_timestamp_and_short_level_names():
    log = parse_log("2026-10-08T10:15:03.250Z WARN slow query")

    assert log["timestamp"] == datetime(2026, 10, 8, 10, 15, 3, 250000, tzinfo=timezone.utc)
    assert log["severity"] == "WARNING"
    assert log["message"] == "slow query"
    assert parse_log("FATAL: database is shutting down")["severity"] == "CRITICAL"


def test_bracket_style():
    log = parse_log("[2026-10-08 10:15:03] [ERROR] [auth] login failed")

    assert (log["severity"], log["service"], log["message"]) == ("ERROR", "auth", "login failed")


def test_python_logging_style():
    log = parse_log("2026-10-08 10:15:03,123 - app.orders - ERROR - could not save order")

    assert log["timestamp"] == datetime(2026, 10, 8, 10, 15, 3, 123000)
    assert log["service"] == "app.orders"
    assert log["severity"] == "ERROR"
    assert log["message"] == "could not save order"


def test_http_status_becomes_error_type():
    log = parse_log("2026-10-08 10:15:03 ERROR [api] POST /checkout returned 503 Service Unavailable")

    assert log["error_type"] == "HTTP 503"


def test_severity_is_guessed_when_missing():
    assert parse_log("ZeroDivisionError: division by zero")["severity"] == "ERROR"
    assert parse_log("GET /cart returned 404")["severity"] == "WARNING"


def test_plain_text_is_kept_as_message():
    log = parse_log("server started")

    assert log["message"] == "server started"
    assert log["severity"] is None and log["timestamp"] is None and log["error_type"] is None


def test_stack_trace_is_separated_from_message():
    raw = (
        "2026-10-08 14:20:11 ERROR [orders-api] ZeroDivisionError: division by zero\n"
        '  File "/app/routes/orders.py", line 57, in get_average\n'
        "    average = total / count"
    )
    log = parse_log(raw)

    assert log["message"] == "ZeroDivisionError: division by zero"
    assert log["stack_trace"].startswith('File "/app/routes/orders.py", line 57')


def test_bare_python_traceback_is_one_entry():
    text = (
        "INFO starting\n"
        "Traceback (most recent call last):\n"
        '  File "app.py", line 3, in <module>\n'
        "    1 / 0\n"
        "ZeroDivisionError: division by zero\n"
        "INFO next line\n"
    )
    entries = split_into_entries(text)

    # The traceback is attached to the line before it, and "INFO next line" is separate
    assert len(entries) == 2
    assert entries[0].endswith("ZeroDivisionError: division by zero")

    log = parse_log(entries[0].split("\n", 1)[1])  # the traceback on its own
    assert log["message"] == "ZeroDivisionError: division by zero"
    assert log["error_type"] == "ZeroDivisionError"
    assert log["severity"] == "ERROR"
    assert "line 3" in log["stack_trace"]


def test_real_world_formats():
    apache = parse_log("[Sun Dec 04 04:47:44 2005] [error] mod_jk child workerEnv in error state 6")
    assert (apache["timestamp"], apache["severity"]) == (datetime(2005, 12, 4, 4, 47, 44), "ERROR")

    hdfs = parse_log("081109 203615 148 WARN dfs.DataNode$PacketResponder: block terminating")
    assert (hdfs["timestamp"], hdfs["severity"], hdfs["service"]) == (
        datetime(2008, 11, 9, 20, 36, 15), "WARNING", "DataNode"
    )

    zookeeper = parse_log(
        "2015-07-29 19:04:29,071 - WARN  [SendWorker:1889:QuorumCnxManager$SendWorker@688] - leaving"
    )
    assert (zookeeper["service"], zookeeper["message"]) == ("QuorumCnxManager", "leaving")

    hadoop = parse_log(
        "2015-10-18 18:06:26,029 FATAL [IPC Server handler 13] org.apache.hadoop.mapred.TaskAttemptListenerImpl: "
        "exited : java.net.NoRouteToHostException: No Route to Host"
    )
    assert (hadoop["severity"], hadoop["service"], hadoop["error_type"]) == (
        "CRITICAL", "TaskAttemptListenerImpl", "NoRouteToHostException"
    )

    openstack = parse_log(
        "nova-api.log.1.2017-05-16_13:53:08 2017-05-16 00:00:17.531 25793 INFO nova.metadata.wsgi.server "
        "[req-f1603c09-bec5-418f-9b75-0f3393afea8a - -] \"GET /user_data HTTP/1.1\" status: 404 len: 176"
    )
    assert openstack["service"] == "nova.metadata"
    assert openstack["request_id"] == "req-f1603c09-bec5-418f-9b75-0f3393afea8a"
    assert openstack["error_type"] == "HTTP 404"


def test_syslog_severity_comes_from_warning_words():
    failed = parse_log("Dec 10 06:55:46 LabSZ sshd[24200]: Failed password for root from 1.2.3.4")
    normal = parse_log("Dec 10 06:55:48 LabSZ sshd[24200]: Connection closed by 1.2.3.4 [preauth]")

    assert (failed["service"], failed["severity"]) == ("sshd", "WARNING")
    assert normal["severity"] == "INFO"
    assert failed["timestamp"].month == 12
    # A syslog date is never in the future: it falls back to last year
    assert failed["timestamp"] <= datetime.now()
