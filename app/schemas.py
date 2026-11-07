"""Pydantic-модели запросов и ответов."""
from typing import Annotated, Optional

from pydantic import BaseModel, Field

LogLine = Annotated[str, Field(min_length=1, max_length=500)]


class IngestRequest(BaseModel):
    lines: list[LogLine] = Field(
        min_length=1,
        max_length=100,
        description="Строки журнала, от 1 до 100 штук, каждая до 500 символов",
        examples=[[
            "2026-10-20T12:34:56Z INFO auth 192.0.2.10 POST /api/login 200 43ms rid=ab12cd34",
            "2026-10-20T12:34:58Z ERROR orders 198.51.100.8 GET /api/orders 503 742ms rid=ee44cc22",
        ]],
    )


class IngestError(BaseModel):
    line_number: int = Field(description="Номер строки в пакете, с единицы")
    code: str
    reason: str
    line: str = Field(description="Исходная строка, обрезанная до 120 символов")


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    errors: list[IngestError]


class SlowRequest(BaseModel):
    rid: str
    duration_ms: int


class StatsResponse(BaseModel):
    queued_total: int = Field(description="Принято в очередь (XADD)")
    processed_total: int = Field(description="Обработано worker (учтено в статистике)")
    backlog: int = Field(description="Разница: ещё не обработано")
    by_level: dict[str, int]
    by_service: dict[str, int]
    by_status: dict[str, int]
    top_slow: list[SlowRequest]
    slow_threshold_ms: int


class EventOut(BaseModel):
    id: str
    timestamp: str
    level: str
    service: str
    ip: str
    method: str
    path: str
    status: int
    duration_ms: int
    rid: str


class EventsResponse(BaseModel):
    count: int
    events: list[EventOut]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Optional[list] = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: str
    api: str
    redis: str
    error: Optional[ErrorBody] = None
