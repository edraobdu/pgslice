#!/usr/bin/env python3
"""
Generate large test dataset for snippy performance testing.

Usage:
    python generate_large_dataset.py > large_sample_data.sql

    # Or pipe directly to database:
    python generate_large_dataset.py | docker compose exec -T postgres \
        psql -U test_user -d test_db

    # Or load via file:
    python generate_large_dataset.py > large_sample_data.sql
    docker compose exec -T postgres psql -U test_user -d test_db < large_sample_data.sql
"""

import random
from datetime import datetime, timedelta
from faker import Faker

# Initialize with seed for reproducibility
fake = Faker()
Faker.seed(42)
random.seed(42)

# Configuration - target ~200K records
NUM_ROLES = 5
NUM_GROUPS = 20
NUM_CATEGORIES = 50
NUM_BANKS = 10
NUM_USERS = 5000
NUM_PRODUCTS = 1000
NUM_BANK_ACCOUNTS = 10000
NUM_USER_GROUPS = 15000
NUM_ORDERS = 20000
NUM_ORDER_ITEMS = 50000
NUM_TRANSACTIONS = 100000


def format_sql_value(value):
    """Format Python value for SQL INSERT."""
    if value is None:
        return "NULL"
    elif isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, datetime):
        return f"'{value.isoformat()}'"
    elif isinstance(value, str):
        # Escape single quotes and backslashes
        escaped = value.replace("'", "''").replace("\\", "\\\\")
        return f"'{escaped}'"
    else:
        return f"'{str(value)}'"


def generate_bulk_insert(table_name, columns, rows):
    """Generate bulk INSERT statement."""
    if not rows:
        return ""

    columns_sql = ", ".join(f'"{col}"' for col in columns)

    values_rows = []
    for row in rows:
        values = [format_sql_value(row[col]) for col in columns]
        values_sql = ", ".join(values)
        values_rows.append(f"    ({values_sql})")

    values_clause = ",\n".join(values_rows)

    sql = f"""-- Table: {table_name} ({len(rows)} records)
INSERT INTO {table_name} ({columns_sql})
VALUES
{values_clause};
"""
    return sql


def generate_roles():
    """Generate role master data."""
    roles = [
        {"id": 1, "name": "admin", "description": "Administrator with full access"},
        {"id": 2, "name": "manager", "description": "Team manager"},
        {"id": 3, "name": "team_lead", "description": "Team lead"},
        {"id": 4, "name": "developer", "description": "Software developer"},
        {"id": 5, "name": "user", "description": "Regular user"},
    ]
    return roles


def generate_groups(num_groups=20):
    """Generate group records."""
    groups = []
    group_names = [
        "Engineering",
        "Sales",
        "Marketing",
        "Finance",
        "HR",
        "Operations",
        "Product",
        "Design",
        "Support",
        "Legal",
        "DevOps",
        "QA",
        "Research",
        "Analytics",
        "Security",
        "Infrastructure",
        "Business Development",
        "Customer Success",
        "Partnerships",
        "Administration",
    ]

    for i in range(1, num_groups + 1):
        group = {
            "id": i,
            "name": group_names[i - 1] if i <= len(group_names) else f"Group {i}",
            "description": fake.catch_phrase(),
        }
        groups.append(group)

    return groups


def generate_categories(num_categories=50):
    """Generate category records with tree structure (self-referencing)."""
    categories = []

    # First 10 categories are root (no parent)
    for i in range(1, 11):
        category = {
            "id": i,
            "name": fake.word().capitalize() + " Category",
            "parent_id": None,
        }
        categories.append(category)

    # Remaining categories have parents
    for i in range(11, num_categories + 1):
        parent_id = random.randint(1, min(i - 1, 10))  # Parent from root categories
        category = {
            "id": i,
            "name": fake.word().capitalize() + " Subcategory",
            "parent_id": parent_id,
        }
        categories.append(category)

    return categories


def generate_banks(num_banks=10):
    """Generate bank records."""
    banks = []
    bank_names = [
        "First National Bank",
        "Global Financial Corp",
        "Community Credit Union",
        "Metropolitan Trust Bank",
        "Regional Savings Bank",
        "United Commerce Bank",
        "Pacific Coast Bank",
        "Eastern Financial",
        "Central Bank & Trust",
        "International Banking Group",
    ]

    for i in range(1, num_banks + 1):
        bank = {
            "id": i,
            "name": bank_names[i - 1] if i <= len(bank_names) else f"Bank {i}",
            "swift_code": f"BANK{i:04d}XXX",
        }
        banks.append(bank)

    return banks


