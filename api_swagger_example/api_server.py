"""
模擬客戶提供的採購系統 API
實際使用時，這些 API 會由客戶的 SAP 系統或其他 ERP 系統提供

Swagger UI: http://localhost:8000/docs
ReDoc: http://localhost:8000/redoc
"""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
import datetime

# ========== Pydantic Models ==========

class PurchaseHistoryItem(BaseModel):
    id: str
    item_name: str
    brand: str
    model: str
    spec: str
    quantity: int
    unit_price: int
    supplier: str
    purchase_date: str
    department: str
    purpose: str

class InventoryItem(BaseModel):
    item_name: str
    brand: str
    model: str
    available: int
    reserved: int
    location: str

class SupplierInfo(BaseModel):
    id: str
    name: str
    category: List[str]
    rating: float
    delivery_days: int
    payment_terms: str
    contact: str
    history_orders: int
    on_time_rate: float

class ProductInfo(BaseModel):
    supplier: str
    item_name: str
    brand: str
    model: str
    spec: str
    unit_price: int
    stock: int

# Request Models
class InventoryRequisitionRequest(BaseModel):
    item_name: Optional[str] = Field(None, description="品項名稱")
    brand: Optional[str] = Field(None, description="品牌")
    model: Optional[str] = Field(None, description="型號")
    quantity: int = Field(1, description="領用數量", ge=1)
    department: Optional[str] = Field(None, description="申請部門")
    requester: Optional[str] = Field(None, description="申請人")
    purpose: Optional[str] = Field(None, description="用途說明")
    notes: Optional[str] = Field(None, description="備註")

class PurchaseRequestCreate(BaseModel):
    item_name: str = Field(..., description="品項名稱")
    spec: Optional[str] = Field(None, description="規格需求")
    quantity: int = Field(..., description="數量", ge=1)
    purpose: Optional[str] = Field(None, description="用途說明")
    department: Optional[str] = Field(None, description="申請部門")
    requester: Optional[str] = Field(None, description="申請人")
    expected_date: Optional[str] = Field(None, description="期望交貨日期 (YYYY-MM-DD)")
    budget: Optional[int] = Field(None, description="預算金額")
    notes: Optional[str] = Field(None, description="備註")

class ApprovalRequest(BaseModel):
    approver: Optional[str] = Field("系統管理員", description="審核人")
    notes: Optional[str] = Field(None, description="審核備註")

class RejectRequest(BaseModel):
    approver: Optional[str] = Field("系統管理員", description="駁回人")
    reason: str = Field(..., description="駁回原因")

class PurchaseOrderCreate(BaseModel):
    pr_id: str = Field(..., description="請購單編號")
    supplier_name: str = Field(..., description="供應商名稱")
    unit_price: int = Field(..., description="單價")
    quantity: Optional[int] = Field(None, description="數量（若不填則使用請購單數量）")
    delivery_date: Optional[str] = Field(None, description="交貨日期")
    payment_terms: Optional[str] = Field(None, description="付款條件")
    notes: Optional[str] = Field(None, description="備註")

# Response Models
class ApiResponse(BaseModel):
    success: bool
    data: Optional[dict | list] = None
    count: Optional[int] = None
    message: Optional[str] = None
    error: Optional[str] = None


# ========== FastAPI App ==========

app = FastAPI(
    title="採購系統 API",
    description="""
## 企業採購管理系統 API

此 API 模擬企業採購系統的核心功能，包括：

### 主要功能
- 📋 **採購歷史查詢** - 查詢過去的採購記錄
- 📦 **庫存管理** - 查詢現有庫存與領用
- 🏢 **供應商管理** - 查詢供應商資訊與評價
- 🛒 **產品目錄** - 查詢各供應商產品與報價（比價用）
- 📝 **請購單管理** - 建立、查詢、審核請購單
- 📄 **採購單管理** - 建立、查詢採購單

### 使用說明
實際使用時，這些 API 會由客戶的 SAP 系統或其他 ERP 系統提供。
""",
    version="1.0.0",
    contact={
        "name": "採購系統管理員",
    },
    license_info={
        "name": "MIT",
    },
)


