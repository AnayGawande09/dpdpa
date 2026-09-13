from pydantic import BaseModel


class CategorySummary(BaseModel):
    category: str
    field_count: int
    sample_fields: list[str]
