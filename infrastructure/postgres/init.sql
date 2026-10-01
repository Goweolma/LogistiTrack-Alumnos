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

-- Idempotencia: cada event_id se procesa una sola vez por consumidor.
CREATE TABLE IF NOT EXISTS processed_events (
    event_id VARCHAR(64) NOT NULL,
    consumer VARCHAR(40) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, consumer)
);

-- TODO(ALUMNO-1): diseñar orders y order_history.

INSERT INTO products (product_id, product_name, product_description, price) VALUES
    ('PROD-001', 'Laptop empresarial', 'Laptop de 14 pulgadas para uso corporativo', 18999.00),
    ('PROD-002', 'Monitor 24 pulgadas', 'Monitor Full HD de 24 pulgadas', 4299.00),
    ('PROD-003', 'Teclado mecánico', 'Teclado mecánico con distribución en español', 1599.00)
ON CONFLICT DO NOTHING;

INSERT INTO inventory (product_id, warehouse, quantity) VALUES
    ('PROD-001', 'NORTE', 8),
    ('PROD-001', 'SUR', 5),
    ('PROD-002', 'NORTE', 12),
    ('PROD-002', 'SUR', 7),
    ('PROD-003', 'NORTE', 20),
    ('PROD-003', 'SUR', 14)
ON CONFLICT DO NOTHING;
