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

-- ALUMNO-2: cuentas de usuario. El registro usa el rol por defecto 'user';
-- un 'admin' solo se asigna de forma manual o mediante un proceso autorizado.
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    email VARCHAR(254) NOT NULL CHECK (email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
    name VARCHAR(120) NOT NULL CHECK (btrim(name) <> ''),
    phone VARCHAR(20) CHECK (phone ~ '^\+?[0-9]{10,15}$'),
    address VARCHAR(200),
    role VARCHAR(10) NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- Email único sin distinguir mayúsculas: Ana@correo.com y ana@correo.com son la misma cuenta.
CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique ON users (lower(email));

-- ALUMNO-2: catálogo de tamaños de paquete. El usuario elige uno al crear el pedido.
CREATE TABLE IF NOT EXISTS package_sizes (
    package_size_id VARCHAR(20) NOT NULL PRIMARY KEY,
    name VARCHAR(60) NOT NULL UNIQUE,
    length_cm NUMERIC(6, 1) NOT NULL CHECK (length_cm > 0),
    width_cm NUMERIC(6, 1) NOT NULL CHECK (width_cm > 0),
    height_cm NUMERIC(6, 1) NOT NULL CHECK (height_cm > 0),
    max_weight_kg NUMERIC(6, 2) NOT NULL CHECK (max_weight_kg > 0),
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
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
    -- ALUMNO-2: tamaño elegido y precio confirmado al crear el pedido. Son opcionales
    -- mientras Orders siga creando pedidos por productos; si se guarda uno, se guardan ambos.
    package_size_id VARCHAR(20) REFERENCES package_sizes(package_size_id),
    confirmed_price NUMERIC(10, 2) CHECK (confirmed_price >= 0),
    -- ALUMNO-2: columnas que asigna Delivery (vacías hasta DRIVER_ASSIGNED).
    driver_id VARCHAR(20),
    vehicle_id VARCHAR(20),
    CHECK ((package_size_id IS NULL) = (confirmed_price IS NULL))
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

INSERT INTO package_sizes (package_size_id, name, length_cm, width_cm, height_cm, max_weight_kg, price) VALUES
    ('PKG-XS', 'Sobre', 35.0, 25.0, 2.0, 0.50, 89.00),
    ('PKG-S', 'Chico', 25.0, 20.0, 10.0, 2.00, 129.00),
    ('PKG-M', 'Mediano', 40.0, 30.0, 20.0, 5.00, 189.00),
    ('PKG-L', 'Grande', 50.0, 40.0, 30.0, 10.00, 269.00),
    ('PKG-XL', 'Extra grande', 70.0, 50.0, 40.0, 25.00, 399.00)
ON CONFLICT DO NOTHING;


