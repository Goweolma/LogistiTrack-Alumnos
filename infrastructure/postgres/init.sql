CREATE TABLE IF NOT EXISTS products (
    product_id VARCHAR(40) NOT NULL PRIMARY KEY,
    product_name VARCHAR(120) NOT NULL,
    product_description VARCHAR(200) NOT NULL,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0)
);

CREATE TABLE IF NOT EXISTS inventory (
    product_id VARCHAR(40) REFERENCES products(product_id),
    warehouse VARCHAR(30) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    PRIMARY KEY (product_id, warehouse)
);

CREATE TABLE IF NOT EXISTS warehouses (
    warehouse_id VARCHAR(40) NOT NULL PRIMARY KEY,
    location VARCHAR(40) NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(40) NOT NULL PRIMARY KEY,
    given_names VARCHAR(50) NOT NULL,
    surname VARCHAR(50) NOT NULL,
    password_hash VARCHAR(35) NOT NULL
);

CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id VARCHAR(40) NOT NULL PRIMARY KEY,
    brand VARCHAR(25) NOT NULL,
    model VARCHAR(40) NOT NULL,
    year INTEGER NOT NULL CHECK (year >= 1900),
    size VARCHAR(15) NOT NULL CHECK (size IN (
        'small', 'medium', 'large'
    )),
    registration VARCHAR(15) NOT NULL,
    warehouse_id VARCHAR(40) REFERENCES warehouses(warehouse_id)
);

CREATE TABLE IF NOT EXISTS drivers (
    driver_id VARCHAR(40) NOT NULL PRIMARY KEY,
    given_names VARCHAR(50) NOT NULL,
    surname VARCHAR(50) NOT NULL,
    vehicle_id VARCHAR(40) REFERENCES vehicles(vehicle_id)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(40) NOT NULL,
    user_id VARCHAR(40) REFERENCES users(user_id),
    PRIMARY KEY(order_id, user_id),

    product_id VARCHAR(40) REFERENCES products(product_id),
    order_quantity INTEGER NOT NULL CHECK (order_quantity >= 0),
    total NUMERIC(10, 2) NOT NULL CHECK (total >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status VARCHAR(20) NOT NULL CHECK (status IN (
        'order_created', 'inventory_reserved', 'order_preparing', 'order_ready',
        'driver_assigned', 'in_transit', 'delivered'
    )),
    address_line VARCHAR(200) NOT NULL,
    driver_id VARCHAR(40) REFERENCES drivers(driver_id)
);


-- TODO(ALUMNO-1 y ALUMNO-2): diseñar orders, order_history y processed_events.

INSERT INTO products (product_id, name, price) VALUES
    ('PROD-001', 'Laptop empresarial', 18999.00),
    ('PROD-002', 'Monitor 24 pulgadas', 4299.00),
    ('PROD-003', 'Teclado mecánico', 1599.00)
ON CONFLICT DO NOTHING;

INSERT INTO inventory (product_id, warehouse, quantity) VALUES
    ('PROD-001', 'NORTE', 8),
    ('PROD-001', 'SUR', 5),
    ('PROD-002', 'NORTE', 12),
    ('PROD-002', 'SUR', 7),
    ('PROD-003', 'NORTE', 20),
    ('PROD-003', 'SUR', 14)
ON CONFLICT DO NOTHING;

