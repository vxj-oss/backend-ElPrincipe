from fastapi import APIRouter

from app.api.v1.endpoints import (
    agent,
    auth,
    categories,
    commercial_terms,
    condicion_opciones,
    customers,
    dashboard,
    decisions,
    history,
    indicators,
    orders,
    products,
    reports,
    users,
    customer_requests,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(dashboard.router)
api_router.include_router(categories.router)
api_router.include_router(products.router)
api_router.include_router(customers.router)
api_router.include_router(orders.router)
api_router.include_router(commercial_terms.router)
api_router.include_router(condicion_opciones.router)
api_router.include_router(indicators.router)
api_router.include_router(agent.router)
api_router.include_router(reports.router)
api_router.include_router(history.router)
api_router.include_router(customer_requests.router)
api_router.include_router(decisions.router)