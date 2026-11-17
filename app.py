import sqlite3
from decimal import Decimal, InvalidOperation

from flask import Flask, jsonify, render_template, request
from database import get_connection

app = Flask(__name__)


# ---------- BOOK HELPERS ----------

def get_books():
    connection = get_connection()

    try:
        rows = connection.execute("""
            SELECT
                books.id,
                books.title,
                books.author,
                books.isbn,
                books.category_id,
                categories.name AS category,
                books.price_cents,
                books.stock
            FROM books
            JOIN categories ON books.category_id = categories.id
            ORDER BY books.title
        """).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


def validate_book(data):
    if not isinstance(data, dict):
        raise ValueError("Please send valid book data.")

    text_fields = {}

    for field in ("title", "author", "isbn"):
        value = data.get(field)

        if not isinstance(value, str) or not value.strip():
            raise ValueError("Title, author, and ISBN are required.")

        text_fields[field] = value.strip()

    try:
        price = Decimal(str(data.get("price", "")))
        stock_text = str(data.get("stock", ""))
        category_text = str(data.get("category_id", ""))

        if not price.is_finite() or price < 0 or price > 1000000:
            raise ValueError

        cents = price * 100

        if cents != cents.to_integral_value():
            raise ValueError

        if not stock_text.isdecimal() or not category_text.isdecimal():
            raise ValueError

        stock = int(stock_text)
        category_id = int(category_text)

        if stock > 1000000:
            raise ValueError

        if not 1 <= category_id <= 9223372036854775807:
            raise ValueError

    except (InvalidOperation, ValueError, OverflowError):
        raise ValueError(
            "Choose a valid category. Enter a price from 0 to 1000000 "
            "with up to 2 decimal places, and whole-number stock "
            "from 0 to 1000000."
        ) from None

    return (
        text_fields["title"],
        text_fields["author"],
        text_fields["isbn"],
        category_id,
        int(cents),
        stock
    )


# ---------- BOOK PAGE ----------

@app.get("/")
def home():
    connection = get_connection()

    try:
        categories = connection.execute("""
            SELECT id, name
            FROM categories
            ORDER BY name
        """).fetchall()

    finally:
        connection.close()

    return render_template(
        "index.html",
        books=get_books(),
        categories=categories
    )


# ---------- BOOK APIs ----------

# READ: View all books.
@app.get("/api/books")
def books_api():
    return jsonify(get_books())


# CREATE: Add a new book.
@app.post("/api/books")
def add_book():
    try:
        values = validate_book(request.get_json(silent=True))
    except ValueError as error:
        return jsonify(error=str(error)), 400

    connection = get_connection()

    try:
        with connection:
            category = connection.execute(
                "SELECT id FROM categories WHERE id = ?",
                (values[3],)
            ).fetchone()

            if category is None:
                return jsonify(
                    error="Please choose an existing category."
                ), 400

            cursor = connection.execute("""
                INSERT INTO books
                (title, author, isbn, category_id, price_cents, stock)
                VALUES (?, ?, ?, ?, ?, ?)
            """, values)

            book_id = cursor.lastrowid

        return jsonify(
            message="Book added successfully!",
            id=book_id
        ), 201

    except sqlite3.IntegrityError:
        return jsonify(
            error="Unable to save. This ISBN may already exist."
        ), 409

    finally:
        connection.close()


# UPDATE: Edit an existing book.
@app.put("/api/books/<int:book_id>")
def update_book(book_id):
    try:
        values = validate_book(request.get_json(silent=True))
    except ValueError as error:
        return jsonify(error=str(error)), 400

    connection = get_connection()

    try:
        with connection:
            existing_book = connection.execute(
                "SELECT id FROM books WHERE id = ?",
                (book_id,)
            ).fetchone()

            if existing_book is None:
                return jsonify(error="Book not found."), 404

            category = connection.execute(
                "SELECT id FROM categories WHERE id = ?",
                (values[3],)
            ).fetchone()

            if category is None:
                return jsonify(
                    error="Please choose an existing category."
                ), 400

            connection.execute("""
                UPDATE books
                SET title = ?,
                    author = ?,
                    isbn = ?,
                    category_id = ?,
                    price_cents = ?,
                    stock = ?
                WHERE id = ?
            """, values + (book_id,))

        return jsonify(message="Book updated successfully!")

    except sqlite3.IntegrityError:
        return jsonify(
            error="Unable to update. This ISBN may already exist."
        ), 409

    finally:
        connection.close()


