const allowedEquipment = new Set(["冷氣", "洗衣機", "冰箱", "獨立衛浴", "網路", "陽台", "可開伙", "電梯", "管理室", "書桌"]);
const allowedRoomTypes = new Set(["獨立套房", "雅房", "整層住家"]);
const maxPosterSize = 1_500_000;

function responseJson(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...headers },
  });
}

function errorResponse(message, status, errors) {
  return responseJson({ detail: errors ? { message, errors } : message }, status);
}

function withCors(response) {
  const headers = new Headers(response.headers);
  headers.set("Access-Control-Allow-Origin", "*");
  headers.set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");
  headers.set("Access-Control-Allow-Headers", "Content-Type, X-Admin-Key");
  headers.set("Access-Control-Max-Age", "86400");
  return new Response(response.body, { status: response.status, headers });
}

async function all(db, sql, ...values) {
  const result = await db.prepare(sql).bind(...values).all();
  return result.results ?? [];
}

async function first(db, sql, ...values) {
  return db.prepare(sql).bind(...values).first();
}

function listingFromRow(row) {
  if (!row) return null;
  const item = { ...row };
  try {
    item.equipment = JSON.parse(item.equipment || "[]");
  } catch {
    item.equipment = [];
  }
  const hasPoster = Boolean(item.poster_stored_name);
  delete item.poster_stored_name;
  item.poster_url = hasPoster ? `/api/listings/${item.id}/poster` : null;
  return item;
}

async function getListing(db, id) {
  const row = await first(db, `
    SELECT l.*, p.stored_name AS poster_stored_name
    FROM listings l LEFT JOIN posters p ON p.listing_id = l.id
    WHERE l.id = ?
  `, id);
  return listingFromRow(row);
}

function validateListing(values) {
  const errors = [];
  const addError = (field, message) => errors.push({ loc: [field], msg: message, type: "value_error" });
  const title = String(values.title ?? "").trim();
  const description = String(values.description ?? "").trim();
  const city = String(values.city ?? "").trim();
  const district = String(values.district ?? "").trim();
  const addressArea = String(values.address_area ?? "").trim();
  const roomType = String(values.room_type ?? "").trim();
  const floor = String(values.floor ?? "").trim();
  const monthlyRent = Number(values.monthly_rent);
  const managementFee = Number(values.management_fee ?? 0);
  const electricityRate = values.electricity_rate === "" || values.electricity_rate == null ? null : Number(values.electricity_rate);
  const waterFee = Number(values.water_fee ?? 0);
  const internetFee = Number(values.internet_fee ?? 0);
  const areaPing = Number(values.area_ping);
  const equipment = Array.isArray(values.equipment) ? values.equipment.map(String) : [];

  if (title.length < 4 || title.length > 80) addError("title", "標題需為 4 至 80 個字。");
  if (description.length < 10 || description.length > 1000) addError("description", "介紹需為 10 至 1000 個字。");
  if (city.length < 2 || city.length > 20) addError("city", "請輸入縣市名稱。");
  if (district.length < 2 || district.length > 20) addError("district", "請輸入行政區名稱。");
  if (addressArea.length < 2 || addressArea.length > 100) addError("address_area", "請輸入交通或生活圈描述。");
  if (!Number.isInteger(monthlyRent) || monthlyRent < 1 || monthlyRent > 200000) addError("monthly_rent", "租金需介於 1 至 200,000 元。");
  if (!Number.isInteger(managementFee) || managementFee < 0 || managementFee > 50000) addError("management_fee", "管理費格式錯誤。");
  if (electricityRate !== null && (!Number.isFinite(electricityRate) || electricityRate <= 0 || electricityRate > 100)) addError("electricity_rate", "電費格式錯誤。");
  if (!Number.isInteger(waterFee) || waterFee < 0 || waterFee > 50000) addError("water_fee", "水費格式錯誤。");
  if (!Number.isInteger(internetFee) || internetFee < 0 || internetFee > 10000) addError("internet_fee", "網路費格式錯誤。");
  if (!allowedRoomTypes.has(roomType)) addError("room_type", "請選擇有效房型。");
  if (!Number.isFinite(areaPing) || areaPing <= 0 || areaPing > 300) addError("area_ping", "坪數格式錯誤。");
  if (!floor || floor.length > 30) addError("floor", "請輸入樓層資訊。");
  if (equipment.length > 20 || equipment.some(item => !allowedEquipment.has(item))) addError("equipment", "設備選項包含不支援的項目。");

  return {
    errors,
    payload: {
      title, description, city, district, address_area: addressArea,
      monthly_rent: monthlyRent, management_fee: managementFee,
      electricity_rate: electricityRate, water_fee: waterFee, internet_fee: internetFee,
      room_type: roomType, area_ping: areaPing, floor,
      equipment: [...new Set(equipment)],
    },
  };
}