def generate_users(num_users=5000):
    """Generate user records with manager hierarchy."""
    users = []

    # First 10 users have no manager (top level)
    for i in range(1, 11):
        user = {
            "id": i,
            "username": fake.user_name() + f"_{i}",  # Ensure uniqueness
            "email": f"user{i}@{fake.domain_name()}",  # Ensure uniqueness
            "role_id": random.choice([1, 2]),  # Admin or Manager
            "manager_id": None,
            "created_at": fake.date_time_between(start_date="-2y", end_date="now"),
        }
        users.append(user)

    # Remaining users have managers from existing users
    for i in range(11, num_users + 1):
        # Manager from earlier users (within reasonable range for realistic hierarchy)
        manager_id = random.randint(1, min(i - 1, 500))
        user = {
            "id": i,
            "username": fake.user_name() + f"_{i}",  # Ensure uniqueness
            "email": f"user{i}@{fake.domain_name()}",  # Ensure uniqueness
            "role_id": random.choice([3, 4, 5]),  # Team lead, dev, or user
            "manager_id": manager_id,
            "created_at": fake.date_time_between(start_date="-2y", end_date="now"),
        }
        users.append(user)

    return users


def generate_products(num_products=1000, categories=[]):
    """Generate product records."""
    products = []

    for i in range(1, num_products + 1):
        category = random.choice(categories)
        product = {
            "id": i,
            "name": fake.catch_phrase(),
            "price": round(random.uniform(9.99, 999.99), 2),
            "category_id": category["id"],
        }
        products.append(product)

    return products


def generate_bank_accounts(num_accounts=10000, users=[], banks=[]):
    """Generate bank account records (1-3 per user)."""
    accounts = []
    account_id = 1

    for user in users:
        # Each user gets 1-3 bank accounts
        num_user_accounts = random.randint(1, 3)
        for _ in range(num_user_accounts):
            if account_id > num_accounts:
                break

            bank = random.choice(banks)
            account = {
                "id": account_id,
                "user_id": user["id"],
                "bank_id": bank["id"],
                "account_number": f"{fake.bban()}{account_id:06d}",
                "balance": round(random.uniform(0, 50000), 2),
            }
            accounts.append(account)
            account_id += 1

    return accounts


def generate_user_groups(num_user_groups=15000, users=[], groups=[]):
    """Generate user-group memberships (many-to-many)."""
    user_groups = []
    used_pairs = set()

    attempts = 0
    max_attempts = num_user_groups * 3

    while len(user_groups) < num_user_groups and attempts < max_attempts:
        user = random.choice(users)
        group = random.choice(groups)
        pair = (user["id"], group["id"])

        if pair not in used_pairs:
            user_group = {
                "user_id": user["id"],
                "group_id": group["id"],
                "joined_at": fake.date_time_between(start_date="-1y", end_date="now"),
            }
            user_groups.append(user_group)
            used_pairs.add(pair)

        attempts += 1

    return user_groups


def generate_orders(num_orders=20000, users=[]):
    """Generate order records."""
    orders = []

    for i in range(1, num_orders + 1):
        user = random.choice(users)
        order = {
            "id": i,
            "user_id": user["id"],
            "total_amount": 0.0,  # Will be calculated based on order items
            "status": random.choice(
                ["pending", "processing", "shipped", "delivered", "cancelled"]
            ),
            "created_at": fake.date_time_between(start_date="-1y", end_date="now"),
        }
        orders.append(order)

    return orders


def generate_order_items(num_order_items=50000, orders=[], products=[]):
    """Generate order item records (2-5 items per order)."""
    order_items = []
    order_item_id = 1

    for order in orders:
        # Each order gets 2-5 items
        num_items = random.randint(2, 5)
        order_total = 0.0

        for _ in range(num_items):
            if order_item_id > num_order_items:
                break

            product = random.choice(products)
            quantity = random.randint(1, 5)
            price_at_time = product["price"] * random.uniform(
                0.9, 1.1
            )  # Slight variation
            subtotal = round(price_at_time * quantity, 2)

            order_item = {
                "id": order_item_id,
                "order_id": order["id"],
                "product_id": product["id"],
                "quantity": quantity,
                "price_at_time": round(price_at_time, 2),
            }
            order_items.append(order_item)
            order_total += subtotal
            order_item_id += 1

        # Update order total (would need to be done in separate UPDATE, but for simplicity...)
        order["total_amount"] = round(order_total, 2)

    return order_items


