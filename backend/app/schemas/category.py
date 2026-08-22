from pydantic import BaseModel


class CategoryResponse(BaseModel):
    slug: str
    label_uz: str
    sort_order: int

    class Config:
        from_attributes = True
