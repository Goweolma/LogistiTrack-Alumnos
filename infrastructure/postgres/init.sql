CREATE TABLE IF NOT EXISTS products (
    product_id VARCHAR(40) NOT NULL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    product_description VARCHAR(200) NOT NULL,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0)
);

CREATE TABLE IF NOT EXISTS inventory (
    product_id VARCHAR(40) REFERENCES products(product_id),
    warehouse VARCHAR(30) NOT NULL CHECK (warehouse IN ('NORTE', 'SUR')),
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    PRIMARY KEY (product_id, warehouse)
);

-- Idempotencia: cada event_id se procesa una sola vez por servicio.
CREATE TABLE IF NOT EXISTS processed_events (
    event_id UUID NOT NULL,
    service_name VARCHAR(40) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id, service_name)
);

-- ALUMNO-2: historial de reservas. Guarda el evento publicado para reenviarlo
-- si Kafka entrega otra vez el mismo ORDER_CREATED.
CREATE TABLE IF NOT EXISTS inventory_reservations (
    event_id UUID NOT NULL PRIMARY KEY,
    order_id VARCHAR(40) NOT NULL,
    status VARCHAR(30) NOT NULL CHECK (status IN ('INVENTORY_RESERVED', 'INVENTORY_REJECTED')),
    warehouse VARCHAR(30) CHECK (warehouse IN ('NORTE', 'SUR')),
    result_event JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ALUMNO-2: numeración PED-000001 ... PED-999999. MAXVALUE evita que lpad recorte
-- un número de siete dígitos y genere un ID repetido.
CREATE SEQUENCE IF NOT EXISTS order_number_seq MINVALUE 1 MAXVALUE 999999 NO CYCLE;

-- ALUMNO-1: tablas de pedidos.
CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(40) PRIMARY KEY DEFAULT ('PED-' || lpad(nextval('order_number_seq')::text, 6, '0')),
    total NUMERIC(10, 2) NOT NULL CHECK (total >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivery_address VARCHAR(200) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'RECEIVED',
    -- ALUMNO-2: columnas que asigna Delivery (vacías hasta DRIVER_ASSIGNED).
    driver_id VARCHAR(20),
    vehicle_id VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS order_history (
    history_id SERIAL PRIMARY KEY,
    order_id VARCHAR(40) NOT NULL REFERENCES orders(order_id),
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- ALUMNO-2: Delivery guarda el evento para republicarlo tras un fallo; opcional para los demás servicios.
    event_id UUID UNIQUE,
    event JSONB
);

CREATE TABLE IF NOT EXISTS order_items (
    order_id VARCHAR(40) NOT NULL REFERENCES orders(order_id),
    product_id VARCHAR(40) NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);

INSERT INTO products (product_id, name, product_description, price) VALUES
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
