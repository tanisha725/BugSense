"""Service monitoring: start, stop and watch the demo services."""

from fastapi import APIRouter, HTTPException

from app.services import monitor

router = APIRouter(prefix="/monitor", tags=["monitoring"])


def check_service(name):
    if name not in monitor.SERVICES:
        raise HTTPException(status_code=404, detail="Unknown service")


@router.get("")
def monitor_status():
    """Status, health, restarts and recent events of every demo service."""
    return monitor.status()


@router.post("/start-all")
def start_all():
    monitor.start_all()
    return monitor.status()


@router.post("/stop-all")
def stop_all():
    monitor.stop_all()
    return monitor.status()


@router.post("/services/{name}/{action}")
def control_service(name: str, action: str):
    """action is start, stop or restart. Only the known demo services can be
    controlled: BugSense never runs a program it was not built to run."""
    check_service(name)
    if action == "start":
        monitor.start(name)
    elif action == "stop":
        monitor.stop(name)
    elif action == "restart":
        monitor.restart(name)
    else:
        raise HTTPException(status_code=400, detail="Action must be start, stop or restart")
    return monitor.status()


@router.post("/scenarios/{key}")
def run_scenario(key: str):
    """Runs one of the demo failure scenarios, or "recover"."""
    if key not in monitor.SCENARIOS:
        raise HTTPException(status_code=404, detail="Unknown scenario")
    monitor.run_scenario(key)
    return monitor.status()
