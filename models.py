from sqlalchemy import Column, String, Text, Integer, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

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

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    
    info_model_json = Column(Text, default="[]") 
    
    # ВОТ ЗДЕСЬ ДОБАВЛЯЕМ post_update=True
    parent = relationship("Category", remote_side="Category.id", backref="subcategories", post_update=True)
    products = relationship("Product", back_populates="category")
    
    def __str__(self):
        return self.name

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    
    # 1. ОБЩИЕ ПОЛЯ
    name = Column(String)
    sku = Column(String)
    price = Column(String)
    manufacturer_id = Column(Integer, ForeignKey("manufacturers.id"), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    
    # 2. МЕДИА И ДОКУМЕНТЫ
    images_json = Column(Text, default="[]") 
    documents_json = Column(Text, default="[]")
    shortDesc = Column(Text)
    fullDesc = Column(Text)
    
    # 3. СПЕЦИФИЧЕСКИЕ ХАРАКТЕРИСТИКИ
    attributes_json = Column(Text, default="{}") 
    
    manufacturer = relationship("Manufacturer", back_populates="products")
    category = relationship("Category", back_populates="products")