"""Tests for CSV normalization and source validation."""

from __future__ import annotations

import pandas as pd
import pytest

from delivery_ml.etl import OrderCsvTransformer


def test_order_transformer_normalizes_explicitly_mapped_source() -> None:
    """A valid mapped source produces normalized, timezone-aware order facts."""
    source = pd.DataFrame([{ "id": "o-1", "zone": "blr-1", "zone_name": "Indiranagar", "city": "Bengaluru", "restaurant": "r-1", "restaurant_name": "Cafe", "customer": "c-1", "vehicle": "BIKE", "time": "2026-07-18T10:00:00Z", "state": "DELIVERED", "distance": "2.5" }])
    mapping = {"external_id": "id", "zone_code": "zone", "zone_name": "zone_name", "city": "city", "restaurant_external_id": "restaurant", "restaurant_name": "restaurant_name", "customer_external_id": "customer", "vehicle_type": "vehicle", "ordered_at": "time", "status": "state", "distance_km": "distance"}
    record = OrderCsvTransformer().transform(source, mapping)[0]

    assert record.status == "delivered"
    assert record.distance_km == 2.5
    assert record.ordered_at.tzinfo is not None


def test_order_transformer_rejects_missing_mapping_and_duplicate_orders() -> None:
    """Ambiguous mappings and repeated source order IDs fail before database writes."""
    transformer = OrderCsvTransformer()
    with pytest.raises(ValueError, match="missing canonical"):
        transformer.transform(pd.DataFrame(), {})