def generate_transactions(num_transactions=100000, bank_accounts=[]):
    """Generate transaction records."""
    transactions = []

    for i in range(1, num_transactions + 1):
        account = random.choice(bank_accounts)
        amount = round(random.uniform(-5000, 5000), 2)

        transaction = {
            "id": i,
            "bank_account_id": account["id"],
            "amount": amount,
            "description": fake.sentence(nb_words=6),
            "created_at": fake.date_time_between(start_date="-1y", end_date="now"),
        }
        transactions.append(transaction)

    return transactions


def main():
    """Generate complete dataset in dependency order."""
    print("-- Generated by generate_large_dataset.py")
    print(f"-- Date: {datetime.now().isoformat()}")
    print(f"-- Seed: 42 (reproducible)")
    print(f"-- Target records: ~201,085")
    print()
    print("BEGIN;")
    print()

    # Generate data in dependency order
    print("-- Master/lookup tables")
    roles = generate_roles()
    print(
        generate_bulk_insert(
            "public.roles", ["id", "name", "description"], roles
        )
    )

    groups = generate_groups(NUM_GROUPS)
    print(
        generate_bulk_insert(
            "public.groups", ["id", "name", "description"], groups
        )
    )

    categories = generate_categories(NUM_CATEGORIES)
    print(
        generate_bulk_insert(
            "public.categories", ["id", "name", "parent_id"], categories
        )
    )

    banks = generate_banks(NUM_BANKS)
    print(generate_bulk_insert("public.banks", ["id", "name", "swift_code"], banks))

    print()
    print("-- User data")
    users = generate_users(NUM_USERS)
    print(
        generate_bulk_insert(
            "public.users",
            ["id", "username", "email", "role_id", "manager_id", "created_at"],
            users,
        )
    )

    print()
    print("-- Product data")
    products = generate_products(NUM_PRODUCTS, categories)
    print(
        generate_bulk_insert(
            "public.products", ["id", "name", "price", "category_id"], products
        )
    )

    print()
    print("-- Bank accounts")
    bank_accounts = generate_bank_accounts(NUM_BANK_ACCOUNTS, users, banks)
    print(
        generate_bulk_insert(
            "public.bank_accounts",
            ["id", "user_id", "bank_id", "account_number", "balance"],
            bank_accounts,
        )
    )

    print()
    print("-- User-Group memberships (M2M)")
    user_groups = generate_user_groups(NUM_USER_GROUPS, users, groups)
    print(
        generate_bulk_insert(
            "public.user_groups", ["user_id", "group_id", "joined_at"], user_groups
        )
    )

    print()
    print("-- Orders")
    orders = generate_orders(NUM_ORDERS, users)
    print(
        generate_bulk_insert(
            "public.orders",
            ["id", "user_id", "total_amount", "status", "created_at"],
            orders,
        )
    )

    print()
    print("-- Order items")
    order_items = generate_order_items(NUM_ORDER_ITEMS, orders, products)
    print(
        generate_bulk_insert(
            "public.order_items",
            ["id", "order_id", "product_id", "quantity", "price_at_time"],
            order_items,
        )
    )

    print()
    print("-- Transactions")
    transactions = generate_transactions(NUM_TRANSACTIONS, bank_accounts)
    print(
        generate_bulk_insert(
            "public.transactions",
            ["id", "bank_account_id", "amount", "description", "created_at"],
            transactions,
        )
    )

    # Reset sequences
    print()
    print("-- Reset sequences")
    print(f"SELECT setval('roles_id_seq', {NUM_ROLES});")
    print(f"SELECT setval('groups_id_seq', {NUM_GROUPS});")
    print(f"SELECT setval('categories_id_seq', {NUM_CATEGORIES});")
    print(f"SELECT setval('banks_id_seq', {NUM_BANKS});")
    print(f"SELECT setval('users_id_seq', {NUM_USERS});")
    print(f"SELECT setval('products_id_seq', {NUM_PRODUCTS});")
    print(f"SELECT setval('bank_accounts_id_seq', {len(bank_accounts)});")
    print(f"SELECT setval('orders_id_seq', {NUM_ORDERS});")
    print(f"SELECT setval('order_items_id_seq', {len(order_items)});")
    print(f"SELECT setval('transactions_id_seq', {NUM_TRANSACTIONS});")

    print()
    print("COMMIT;")
    print()
    print(f"-- Total records generated: {NUM_ROLES + NUM_GROUPS + NUM_CATEGORIES + NUM_BANKS + NUM_USERS + NUM_PRODUCTS + len(bank_accounts) + NUM_USER_GROUPS + NUM_ORDERS + len(order_items) + NUM_TRANSACTIONS}")


if __name__ == "__main__":
    main()
