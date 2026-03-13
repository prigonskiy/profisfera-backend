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

# --- Инициализация базы начальными данными (УМНАЯ МИГРАЦИЯ) ---
def seed_db_from_json():
    db = SessionLocal()
    # Если база уже заполнена - ничего не делаем
    if db.query(Product).count() > 0:
        db.close()
        return

    if not os.path.exists("products.json"):
        db.close()
        return

    with open("products.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Создаем Бренды
    brands = set(item.get("brand", "Без бренда") for item in data)
    brand_map = {}
    for b_name in brands:
        manuf = Manufacturer(name=b_name)
        db.add(manuf)
        db.commit()
        db.refresh(manuf)
        brand_map[b_name] = manuf.id

    # 2. Умное создание дерева категорий
    cat_map = {}
    def get_or_create_cat(name, parent_id):
        if not name: return None
        key = f"{parent_id}_{name}"
        if key not in cat_map:
            cat = Category(name=name, parent_id=parent_id)
            db.add(cat)
            db.commit()
            db.refresh(cat)
            cat_map[key] = cat.id
        return cat_map[key]

    # 3. Переносим товары и их характеристики
    # Это список всех специфических ключей, которые были в вашем JSON
    specific_keys = ['series', 'colors', 'appointment', 'consistency', 'viscosity', 'curing', 'materialType', 'packaging', 'selfEtching', 'hardness', 'purposes', 'specializations', 'groupId', 'groupFamilyName', 'deliveryType', 'optionName']

    for item in data:
        # Выстраиваем цепочку категорий в базе
        c1_id = get_or_create_cat(item.get("cat1"), None)
        c2_id = get_or_create_cat(item.get("cat2"), c1_id) if c1_id else None
        c3_id = get_or_create_cat(item.get("cat3"), c2_id) if c2_id else None
        
        # Товар привязываем к самой глубокой из доступных категорий
        final_cat_id = c3_id or c2_id or c1_id

        # Собираем специфические атрибуты
        attrs = {}
        for k in specific_keys:
            if k in item and item[k]:
                attrs[k] = item[k]
                
        p_id = int(item.get("id", 0))
        old_img = item.get("image", "")
        images_arr = [{"orig": old_img, "thumb": old_img}] if old_img else []

        db_product = Product(
            id=p_id,
            name=item.get("name", ""),
            sku=item.get("partNumber", ""),
            price=str(item.get("price", "")),
            manufacturer_id=brand_map.get(item.get("brand", "Без бренда")),
            category_id=final_cat_id,
            images_json=json.dumps(images_arr),
            shortDesc=item.get("shortDesc", ""),
            fullDesc=item.get("fullDesc", ""),
            attributes_json=json.dumps(attrs, ensure_ascii=False) # Магия здесь!
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
    DOMAIN = "https://185.185.71.149.nip.io" # При локальном тесте можно закомментировать использование DOMAIN ниже
    
    for p in products:
        item = {} # Создаем с чистого листа, без other_data
        item["id"] = p.id
        item["name"] = p.name
        item["partNumber"] = p.sku # Транслируем артикул для фронтенда
        item["brand"] = p.manufacturer.name if p.manufacturer else "Без бренда"
        item["price"] = p.price
        
        # Собираем путь категорий
        if p.category:
            cat_tree = []
            curr_cat = p.category
            visited = set()
            while curr_cat and curr_cat.id not in visited:
                visited.add(curr_cat.id)
                cat_tree.insert(0, curr_cat.name)
                curr_cat = curr_cat.parent
                
            if len(cat_tree) > 0: item["cat1"] = cat_tree[0]
            if len(cat_tree) > 1: item["cat2"] = cat_tree[1]
            if len(cat_tree) > 2: item["cat3"] = cat_tree[2]
        
        # Распаковываем специфические свойства и специализации
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

# --- ВРЕМЕННЫЙ МАРШРУТ ДЛЯ АВТОГЕНЕРАЦИИ ИНФОМОДЕЛЕЙ ---
@app.get("/api/admin/auto-generate-models")
def auto_generate_models():
    db = SessionLocal()
    categories = db.query(Category).all()
    
    # Словарь перевода ваших ключей на нормальный русский (мы брали их из state.js)
    KNOWN_ATTRS = {
        'series': 'Серия',
        'colors': 'Цвет',
        'appointment': 'Назначение',
        'consistency': 'Консистенция',
        'viscosity': 'Вязкость',
        'curing': 'Отверждение',
        'materialType': 'Тип материала',
        'packaging': 'Форма выпуска',
        'selfEtching': 'Самопротравливающийся',
        'hardness': 'Твёрдость',
        'purposes': 'Предназначение',
        'specializations': 'Специализации',
        'groupId': 'ID Группы',
        'groupFamilyName': 'Название семейства',
        'deliveryType': 'Тип поставки',
        'optionName': 'Название опции'
    }
    
    updated_count = 0
    
    for cat in categories:
        # Ищем все товары, принадлежащие этой категории
        products = db.query(Product).filter(Product.category_id == cat.id).all()
        if not products:
            continue
            
        # Собираем все уникальные ключи из товаров этой категории
        cat_attrs = set()
        for p in products:
            if p.attributes_json:
                try:
                    attrs = json.loads(p.attributes_json)
                    for k, v in attrs.items():
                        if v: # Берем ключ, только если там есть какие-то данные
                            cat_attrs.add(k)
                except:
                    pass
        
        # Если нашли характеристики — собираем из них Инфомодель
        if cat_attrs:
            info_model = []
            for k in cat_attrs:
                label = KNOWN_ATTRS.get(k, k) # Если не знаем перевод, оставляем английский ключ
                info_model.append({
                    "name": k,
                    "label": label,
                    "type": "string", # По умолчанию делаем текстовым полем
                    "options": []
                })
            
            cat.info_model_json = json.dumps(info_model, ensure_ascii=False)
            updated_count += 1
            
    db.commit()
    db.close()
    
    return {
        "status": "Успешно!", 
        "message": f"Инфомодели сгенерированы для {updated_count} категорий."
    }