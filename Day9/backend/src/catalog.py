"""
E-commerce catalog and order management following ACP-inspired patterns.
"""
import json
from datetime import datetime
from typing import Optional
from copy import deepcopy

# Product Catalog (ACP-inspired)
PRODUCTS = [
    {
        "id": "mug-001",
        "name": "Stoneware Coffee Mug",
        "description": "Classic ceramic coffee mug with a smooth finish",
        "price": 800,
        "currency": "INR",
        "category": "mug",
        "color": "white",
        "stock": 50,
    },
    {
        "id": "mug-002",
        "name": "Travel Coffee Mug",
        "description": "Insulated stainless steel travel mug",
        "price": 1200,
        "currency": "INR",
        "category": "mug",
        "color": "black",
        "stock": 30,
    },
    {
        "id": "tshirt-001",
        "name": "Cotton T-Shirt",
        "description": "Comfortable 100% cotton t-shirt",
        "price": 900,
        "currency": "INR",
        "category": "clothing",
        "sizes": ["S", "M", "L", "XL"],
        "color": "blue",
        "stock": 100,
    },
    {
        "id": "tshirt-002",
        "name": "Premium T-Shirt",
        "description": "Premium quality organic cotton t-shirt",
        "price": 1500,
        "currency": "INR",
        "category": "clothing",
        "sizes": ["S", "M", "L", "XL"],
        "color": "white",
        "stock": 75,
    },
    {
        "id": "hoodie-001",
        "name": "Black Hoodie",
        "description": "Warm fleece hoodie with kangaroo pocket",
        "price": 2500,
        "currency": "INR",
        "category": "clothing",
        "sizes": ["S", "M", "L", "XL"],
        "color": "black",
        "stock": 40,
    },
    {
        "id": "hoodie-002",
        "name": "Gray Hoodie",
        "description": "Comfortable zip-up hoodie",
        "price": 2800,
        "currency": "INR",
        "category": "clothing",
        "sizes": ["S", "M", "L", "XL"],
        "color": "gray",
        "stock": 35,
    },
    {
        "id": "bottle-001",
        "name": "Water Bottle",
        "description": "Stainless steel water bottle, 1L capacity",
        "price": 600,
        "currency": "INR",
        "category": "accessories",
        "color": "silver",
        "stock": 60,
    },
    {
        "id": "cap-001",
        "name": "Baseball Cap",
        "description": "Adjustable baseball cap with embroidered logo",
        "price": 500,
        "currency": "INR",
        "category": "accessories",
        "color": "navy",
        "stock": 80,
    },
]

# Order storage (in-memory for now)
ORDERS = []


def list_products(filters: Optional[dict] = None) -> list[dict]:
    """
    List products with optional filtering.
    
    Args:
        filters: Optional dict with keys like:
            - category: str
            - max_price: int
            - color: str
            - search: str (search in name/description)
    
    Returns:
        List of product dictionaries
    """
    if filters is None:
        return deepcopy(PRODUCTS)
    
    results = PRODUCTS.copy()
    
    # Filter by category
    if "category" in filters:
        category = filters["category"].lower()
        results = [p for p in results if p.get("category", "").lower() == category]
    
    # Filter by max price
    if "max_price" in filters:
        max_price = filters["max_price"]
        results = [p for p in results if p.get("price", 0) <= max_price]
    
    # Filter by color
    if "color" in filters:
        color = filters["color"].lower()
        results = [p for p in results if p.get("color", "").lower() == color]
    
    # Search in name/description
    if "search" in filters:
        search_term = filters["search"].lower()
        results = [
            p for p in results
            if search_term in p.get("name", "").lower()
            or search_term in p.get("description", "").lower()
        ]
    
    return deepcopy(results)


def get_product_by_id(product_id: str) -> Optional[dict]:
    """Get a single product by ID."""
    for product in PRODUCTS:
        if product["id"] == product_id:
            return deepcopy(product)
    return None


def create_order(line_items: list[dict], customer_info: Optional[dict] = None) -> dict:
    """
    Create an order from line items.
    
    Args:
        line_items: List of dicts with keys:
            - product_id: str
            - quantity: int
            - size: str (optional, for clothing)
        customer_info: Optional dict with customer details
    
    Returns:
        Order dictionary with id, items, total, currency, created_at
    """
    # Generate order ID
    order_id = f"ORD-{len(ORDERS) + 1:05d}"
    
    # Process line items
    order_items = []
    total = 0
    currency = "INR"
    
    for item in line_items:
        product_id = item.get("product_id")
        quantity = item.get("quantity", 1)
        size = item.get("size")
        
        if not product_id:
            continue
        
        # Look up product
        product = get_product_by_id(product_id)
        if not product:
            continue
        
        # Calculate item total
        item_total = product["price"] * quantity
        total += item_total
        
        # Build order item
        order_item = {
            "product_id": product_id,
            "product_name": product["name"],
            "quantity": quantity,
            "price": product["price"],
            "item_total": item_total,
        }
        
        if size:
            order_item["size"] = size
        
        order_items.append(order_item)
    
    # Create order object
    order = {
        "id": order_id,
        "items": order_items,
        "total": total,
        "currency": currency,
        "status": "confirmed",
        "created_at": datetime.now().isoformat(),
    }
    
    if customer_info:
        order["customer"] = customer_info
    
    # Store order
    ORDERS.append(order)
    
    return deepcopy(order)


def get_last_order() -> Optional[dict]:
    """Get the most recent order."""
    if not ORDERS:
        return None
    return deepcopy(ORDERS[-1])


def get_order_by_id(order_id: str) -> Optional[dict]:
    """Get an order by ID."""
    for order in ORDERS:
        if order["id"] == order_id:
            return deepcopy(order)
    return None


def get_all_orders() -> list[dict]:
    """Get all orders."""
    return deepcopy(ORDERS)


def update_order(order_id: str, line_items: list[dict], customer_info: Optional[dict] = None) -> Optional[dict]:
    """
    Update an existing order's line items and totals.

    Args:
        order_id: ID of the order to update
        line_items: New list of line items (same shape as create_order)
        customer_info: Optional customer details to merge

    Returns:
        The updated order dict or None if not found
    """
    for idx, order in enumerate(ORDERS):
        if order.get("id") == order_id:
            # Rebuild items and total
            order_items = []
            total = 0
            for item in line_items:
                product_id = item.get("product_id")
                quantity = item.get("quantity", 1)
                size = item.get("size")

                if not product_id:
                    continue

                product = get_product_by_id(product_id)
                if not product:
                    continue

                item_total = product["price"] * quantity
                total += item_total

                order_item = {
                    "product_id": product_id,
                    "product_name": product["name"],
                    "quantity": quantity,
                    "price": product["price"],
                    "item_total": item_total,
                }
                if size:
                    order_item["size"] = size
                order_items.append(order_item)

            # Update order fields
            updated_order = deepcopy(order)
            updated_order["items"] = order_items
            updated_order["total"] = total
            if customer_info:
                updated_order["customer"] = customer_info
            # mark updated time
            updated_order["updated_at"] = datetime.now().isoformat()

            ORDERS[idx] = updated_order
            return deepcopy(updated_order)

    return None
