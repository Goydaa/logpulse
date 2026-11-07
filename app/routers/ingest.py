from fastapi import APIRouter, Depends
from redis import Redis

from app import store
from app.parser import LogParseError, parse_line
from app.redis_client import get_redis
from app.schemas import ErrorResponse, IngestError, IngestRequest, IngestResponse

router = APIRouter(tags=["ingest"])


@router.post(
    "/ingest",
    response_model=IngestResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Ошибка структуры запроса"},
        503: {"model": ErrorResponse, "description": "Redis недоступен"},
    },
    summary="Приём пакета строк журнала",
)
def ingest(payload: IngestRequest, r: Redis = Depends(get_redis)):
    events: list[dict] = []
    errors: list[IngestError] = []
    for number, line in enumerate(payload.lines, start=1):
        try:
            events.append(parse_line(line, number))
        except LogParseError as exc:
            errors.append(
                IngestError(
                    line_number=exc.line_number,
                    code=exc.code,
                    reason=exc.reason,
                    line=line[:120],
                )
            )
    # в очередь попадают только корректные события
    store.publish_events(r, events)
    return IngestResponse(accepted=len(events), rejected=len(errors), errors=errors)
