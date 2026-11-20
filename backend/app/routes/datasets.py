"""Real-world datasets: importing them, and replaying them live."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import replay
from app.services.datasets import (
    browse,
    browse_csv,
    catalog,
    csv_path,
    dataset_path,
    get_dataset,
    import_dataset,
    parsed_csv,
    summary,
    verify,
)

router = APIRouter(prefix="/datasets", tags=["datasets"])

ALLOWED_SPEEDS = {1, 2, 5, 10, 20}
Offset = Annotated[int, Query(ge=0)]
PageSize = Annotated[int, Query(ge=1, le=200)]
Search = Annotated[str | None, Query(max_length=200)]


def check_dataset(key):
    if get_dataset(key) is None:
        raise HTTPException(status_code=404, detail="Unknown dataset")


@router.get("")
def list_datasets():
    return catalog()


@router.get("/stream")
def stream_status():
    """Tells the frontend whether a live replay is running and how far it is."""
    return replay.status()


@router.post("/stream/stop")
def stop_stream():
    return replay.stop()


@router.post("/{key}/import")
def import_one(key: str, db: Session = Depends(get_db)):
    """Imports the whole dataset at once, with its original timestamps."""
    check_dataset(key)
    project, created = import_dataset(db, key)
    return {"project_id": project.id, "project_name": project.name, "created": created}


@router.post("/{key}/stream")
def start_stream(key: str, speed: int = 5):
    """Starts sending the dataset in live, `speed` lines per second."""
    check_dataset(key)
    if speed not in ALLOWED_SPEEDS:
        raise HTTPException(status_code=400, detail=f"Speed must be one of {sorted(ALLOWED_SPEEDS)}")
    return replay.start(key, speed)


@router.get("/{key}")
def view_dataset(key: str, search: Search = None, offset: Offset = 0, limit: PageSize = 50):
    """The dataset viewer: facts about the file, plus one page of its lines,
    each shown raw and as the fields the parser found."""
    check_dataset(key)
    dataset = get_dataset(key)
    page = browse(key, search, offset, limit)
    return {
        "key": key,
        "name": dataset["name"],
        "system": dataset["system"],
        "description": dataset["description"],
        **summary(key),
        "verification": verify(key),
        **page,
    }


@router.get("/{key}/download")
def download_dataset(key: str):
    """Sends the original, unchanged dataset file."""
    check_dataset(key)
    return FileResponse(
        dataset_path(key), media_type="text/plain", filename=get_dataset(key)["file"]
    )


@router.get("/{key}/csv")
def view_csv(key: str, search: Search = None, offset: Offset = 0, limit: PageSize = 50):
    """One page of Loghub's official CSV for this dataset, exactly as published."""
    check_dataset(key)
    return browse_csv(key, search, offset, limit)


@router.get("/{key}/csv/download")
def download_csv(key: str):
    """Sends Loghub's original CSV file, unchanged."""
    check_dataset(key)
    return FileResponse(csv_path(key), media_type="text/csv", filename=csv_path(key).name)


@router.get("/{key}/parsed.csv")
def download_parsed_csv(key: str):
    """Sends BugSense's own parsing result as CSV, to compare with Loghub's CSV."""
    check_dataset(key)
    filename = f"{key}_parsed_by_bugsense.csv"
    return Response(
        parsed_csv(key),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