# ========== 模擬資料庫 ==========

PURCHASE_HISTORY = [
    {
        "id": "PH001",
        "item_name": "筆記型電腦",
        "brand": "Dell",
        "model": "Latitude 5540",
        "spec": "Intel i7-1365U, 16GB RAM, 512GB SSD",
        "quantity": 10,
        "unit_price": 42000,
        "supplier": "德誼數位",
        "purchase_date": "2025-06-15",
        "department": "研發部",
        "purpose": "新進工程師配發",
    },
    {
        "id": "PH002",
        "item_name": "筆記型電腦",
        "brand": "Lenovo",
        "model": "ThinkPad T14s",
        "spec": "Intel i7-1360P, 32GB RAM, 1TB SSD",
        "quantity": 5,
        "unit_price": 52000,
        "supplier": "聯強國際",
        "purchase_date": "2025-08-20",
        "department": "資訊部",
        "purpose": "資深工程師升級",
    },
    {
        "id": "PH003",
        "item_name": "螢幕",
        "brand": "Dell",
        "model": "U2723QE",
        "spec": "27吋 4K IPS",
        "quantity": 20,
        "unit_price": 18500,
        "supplier": "德誼數位",
        "purchase_date": "2025-09-10",
        "department": "全公司",
        "purpose": "辦公設備更新",
    },
    {
        "id": "PH004",
        "item_name": "機械鍵盤",
        "brand": "Logitech",
        "model": "MX Mechanical",
        "spec": "茶軸 無線",
        "quantity": 30,
        "unit_price": 4500,
        "supplier": "PChome企業採購",
        "purchase_date": "2025-10-01",
        "department": "全公司",
        "purpose": "員工福利",
    },
]

INVENTORY = [
    {
        "item_name": "筆記型電腦",
        "brand": "Dell",
        "model": "Latitude 5540",
        "available": 3,
        "reserved": 2,
        "location": "總部倉庫",
    },
    {
        "item_name": "筆記型電腦",
        "brand": "Lenovo",
        "model": "ThinkPad T14s",
        "available": 0,
        "reserved": 0,
        "location": "總部倉庫",
    },
    {
        "item_name": "螢幕",
        "brand": "Dell",
        "model": "U2723QE",
        "available": 8,
        "reserved": 5,
        "location": "總部倉庫",
    },
    {
        "item_name": "機械鍵盤",
        "brand": "Logitech",
        "model": "MX Mechanical",
        "available": 15,
        "reserved": 3,
        "location": "總部倉庫",
    },
    {
        "item_name": "滑鼠",
        "brand": "Logitech",
        "model": "MX Master 3S",
        "available": 20,
        "reserved": 0,
        "location": "總部倉庫",
    },
]

SUPPLIERS = [
    {
        "id": "SUP001",
        "name": "德誼數位",
        "category": ["電腦", "螢幕", "週邊設備"],
        "rating": 4.8,
        "delivery_days": 3,
        "payment_terms": "月結30天",
        "contact": "02-2345-6789",
        "history_orders": 45,
        "on_time_rate": 0.96,
    },
    {
        "id": "SUP002",
        "name": "聯強國際",
        "category": ["電腦", "伺服器", "網路設備"],
        "rating": 4.6,
        "delivery_days": 5,
        "payment_terms": "月結45天",
        "contact": "02-8765-4321",
        "history_orders": 32,
        "on_time_rate": 0.92,
    },
    {
        "id": "SUP003",
        "name": "PChome企業採購",
        "category": ["週邊設備", "辦公用品", "電腦"],
        "rating": 4.2,
        "delivery_days": 2,
        "payment_terms": "月結30天",
        "contact": "02-1234-5678",
        "history_orders": 78,
        "on_time_rate": 0.88,
    },
    {
        "id": "SUP004",
        "name": "神腦國際",
        "category": ["電腦", "手機", "平板"],
        "rating": 4.5,
        "delivery_days": 4,
        "payment_terms": "月結30天",
        "contact": "02-9876-5432",
        "history_orders": 28,
        "on_time_rate": 0.94,
    },
]

