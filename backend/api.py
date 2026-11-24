from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

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


class PredictionRequest(BaseModel):
    serial: str = Field(..., min_length=1)
    price: float = Field(..., gt=0)
    brand: str = Field(..., min_length=1)
    reference: str = Field(..., min_length=1)
    model: str | None = None
    variant: str | None = None
    name: str | None = None
    description: str | None = None
    category: str | None = None
    subcategory: str | None = None
    currency: str = "USD"
    releaseYear: int | None = None
    condition: ConditionIn | None = None
    purchase: PurchaseIn | None = None
    location: LocationIn | None = None
    images: list[ImageIn] = Field(default_factory=list)
    live: bool = True


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


app = FastAPI(title="Watch Price Predictor API", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict", response_model=PredictionResponse)
def predict(payload: PredictionRequest):
    try:
        return build_prediction_payload(payload.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
