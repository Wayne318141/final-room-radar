from __future__ import annotations

import hmac
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, field_validator


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
UPLOAD_DIR = Path(os.getenv("ROOMRADAR_UPLOAD_DIR", ROOT / "uploads"))
DATABASE_PATH = Path(os.getenv("ROOMRADAR_DATABASE", ROOT / "roomradar.db"))
MAX_POSTER_SIZE = 2 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_TYPES_BY_EXTENSION = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with connect_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                landlord_id TEXT NOT NULL DEFAULT 'demo-landlord',
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                city TEXT NOT NULL,
                district TEXT NOT NULL,
                address_area TEXT NOT NULL,
                monthly_rent INTEGER NOT NULL CHECK (monthly_rent > 0),
                management_fee INTEGER NOT NULL DEFAULT 0 CHECK (management_fee >= 0),
                electricity_rate REAL,
                water_fee INTEGER NOT NULL DEFAULT 0 CHECK (water_fee >= 0),
                internet_fee INTEGER NOT NULL DEFAULT 0 CHECK (internet_fee >= 0),
                room_type TEXT NOT NULL,
                area_ping REAL NOT NULL CHECK (area_ping > 0),
                floor TEXT NOT NULL,
                equipment TEXT NOT NULL DEFAULT '[]',
                image_url TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'available',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, listing_id)
            );
            CREATE TABLE IF NOT EXISTS posters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id INTEGER NOT NULL UNIQUE REFERENCES listings(id) ON DELETE CASCADE,
                stored_name TEXT NOT NULL UNIQUE,
                original_name TEXT NOT NULL,
                content_type TEXT NOT NULL,
                size INTEGER NOT NULL CHECK (size > 0 AND size <= 2097152),
                uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        if connection.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 0:
            samples = [
                ("採光通風・近捷運獨立套房", "安靜巷弄，生活機能完整，適合重視通勤與採光的學生。", "臺北市", "大安區", "科技大樓站步行 6 分鐘", 12500, 800, 5.5, 0, 300, "獨立套房", 7.2, "5 樓 / 共 7 樓", ["獨立衛浴", "冷氣", "洗衣機", "網路"], "linear-gradient(135deg,#d8e6dc,#a7c5b5)"),
                ("近校溫馨雅房・可開伙", "共用空間維護良好，附近有超市與公車站，室友單純。", "臺中市", "西區", "公車 15 分鐘到校", 7800, 500, 5.0, 150, 0, "雅房", 5.8, "3 樓 / 共 5 樓", ["可開伙", "冰箱", "洗衣機", "陽台"], "linear-gradient(135deg,#eee0cb,#d6b994)"),
                ("新整理電梯大樓套房", "格局方正、家具齊全，管理室代收包裹，適合需要穩定生活空間的租客。", "新竹市", "東區", "清大側門步行 9 分鐘", 14800, 1200, 6.0, 0, 0, "獨立套房", 8.5, "8 樓 / 共 12 樓", ["電梯", "管理室", "雙人床", "書桌"], "linear-gradient(135deg,#dce5ef,#b2c3d6)"),
                ("兩房合租・近火車站", "兩房一廳適合好友合租，租金可平分，附近有超商與餐飲。", "臺南市", "東區", "臺南車站騎車 7 分鐘", 16000, 1000, 5.0, 0, 0, "整層住家", 18.0, "4 樓 / 共 6 樓", ["可合租", "陽台", "冰箱", "天然瓦斯"], "linear-gradient(135deg,#e8dce5,#c6a9bf)"),
                ("簡約採光雅房・含網路", "房間明亮，公共區域定期清潔，租金已含網路費。", "高雄市", "三民區", "捷運後驛站步行 8 分鐘", 6900, 300, 5.0, 0, 0, "雅房", 5.2, "2 樓 / 共 4 樓", ["網路", "冷氣", "書桌", "飲水機"], "linear-gradient(135deg,#e7e4cd,#c9c19b)"),
                ("近校靜巷獨立套房", "家具家電齊全，鄰近公園與超商，適合希望安靜讀書的租客。", "臺北市", "文山區", "景美站步行 10 分鐘", 9800, 600, 5.0, 100, 0, "獨立套房", 6.5, "2 樓 / 共 4 樓", ["獨立衛浴", "冰箱", "書桌", "可開伙"], "linear-gradient(135deg,#d8e4e8,#9dbdc4)"),
            ]
            connection.executemany(
                """INSERT INTO listings
                (title,description,city,district,address_area,monthly_rent,management_fee,electricity_rate,water_fee,internet_fee,room_type,area_ping,floor,equipment,image_url)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(*row[:13], json.dumps(row[13], ensure_ascii=False), row[14]) for row in samples],
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="RoomRadar API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("ROOMRADAR_ALLOWED_ORIGINS", "*").split(",") if origin.strip()],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Key"],
)


def require_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("ROOMRADAR_ADMIN_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="管理後台尚未設定管理密鑰")
    if not hmac.compare_digest((x_admin_key or "").encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="管理密鑰錯誤或未提供")


class ListingCreate(BaseModel):
    model_config = {"str_strip_whitespace": True}

    title: str = Field(min_length=4, max_length=80)
    description: str = Field(min_length=10, max_length=1000)
    city: str = Field(min_length=2, max_length=20)
    district: str = Field(min_length=2, max_length=20)
    address_area: str = Field(min_length=2, max_length=100)
    monthly_rent: int = Field(gt=0, le=200000)
    management_fee: int = Field(default=0, ge=0, le=50000)
    electricity_rate: float | None = Field(default=None, gt=0, le=100)
    water_fee: int = Field(default=0, ge=0, le=50000)
    internet_fee: int = Field(default=0, ge=0, le=10000)
    room_type: Literal["獨立套房", "雅房", "整層住家"]
    area_ping: float = Field(gt=0, le=300)
    floor: str = Field(min_length=1, max_length=30)
    equipment: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("equipment")
    @classmethod
    def validate_equipment(cls, value: list[str]) -> list[str]:
        allowed = {"冷氣", "洗衣機", "冰箱", "獨立衛浴", "網路", "陽台", "可開伙", "電梯", "管理室", "書桌"}
        if not set(value).issubset(allowed):
            raise ValueError("設備選項不在允許清單中")
        return value


class UserCreate(BaseModel):
    model_config = {"str_strip_whitespace": True}

    display_name: str = Field(min_length=1, max_length=30)


class CostEstimate(BaseModel):
    monthly_rent: int = Field(gt=0)
    management_fee: int = Field(default=0, ge=0)
    electricity_rate: float | None = Field(default=None, gt=0)
    monthly_electricity_usage: float = Field(default=0, ge=0)
    water_fee: int = Field(default=0, ge=0)
    internet_fee: int = Field(default=0, ge=0)
    subsidy: int = Field(default=0, ge=0)


def listing_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["equipment"] = json.loads(data["equipment"])
    stored_name = data.pop("poster_stored_name", None)
    data["poster_url"] = f"/api/listings/{data['id']}/poster" if stored_name else None
    return data


@app.get("/api/listings")
def get_listings(
    area: str | None = None,
    max_rent: int | None = Query(default=None, ge=1),
    room_type: str | None = None,
    equipment: list[str] | None = Query(default=None),
    q: str | None = None,
    sort: str = "recommended",
):
    query = """SELECT l.*, p.stored_name AS poster_stored_name
               FROM listings l LEFT JOIN posters p ON p.listing_id = l.id
               WHERE l.status = 'available'"""
    params: list[Any] = []
    if area:
        query += " AND (l.city = ? OR l.district = ?)"
        params.extend([area, area])
    if max_rent:
        query += " AND l.monthly_rent <= ?"
        params.append(max_rent)
    if room_type:
        query += " AND l.room_type = ?"
        params.append(room_type)
    if q:
        query += " AND (l.title LIKE ? OR l.description LIKE ? OR l.address_area LIKE ?)"
        params.extend([f"%{q}%"] * 3)
    order_by = {"rent_asc": "l.monthly_rent ASC", "rent_desc": "l.monthly_rent DESC", "newest": "l.created_at DESC"}.get(sort, "l.id ASC")
    query += f" ORDER BY {order_by}"
    with connect_db() as connection:
        listings = [listing_dict(row) for row in connection.execute(query, params).fetchall()]
    if equipment:
        listings = [item for item in listings if set(equipment).issubset(item["equipment"])]
    return {"items": listings, "total": len(listings)}


@app.get("/api/listings/{listing_id}")
def get_listing(listing_id: int):
    with connect_db() as connection:
        row = connection.execute(
            """SELECT l.*, p.stored_name AS poster_stored_name FROM listings l
               LEFT JOIN posters p ON p.listing_id = l.id WHERE l.id = ?""",
            (listing_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="找不到這筆房源")
    return listing_dict(row)


@app.get("/api/admin/overview", dependencies=[Depends(require_admin_key)])
def admin_overview():
    with connect_db() as connection:
        listings = connection.execute(
            """SELECT l.*, p.stored_name AS poster_stored_name FROM listings l
               LEFT JOIN posters p ON p.listing_id = l.id ORDER BY l.id DESC"""
        ).fetchall()
        users = connection.execute("SELECT id, display_name, created_at FROM users ORDER BY created_at DESC").fetchall()
        favorites = connection.execute(
            """SELECT f.id, f.user_id, u.display_name, f.listing_id, l.title, f.created_at
               FROM favorites f JOIN users u ON u.id = f.user_id
               JOIN listings l ON l.id = f.listing_id ORDER BY f.created_at DESC"""
        ).fetchall()
        posters = connection.execute(
            """SELECT p.listing_id, l.title, p.original_name, p.content_type, p.size, p.uploaded_at
               FROM posters p JOIN listings l ON l.id = p.listing_id ORDER BY p.uploaded_at DESC"""
        ).fetchall()
    return {
        "listings": [listing_dict(row) for row in listings],
        "users": [dict(row) for row in users],
        "favorites": [dict(row) for row in favorites],
        "posters": [dict(row) for row in posters],
        "counts": {"listings": len(listings), "users": len(users), "favorites": len(favorites), "posters": len(posters)},
    }


@app.put("/api/admin/users/{user_id}", dependencies=[Depends(require_admin_key)])
def update_user(user_id: str, payload: UserCreate):
    with connect_db() as connection:
        cursor = connection.execute("UPDATE users SET display_name = ? WHERE id = ?", (payload.display_name, user_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="找不到這位使用者")
    return {"id": user_id, "display_name": payload.display_name}


@app.delete("/api/admin/users/{user_id}", status_code=204, dependencies=[Depends(require_admin_key)])
def delete_user(user_id: str):
    with connect_db() as connection:
        cursor = connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="找不到這位使用者")


@app.delete("/api/admin/favorites/{favorite_id}", status_code=204, dependencies=[Depends(require_admin_key)])
def delete_favorite(favorite_id: int):
    with connect_db() as connection:
        cursor = connection.execute("DELETE FROM favorites WHERE id = ?", (favorite_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="找不到這筆收藏紀錄")


async def store_image(upload: UploadFile) -> tuple[str, str, str, int]:
    original_name = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=415, detail="海報只接受 JPG、PNG 或 WebP 圖片")

    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(64 * 1024):
        size += len(chunk)
        if size > MAX_POSTER_SIZE:
            raise HTTPException(status_code=413, detail="海報大小不可超過 2 MB")
        chunks.append(chunk)
    content = b"".join(chunks)
    detected_type = None
    if content.startswith(b"\xff\xd8\xff"):
        detected_type = "image/jpeg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        detected_type = "image/png"
    elif len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        detected_type = "image/webp"
    extension_type = IMAGE_TYPES_BY_EXTENSION.get(extension)
    if not detected_type or extension_type != detected_type:
        raise HTTPException(status_code=415, detail="檔案內容與副檔名不符，請選擇有效的 JPG、PNG 或 WebP 圖片")

    stored_name = f"{uuid4().hex}{extension}"
    (UPLOAD_DIR / stored_name).write_bytes(content)
    return stored_name, original_name, detected_type, size


def remove_stored_image(stored_name: str | None) -> None:
    if stored_name:
        (UPLOAD_DIR / stored_name).unlink(missing_ok=True)


@app.post("/api/listings")
async def create_listing(
    title: Annotated[str, Form()],
    description: Annotated[str, Form()],
    city: Annotated[str, Form()],
    district: Annotated[str, Form()],
    address_area: Annotated[str, Form()],
    monthly_rent: Annotated[int, Form()],
    room_type: Annotated[str, Form()],
    area_ping: Annotated[float, Form()],
    floor: Annotated[str, Form()],
    management_fee: Annotated[int, Form()] = 0,
    electricity_rate: Annotated[str, Form()] = "",
    water_fee: Annotated[int, Form()] = 0,
    internet_fee: Annotated[int, Form()] = 0,
    equipment: Annotated[list[str], Form()] = [],
    agree: Annotated[bool, Form()] = False,
    poster: Annotated[UploadFile | None, File()] = None,
):
    try:
        electricity_value = float(electricity_rate) if electricity_rate.strip() else None
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"message": "每度電費請輸入有效數字", "errors": [{"loc": ["electricity_rate"], "msg": "每度電費請輸入有效數字"}]}) from error
    values = {
        "title": title, "description": description, "city": city, "district": district,
        "address_area": address_area, "monthly_rent": monthly_rent,
        "management_fee": management_fee, "electricity_rate": electricity_value,
        "water_fee": water_fee, "internet_fee": internet_fee, "room_type": room_type,
        "area_ping": area_ping, "floor": floor, "equipment": equipment,
    }
    try:
        payload = ListingCreate(**values)
    except ValidationError as error:
        errors = [{"loc": item["loc"], "msg": item["msg"], "type": item["type"]} for item in error.errors()]
        raise HTTPException(status_code=422, detail={"message": "請修正標示欄位後再送出", "errors": errors}) from error
    if not agree:
        raise HTTPException(status_code=422, detail={"message": "請確認房源資訊屬實並同意刊登", "errors": [{"loc": ["agree"], "msg": "請先勾選確認事項"}]})

    saved_image = await store_image(poster) if poster and poster.filename else None
    try:
        with connect_db() as connection:
            cursor = connection.execute(
                """INSERT INTO listings
                (title,description,city,district,address_area,monthly_rent,management_fee,electricity_rate,water_fee,internet_fee,room_type,area_ping,floor,equipment)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (payload.title, payload.description, payload.city, payload.district, payload.address_area,
                 payload.monthly_rent, payload.management_fee, payload.electricity_rate, payload.water_fee,
                 payload.internet_fee, payload.room_type, payload.area_ping, payload.floor,
                 json.dumps(payload.equipment, ensure_ascii=False)),
            )
            listing_id = cursor.lastrowid
            if saved_image:
                connection.execute(
                    "INSERT INTO posters (listing_id, stored_name, original_name, content_type, size) VALUES (?,?,?,?,?)",
                    (listing_id, *saved_image),
                )
    except Exception:
        if saved_image:
            remove_stored_image(saved_image[0])
        raise
    return RedirectResponse(url=f"/?created={listing_id}#homes", status_code=303)