# DELETE: Remove a book that is not used in an order.
@app.delete("/api/books/<int:book_id>")
def delete_book(book_id):
    connection = get_connection()

    try:
        with connection:
            cursor = connection.execute(
                "DELETE FROM books WHERE id = ?",
                (book_id,)
            )

            if cursor.rowcount == 0:
                return jsonify(error="Book not found."), 404

        return jsonify(message="Book deleted successfully!")

    except sqlite3.IntegrityError:
        return jsonify(
            error="This book belongs to an order and cannot be deleted."
        ), 409

    finally:
        connection.close()


# ---------- CUSTOMER HELPER ----------

def get_customers():
    connection = get_connection()

    try:
        rows = connection.execute("""
            SELECT id, name, email
            FROM customers
            ORDER BY name
        """).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


# ---------- CUSTOMER PAGE ----------

@app.get("/customers")
def customers_page():
    return render_template(
        "customers.html",
        customers=get_customers()
    )


# ---------- CUSTOMER APIs ----------

# READ: View all customers.
@app.get("/api/customers")
def customers_api():
    return jsonify(get_customers())


# CREATE: Add a new customer.
@app.post("/api/customers")
def add_customer():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(
            error="Please send valid customer data."
        ), 400

    name = data.get("name")
    email = data.get("email")

    if not isinstance(name, str) or not name.strip():
        return jsonify(
            error="Customer name is required."
        ), 400

    if not isinstance(email, str):
        return jsonify(
            error="A valid email is required."
        ), 400

    name = name.strip()
    email = email.strip().lower()

    parts = email.split("@")

    if (
        len(parts) != 2
        or not parts[0]
        or "." not in parts[1]
        or parts[1].startswith(".")
        or parts[1].endswith(".")
        or any(character.isspace() for character in email)
    ):
        return jsonify(
            error="Enter a valid email address."
        ), 400

    connection = get_connection()

    try:
        with connection:
            cursor = connection.execute("""
                INSERT INTO customers (name, email)
                VALUES (?, ?)
            """, (name, email))

            customer_id = cursor.lastrowid

        return jsonify(
            message="Customer added successfully!",
            id=customer_id
        ), 201

    except sqlite3.IntegrityError:
        return jsonify(
            error="A customer with this email already exists."
        ), 409

    finally:
        connection.close()
        # ---------- ORDER HELPER ----------

def get_orders():
    connection = get_connection()

    try:
        rows = connection.execute("""
            SELECT
                orders.id,
                customers.name AS customer_name,
                orders.created_at,
                orders.status,
                SUM(
                    order_items.quantity *
                    order_items.unit_price_cents
                ) AS total_cents
            FROM orders
            JOIN customers ON customers.id = orders.customer_id
            JOIN order_items ON order_items.order_id = orders.id
            GROUP BY
                orders.id,
                customers.name,
                orders.created_at,
                orders.status
            ORDER BY orders.id DESC
        """).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


# ---------- ORDER PAGE ----------

@app.get("/orders")
def orders_page():
    return render_template(
        "orders.html",
        books=get_books(),
        customers=get_customers(),
        orders=get_orders()
    )


# ---------- ORDER APIs ----------

@app.get("/api/orders")
def orders_api():
    return jsonify(get_orders())


