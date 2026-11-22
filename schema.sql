PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 30),
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
  content_type TEXT NOT NULL CHECK (content_type IN ('image/jpeg', 'image/png', 'image/webp')),
  size INTEGER NOT NULL CHECK (size > 0 AND size <= 1500000),
  data BLOB NOT NULL,
  uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO listings (title,description,city,district,address_area,monthly_rent,management_fee,electricity_rate,water_fee,internet_fee,room_type,area_ping,floor,equipment,image_url)
SELECT '採光通風・近捷運獨立套房','安靜巷弄，生活機能完整，適合重視通勤與採光的學生。','臺北市','大安區','科技大樓站步行 6 分鐘',12500,800,5.5,0,300,'獨立套房',7.2,'5 樓 / 共 7 樓','["獨立衛浴","冷氣","洗衣機","網路"]',''
WHERE NOT EXISTS (SELECT 1 FROM listings);
INSERT INTO listings (title,description,city,district,address_area,monthly_rent,management_fee,electricity_rate,water_fee,internet_fee,room_type,area_ping,floor,equipment,image_url)
SELECT '近校溫馨雅房・可開伙','共用空間維護良好，附近有超市與公車站，室友單純。','臺中市','西區','公車 15 分鐘到校',7800,500,5.0,150,0,'雅房',5.8,'3 樓 / 共 5 樓','["可開伙","冰箱","洗衣機","陽台"]',''
WHERE (SELECT COUNT(*) FROM listings)=1;
INSERT INTO listings (title,description,city,district,address_area,monthly_rent,management_fee,electricity_rate,water_fee,internet_fee,room_type,area_ping,floor,equipment,image_url)
SELECT '新整理電梯大樓套房','格局方正、家具齊全，管理室代收包裹，適合需要穩定生活空間的租客。','新竹市','東區','清大側門步行 9 分鐘',14800,1200,6.0,0,0,'獨立套房',8.5,'8 樓 / 共 12 樓','["電梯","管理室","書桌"]',''
WHERE (SELECT COUNT(*) FROM listings)=2;
INSERT INTO listings (title,description,city,district,address_area,monthly_rent,management_fee,electricity_rate,water_fee,internet_fee,room_type,area_ping,floor,equipment,image_url)
SELECT '簡約採光雅房・含網路','房間明亮，公共區域定期清潔，租金已含網路費。','高雄市','三民區','捷運後驛站步行 8 分鐘',6900,300,5.0,0,0,'雅房',5.2,'2 樓 / 共 4 樓','["網路","冷氣","書桌"]',''
WHERE (SELECT COUNT(*) FROM listings)=3;
