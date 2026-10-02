CREATE TABLE IF NOT EXISTS products (
    product_id VARCHAR(40) PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0)
);

CREATE TABLE IF NOT EXISTS inventory (
    product_id VARCHAR(40) REFERENCES products(product_id),
    warehouse VARCHAR(30) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    PRIMARY KEY (product_id, warehouse)
);

-- ALUMNO-1: tablas de pedidos.
-- TODO(ALUMNO-2): diseñar processed_events.
CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(40) PRIMARY KEY,
    total NUMERIC(10, 2) NOT NULL CHECK (total >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivery_address VARCHAR(200) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'RECEIVED'
);

CREATE TABLE IF NOT EXISTS order_history (
    history_id SERIAL PRIMARY KEY,
    order_id VARCHAR(40) NOT NULL REFERENCES orders(order_id),
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id VARCHAR(40) NOT NULL REFERENCES orders(order_id),
    product_id VARCHAR(40) NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);

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