# Place an order containing one or more books.
@app.post("/api/orders")
def create_order():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(error="Please send valid order data."), 400

    customer_id = data.get("customer_id")
    items = data.get("items")

    # Accept positive whole-number IDs and quantities.
    def positive_integer(value):
        text = str(value)

        if not text.isdecimal():
            raise ValueError

        number = int(text)

        if not 1 <= number <= 1000000:
            raise ValueError

        return number

    try:
        customer_id = positive_integer(customer_id)

        if not isinstance(items, list) or not items:
            raise ValueError

        # Combine repeated books into one order item.
        quantities = {}

        for item in items:
            if not isinstance(item, dict):
                raise ValueError

            book_id = positive_integer(item.get("book_id"))
            quantity = positive_integer(item.get("quantity"))

            quantities[book_id] = quantities.get(book_id, 0) + quantity

            if quantities[book_id] > 1000000:
                raise ValueError

    except (ValueError, OverflowError):
        return jsonify(
            error="Choose a customer and at least one book "
                  "with a positive whole-number quantity."
        ), 400

    connection = get_connection()

    try:
        # Lock writes before checking stock.
        connection.execute("BEGIN IMMEDIATE")

        customer = connection.execute(
            "SELECT id FROM customers WHERE id = ?",
            (customer_id,)
        ).fetchone()

        if customer is None:
            return jsonify(error="Customer not found."), 404

        checked_items = []

        for book_id, quantity in quantities.items():
            book = connection.execute("""
                SELECT id, title, price_cents, stock
                FROM books
                WHERE id = ?
            """, (book_id,)).fetchone()

            if book is None:
                return jsonify(error="A selected book no longer exists."), 404

            if quantity > book["stock"]:
                return jsonify(
                    error=f"Not enough stock for {book['title']}. "
                          f"Available: {book['stock']}."
                ), 400

            checked_items.append(
                (book_id, quantity, book["price_cents"])
            )

        cursor = connection.execute(
            "INSERT INTO orders (customer_id) VALUES (?)",
            (customer_id,)
        )

        order_id = cursor.lastrowid
        total_cents = 0

        for book_id, quantity, price_cents in checked_items:
            connection.execute("""
                INSERT INTO order_items
                (order_id, book_id, quantity, unit_price_cents)
                VALUES (?, ?, ?, ?)
            """, (order_id, book_id, quantity, price_cents))

            connection.execute("""
                UPDATE books
                SET stock = stock - ?
                WHERE id = ?
            """, (quantity, book_id))

            total_cents += quantity * price_cents

        connection.commit()

        return jsonify(
            message="Order placed successfully!",
            id=order_id,
            total_cents=total_cents
        ), 201

    except sqlite3.Error:
        connection.rollback()
        app.logger.exception("Unable to place order")

        return jsonify(
            error="Unable to place the order. Please try again."
        ), 500

    finally:
        # Roll back any unfinished transaction before closing.
        if connection.in_transaction:
            connection.rollback()

        connection.close()


# Cancel an order and restore its stock.
@app.post("/api/orders/<int:order_id>/cancel")
def cancel_order(order_id):
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        order = connection.execute(
            "SELECT id, status FROM orders WHERE id = ?",
            (order_id,)
        ).fetchone()

        if order is None:
            return jsonify(error="Order not found."), 404

        if order["status"] == "Cancelled":
            return jsonify(error="This order is already cancelled."), 409

        items = connection.execute("""
            SELECT book_id, quantity
            FROM order_items
            WHERE order_id = ?
        """, (order_id,)).fetchall()

        for item in items:
            connection.execute("""
                UPDATE books
                SET stock = stock + ?
                WHERE id = ?
            """, (item["quantity"], item["book_id"]))

        connection.execute("""
            UPDATE orders
            SET status = 'Cancelled'
            WHERE id = ?
        """, (order_id,))

        connection.commit()

        return jsonify(
            message="Order cancelled. Book stock has been restored."
        )

    except sqlite3.Error:
        connection.rollback()
        app.logger.exception("Unable to cancel order")

        return jsonify(
            error="Unable to cancel the order. Please try again."
        ), 500

    finally:
        if connection.in_transaction:
            connection.rollback()

        connection.close()
        # ---------- DASHBOARD ----------

@app.get("/dashboard")
def dashboard():
    connection = get_connection()

    try:
        inventory = connection.execute("""
            SELECT
                COUNT(*) AS book_titles,
                COALESCE(SUM(stock), 0) AS stock_total
            FROM books
        """).fetchone()

        customer_count = connection.execute("""
            SELECT COUNT(*) AS total
            FROM customers
        """).fetchone()["total"]

        completed_orders = connection.execute("""
            SELECT COUNT(*) AS total
            FROM orders
            WHERE status = 'Completed'
        """).fetchone()["total"]

        sales_cents = connection.execute("""
            SELECT COALESCE(
                SUM(order_items.quantity * order_items.unit_price_cents),
                0
            ) AS total
            FROM order_items
            JOIN orders ON orders.id = order_items.order_id
            WHERE orders.status = 'Completed'
        """).fetchone()["total"]

        low_stock = connection.execute("""
            SELECT title, stock
            FROM books
            WHERE stock < 5
            ORDER BY stock, title
        """).fetchall()

        stats = {
            "book_titles": inventory["book_titles"],
            "stock_total": inventory["stock_total"],
            "customers": customer_count,
            "completed_orders": completed_orders,
            "sales_cents": sales_cents
        }

    finally:
        connection.close()

    return render_template(
        "dashboard.html",
        stats=stats,
        low_stock=low_stock
    )
