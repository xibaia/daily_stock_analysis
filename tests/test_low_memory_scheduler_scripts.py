from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "run_scheduled_analysis_once.sh"
INSTALLER = REPO_ROOT / "scripts" / "install_systemd_analysis_timer.sh"


def test_analyzer_is_opt_in_scheduler_profile() -> None:
    compose = yaml.safe_load(
        (REPO_ROOT / "docker" / "docker-compose.yml").read_text(encoding="utf-8")
    )

    assert compose["services"]["analyzer"]["profiles"] == ["scheduler"]


def test_one_shot_runner_uses_ephemeral_container_and_disables_nested_schedule(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log_path = tmp_path / "docker.log"
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$DOCKER_LOG\"\nexit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "DOCKER_LOG": str(log_path),
            "DSA_ANALYSIS_LOCK_DIR": str(tmp_path / "analysis.lock"),
            "DSA_COMPOSE_FILE": str(REPO_ROOT / "docker" / "docker-compose.yml"),
        }
    )

    completed = subprocess.run(
        ["sh", str(RUNNER)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    invocation = log_path.read_text(encoding="utf-8")
    assert "--profile scheduler run --rm --no-deps" in invocation
    assert "-e SCHEDULE_ENABLED=false" in invocation
    assert "-e SCHEDULE_RUN_IMMEDIATELY=false" in invocation
    assert "-e RUN_IMMEDIATELY=true" in invocation
    assert "analyzer python main.py" in invocation
    assert not (tmp_path / "analysis.lock").exists()


def test_one_shot_runner_refuses_overlapping_run(tmp_path: Path) -> None:
    lock_dir = tmp_path / "analysis.lock"
    lock_dir.mkdir()
    env = os.environ.copy()
    env["DSA_ANALYSIS_LOCK_DIR"] = str(lock_dir)

    completed = subprocess.run(
        ["sh", str(RUNNER)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 75
    assert "already running" in completed.stderr


def test_installer_render_only_supports_current_multiple_schedule_times(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text('SCHEDULE_TIME=17:00\nSCHEDULE_TIMES="09:30,18:05"\n', encoding="utf-8")
    systemd_dir = tmp_path / "systemd"
    env = os.environ.copy()
    env.update({"DSA_ENV_FILE": str(env_file), "DSA_SYSTEMD_DIR": str(systemd_dir)})

    completed = subprocess.run(
        ["sh", str(INSTALLER), "--render-only"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    service = (systemd_dir / "dsa-analysis.service").read_text(encoding="utf-8")
    timer = (systemd_dir / "dsa-analysis.timer").read_text(encoding="utf-8")
    assert f"ExecStart={RUNNER}" in service
    assert "OnCalendar=*-*-* 09:30:00" in timer
    assert "OnCalendar=*-*-* 18:05:00" in timer
    assert "rendered" in completed.stdout


def test_installer_rejects_invalid_schedule_without_writing_units(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SCHEDULE_TIMES=18:00,25:00\n", encoding="utf-8")
    systemd_dir = tmp_path / "systemd"
    env = os.environ.copy()
    env.update({"DSA_ENV_FILE": str(env_file), "DSA_SYSTEMD_DIR": str(systemd_dir)})

    completed = subprocess.run(
        ["sh", str(INSTALLER), "--render-only"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "invalid schedule time" in completed.stderr
    assert not (systemd_dir / "dsa-analysis.timer").exists()