function parseJsonBody(body) {
  if (!body || typeof body !== "object") return {};
  return body;
}

function requireAdmin(request, env) {
  return Boolean(env.ADMIN_KEY) && request.headers.get("X-Admin-Key") === env.ADMIN_KEY;
}

function validateImage(file) {
  if (!(file instanceof File) || file.size === 0) return { error: "請選擇圖片檔案", status: 415 };
  if (file.size > maxPosterSize) return { error: "圖片大小不可超過 1.5 MB。", status: 413 };
  const name = file.name.replaceAll("\\", "/").split("/").pop() || "poster";
  const extension = name.toLowerCase().split(".").pop();
  const expectedType = { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp" }[extension];
  if (!expectedType || file.type !== expectedType) return { error: "只接受 JPG、PNG 或 WebP 圖片。", status: 415 };
  return { name, contentType: expectedType };
}

async function storePoster(db, listingId, file) {
  const valid = validateImage(file);
  if (valid.error) return valid;
  const bytes = await file.arrayBuffer();
  const data = new Uint8Array(bytes);
  const isJpeg = data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff;
  const isPng = data.length >= 8 && [137, 80, 78, 71, 13, 10, 26, 10].every((byte, index) => data[index] === byte);
  const isWebp = data.length >= 12 && String.fromCharCode(...data.slice(0, 4)) === "RIFF" && String.fromCharCode(...data.slice(8, 12)) === "WEBP";
  if (!(isJpeg || isPng || isWebp)) return { error: "檔案內容不是有效的圖片。", status: 415 };
  const key = `${crypto.randomUUID()}.${valid.name.split(".").pop().toLowerCase()}`;
  await db.prepare(`
    INSERT INTO posters (listing_id, stored_name, original_name, content_type, size, data, uploaded_at)
    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(listing_id) DO UPDATE SET
      stored_name = excluded.stored_name,
      original_name = excluded.original_name,
      content_type = excluded.content_type,
      size = excluded.size,
      data = excluded.data,
      uploaded_at = CURRENT_TIMESTAMP
  `).bind(listingId, key, valid.name, valid.contentType, file.size, bytes).run();
  return { storedName: key, size: file.size };
}

async function handle(request, env) {
  if (request.method === "OPTIONS") return new Response(null, { status: 204 });
  if (!env.DB) return errorResponse("Cloudflare D1 尚未綁定到 Pages Function。", 503);
  const url = new URL(request.url);
  const path = url.pathname.replace(/\/$/, "") || "/";
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  const db = env.DB;

  if (path === "/api/health" && request.method === "GET") {
    await db.prepare("SELECT 1").first();
    return responseJson({ ok: true, database: "D1" });
  }

  if (path === "/api/listings" && request.method === "GET") {
    const filters = [];
    const values = [];
    filters.push("l.status = 'available'");
    const area = url.searchParams.get("area");
    const maxRent = Number(url.searchParams.get("max_rent"));
    const roomType = url.searchParams.get("room_type");
    const search = url.searchParams.get("q")?.trim();
    if (area) { filters.push("(l.city = ? OR l.district = ?)"); values.push(area, area); }
    if (Number.isFinite(maxRent) && maxRent > 0) { filters.push("l.monthly_rent <= ?"); values.push(maxRent); }
    if (roomType) { filters.push("l.room_type = ?"); values.push(roomType); }
    if (search) {
      filters.push("(l.title LIKE ? OR l.description LIKE ? OR l.address_area LIKE ?)");
      values.push(`%${search}%`, `%${search}%`, `%${search}%`);
    }
    const sort = url.searchParams.get("sort");
    const orderBy = { rent_asc: "l.monthly_rent ASC", rent_desc: "l.monthly_rent DESC", newest: "l.created_at DESC" }[sort] || "l.id ASC";
    const rows = await all(db, `
      SELECT l.*, p.stored_name AS poster_stored_name
      FROM listings l LEFT JOIN posters p ON p.listing_id = l.id
      WHERE ${filters.join(" AND ")} ORDER BY ${orderBy}
    `, ...values);
    const selectedEquipment = url.searchParams.getAll("equipment");
    let items = rows.map(listingFromRow);
    if (selectedEquipment.length) items = items.filter(item => selectedEquipment.every(value => item.equipment.includes(value)));
    return responseJson({ items, total: items.length });
  }

  if (path === "/api/listings" && request.method === "POST") {
    const form = await request.formData();
    const values = {
      title: form.get("title"), description: form.get("description"), city: form.get("city"),
      district: form.get("district"), address_area: form.get("address_area"), monthly_rent: form.get("monthly_rent"),
      management_fee: form.get("management_fee"), electricity_rate: form.get("electricity_rate"),
      water_fee: form.get("water_fee"), internet_fee: form.get("internet_fee"), room_type: form.get("room_type"),
      area_ping: form.get("area_ping"), floor: form.get("floor"), equipment: form.getAll("equipment"),
    };
    const { payload, errors } = validateListing(values);
    if (errors.length) return errorResponse("請修正標示欄位後再送出。", 422, errors);
    if (form.get("agree") !== "on") return errorResponse("請確認房源資訊屬實並同意刊登。", 422, [{ loc: ["agree"], msg: "請先勾選確認事項。" }]);
    const result = await db.prepare(`
      INSERT INTO listings (title, description, city, district, address_area, monthly_rent, management_fee,
        electricity_rate, water_fee, internet_fee, room_type, area_ping, floor, equipment)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(payload.title, payload.description, payload.city, payload.district, payload.address_area,
      payload.monthly_rent, payload.management_fee, payload.electricity_rate, payload.water_fee,
      payload.internet_fee, payload.room_type, payload.area_ping, payload.floor, JSON.stringify(payload.equipment)).run();
    const listingId = result.meta.last_row_id;
    const poster = form.get("poster");
    if (poster instanceof File && poster.size > 0) {
      const saved = await storePoster(db, listingId, poster);
      if (saved.error) {
        await db.prepare("DELETE FROM listings WHERE id = ?").bind(listingId).run();
        return errorResponse(saved.error, saved.status);
      }
    }
    return responseJson({ ok: true, id: listingId }, 201);
  }

  if (parts[0] === "api" && parts[1] === "listings" && parts.length === 3 && request.method === "GET") {
    const id = Number(parts[2]);
    if (!Number.isInteger(id) || id < 1) return errorResponse("找不到這筆房源", 404);
    const item = await getListing(db, id);
    return item ? responseJson(item) : errorResponse("找不到這筆房源", 404);
  }

  if (parts[0] === "api" && parts[1] === "listings" && parts.length >= 3) {
    const listingId = Number(parts[2]);
    if (!Number.isInteger(listingId)) return errorResponse("找不到這筆房源", 404);
    const suffix = parts.slice(3).join("/");
    if (suffix === "poster/info" && request.method === "GET") {
      const row = await first(db, "SELECT original_name, content_type, size, uploaded_at FROM posters WHERE listing_id = ?", listingId);
      return row ? responseJson(row) : errorResponse("這筆房源尚未上傳海報", 404);
    }
    if (suffix === "poster" && request.method === "GET") {
      const row = await first(db, "SELECT content_type, data FROM posters WHERE listing_id = ?", listingId);
      if (!row) return errorResponse("這筆房源尚未上傳海報", 404);
      const bytes = row.data instanceof ArrayBuffer ? row.data : Uint8Array.from(row.data).buffer;
      return new Response(bytes, { headers: { "Content-Type": row.content_type, "X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=3600" } });
    }
    if (suffix === "poster" && request.method === "PUT") {
      if (!env.ADMIN_KEY) return errorResponse("管理後台尚未設定管理密鑰。", 503);
      if (!requireAdmin(request, env)) return errorResponse("管理密鑰錯誤或未提供。", 401);
      const form = await request.formData();
      const poster = form.get("poster");
      const saved = await storePoster(db, listingId, poster);
      if (saved.error) return errorResponse(saved.error, saved.status);
      return responseJson({ listing_id: listingId, poster_url: `/api/listings/${listingId}/poster`, size: saved.size }, 200);
    }
    if (suffix === "poster" && request.method === "DELETE") {
      if (!env.ADMIN_KEY) return errorResponse("管理後台尚未設定管理密鑰。", 503);
      if (!requireAdmin(request, env)) return errorResponse("管理密鑰錯誤或未提供。", 401);
      const result = await db.prepare("DELETE FROM posters WHERE listing_id = ?").bind(listingId).run();
      if (!result.meta.changes) return errorResponse("這筆房源尚未上傳海報", 404);
      return new Response(null, { status: 204 });
    }
  }

  if (path === "/api/cost-estimates" && request.method === "POST") {
    const payload = parseJsonBody(await request.json());
    const rent = Number(payload.monthly_rent);
    const management = Number(payload.management_fee || 0);
    const electricityRate = Number(payload.electricity_rate || 0);
    const electricity = Math.round(Number(payload.monthly_electricity_usage || 0) * electricityRate);
    const water = Number(payload.water_fee || 0);
    const internet = Number(payload.internet_fee || 0);
    const subsidy = Number(payload.subsidy || 0);
    if (![rent, management, electricityRate, electricity, water, internet, subsidy].every(Number.isFinite) || rent <= 0 || [management, electricity, water, internet, subsidy].some(value => value < 0)) {
      return errorResponse("費用資料格式錯誤", 422);
    }
    const gross = rent + management + electricity + water + internet;
    return responseJson({ monthly_rent: rent, management_fee: management, electricity, water_fee: water, internet_fee: internet, gross_monthly_cost: gross, subsidy_input: subsidy, estimated_monthly_cost: Math.max(0, gross - subsidy), disclaimer: "費用為依輸入資料試算；補助金額由使用者自行填寫，非資格判定。" });
  }

  if (path === "/api/users" && request.method === "POST") {
    const payload = parseJsonBody(await request.json());
    const displayName = String(payload.display_name || "").trim();
    if (!displayName || displayName.length > 30) return errorResponse("顯示名稱需為 1 至 30 個字。", 422);
    const id = crypto.randomUUID();
    await db.prepare("INSERT INTO users (id, display_name) VALUES (?, ?)").bind(id, displayName).run();
    return responseJson({ id, display_name: displayName }, 201);
  }

  if (parts[0] === "api" && parts[1] === "users" && parts.length === 4 && parts[3] === "favorites" && request.method === "GET") {
    const rows = await all(db, `
      SELECT l.*, p.stored_name AS poster_stored_name
      FROM listings l JOIN favorites f ON f.listing_id = l.id
      LEFT JOIN posters p ON p.listing_id = l.id
      WHERE f.user_id = ? ORDER BY f.created_at DESC
    `, parts[2]);
    return responseJson({ items: rows.map(listingFromRow) });
  }

  if (parts[0] === "api" && parts[1] === "users" && parts.length === 5 && parts[3] === "favorites") {
    const userId = parts[2];
    const listingId = Number(parts[4]);
    if (request.method === "POST") {
      if (!(await first(db, "SELECT id FROM users WHERE id = ?", userId))) return errorResponse("找不到使用者", 404);
      if (!(await first(db, "SELECT id FROM listings WHERE id = ?", listingId))) return errorResponse("找不到房源", 404);
      await db.prepare("INSERT OR IGNORE INTO favorites (user_id, listing_id) VALUES (?, ?)").bind(userId, listingId).run();
      return responseJson({ ok: true, listing_id: listingId }, 201);
    }
    if (request.method === "DELETE") {
      await db.prepare("DELETE FROM favorites WHERE user_id = ? AND listing_id = ?").bind(userId, listingId).run();
      return new Response(null, { status: 204 });
    }
  }

  if (parts[0] === "api" && parts[1] === "admin") {
    if (!env.ADMIN_KEY) return errorResponse("管理後台尚未設定管理密鑰。", 503);
    if (!requireAdmin(request, env)) return errorResponse("管理密鑰錯誤或未提供。", 401);
    if (path === "/api/admin/overview" && request.method === "GET") {
      const listingRows = await all(db, `SELECT l.*, p.stored_name AS poster_stored_name FROM listings l LEFT JOIN posters p ON p.listing_id = l.id ORDER BY l.id DESC`);
      const users = await all(db, "SELECT id, display_name, created_at FROM users ORDER BY created_at DESC");
      const favorites = await all(db, `SELECT f.id, f.user_id, u.display_name, f.listing_id, l.title, f.created_at FROM favorites f JOIN users u ON u.id = f.user_id JOIN listings l ON l.id = f.listing_id ORDER BY f.created_at DESC`);
      const posters = await all(db, "SELECT p.listing_id, l.title, p.original_name, p.content_type, p.size, p.uploaded_at FROM posters p JOIN listings l ON l.id = p.listing_id ORDER BY p.uploaded_at DESC");
      const listings = listingRows.map(listingFromRow);
      return responseJson({ listings, users, favorites, posters, counts: { listings: listings.length, users: users.length, favorites: favorites.length, posters: posters.length } });
    }
    if (parts[2] === "listings" && parts.length === 4) {
      const listingId = Number(parts[3]);
      if (request.method === "PUT") {
        const { payload, errors } = validateListing(parseJsonBody(await request.json()));
        if (errors.length) return errorResponse("請修正標示欄位後再送出。", 422, errors);
        const result = await db.prepare(`UPDATE listings SET title=?, description=?, city=?, district=?, address_area=?, monthly_rent=?, management_fee=?, electricity_rate=?, water_fee=?, internet_fee=?, room_type=?, area_ping=?, floor=?, equipment=? WHERE id=?`).bind(payload.title, payload.description, payload.city, payload.district, payload.address_area, payload.monthly_rent, payload.management_fee, payload.electricity_rate, payload.water_fee, payload.internet_fee, payload.room_type, payload.area_ping, payload.floor, JSON.stringify(payload.equipment), listingId).run();
        if (!result.meta.changes) return errorResponse("找不到這筆房源", 404);
        return responseJson(await getListing(db, listingId));
      }
      if (request.method === "DELETE") {
        const result = await db.prepare("DELETE FROM listings WHERE id = ?").bind(listingId).run();
        if (!result.meta.changes) return errorResponse("找不到這筆房源", 404);
        return new Response(null, { status: 204 });
      }
    }
    if (parts[2] === "users" && parts.length === 4) {
      const userId = parts[3];
      if (request.method === "PUT") {
        const payload = parseJsonBody(await request.json());
        const name = String(payload.display_name || "").trim();
        if (!name || name.length > 30) return errorResponse("顯示名稱需為 1 至 30 個字。", 422);
        const result = await db.prepare("UPDATE users SET display_name = ? WHERE id = ?").bind(name, userId).run();
        if (!result.meta.changes) return errorResponse("找不到使用者", 404);
        return responseJson({ id: userId, display_name: name });
      }
      if (request.method === "DELETE") {
        const result = await db.prepare("DELETE FROM users WHERE id = ?").bind(userId).run();
        if (!result.meta.changes) return errorResponse("找不到使用者", 404);
        return new Response(null, { status: 204 });
      }
    }
    if (parts[2] === "favorites" && parts.length === 4 && request.method === "DELETE") {
      const result = await db.prepare("DELETE FROM favorites WHERE id = ?").bind(Number(parts[3])).run();
      if (!result.meta.changes) return errorResponse("找不到收藏紀錄", 404);
      return new Response(null, { status: 204 });
    }
  }

  return errorResponse("找不到 API 路徑", 404);
}

export async function onRequest(context) {
  try {
    return withCors(await handle(context.request, context.env));
  } catch (error) {
    console.error("RoomRadar API error", error);
    return withCors(errorResponse("伺服器處理失敗，請稍後再試。", 500));
  }
}
