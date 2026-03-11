from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqladmin import Admin
import json
import os

# Импортируем из наших новых модулей
from database import engine, SessionLocal, Base
from models import Manufacturer, Product, Category
from admin import authentication_backend, ManufacturerAdmin, ProductAdmin, CategoryAdmin

# Создаем таблицы в БД (если их еще нет)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Профисфера API")

# Папки для статики
os.makedirs("static/products", exist_ok=True)
os.makedirs("static/manufacturers", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Настройки CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем админку
admin = Admin(app, engine, authentication_backend=authentication_backend, templates_dir="templates")
admin.add_view(CategoryAdmin) # <--- ДОБАВИЛИ КАТЕГОРИИ
admin.add_view(ManufacturerAdmin)
admin.add_view(ProductAdmin)

@app.get("/api/admin/categories/{cat_id}")
def get_category_info_model(cat_id: int):
    db = SessionLocal()
    category = db.query(Category).filter(Category.id == cat_id).first()
    db.close()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"info_model_json": category.info_model_json}

# --- Инициализация базы начальными данными (Seed) ---
def seed_db_from_json():
    db = SessionLocal()
    if db.query(Product).count() == 0 and os.path.exists("products.json"):
        with open("products.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            
            brands = set(item.get("brand", "Без бренда") for item in data)
            brand_map = {}
            for b_name in brands:
                manuf = Manufacturer(name=b_name)
                db.add(manuf)
                db.commit()
                db.refresh(manuf)
                brand_map[b_name] = manuf.id

            for item in data:
                p_id = int(item.pop("id", 0))
                p_name = item.pop("name", "")
                p_brand_name = item.pop("brand", "Без бренда")
                p_price = item.pop("price", "")
                
                old_img = item.pop("image", "")
                images_arr = [{"orig": old_img, "thumb": old_img}] if old_img else []
                
                p_short = item.pop("shortDesc", "")
                p_full = item.pop("fullDesc", "")
                other = json.dumps(item, ensure_ascii=False)
                
                db_product = Product(
                    id=p_id, name=p_name, manufacturer_id=brand_map[p_brand_name], 
                    price=str(p_price), images_json=json.dumps(images_arr), 
                    shortDesc=p_short, fullDesc=p_full, other_data=other
                )
                db.add(db_product)
        db.commit()
    db.close()

@app.on_event("startup")
def on_startup():
    seed_db_from_json()

# --- API МАРШРУТЫ ---
@app.get("/api/products")
def get_products():
    db = SessionLocal()
    products = db.query(Product).all()
    
    result = []
    DOMAIN = "https://185.185.71.149"
    
    for p in products:
        item = json.loads(p.other_data) if p.other_data else {}
        item["id"] = p.id
        item["name"] = p.name
        item["sku"] = p.sku  # Не забываем отдавать артикул
        item["brand"] = p.manufacturer.name if p.manufacturer else "Без бренда"
        item["price"] = p.price
        
        # МАГИЯ ДЕРЕВА КАТЕГОРИЙ (Собираем cat1, cat2, cat3 для фронтенда)
        if p.category:
            cat_tree = []
            curr_cat = p.category
            while curr_cat:
                cat_tree.insert(0, curr_cat.name)  # Добавляем в начало списка
                curr_cat = curr_cat.parent
                
            if len(cat_tree) > 0: item["cat1"] = cat_tree[0]
            if len(cat_tree) > 1: item["cat2"] = cat_tree[1]
            if len(cat_tree) > 2: item["cat3"] = cat_tree[2]
        
        # Динамические характеристики
        if p.attributes_json:
            try:
                attrs = json.loads(p.attributes_json)
                item.update(attrs)
            except: pass
        
        # Обработка картинок
        images_list = json.loads(p.images_json) if p.images_json else []
        for img in images_list:
            if img["orig"].startswith("/static/"): img["orig"] = DOMAIN + img["orig"]
            if img["thumb"].startswith("/static/"): img["thumb"] = DOMAIN + img["thumb"]
        
        item["images"] = images_list 
        item["shortDesc"] = p.shortDesc
        item["fullDesc"] = p.fullDesc
        
        result.append(item)
        
    db.close()
    return result