PRODUCT_CATALOG = [
    {
        "supplier": "德誼數位",
        "item_name": "筆記型電腦",
        "brand": "Dell",
        "model": "Latitude 5540",
        "spec": "Intel i7-1365U, 16GB RAM, 512GB SSD",
        "unit_price": 41500,
        "stock": 50,
    },
    {
        "supplier": "德誼數位",
        "item_name": "筆記型電腦",
        "brand": "Dell",
        "model": "Latitude 5550",
        "spec": "Intel i7-1370P, 32GB RAM, 1TB SSD",
        "unit_price": 55000,
        "stock": 30,
    },
    {
        "supplier": "聯強國際",
        "item_name": "筆記型電腦",
        "brand": "Lenovo",
        "model": "ThinkPad T14s",
        "spec": "Intel i7-1360P, 16GB RAM, 512GB SSD",
        "unit_price": 45000,
        "stock": 40,
    },
    {
        "supplier": "聯強國際",
        "item_name": "筆記型電腦",
        "brand": "Lenovo",
        "model": "ThinkPad T14s",
        "spec": "Intel i7-1360P, 32GB RAM, 1TB SSD",
        "unit_price": 52000,
        "stock": 25,
    },
    {
        "supplier": "神腦國際",
        "item_name": "筆記型電腦",
        "brand": "HP",
        "model": "EliteBook 840 G10",
        "spec": "Intel i7-1365U, 16GB RAM, 512GB SSD",
        "unit_price": 43000,
        "stock": 35,
    },
    {
        "supplier": "PChome企業採購",
        "item_name": "筆記型電腦",
        "brand": "ASUS",
        "model": "ExpertBook B5",
        "spec": "Intel i7-1360P, 16GB RAM, 512GB SSD",
        "unit_price": 38000,
        "stock": 60,
    },
    {
        "supplier": "德誼數位",
        "item_name": "螢幕",
        "brand": "Dell",
        "model": "U2723QE",
        "spec": "27吋 4K IPS USB-C",
        "unit_price": 18000,
        "stock": 100,
    },
    {
        "supplier": "聯強國際",
        "item_name": "螢幕",
        "brand": "Lenovo",
        "model": "ThinkVision T27p-30",
        "spec": "27吋 4K IPS USB-C",
        "unit_price": 17500,
        "stock": 80,
    },
    {
        "supplier": "PChome企業採購",
        "item_name": "機械鍵盤",
        "brand": "Logitech",
        "model": "MX Mechanical",
        "spec": "茶軸 無線 背光",
        "unit_price": 4200,
        "stock": 200,
    },
]

# 請購單/採購單/領用單儲存
PURCHASE_REQUESTS = []
PURCHASE_ORDERS = []
INVENTORY_REQUISITIONS = []


# ========== API 端點 ==========


