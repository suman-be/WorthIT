import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

import watches
from prediction_service import build_prediction_payload


class ConditionIn(BaseModel):
    grade: str | None = None
    description: str | None = None
    issues: list[str] = Field(default_factory=list)
    accessories: list[str] = Field(default_factory=list)


class PurchaseIn(BaseModel):
    purchaseDate: str | None = None
    originalPrice: float | None = Field(default=None, gt=0)
    currency: str | None = None


class LocationIn(BaseModel):
    country: str | None = None
    region: str | None = None


class ImageIn(BaseModel):
    url: str
    type: str | None = None


class PricePointIn(BaseModel):
    date: str
    averageValue: float | None = Field(default=None, gt=0)
    minimumValue: float | None = Field(default=None, gt=0)
    maximumValue: float | None = Field(default=None, gt=0)


class ComparableSaleIn(BaseModel):
    id: str | None = None
    title: str | None = None
    price: float = Field(..., gt=0)
    currency: str | None = None
    condition: str | None = None
    soldAt: str | None = None
    source: str | None = None
    similarityScore: int | None = Field(default=None, ge=0, le=100)
    url: str | None = None


class PredictionRequest(BaseModel):
    price: float = Field(..., gt=0)
    identifier: str | None = None
    serial: str | None = None
    name: str | None = None
    brand: str | None = None
    reference: str | None = None
    model: str | None = None
    variant: str | None = None
    description: str | None = None
    category: str | None = None
    subcategory: str | None = None
    currency: str = "USD"
    releaseYear: int | None = None
    condition: ConditionIn | None = None
    purchase: PurchaseIn | None = None
    location: LocationIn | None = None
    images: list[ImageIn] = Field(default_factory=list)
    priceHistory: list[PricePointIn] = Field(default_factory=list)
    comparableSales: list[ComparableSaleIn] = Field(default_factory=list)
    live: bool = True

    @model_validator(mode="after")
    def require_identity(self):
        values = (self.identifier, self.serial, self.name, self.brand, self.reference)
        if not any(str(value).strip() for value in values if value is not None):
            raise ValueError("identifier, serial, name, brand, or reference is required")
        return self


class PredictionResponse(BaseModel):
    predictionId: str
    status: str
    createdAt: str
    expiresAt: str
    currency: str
    item: dict[str, Any]
    valuation: dict[str, Any]
    marketAnalysis: dict[str, Any]
    priceHistory: dict[str, Any]
    comparableSales: dict[str, Any]
    priceFactors: list[dict[str, Any]]
    futureValuation: dict[str, Any]
    recommendation: dict[str, Any]
    dataQuality: dict[str, Any]
    aiInsights: dict[str, Any]


class SerialLookupIn(BaseModel):
    serial: str = ""


logger = logging.getLogger(__name__)

app = FastAPI(title="WorthIT API", version="1.2.0")

# The frontend sends credentials (credentials: 'include'), so origins must be listed
# explicitly; "*" is not allowed together with credentials.
DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.environ.get("CORS_ORIGINS", DEFAULT_ORIGINS).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Accept", "Content-Type"],
    expose_headers=["Retry-After"],
)


def error_response(status, message, field=None, headers=None):
    """Error body the frontend reads: {"error": {"message", "field"}}."""
    error = {"message": message}
    if field:
        error["field"] = field
    return JSONResponse(status_code=status, content={"error": error}, headers=headers)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return error_response(exc.status_code, message, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first = errors[0] if errors else {}
    location = [part for part in first.get("loc", ()) if part not in ("body", "query", "path")]
    field = str(location[-1]) if location else None
    message = first.get("msg", "The request is not valid.")
    if field:
        message = f"{field}: {message}"
    return error_response(422, message, field=field)


@app.exception_handler(watches.WatchLookupError)
async def lookup_error(request: Request, exc: watches.WatchLookupError):
    return error_response(exc.status, exc.message, field=exc.field)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict", response_model=PredictionResponse)
def predict(payload: PredictionRequest):
    request = payload.model_dump()
    live = request.pop("live", True)
    try:
        return build_prediction_payload(request, live=live)
    except Exception as exc:
        identity = payload.identifier or payload.name or payload.serial or payload.reference or "item"
        logger.exception("prediction failed for %s", identity)
        raise HTTPException(status_code=500, detail="prediction failed") from exc


@app.get("/watches")
def list_watches(ids: str | None = Query(default=None, description="Comma-separated watch ids")):
    """All catalogue watches, or the given ids in request order (unknown ids are skipped)."""
    if ids is None:
        return watches.get_watches()
    wanted = [part.strip() for part in ids.split(",") if part.strip()]
    return watches.get_watches(wanted)


@app.get("/watches/{watch_id}")
def get_watch(watch_id: str):
    return watches.get_watch(watch_id)


@app.post("/serial-lookups")
def serial_lookup(payload: SerialLookupIn):
    return watches.lookup_serial(payload.serial)
