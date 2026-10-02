"""P2 运维：结构化日志。"""
import json
import logging
import os

import core.log as log


def test_setup_emits_json_lines(tmp_path, capsys):
    log.setup_logging("INFO", "stdout")
    log.get_logger("t").info("hello %s", "world")
    out = capsys.readouterr().out
    line = out.strip().splitlines()[-1]
    obj = json.loads(line)
    assert obj["level"] == "INFO"
    assert obj["msg"] == "hello world"
    assert "ts" in obj and "logger" in obj
    log.setup_logging(None, None)  # 重入不报错


def test_level_filters_lower_messages(tmp_path, capsys):
    log.setup_logging("WARNING", "stdout")
    log.get_logger("t").info("should not appear")
    log.get_logger("t").warning("warn appears")
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert json.loads(out[0])["level"] == "WARNING"
    log.setup_logging(None, None)


def test_exc_info_captured(tmp_path, capsys):
    log.setup_logging("ERROR", "stdout")
    try:
        raise ValueError("boom")
    except ValueError:
        log.get_logger("t").exception("failed")
    line = capsys.readouterr().out.strip().splitlines()[-1]
    obj = json.loads(line)
    assert "ValueError" in obj["exc"]
    log.setup_logging(None, None)


def test_file_rotation_controls_capacity(tmp_path):
    target = "file:" + str(tmp_path / "app.log")
    log.setup_logging("INFO", target)
    # 造一个大文件再写入，触发按 OPTV2_LOG_FILE_MAX 轮转
    p = tmp_path / "app.log"
    p.write_text("x" * 2048)
    os.environ["OPTV2_LOG_FILE_MAX"] = "1024"
    log.get_logger("t").info("after rotation")
    p2 = tmp_path / "app.log.1"
    log.setup_logging(None, None)
    del os.environ["OPTV2_LOG_FILE_MAX"]
    assert p2.exists()          # 旧的 2KB 文件被 .1 轮转
    assert p.read_text().find("after rotation") != -1  # 轮转后新建文件写新日志


def test_rerun_does_not_duplicate_handlers(tmp_path):
    log.setup_logging("INFO", "stdout")
    log.setup_logging("INFO", "stdout")
    root = logging.getLogger()
    json_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
    assert len(json_handlers) == 1
