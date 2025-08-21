# Filename: app/models.py
# Approx lines modified: ~1-80
# Reason:
#  - ADD Product model to store catalog info (anchor → name, price, stock, product image URL)
#  - Keep Conversation unchanged

from sqlalchemy import Column, Integer, String, Index  # [ADDED Index for fast anchor lookup]
from app.database import Base

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String)
    message = Column(String)
    response = Column(String)

    def __repr__(self) -> str:
        return f"<Conversation id={self.id} sender={self.sender!r}>"

# ------------------ NEW MODEL ------------------ #
class Product(Base):  # [ADDED ~35]
    """
    Store items we can sell over WhatsApp.
    - anchor: normalized keyword from HARDWARE_ANCHORS (e.g., 'martillo')
    - name: human-friendly product name
    - price_cents: integer cents to avoid float errors
    - stock: integer available units
    - image_url: public URL to product picture (we will attach this in WA)
    """
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    anchor = Column(String, index=True, nullable=False)        # e.g., "martillo"
    name = Column(String, nullable=False)                      # e.g., "Martillo de uña 16oz"
    price_cents = Column(Integer, nullable=False, default=0)   # store cents
    stock = Column(Integer, nullable=False, default=0)         # available units
    image_url = Column(String, nullable=True)                  # public URL for WA media

    def __repr__(self) -> str:  # [ADDED]
        return f"<Product id={self.id} anchor={self.anchor!r} name={self.name!r}>"

# (Optional) For heavier catalogs you'd add uniqueness constraints, SKUs, etc.
# Index on anchor already created via index=True above.
