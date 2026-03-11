import json
import time
import io
import uuid
from PIL import Image
from markupsafe import Markup
from wtforms import StringField, FileField
from sqladmin import ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from models import Manufacturer, Product

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

# --- УМНЫЙ ВИДЖЕТ DRAG & DROP ---
class DragDropGalleryWidget:
    def __call__(self, field, **kwargs):
        existing_data = field.object_data if field.object_data else "[]"
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
                items = items.map(img => ({ type: 'old', orig: img.orig, thumb: img.thumb, id: Math.random().toString(36).substr(2, 9) }));
                let dt = new DataTransfer();

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
                        delBtn.onclick = () => removeItem(item.id);
                        div.appendChild(img); div.appendChild(delBtn); container.appendChild(div);
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
                        dt = newDt; fileInput.files = dt.files;
                    }
                    items = items.filter(i => i.id !== id);
                    render();
                }

                function updateHidden() {
                    hiddenInput.value = JSON.stringify(items.map(item => {
                        if (item.type === 'old') return { type: 'old', orig: item.orig, thumb: item.thumb };
                        return { type: 'new', name: item.name };
                    }));
                }

                fileInput.addEventListener('change', (e) => {
                    Array.from(e.target.files).forEach(file => {
                        if (items.some(i => i.type === 'new' && i.name === file.name)) return;
                        dt.items.add(file);
                        const reader = new FileReader();
                        reader.onload = (ev) => {
                            items.push({ type: 'new', name: file.name, previewUrl: ev.target.result, id: Math.random().toString(36).substr(2, 9) });
                            render();
                        };
                        reader.readAsDataURL(file);
                    });
                    fileInput.files = dt.files;
                });

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
        html = html.replace("__FIELD_ID__", field.id).replace("__FIELD_NAME__", field.name)
        safe_data = existing_data.replace("'", "&#39;")
        html = html.replace("__EXISTING_DATA__", safe_data)
        return Markup(html)

class DragDropGalleryField(StringField):
    widget = DragDropGalleryWidget()

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
    form_overrides = dict(images_json=DragDropGalleryField)

    column_formatters = {
        Product.images_json: lambda m, a: Markup(f'<img src="{json.loads(m.images_json)[0]["thumb"]}" style="max-height: 40px;">') if m.images_json and json.loads(m.images_json) else ""
    }

    async def on_model_change(self, data, model, is_created, request):
        if "images_json" in data:
            gallery_order_str = data["images_json"]
            form = await request.form()
            new_files = form.getlist("new_images")
            new_files_map = {f.filename: f for f in new_files if f.filename}
            
            try: gallery_order = json.loads(gallery_order_str)
            except: gallery_order = []
                
            final_images = []
            for item in gallery_order:
                if item.get("type") == "old":
                    final_images.append({"orig": item["orig"], "thumb": item["thumb"]})
                elif item.get("type") == "new":
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
                            if img.mode != 'RGB': img = img.convert('RGB')
                            img.thumbnail((400, 400))
                            img.save(path_thumb, format="JPEG", quality=85)
                            final_images.append({"orig": f"/{path_orig}", "thumb": f"/{path_thumb}"})
                        except Exception as e: print(f"Ошибка картинки: {e}")
                            
            data["images_json"] = json.dumps(final_images)