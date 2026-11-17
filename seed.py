from database import get_connection


def add_sample_data():
    connection = get_connection()

    try:
        with connection:
            # Add categories.
            for name in ["Fiction", "Technology", "Business"]:
                connection.execute(
                    "INSERT OR IGNORE INTO categories (name) VALUES (?)",
                    (name,)
                )

            # Prices are stored in cents: 1599 means $15.99.
            books = [
                ("The Lantern House", "Maya Reed",
                 "9780000000001", "Fiction", 1599, 10),

                ("Python Starter Guide", "Alex Carter",
                 "9780000000002", "Technology", 2499, 8),

                ("Learning SQL", "Sam Taylor",
                 "9780000000003", "Technology", 1999, 12),

                ("Everyday Business", "Jordan Lee",
                 "9780000000004", "Business", 1799, 4),

                ("The Quiet Journey", "Nina Brooks",
                 "9780000000005", "Fiction", 1299, 3),
            ]

            for title, author, isbn, category, price, stock in books:
                category_id = connection.execute(
                    "SELECT id FROM categories WHERE name = ?",
                    (category,)
                ).fetchone()["id"]

                connection.execute("""
                    INSERT OR IGNORE INTO books
                    (title, author, isbn, category_id, price_cents, stock)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (title, author, isbn, category_id, price, stock))

            # Add fictional customers.
            customers = [
                ("Alex Student", "alex@example.com"),
                ("Taylor Reader", "taylor@example.com"),
                ("Morgan Booklover", "morgan@example.com"),
            ]

            connection.executemany("""
                INSERT OR IGNORE INTO customers (name, email)
                VALUES (?, ?)
            """, customers)

        print("Sample data added successfully!")

        for table in ["categories", "books", "customers"]:
            count = connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

            print(f"{table}: {count}")

    finally:
        connection.close()


if __name__ == "__main__":
    add_sample_data()