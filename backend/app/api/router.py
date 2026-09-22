from fastapi import APIRouter

from app.api import (
    admin_console,
    auth,
    categories,
    departments,
    employees,
    group_messages,
    hemis_sync,
    inventory,
    oauth_admin,
    quick_auth,
    ratings,
    requests,
    soft,
    stats,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin_console.router)
api_router.include_router(quick_auth.router)
api_router.include_router(oauth_admin.router)
api_router.include_router(hemis_sync.router)
api_router.include_router(departments.router)
api_router.include_router(employees.router)
api_router.include_router(requests.router)
api_router.include_router(group_messages.router)
api_router.include_router(categories.router)
api_router.include_router(ratings.router)
api_router.include_router(inventory.router)
api_router.include_router(soft.router)
api_router.include_router(stats.router)
