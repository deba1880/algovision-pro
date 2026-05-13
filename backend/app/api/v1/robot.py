"""Robot API — start/stop/configure the paper trading robot."""

import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from app.ai.robot.engine import (
    start_robot, stop_robot, is_running,
    get_status, get_config, update_config, get_trades,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class RobotConfigRequest(BaseModel):
    symbols: Optional[list[str]] = None
    lot_sizes: Optional[dict[str, int]] = None
    max_lots_per_trade: Optional[int] = None
    capital_per_trade_pct: Optional[float] = None
    strike_selection: Optional[str] = None
    expiry_preference: Optional[str] = None
    timeframe: Optional[str] = None
    target1_pct: Optional[float] = None
    target2_pct: Optional[float] = None
    target3_pct: Optional[float] = None
    stoploss_pct: Optional[float] = None
    trail_sl_after_t1: Optional[bool] = None
    exit1_qty_pct: Optional[int] = None
    exit2_qty_pct: Optional[int] = None
    exit3_qty_pct: Optional[int] = None
    max_trades_per_day: Optional[int] = None
    auto_square_off_time: Optional[str] = None
    enabled: Optional[bool] = None


@router.get("/config")
async def get_robot_config():
    from dataclasses import asdict
    return asdict(get_config())


@router.put("/config")
async def update_robot_config(req: RobotConfigRequest):
    from dataclasses import asdict
    new_cfg = await update_config(req.model_dump(exclude_none=True))
    return {"status": "updated", "config": asdict(new_cfg)}


@router.post("/start")
async def start_robot_endpoint():
    started = await start_robot()
    if not started:
        return {"status": "already_running", "running": True}
    return {"status": "started", "running": True}


@router.post("/stop")
async def stop_robot_endpoint():
    await stop_robot()
    return {"status": "stopped", "running": False}


@router.get("/status")
async def get_robot_status():
    return get_status()


@router.get("/trades")
async def get_robot_trades(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    return {"trades": get_trades(status_filter=status, limit=limit)}
