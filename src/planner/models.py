from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class PlanItem(BaseModel):
    plan_number: int = Field(description="Số thứ tự kế hoạch (1, 2, 3)")
    bias: Literal["BUY", "SELL"] = Field(description="Hướng giao dịch: BUY hoặc SELL")
    wait_zone_low: float = Field(description="Mức giá thấp nhất của vùng chờ")
    wait_zone_high: float = Field(description="Mức giá cao nhất của vùng chờ")
    entry_condition: str = Field(
        description="Điều kiện kích hoạt vào lệnh theo Order Flow (Footprint, Bookmap) bằng tiếng Việt"
    )


class DailyPlan(BaseModel):
    date: str = Field(description="Ngày kế hoạch theo định dạng dd/mm/yyyy (ví dụ: 06/11/2026)")
    symbol: str = Field(default="XAUUSD", description="Mã giao dịch")
    overview: str = Field(description="Tổng quan bối cảnh thị trường trong ngày bằng tiếng Việt, tối đa 100 ký tự")
    plans: List[PlanItem] = Field(description="Danh sách các kế hoạch giao dịch trong ngày (tối đa 3 plan)")
    generated_at: str = Field(description="Thời gian tạo kế hoạch (ISO format)")


def get_daily_plan_json_schema() -> dict:
    return DailyPlan.model_json_schema()

