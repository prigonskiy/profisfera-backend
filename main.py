from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqladmin import Admin
import json
import os
import pandas as pd
from io import BytesIO
from fastapi import UploadFile, File
from fastapi.responses import StreamingResponse, HTMLResponse
import math

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
admin.add_view(ProductFamilyAdmin)

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
        # МАГИЯ ДВУХУРОВНЕВОЙ ГРУППИРОВКИ
        if p.family:
            item["groupId"] = str(p.family.id)
            item["groupFamilyName"] = p.family.name
            
        if p.optionName:
            item["optionName"] = p.optionName
        
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
    
# ==========================================
# EXCEL МЕНЕДЖЕР ТОВАРОВ
# ==========================================

# 1. МАРШРУТ: ВЫГРУЗКА EXCEL
@app.get("/api/admin/category/{cat_id}/export")
def export_category_excel(cat_id: int):
    db = SessionLocal()
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if not cat:
        return {"error": "Категория не найдена"}

    # Достаем ключи и названия из Инфомодели
    info_model = json.loads(cat.info_model_json) if cat.info_model_json else []
    attr_map = {item["name"]: item.get("label", item["name"]) for item in info_model}
    
    products = db.query(Product).filter(Product.category_id == cat_id).all()
    
    data = []
    for p in products:
        row = {
            "ID (Не менять!)": p.id,
            "Название": p.name,
            "Артикул": p.sku,
            "Цена": p.price,
            "Бренд": p.manufacturer.name if p.manufacturer else "",
            "Краткое описание": p.shortDesc,
            "Полное описание": p.fullDesc,
        }
        
        # Распаковываем динамические атрибуты в столбцы
        attrs = json.loads(p.attributes_json) if p.attributes_json else {}
        for k, label in attr_map.items():
            row[label] = attrs.get(k, "")
            
        data.append(row)
        
    # Если товаров нет, создаем пустую строку-шаблон с правильными столбцами
    if not data:
        empty_row = {"ID (Не менять!)": "", "Название": "", "Артикул": "", "Цена": "", "Бренд": "", "Краткое описание": "", "Полное описание": ""}
        for label in attr_map.values():
            empty_row[label] = ""
        data.append(empty_row)

    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Товары')
    
    output.seek(0)
    db.close()
    
    return StreamingResponse(
        output, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=Category_{cat_id}_Products.xlsx"}
    )

# 2. МАРШРУТ: ЗАГРУЗКА EXCEL
@app.post("/api/admin/category/{cat_id}/import")
async def import_category_excel(cat_id: int, file: UploadFile = File(...)):
    contents = await file.read()
    try:
        df = pd.read_excel(BytesIO(contents))
        df = df.fillna("") # Заменяем NaN на пустые строки
    except Exception as e:
        return {"status": "error", "message": "Ошибка чтения файла. Убедитесь, что это .xlsx"}
        
    db = SessionLocal()
    cat = db.query(Category).filter(Category.id == cat_id).first()
    
    info_model = json.loads(cat.info_model_json) if cat.info_model_json else []
    # Карта для обратного перевода русских названий столбцов в английские ключи базы
    label_to_key = {item.get("label", item["name"]): item["name"] for item in info_model}
    
    added_count = 0
    updated_count = 0
    
    for index, row in df.iterrows():
        name = str(row.get("Название", "")).strip()
        if not name:
            continue # Пропускаем пустые строки
        
        # Обработка ID (Pandas может сделать его float, например 101.0)
        p_id_raw = row.get("ID (Не менять!)", "")
        p_id = None
        if p_id_raw != "":
            try: p_id = int(float(p_id_raw))
            except: pass
        
        # Обработка Бренда (Авто-создание, если нет)
        brand_name = str(row.get("Бренд", "")).strip()
        manuf_id = None
        if brand_name:
            manuf = db.query(Manufacturer).filter(Manufacturer.name == brand_name).first()
            if not manuf:
                manuf = Manufacturer(name=brand_name)
                db.add(manuf)
                db.flush() # Получаем ID без полного коммита
            manuf_id = manuf.id
        
        # Собираем динамические атрибуты
        attrs = {}
        for label, key in label_to_key.items():
            if label in row:
                val = str(row[label]).strip()
                if val: attrs[key] = val
                
        # Обновляем или создаем товар
        if p_id:
            product = db.query(Product).filter(Product.id == p_id).first()
            if product:
                product.name = name
                product.sku = str(row.get("Артикул", ""))
                product.price = str(row.get("Цена", ""))
                product.manufacturer_id = manuf_id
                product.shortDesc = str(row.get("Краткое описание", ""))
                product.fullDesc = str(row.get("Полное описание", ""))
                product.attributes_json = json.dumps(attrs, ensure_ascii=False)
                updated_count += 1
        else:
            product = Product(
                name=name,
                sku=str(row.get("Артикул", "")),
                price=str(row.get("Цена", "")),
                category_id=cat_id,
                manufacturer_id=manuf_id,
                shortDesc=str(row.get("Краткое описание", "")),
                fullDesc=str(row.get("Полное описание", "")),
                attributes_json=json.dumps(attrs, ensure_ascii=False)
            )
            db.add(product)
            added_count += 1
            
    db.commit()
    db.close()
    return {"status": "ok", "message": f"Успешно! Добавлено: {added_count}, Обновлено: {updated_count}"}

