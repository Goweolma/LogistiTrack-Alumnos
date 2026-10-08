export const SERVICE_NAMES = ["orders", "inventory", "warehouse", "delivery"];

export const PATHS = {
  platformHealth: "/api/health",
  products: "/api/products",
  orders: "/api/orders",
  inventory: "/api/inventory",
  warehouse: "/api/warehouse",
  delivery: "/api/delivery",
};

export function serviceHealthPath(service) {
  return `/api/services/${service}/health`;
}

export function orderPath(orderId) {
  return `/api/orders/${encodeURIComponent(orderId)}`;
}

const ERROR_TEXT = {
  INVALID_JSON: "El cuerpo no es JSON válido.",
  INVALID_DELIVERY_ADDRESS: "La dirección debe tener entre 1 y 200 caracteres.",
  INVALID_ITEMS: "Agrega al menos un producto.",
  INVALID_ITEM: "Hay un producto mal formado.",
  INVALID_PRODUCT_ID: "Cada producto necesita un identificador.",
  INVALID_QUANTITY: "La cantidad debe ser un entero mayor que cero.",
  DUPLICATE_PRODUCT: "No repitas el mismo producto en el pedido.",
  NOT_IMPLEMENTED: "La API todavía no está implementada. La pantalla ya envía el contrato acordado.",
  ORDER_NOT_FOUND: "No existe un pedido con ese identificador.",
  DATABASE_UNAVAILABLE: "La base de datos no está disponible.",
  PRODUCT_NOT_FOUND: "Ese producto no existe.",
  INVALID_ORDER: "El pedido no es válido.",
};

export function describeApiError(status, data) {
  if (status === 0) {
    return "No fue posible contactar la API.";
  }
  if (status === 501 || data?.error === "NOT_IMPLEMENTED") {
    return ERROR_TEXT.NOT_IMPLEMENTED;
  }
  if (data?.detail && ERROR_TEXT[data.detail]) {
    return ERROR_TEXT[data.detail];
  }
  if (data?.error && ERROR_TEXT[data.error]) {
    return ERROR_TEXT[data.error];
  }
  if (status === 404) {
    return "No se encontró el recurso.";
  }
  if (status === 502 || status === 504) {
    return "El servicio no respondió a través del proxy.";
  }
  return `La API respondió HTTP ${status}.`;
}

export async function apiRequest(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  try {
    const response = await fetch(path, { ...options, headers });
    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { error: "INVALID_RESPONSE" };
      }
    }
    return { ok: response.ok, status: response.status, data };
  } catch (error) {
    return { ok: false, status: 0, data: null, networkError: error.message };
  }
}