@app.put("/api/admin/listings/{listing_id}", dependencies=[Depends(require_admin_key)])
def update_listing(listing_id: int, payload: ListingCreate):
    with connect_db() as connection:
        exists = connection.execute("SELECT 1 FROM listings WHERE id = ?", (listing_id,)).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="找不到這筆房源")
        connection.execute(
            """UPDATE listings SET title=?, description=?, city=?, district=?, address_area=?,
               monthly_rent=?, management_fee=?, electricity_rate=?, water_fee=?, internet_fee=?,
               room_type=?, area_ping=?, floor=?, equipment=? WHERE id=?""",
            (payload.title, payload.description, payload.city, payload.district, payload.address_area,
             payload.monthly_rent, payload.management_fee, payload.electricity_rate, payload.water_fee,
             payload.internet_fee, payload.room_type, payload.area_ping, payload.floor,
             json.dumps(payload.equipment, ensure_ascii=False), listing_id),
        )
    return get_listing(listing_id)


@app.delete("/api/admin/listings/{listing_id}", status_code=204, dependencies=[Depends(require_admin_key)])
def delete_listing(listing_id: int):
    with connect_db() as connection:
        row = connection.execute("SELECT stored_name FROM posters WHERE listing_id = ?", (listing_id,)).fetchone()
        cursor = connection.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="找不到這筆房源")
    if row:
        remove_stored_image(row["stored_name"])


