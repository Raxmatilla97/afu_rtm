from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Category
from app.deps import get_db
from app.schemas.category import CategoryResponse

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
async def list_categories(session: AsyncSession = Depends(get_db)) -> list[Category]:
    result = await session.execute(
        select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order)
    )
    return list(result.scalars())