# 3. МАРШРУТ: ВИЗУАЛЬНАЯ ПАНЕЛЬ (ДАШБОРД)
@app.get("/admin-excel", response_class=HTMLResponse)
def admin_excel_dashboard():
    db = SessionLocal()
    categories = db.query(Category).all()
    # Собираем красивое дерево для селекта, чтобы было понятно, где подкатегория
    options = "".join([f'<option value="{c.id}">{c.name} (ID: {c.id})</option>' for c in categories])
    db.close()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Импорт / Экспорт Excel</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 40px; background: #f4f6f9; display: flex; justify-content: center; }}
            .card {{ background: #fff; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); width: 100%; max-width: 500px; }}
            h2 {{ color: #2c3e50; margin-top: 0; text-align: center; }}
            label {{ font-weight: bold; color: #34495e; display: block; margin-bottom: 8px; }}
            select, input[type="file"] {{ width: 100%; padding: 12px; margin-bottom: 20px; border: 1px solid #bdc3c7; border-radius: 6px; box-sizing: border-box; }}
            button {{ width: 100%; padding: 12px; border: none; font-size: 16px; font-weight: bold; border-radius: 6px; cursor: pointer; transition: 0.2s; }}
            .btn-blue {{ background: #3498db; color: white; margin-bottom: 10px; }}
            .btn-blue:hover {{ background: #2980b9; }}
            .btn-green {{ background: #2ecc71; color: white; }}
            .btn-green:hover {{ background: #27ae60; }}
            .divider {{ height: 1px; background: #ecf0f1; margin: 25px 0; }}
            #status {{ margin-top: 15px; font-weight: bold; text-align: center; color: #e67e22; }}
        </style> </head>
    <body>
        <div class="card">
            <h2>📊 Менеджер Excel</h2>
            <label>1. Выберите категорию:</label>
            <select id="catSelect">
                <option value="">-- Нажмите для выбора --</option>
                {options}
            </select>
            
            <div class="divider"></div>
            
            <label>2. Выгрузить данные:</label>
            <button class="btn-blue" onclick="downloadExcel()">📥 Скачать шаблон с товарами</button>
            <p style="font-size: 12px; color: #7f8c8d; margin-top: -5px; margin-bottom: 20px;">* Скачает все товары категории со столбцами из её инфомодели.</p>
            
            <div class="divider"></div>
            
            <label>3. Загрузить изменения:</label>
            <input type="file" id="excelFile" accept=".xlsx">
            <button class="btn-green" onclick="uploadExcel()">📤 Синхронизировать с базой</button>
            <div id="status"></div>
        </div>

        <script>
            function downloadExcel() {{
                const catId = document.getElementById('catSelect').value;
                if(!catId) return alert('Пожалуйста, выберите категорию!');
                window.location.href = `/api/admin/category/${{catId}}/export`;
            }}
            
            async function uploadExcel() {{
                const catId = document.getElementById('catSelect').value;
                const fileInput = document.getElementById('excelFile');
                
                if(!catId) return alert('Пожалуйста, выберите категорию!');
                if(fileInput.files.length === 0) return alert('Пожалуйста, выберите файл!');
                
                const formData = new FormData();
                formData.append('file', fileInput.files[0]);
                
                document.getElementById('status').style.color = '#e67e22';
                document.getElementById('status').innerHTML = '⏳ Обработка данных...';
                
                try {{
                    const response = await fetch(`/api/admin/category/${{catId}}/import`, {{
                        method: 'POST',
                        body: formData
                    }});
                    const result = await response.json();
                    if(response.ok && result.status === "ok") {{
                        document.getElementById('status').style.color = '#27ae60';
                        document.getElementById('status').innerHTML = '✅ ' + result.message;
                        fileInput.value = '';
                    }} else {{
                        document.getElementById('status').style.color = '#c0392b';
                        document.getElementById('status').innerHTML = '❌ Ошибка: ' + (result.message || 'Неизвестная ошибка');
                    }}
                }} catch(e) {{
                    document.getElementById('status').style.color = '#c0392b';
                    document.getElementById('status').innerHTML = '❌ Ошибка сети при отправке файла!';
                }}
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)