@app.get(
    "/api/purchase-history",
    tags=["採購歷史"],
    summary="查詢採購歷史記錄",
    description="查詢過去的採購記錄，可依品項關鍵字、部門、日期範圍篩選",
    response_model=ApiResponse,
)
def get_purchase_history(
    item_keyword: Optional[str] = Query(None, description="品項關鍵字（品名、品牌、型號）"),
    department: Optional[str] = Query(None, description="部門名稱"),
    date_from: Optional[str] = Query(None, description="起始日期 (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="結束日期 (YYYY-MM-DD)"),
):
    """
    查詢採購歷史記錄
    
    - **item_keyword**: 可搜尋品名、品牌、型號
    - **department**: 篩選特定部門的採購記錄
    - **date_from / date_to**: 日期範圍篩選
    """
    results = PURCHASE_HISTORY.copy()

    if item_keyword:
        results = [
            r
            for r in results
            if item_keyword.lower() in r["item_name"].lower()
            or item_keyword.lower() in r.get("brand", "").lower()
            or item_keyword.lower() in r.get("model", "").lower()
        ]

    if department:
        results = [r for r in results if department in r["department"]]

    if date_from:
        results = [r for r in results if r["purchase_date"] >= date_from]

    if date_to:
        results = [r for r in results if r["purchase_date"] <= date_to]

    return {"success": True, "data": results, "count": len(results)}


@app.get(
    "/api/inventory",
    tags=["庫存管理"],
    summary="查詢庫存資訊",
    description="查詢現有庫存狀態，可依品項、品牌篩選，也可只顯示有庫存的品項",
    response_model=ApiResponse,
)
def get_inventory(
    item_keyword: Optional[str] = Query(None, description="品項關鍵字"),
    brand: Optional[str] = Query(None, description="品牌"),
    available_only: bool = Query(False, description="只顯示有庫存的品項"),
):
    """
    查詢庫存資訊
    
    - **item_keyword**: 品項名稱關鍵字
    - **brand**: 指定品牌
    - **available_only**: 設為 true 只顯示可用數量 > 0 的品項
    """
    results = INVENTORY.copy()

    if item_keyword:
        results = [r for r in results if item_keyword.lower() in r["item_name"].lower()]

    if brand:
        results = [r for r in results if brand.lower() in r["brand"].lower()]

    if available_only:
        results = [r for r in results if r["available"] > 0]

    return {"success": True, "data": results, "count": len(results)}


# ========== 庫存領用 API ==========


@app.post(
    "/api/inventory/requisitions",
    tags=["庫存管理"],
    summary="建立庫存領用單",
    description="從庫存中領用物品，會自動扣減庫存數量",
    response_model=ApiResponse,
)
def create_inventory_requisition(req: InventoryRequisitionRequest):
    """
    建立庫存領用單
    
    需指定要領用的品項（item_name, brand, model 至少填一項），系統會查找庫存並扣減。
    
    回傳領用單資訊與剩餘庫存數量。
    """
    # 找到對應的庫存項目
    inventory_item = None
    for item in INVENTORY:
        match = True
        if req.item_name and req.item_name.lower() not in item["item_name"].lower():
            match = False
        if req.brand and req.brand.lower() != item["brand"].lower():
            match = False
        if req.model and req.model.lower() != item["model"].lower():
            match = False
        if match:
            inventory_item = item
            break

    if not inventory_item:
        raise HTTPException(status_code=404, detail="找不到符合條件的庫存品項")

    # 檢查庫存是否足夠
    if inventory_item["available"] < req.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"庫存不足，目前可用數量為 {inventory_item['available']}，需求數量為 {req.quantity}",
        )

    # 建立領用單
    req_id = f"IR{datetime.datetime.now().strftime('%Y%m%d')}{str(len(INVENTORY_REQUISITIONS) + 1).zfill(4)}"

    requisition_data = {
        "requisition_id": req_id,
        "item_name": inventory_item["item_name"],
        "brand": inventory_item["brand"],
        "model": inventory_item["model"],
        "quantity": req.quantity,
        "location": inventory_item["location"],
        "department": req.department,
        "requester": req.requester,
        "purpose": req.purpose,
        "notes": req.notes,
        "status": "已領用",
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 扣減庫存
    inventory_item["available"] -= req.quantity

    INVENTORY_REQUISITIONS.append(requisition_data)

    return {
        "success": True,
        "data": requisition_data,
        "message": f"成功領用 {req.quantity} 個 {inventory_item['brand']} {inventory_item['model']}",
    }


@app.get(
    "/api/inventory/requisitions",
    tags=["庫存管理"],
    summary="查詢庫存領用單",
    description="查詢已建立的庫存領用單記錄",
    response_model=ApiResponse,
)
def get_inventory_requisitions(
    requisition_id: Optional[str] = Query(None, description="領用單編號"),
    department: Optional[str] = Query(None, description="部門"),
    requester: Optional[str] = Query(None, description="申請人"),
):
    """查詢庫存領用單"""
    results = INVENTORY_REQUISITIONS.copy()

    if requisition_id:
        results = [r for r in results if r["requisition_id"] == requisition_id]
    if department:
        results = [r for r in results if department in r.get("department", "")]
    if requester:
        results = [r for r in results if requester in r.get("requester", "")]

    return {"success": True, "data": results, "count": len(results)}


@app.get(
    "/api/suppliers",
    tags=["供應商管理"],
    summary="查詢供應商資訊",
    description="查詢供應商列表，可依產品類別、最低評分篩選",
    response_model=ApiResponse,
)
def get_suppliers(
    category: Optional[str] = Query(None, description="產品類別（電腦、螢幕、週邊設備等）"),
    min_rating: Optional[float] = Query(None, description="最低評分 (0-5)", ge=0, le=5),
):
    """
    查詢供應商資訊
    
    回傳結果會依評分由高至低排序。
    """
    results = SUPPLIERS.copy()

    if category:
        results = [r for r in results if any(category in cat for cat in r["category"])]

    if min_rating:
        results = [r for r in results if r["rating"] >= min_rating]

    results.sort(key=lambda x: x["rating"], reverse=True)

    return {"success": True, "data": results, "count": len(results)}


@app.get(
    "/api/suppliers/{supplier_id}",
    tags=["供應商管理"],
    summary="查詢單一供應商詳細資訊",
    description="取得供應商詳細資訊，包含歷史採購記錄與採購金額統計",
    response_model=ApiResponse,
)
def get_supplier_detail(supplier_id: str):
    """
    查詢單一供應商詳細資訊
    
    - **supplier_id**: 可使用供應商 ID (如 SUP001) 或供應商名稱
    """
    supplier = next(
        (s for s in SUPPLIERS if s["id"] == supplier_id or supplier_id in s["name"]),
        None,
    )

    if not supplier:
        raise HTTPException(status_code=404, detail="供應商不存在")

    # 取得該供應商的歷史採購
    history = [h for h in PURCHASE_HISTORY if supplier["name"] in h["supplier"]]

    return {
        "success": True,
        "data": {
            **supplier,
            "purchase_history": history,
            "total_purchase_amount": sum(
                h["unit_price"] * h["quantity"] for h in history
            ),
        },
    }


@app.get(
    "/api/products",
    tags=["產品目錄"],
    summary="查詢產品目錄（比價用）",
    description="查詢各供應商的產品報價，用於比價與選擇供應商",
    response_model=ApiResponse,
)
def get_products(
    item_keyword: Optional[str] = Query(None, description="品項關鍵字（品名或品牌）"),
    spec_requirement: Optional[str] = Query(None, description="規格需求關鍵字（用空格分隔多個關鍵字）"),
    supplier: Optional[str] = Query(None, description="指定供應商"),
):
    """
    查詢產品目錄（比價用）
    
    - **item_keyword**: 搜尋品名或品牌
    - **spec_requirement**: 規格需求，如 "i7 32GB" 會搜尋含有 i7 或 32GB 的規格
    - **supplier**: 只顯示特定供應商的產品
    
    結果會依單價由低至高排序。
    """
    results = PRODUCT_CATALOG.copy()

    if item_keyword:
        results = [
            r
            for r in results
            if item_keyword.lower() in r["item_name"].lower()
            or item_keyword.lower() in r.get("brand", "").lower()
        ]

    if spec_requirement:
        spec_keywords = spec_requirement.lower().split()
        filtered = []
        for r in results:
            spec_lower = r["spec"].lower()
            if any(kw in spec_lower for kw in spec_keywords):
                filtered.append(r)
        if filtered:
            results = filtered

    if supplier:
        results = [r for r in results if supplier in r["supplier"]]

    results.sort(key=lambda x: x["unit_price"])

    return {"success": True, "data": results, "count": len(results)}


# ========== 請購單 API ==========


@app.post(
    "/api/purchase-requests",
    tags=["請購單管理"],
    summary="建立請購單",
    description="建立新的請購單，建立後狀態為「待審核」",
    response_model=ApiResponse,
)
def create_purchase_request(pr: PurchaseRequestCreate):
    """
    建立請購單
    
    請購單建立後需經過審核才能轉為採購單。
    """
    pr_id = f"PR{datetime.datetime.now().strftime('%Y%m%d')}{str(len(PURCHASE_REQUESTS) + 1).zfill(4)}"

    pr_data = {
        "pr_id": pr_id,
        "item_name": pr.item_name,
        "spec": pr.spec,
        "quantity": pr.quantity,
        "purpose": pr.purpose,
        "department": pr.department,
        "requester": pr.requester,
        "expected_date": pr.expected_date
        or (datetime.datetime.now() + datetime.timedelta(days=14)).strftime("%Y-%m-%d"),
        "budget": pr.budget,
        "notes": pr.notes,
        "status": "待審核",
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    PURCHASE_REQUESTS.append(pr_data)

    return {"success": True, "data": pr_data}


@app.get(
    "/api/purchase-requests",
    tags=["請購單管理"],
    summary="查詢請購單",
    description="查詢請購單列表，可依編號、部門、狀態篩選",
    response_model=ApiResponse,
)
def get_purchase_requests(
    pr_id: Optional[str] = Query(None, description="請購單編號"),
    department: Optional[str] = Query(None, description="部門"),
    status: Optional[str] = Query(None, description="狀態（待審核、已審核、已駁回、已轉採購單）"),
):
    """查詢請購單"""
    results = PURCHASE_REQUESTS.copy()

    if pr_id:
        results = [p for p in results if p["pr_id"] == pr_id]
    if department:
        results = [p for p in results if department in p["department"]]
    if status:
        results = [p for p in results if status in p["status"]]

    return {"success": True, "data": results, "count": len(results)}


@app.get(
    "/api/purchase-requests/{pr_id}",
    tags=["請購單管理"],
    summary="查詢單一請購單",
    description="取得特定請購單的詳細資訊",
    response_model=ApiResponse,
)
def get_purchase_request_detail(pr_id: str):
    """查詢單一請購單"""
    pr = next((p for p in PURCHASE_REQUESTS if p["pr_id"] == pr_id), None)

    if not pr:
        raise HTTPException(status_code=404, detail="請購單不存在")

    return {"success": True, "data": pr}


@app.post(
    "/api/purchase-requests/{pr_id}/approve",
    tags=["請購單管理"],
    summary="審核通過請購單",
    description="將請購單狀態更新為「已審核」，通過後可轉為採購單",
    response_model=ApiResponse,
)
def approve_purchase_request(pr_id: str, approval: ApprovalRequest = None):
    """
    審核通過請購單
    
    只有狀態為「待審核」的請購單可以進行審核。
    """
    pr = next((p for p in PURCHASE_REQUESTS if p["pr_id"] == pr_id), None)

    if not pr:
        raise HTTPException(status_code=404, detail="請購單不存在")

    if pr["status"] != "待審核":
        raise HTTPException(
            status_code=400, detail=f"請購單狀態為「{pr['status']}」，無法審核"
        )

    if approval is None:
        approval = ApprovalRequest()

    pr["status"] = "已審核"
    pr["approved_by"] = approval.approver
    pr["approved_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pr["approval_notes"] = approval.notes or ""
    pr["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {"success": True, "data": pr, "message": "請購單審核通過"}


@app.post(
    "/api/purchase-requests/{pr_id}/reject",
    tags=["請購單管理"],
    summary="駁回請購單",
    description="將請購單狀態更新為「已駁回」，需提供駁回原因",
    response_model=ApiResponse,
)
def reject_purchase_request(pr_id: str, rejection: RejectRequest):
    """
    駁回請購單
    
    只有狀態為「待審核」的請購單可以進行駁回，需提供駁回原因。
    """
    pr = next((p for p in PURCHASE_REQUESTS if p["pr_id"] == pr_id), None)

    if not pr:
        raise HTTPException(status_code=404, detail="請購單不存在")

    if pr["status"] != "待審核":
        raise HTTPException(
            status_code=400, detail=f"請購單狀態為「{pr['status']}」，無法駁回"
        )

    pr["status"] = "已駁回"
    pr["rejected_by"] = rejection.approver
    pr["rejected_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pr["rejection_reason"] = rejection.reason
    pr["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {"success": True, "data": pr, "message": "請購單已駁回"}


# ========== 採購單 API ==========


@app.post(
    "/api/purchase-orders",
    tags=["採購單管理"],
    summary="建立採購單",
    description="將已審核的請購單轉為採購單，需指定供應商與單價",
    response_model=ApiResponse,
)
def create_purchase_order(po: PurchaseOrderCreate):
    """
    建立採購單
    
    需要：
    - 已存在且已審核的請購單 (pr_id)
    - 有效的供應商 (supplier_name)
    - 單價 (unit_price)
    
    建立後會自動更新請購單狀態為「已轉採購單」。
    """
    # 查找請購單
    pr = next((p for p in PURCHASE_REQUESTS if p["pr_id"] == po.pr_id), None)

    if not pr:
        raise HTTPException(status_code=404, detail=f"請購單 {po.pr_id} 不存在")

    # 查找供應商
    supplier = next(
        (s for s in SUPPLIERS if po.supplier_name in s["name"]), None
    )

    if not supplier:
        raise HTTPException(status_code=404, detail=f"供應商 {po.supplier_name} 不存在")

    po_id = f"PO{datetime.datetime.now().strftime('%Y%m%d')}{str(len(PURCHASE_ORDERS) + 1).zfill(4)}"

    final_quantity = po.quantity or pr["quantity"]
    total_amount = po.unit_price * final_quantity

    po_data = {
        "po_id": po_id,
        "pr_id": po.pr_id,
        "item_name": pr["item_name"],
        "spec": pr["spec"],
        "quantity": final_quantity,
        "unit_price": po.unit_price,
        "total_amount": total_amount,
        "supplier_id": supplier["id"],
        "supplier_name": supplier["name"],
        "delivery_date": po.delivery_date
        or (
            datetime.datetime.now() + datetime.timedelta(days=supplier["delivery_days"])
        ).strftime("%Y-%m-%d"),
        "payment_terms": po.payment_terms or supplier["payment_terms"],
        "department": pr["department"],
        "requester": pr["requester"],
        "purpose": pr["purpose"],
        "notes": po.notes,
        "status": "已下單",
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    PURCHASE_ORDERS.append(po_data)

    # 更新請購單狀態
    pr["status"] = "已轉採購單"
    pr["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {"success": True, "data": po_data}


@app.get(
    "/api/purchase-orders",
    tags=["採購單管理"],
    summary="查詢採購單",
    description="查詢採購單列表，可依編號、請購單編號、部門、狀態篩選",
    response_model=ApiResponse,
)
def get_purchase_orders(
    po_id: Optional[str] = Query(None, description="採購單編號"),
    pr_id: Optional[str] = Query(None, description="請購單編號"),
    department: Optional[str] = Query(None, description="部門"),
    status: Optional[str] = Query(None, description="狀態"),
):
    """查詢採購單"""
    results = PURCHASE_ORDERS.copy()

    if po_id:
        results = [p for p in results if p["po_id"] == po_id]
    if pr_id:
        results = [p for p in results if p["pr_id"] == pr_id]
    if department:
        results = [p for p in results if department in p["department"]]
    if status:
        results = [p for p in results if status in p["status"]]

    return {"success": True, "data": results, "count": len(results)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