@app.put("/api/listings/{listing_id}/poster", dependencies=[Depends(require_admin_key)])
async def replace_poster(listing_id: int, poster: Annotated[UploadFile, File()]):
    with connect_db() as connection:
        exists = connection.execute("SELECT 1 FROM listings WHERE id = ?", (listing_id,)).fetchone()
        old = connection.execute("SELECT stored_name FROM posters WHERE listing_id = ?", (listing_id,)).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail="找不到這筆房源")
    saved_image = await store_image(poster)
    try:
        with connect_db() as connection:
            connection.execute(
                """INSERT INTO posters (listing_id, stored_name, original_name, content_type, size)
                   VALUES (?,?,?,?,?) ON CONFLICT(listing_id) DO UPDATE SET
                   stored_name=excluded.stored_name, original_name=excluded.original_name,
                   content_type=excluded.content_type, size=excluded.size, uploaded_at=CURRENT_TIMESTAMP""",
                (listing_id, *saved_image),
            )
    except Exception:
        remove_stored_image(saved_image[0])
        raise
    if old:
        remove_stored_image(old["stored_name"])
    return JSONResponse(
        status_code=200 if old else 201,
        headers={"Location": f"/api/listings/{listing_id}/poster"},
        content={"listing_id": listing_id, "poster_url": f"/api/listings/{listing_id}/poster", "size": saved_image[3]},
    )


