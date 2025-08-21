# Filename: app/models.py
# Approx lines modified: ~1-20 (imports), ~30-50 (Conversation model), ~60-80 (Product model)
from sqlalchemy import Column, Integer, String, Index
from app.database import ChatBase, CatalogBase  # [CHANGED] Import separate Bases

class Conversation(ChatBase):  # [CHANGED] Use ChatBase for postgres DB
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String)
    message = Column(String)
    response = Column(String)

    def __repr__(self) -> str:
        return f"<Conversation id={self.id} sender={self.sender!r}>"

# ------------------ NEW MODEL ------------------ #
class Product(CatalogBase):  # [CHANGED] Use CatalogBase for my_catalog_db
    """
    ... (rest unchanged)
    """
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    anchor = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    price_cents = Column(Integer, nullable=False, default=0)
    stock = Column(Integer, nullable=False, default=0)
    image_url = Column(String, nullable=True)

    def __repr__(self) -> str:
        return f"<Product id={self.id} anchor={self.anchor!r} name={self.name!r}>"