# ---------- CATEGORY MANAGEMENT ----------

def get_categories():
    connection = get_connection()

    try:
        rows = connection.execute("""
            SELECT
                categories.id,
                categories.name,
                COUNT(books.id) AS book_count
            FROM categories
            LEFT JOIN books ON books.category_id = categories.id
            GROUP BY categories.id, categories.name
            ORDER BY categories.name
        """).fetchall()

        return [dict(row) for row in rows]

    finally:
        connection.close()


@app.get("/categories")
def categories_page():
    return render_template(
        "categories.html",
        categories=get_categories()
    )


@app.get("/api/categories")
def categories_api():
    return jsonify(get_categories())


@app.post("/api/categories")
def add_category():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(error="Please send valid category data."), 400

    name = data.get("name")

    if not isinstance(name, str) or not name.strip():
        return jsonify(error="Category name is required."), 400

    connection = get_connection()

    try:
        with connection:
            cursor = connection.execute(
                "INSERT INTO categories (name) VALUES (?)",
                (name.strip(),)
            )

        return jsonify(
            message="Category added successfully!",
            id=cursor.lastrowid
        ), 201

    except sqlite3.IntegrityError:
        return jsonify(error="This category already exists."), 409

    finally:
        connection.close()


@app.put("/api/categories/<int:category_id>")
def update_category(category_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(error="Please send valid category data."), 400

    name = data.get("name")

    if not isinstance(name, str) or not name.strip():
        return jsonify(error="Category name is required."), 400

    connection = get_connection()

    try:
        with connection:
            cursor = connection.execute("""
                UPDATE categories
                SET name = ?
                WHERE id = ?
            """, (name.strip(), category_id))

            if cursor.rowcount == 0:
                return jsonify(error="Category not found."), 404

        return jsonify(message="Category updated successfully!")

    except sqlite3.IntegrityError:
        return jsonify(error="This category name already exists."), 409

    finally:
        connection.close()


@app.delete("/api/categories/<int:category_id>")
def delete_category(category_id):
    connection = get_connection()

    try:
        with connection:
            cursor = connection.execute(
                "DELETE FROM categories WHERE id = ?",
                (category_id,)
            )

            if cursor.rowcount == 0:
                return jsonify(error="Category not found."), 404

        return jsonify(message="Category deleted successfully!")

    except sqlite3.IntegrityError:
        return jsonify(
            error="This category contains books. "
                  "Move those books to another category first."
        ), 409

    finally:
        connection.close()
        # UPDATE: Edit a customer.
@app.put("/api/customers/<int:customer_id>")
def update_customer(customer_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify(error="Please send valid customer data."), 400

    name = data.get("name")
    email = data.get("email")

    if not isinstance(name, str) or not name.strip():
        return jsonify(error="Customer name is required."), 400

    if not isinstance(email, str):
        return jsonify(error="A valid email is required."), 400

    name = name.strip()
    email = email.strip().lower()
    parts = email.split("@")

    if (
        len(parts) != 2
        or not parts[0]
        or "." not in parts[1]
        or parts[1].startswith(".")
        or parts[1].endswith(".")
        or any(character.isspace() for character in email)
    ):
        return jsonify(error="Enter a valid email address."), 400

    connection = get_connection()

    try:
        with connection:
            cursor = connection.execute("""
                UPDATE customers
                SET name = ?, email = ?
                WHERE id = ?
            """, (name, email, customer_id))

            if cursor.rowcount == 0:
                return jsonify(error="Customer not found."), 404

        return jsonify(message="Customer updated successfully!")

    except sqlite3.IntegrityError:
        return jsonify(
            error="A customer with this email already exists."
        ), 409

    finally:
        connection.close()


# DELETE: Remove a customer who has no orders.
@app.delete("/api/customers/<int:customer_id>")
def delete_customer(customer_id):
    connection = get_connection()

    try:
        with connection:
            cursor = connection.execute(
                "DELETE FROM customers WHERE id = ?",
                (customer_id,)
            )

            if cursor.rowcount == 0:
                return jsonify(error="Customer not found."), 404

        return jsonify(message="Customer deleted successfully!")

    except sqlite3.IntegrityError:
        return jsonify(
            error="This customer has order history and cannot be deleted."
        ), 409

    finally:
        connection.close()