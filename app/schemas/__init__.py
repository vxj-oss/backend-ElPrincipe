from .agent import (
    AgentMessageBase,
    AgentMessageCreate,
    AgentMessageResponse,
    AgentQueryRequest,
    AgentQueryResponse,
    AgentSessionBase,
    AgentSessionCreate,
    AgentSessionResponse,
)
from .auth import LoginRequest, Token, TokenPayload, UserAuthResponse
from .category import CategoryCreate, CategoryResponse, CategoryUpdate
from .commercial_term import (
    CommercialTermCreate,
    CommercialTermResponse,
    CommercialTermUpdate,
)
from .commercial_term_failure import (
    CommercialTermFailureBase,
    CommercialTermFailureCreate,
    CommercialTermFailureResponse,
    CommercialTermFailureUpdate,
)
from .customer import CustomerCreate, CustomerResponse, CustomerUpdate
from .customer_request import (
    ComparacionPedidoItem,
    ComparacionPedidoRequest,
    ComparacionPedidoResponse,
    SolicitudClienteBase,
    SolicitudClienteCreate,
    SolicitudClienteResponse,
)
from .customer_request_item import (
    SolicitudClienteDetalleBase,
    SolicitudClienteDetalleCreate,
    SolicitudClienteDetalleResponse,
)
from .history import AuditHistoryCreate, AuditHistoryResponse
from .indicator import (
    IndicatorLogCreate,
    IndicatorLogResponse,
    IndicatorSummaryResponse,
)
from .order import OrderCreate, OrderResponse, OrderUpdate
from .order_item import OrderItemCreate, OrderItemResponse, OrderItemUpdate
from .product import ProductCreate, ProductResponse, ProductUpdate
from .report import IndicatorReportResponse, ReportFilterRequest, SalesKPIReport
from .user import UserCreate, UserResponse, UserUpdate

__all__ = [
    # Auth
    "LoginRequest",
    "Token",
    "TokenPayload",
    "UserAuthResponse",
    # User
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    # Category
    "CategoryCreate",
    "CategoryUpdate",
    "CategoryResponse",
    # Product
    "ProductCreate",
    "ProductUpdate",
    "ProductResponse",
    # Customer
    "CustomerCreate",
    "CustomerUpdate",
    "CustomerResponse",
    # Customer Request
    "SolicitudClienteBase",
    "SolicitudClienteCreate",
    "SolicitudClienteResponse",
    "ComparacionPedidoItem",
    "ComparacionPedidoRequest",
    "ComparacionPedidoResponse",
    # Customer Request Item
    "SolicitudClienteDetalleBase",
    "SolicitudClienteDetalleCreate",
    "SolicitudClienteDetalleResponse",
    # Order Item
    "OrderItemCreate",
    "OrderItemUpdate",
    "OrderItemResponse",
    # Commercial Term
    "CommercialTermCreate",
    "CommercialTermUpdate",
    "CommercialTermResponse",
    # Commercial Term Failure (Fallas CC)
    "CommercialTermFailureBase",
    "CommercialTermFailureCreate",
    "CommercialTermFailureUpdate",
    "CommercialTermFailureResponse",
    # Order
    "OrderCreate",
    "OrderUpdate",
    "OrderResponse",
    # Agent
    "AgentMessageBase",
    "AgentMessageCreate",
    "AgentMessageResponse",
    "AgentSessionBase",
    "AgentSessionCreate",
    "AgentSessionResponse",
    "AgentQueryRequest",
    "AgentQueryResponse",
    # Indicator
    "IndicatorLogCreate",
    "IndicatorLogResponse",
    "IndicatorSummaryResponse",
    # History
    "AuditHistoryCreate",
    "AuditHistoryResponse",
    # Report
    "ReportFilterRequest",
    "SalesKPIReport",
    "IndicatorReportResponse",
]