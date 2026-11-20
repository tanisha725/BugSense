"""Service monitoring: start, stop and watch the demo services."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request

from app.services import monitor


def remember_api_url(request: Request):
    """The demo services send OpenTelemetry data back to this backend. Its
    address is taken from the request, so it is right on port 8000 or 8001."""
    monitor.set_api_url(str(request.base_url))


router = APIRouter(prefix="/monitor", tags=["monitoring"], dependencies=[Depends(remember_api_url)])

Fault = Literal[monitor.FAULTS]  # type: ignore[valid-type]


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
def control_service(name: str, action: Literal["start", "stop", "restart"], fault: Fault | None = None):
    """Starts, stops or restarts one demo service. Only the known demo services
    can be controlled: BugSense never runs a program it was not built to run.

    fault (restart only): start shop-api with a demo fault ("" removes it).
    """
    if name not in monitor.SERVICES:
        raise HTTPException(status_code=404, detail="Unknown service")
    if fault is not None:
        if action != "restart":
            raise HTTPException(status_code=422, detail="fault can only be given with restart")
        if name != "shop-api" and fault:
            raise HTTPException(status_code=422, detail="Only shop-api has demo faults")
    if action == "start":
        monitor.start(name)
    elif action == "stop":
        monitor.stop(name)
    else:
        monitor.restart(name, fault)
    return monitor.status()


@router.post("/scenarios/{key}")
def run_scenario(key: str):
    """Runs one of the demo failure scenarios, or "recover"."""
    if key not in monitor.SCENARIOS:
        raise HTTPException(status_code=404, detail="Unknown scenario")
    monitor.run_scenario(key)
    return monitor.status()
