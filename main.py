from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, String, Text, Integer, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from wtforms import StringField, FileField
from markupsafe import Markup
from PIL import Image
import json
import os
import time
import io
import uuid

SQLALCHEMY_DATABASE_URL = "sqlite:///./profisfera.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Manufacturer(Base):
    __tablename__ = "manufacturers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    logo = Column(String)
    website = Column(String)
    description = Column(Text)
    products = relationship("Product", back_populates="manufacturer")

    def __str__(self):
        return self.name

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    price = Column(String)
    images_json = Column(Text, default="[]") 
    shortDesc = Column(Text)
    fullDesc = Column(Text)
    other_data = Column(Text)
    manufacturer_id = Column(Integer, ForeignKey("manufacturers.id"))
    manufacturer = relationship("Manufacturer", back_populates="products")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Профисфера API")

os.makedirs("static/products", exist_ok=True)
os.makedirs("static/manufacturers", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username, password = form["username"], form["password"]
        if username == "prplstn" and password == "Qwertyjeff12":
            request.session.update({"token": "admin_token"})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("token")
        if not token:
            return False
        return True

authentication_backend = AdminAuth(secret_key="secret_key_123")

# ==========================================
# МАГИЯ DRAG & DROP ГАЛЕРЕИ (JAVASCRIPT)
# ==========================================
class DragDropGalleryWidget:
    def __call__(self, field, **kwargs):
        existing_data = field.object_data if field.object_data else "[]"
        
        # HTML + JS код виджета
        html = """
        <div id="custom-gallery-container" style="border: 2px dashed #ccc; padding: 15px; border-radius: 8px; background: #fafafa;">
            <div id="gallery-preview" style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 15px; min-height: 50px;"></div>
            
            <input type="file" id="new_images_input" name="new_images" multiple accept="image/*" style="display:none;">
            
            <button type="button" onclick="document.getElementById('new_images_input').click()" style="padding: 10px 20px; background: #2ecc71; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 14px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">+ Добавить изображения</button>
            <span style="font-size: 12px; color: #7f8c8d; margin-left: 10px;">(Можно менять порядок мышкой)</span>
            
            <input type="hidden" id="__FIELD_ID__" name="__FIELD_NAME__" value='__EXISTING_DATA__'>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/sortablejs@latest/Sortable.min.js"></script>
        
        <script>
            (function() {
                const container = document.getElementById('gallery-preview');
                const fileInput = document.getElementById('new_images_input');
                const hiddenInput = document.getElementById('__FIELD_ID__');
                
                let items = [];
                try { items = JSON.parse(hiddenInput.value || '[]'); } catch(e) {}
                
                // Превращаем старые картинки во внутренний формат
                items = items.map(img => ({ type: 'old', orig: img.orig, thumb: img.thumb, id: Math.random().toString(36).substr(2, 9) }));
                
                let dt = new DataTransfer(); // Хранилище браузера для новых файлов

                function render() {
                    container.innerHTML = '';
                    items.forEach((item) => {
                        const div = document.createElement('div');
                        div.style.cssText = 'width: 120px; height: 120px; position: relative; border-radius: 6px; overflow: hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.2); cursor: grab; background: #fff;';
                        
                        const img = document.createElement('img');
                        img.style.cssText = 'width: 100%; height: 100%; object-fit: cover;';
                        img.src = item.type === 'old' ? item.thumb : item.previewUrl;
                        
                        const delBtn = document.createElement('div');
                        delBtn.innerHTML = '×';
                        delBtn.style.cssText = 'position: absolute; top: 5px; right: 5px; background: rgba(255,0,0,0.8); color: white; width: 24px; height: 24px; text-align: center; line-height: 22px; border-radius: 50%; cursor: pointer; font-weight: bold; font-size: 16px; transition: 0.2s; z-index: 10;';
                        delBtn.onmouseover = () => delBtn.style.background = 'rgba(255,0,0,1)';
                        delBtn.onmouseout = () => delBtn.style.background = 'rgba(255,0,0,0.8)';
                        delBtn.onclick = () => removeItem(item.id);
                        
                        div.appendChild(img);
                        div.appendChild(delBtn);
                        container.appendChild(div);
                    });
                    updateHidden();
                }

                function removeItem(id) {
                    const itemToRemove = items.find(i => i.id === id);
                    if (itemToRemove && itemToRemove.type === 'new') {
                        let newDt = new DataTransfer();
                        for (let i = 0; i < dt.files.length; i++) {
                            if (dt.files[i].name !== itemToRemove.name) newDt.items.add(dt.files[i]);
                        }
                        dt = newDt;
                        fileInput.files = dt.files;
                    }
                    items = items.filter(i => i.id !== id);
                    render();
                }

                function updateHidden() {
                    const exportData = items.map(item => {
                        if (item.type === 'old') return { type: 'old', orig: item.orig, thumb: item.thumb };
                        return { type: 'new', name: item.name };
                    });
                    hiddenInput.value = JSON.stringify(exportData);
                }

                fileInput.addEventListener('change', (e) => {
                    const newFiles = Array.from(e.target.files);
                    newFiles.forEach(file => {
                        if (items.some(i => i.type === 'new' && i.name === file.name)) return;
                        dt.items.add(file);
                        
                        // Читаем файл "на лету" для превью
                        const reader = new FileReader();
                        reader.onload = (ev) => {
                            items.push({ type: 'new', name: file.name, previewUrl: ev.target.result, id: Math.random().toString(36).substr(2, 9) });
                            render();
                        };
                        reader.readAsDataURL(file);
                    });
                    fileInput.files = dt.files;
                });

                // Инициализация Drag&Drop
                new Sortable(container, {
                    animation: 150,
                    onEnd: function (evt) {
                        const itemEl = items.splice(evt.oldIndex, 1)[0];
                        items.splice(evt.newIndex, 0, itemEl);
                        updateHidden();
                    }
                });

                render();
            })();
        </script>
        """
        
        # Подставляем реальные ID и данные
        html = html.replace("__FIELD_ID__", field.id).replace("__FIELD_NAME__", field.name)
        safe_data = existing_data.replace("'", "&#39;")
        html = html.replace("__EXISTING_DATA__", safe_data)
        
        return Markup(html)

class DragDropGalleryField(StringField):
    widget = DragDropGalleryWidget()
# ==========================================

class ManufacturerAdmin(ModelView, model=Manufacturer):
    column_list = [Manufacturer.id, Manufacturer.logo, Manufacturer.name, Manufacturer.website]
    column_sortable_list = [Manufacturer.id, Manufacturer.name]
    form_columns = [Manufacturer.name, Manufacturer.logo, Manufacturer.website, Manufacturer.description]
    name = "Производитель"
    icon = "fa-solid fa-industry"
    create_template = "custom_create.html"
    edit_template = "custom_edit.html"
    form_overrides = dict(logo=FileField)

    column_formatters = {
        Manufacturer.logo: lambda m, a: Markup(f'<img src="{m.logo}" style="max-height: 40px;">') if m.logo else ""
    }

    async def on_model_change(self, data, model, is_created, request):
        if "logo" in data:
            file = data["logo"]
            if hasattr(file, "filename") and file.filename:
                filename = f"{int(time.time())}_{file.filename.replace(' ', '_')}"
                filepath = f"static/manufacturers/{filename}"
                content = await file.read()
                with open(filepath, "wb") as f:
                    f.write(content)
                data["logo"] = f"/{filepath}"
            else:
                data.pop("logo", None)

class ProductAdmin(ModelView, model=Product):
    column_list = [Product.id, Product.images_json, Product.name, Product.manufacturer, Product.price]
    column_sortable_list = [Product.id, Product.name, Product.price]
    column_searchable_list = [Product.name]
    column_details_exclude_list = [Product.other_data]
    form_columns = [Product.id, Product.name, Product.manufacturer, Product.price, Product.images_json, Product.shortDesc, Product.fullDesc]
    name = "Товар"
    icon = "fa-solid fa-box"
    create_template = "custom_create.html"
    edit_template = "custom_edit.html"

    # Привязываем наш новый магический виджет
    form_overrides = dict(images_json=DragDropGalleryField)

    column_formatters = {
        Product.images_json: lambda m, a: Markup(f'<img src="{json.loads(m.images_json)[0]["thumb"]}" style="max-height: 40px;">') if m.images_json and json.loads(m.images_json) else ""
    }

    async def on_model_change(self, data, model, is_created, request):
        if "images_json" in data:
            # Получаем от виджета JSON с порядком: [старое фото, новое фото, старое фото...]
            gallery_order_str = data["images_json"]
            
            form = await request.form()
            new_files = form.getlist("new_images")
            new_files_map = {f.filename: f for f in new_files if f.filename}
            
            try:
                gallery_order = json.loads(gallery_order_str)
            except:
                gallery_order = []
                
            final_images = []
            
            # Собираем финальный массив картинок строго в том порядке, как указал пользователь
            for item in gallery_order:
                if item.get("type") == "old":
                    # Если фото было загружено ранее, просто оставляем пути к нему
                    final_images.append({"orig": item["orig"], "thumb": item["thumb"]})
                
                elif item.get("type") == "new":
                    # Если это новое фото, сохраняем его на диск
                    file = new_files_map.get(item["name"])
                    if file:
                        content = await file.read()
                        unique_id = uuid.uuid4().hex[:8] 
                        safe_name = file.filename.replace(' ', '_')
                        
                        path_orig = f"static/products/{unique_id}_orig_{safe_name}"
                        path_thumb = f"static/products/{unique_id}_thumb_{safe_name}"
                        
                        with open(path_orig, "wb") as f:
                            f.write(content)
                            
                        try:
                            img = Image.open(io.BytesIO(content))
                            if img.mode != 'RGB':
                                img = img.convert('RGB')
                            img.thumbnail((400, 400))
                            img.save(path_thumb, format="JPEG", quality=85)
                            
                            final_images.append({"orig": f"/{path_orig}", "thumb": f"/{path_thumb}"})
                        except Exception as e:
                            print(f"Ошибка картинки: {e}")
                            
            data["images_json"] = json.dumps(final_images)

admin = Admin(app, engine, authentication_backend=authentication_backend, templates_dir="templates")
admin.add_view(ManufacturerAdmin)
admin.add_view(ProductAdmin)

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
        item["brand"] = p.manufacturer.name if p.manufacturer else "Без бренда"
        item["price"] = p.price
        
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