@app.get("/api/listings/{listing_id}/poster")
def get_poster(listing_id: int):
    with connect_db() as connection:
        row = connection.execute("SELECT stored_name, content_type FROM posters WHERE listing_id = ?", (listing_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="這筆房源尚未上傳海報")
    return FileResponse(UPLOAD_DIR / row["stored_name"], media_type=row["content_type"], headers={"X-Content-Type-Options": "nosniff"})


@app.get("/api/listings/{listing_id}/poster/info")
def get_poster_info(listing_id: int):
    with connect_db() as connection:
        row = connection.execute(
            "SELECT original_name, content_type, size, uploaded_at FROM posters WHERE listing_id = ?",
            (listing_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="這筆房源尚未上傳海報")
    return dict(row)


@app.delete("/api/listings/{listing_id}/poster", status_code=204, dependencies=[Depends(require_admin_key)])
def delete_poster(listing_id: int):
    with connect_db() as connection:
        row = connection.execute("SELECT stored_name FROM posters WHERE listing_id = ?", (listing_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="這筆房源尚未上傳海報")
        connection.execute("DELETE FROM posters WHERE listing_id = ?", (listing_id,))
    remove_stored_image(row["stored_name"])


@app.post("/api/cost-estimates")
def estimate_cost(payload: CostEstimate):
    electricity = round(payload.monthly_electricity_usage * payload.electricity_rate) if payload.electricity_rate else 0
    subtotal = payload.monthly_rent + payload.management_fee + electricity + payload.water_fee + payload.internet_fee
    return {
        "monthly_rent": payload.monthly_rent,
        "management_fee": payload.management_fee,
        "electricity": electricity,
        "water_fee": payload.water_fee,
        "internet_fee": payload.internet_fee,
        "gross_monthly_cost": subtotal,
        "subsidy_input": payload.subsidy,
        "estimated_monthly_cost": max(0, subtotal - payload.subsidy),
        "disclaimer": "費用為依輸入資料試算；補助金額由使用者自行填寫，非資格判定。",
    }


@app.post("/api/users", status_code=201)
def create_user(payload: UserCreate):
    user_id = str(uuid4())
    with connect_db() as connection:
        connection.execute("INSERT INTO users (id, display_name) VALUES (?, ?)", (user_id, payload.display_name))
    return {"id": user_id, "display_name": payload.display_name}


@app.get("/api/users/{user_id}/favorites")
def get_favorites(user_id: str):
    with connect_db() as connection:
        rows = connection.execute(
            """SELECT l.*, p.stored_name AS poster_stored_name FROM listings l
               JOIN favorites f ON f.listing_id = l.id
               LEFT JOIN posters p ON p.listing_id = l.id
               WHERE f.user_id = ? ORDER BY f.created_at DESC""",
            (user_id,),
        ).fetchall()
    return {"items": [listing_dict(row) for row in rows]}


@app.post("/api/users/{user_id}/favorites/{listing_id}", status_code=201)
def add_favorite(user_id: str, listing_id: int):
    with connect_db() as connection:
        if connection.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到使用者")
        if connection.execute("SELECT 1 FROM listings WHERE id = ?", (listing_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="找不到房源")
        connection.execute("INSERT OR IGNORE INTO favorites (user_id, listing_id) VALUES (?, ?)", (user_id, listing_id))
    return {"ok": True, "listing_id": listing_id}


@app.delete("/api/users/{user_id}/favorites/{listing_id}", status_code=204)
def remove_favorite(user_id: str, listing_id: int):
    with connect_db() as connection:
        connection.execute("DELETE FROM favorites WHERE user_id = ? AND listing_id = ?", (user_id, listing_id))


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin")
def admin():
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/admin.html")
def admin_html():
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/config.js")
def frontend_config():
    return FileResponse(STATIC_DIR / "config.js", media_type="application/javascript")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
