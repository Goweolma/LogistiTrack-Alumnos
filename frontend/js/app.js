import {
  PATHS,
  SERVICE_NAMES,
  apiRequest,
  describeApiError,
  orderPath,
  serviceHealthPath,
} from "./api.js";

const STATUS_CLASS = {
  RECEIVED: "status-pendiente",
  INVENTORY_RESERVED: "status-pendiente",
  INVENTORY_REJECTED: "status-pendiente",
  PREPARING: "status-preparando",
  READY_FOR_DELIVERY: "status-preparando",
  DRIVER_ASSIGNED: "status-transito",
  IN_TRANSIT: "status-transito",
  NEAR_DESTINATION: "status-transito",
  DELIVERED: "status-entregado",
};

const SERVICE_LABELS = {
  orders: "Pedidos",
  inventory: "Inventario",
  warehouse: "Almacén",
  delivery: "Reparto",
};

const state = {
  orders: [],
  draft: [],
  products: [],
};

const $ = (selector) => document.querySelector(selector);

function text(selector, value) {
  $(selector).textContent = value;
}

function money(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";
  return new Intl.NumberFormat("es-MX", { style: "currency", currency: "MXN" }).format(amount);
}

function when(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value ? String(value) : "—";
  return new Intl.DateTimeFormat("es-MX", { dateStyle: "short", timeStyle: "short" }).format(date);
}

function badge(label, kind) {
  const span = document.createElement("span");
  span.className = `badge${kind ? ` ${kind}` : ""}`;
  span.textContent = label;
  return span;
}

function asList(data) {
  return Array.isArray(data) ? data : null;
}

function normalizeProduct(item) {
  if (typeof item === "string" && item.trim()) {
    return { product_id: item.trim(), name: item.trim() };
  }
  if (!item || typeof item !== "object" || typeof item.product_id !== "string") {
    return null;
  }
  const productId = item.product_id.trim();
  if (!productId) return null;
  return {
    product_id: productId,
    name: typeof item.name === "string" && item.name.trim() ? item.name.trim() : productId,
    stock: item.stock && typeof item.stock === "object" ? item.stock : null,
  };
}

async function loadPlatform() {
  const result = await apiRequest(PATHS.platformHealth);
  const status = $("#status");
  if (result.ok) {
    status.className = "badge ok";
    status.textContent = result.data?.status || "LISTO";
    text("#message", result.data?.message || "La API de pedidos respondió.");
    return;
  }
  status.className = result.status === 0 ? "badge error" : "badge warn";
  status.textContent = result.status === 0 ? "SIN CONEXIÓN" : "REVISAR";
  text("#message", describeApiError(result.status, result.data));
}

function serviceBadge(result) {
  if (result.status === 0) return badge("SIN CONEXIÓN", "error");
  const reported = result.data?.status;
  if (result.ok && (reported === "UP" || reported === "BASE_READY")) {
    return badge(reported, "ok");
  }
  if (result.status === 404) return badge("SIN API", "warn");
  if (reported) return badge(String(reported), result.ok ? "ok" : "error");
  return badge(`HTTP ${result.status}`, "error");
}

async function loadServices() {
  const root = $("#services");
  root.replaceChildren();
  const results = await Promise.all(
    SERVICE_NAMES.map(async (service) => [service, await apiRequest(serviceHealthPath(service))]),
  );
  for (const [service, result] of results) {
    const card = document.createElement("article");
    card.className = "service";
    const name = document.createElement("strong");
    name.textContent = SERVICE_LABELS[service];
    card.append(name, serviceBadge(result));
    root.append(card);
  }
}

function setCatalog(products, source) {
  state.products = products;
  const select = $("#productId");
  const manual = $("#productIdManual");
  select.replaceChildren();
  if (products.length) {
    for (const product of products) {
      const option = document.createElement("option");
      option.value = product.product_id;
      option.textContent = `${product.name} (${product.product_id})`;
      select.append(option);
    }
    select.hidden = false;
    select.required = true;
    manual.hidden = true;
    manual.required = false;
    $("#productLabel").htmlFor = "productId";
    text(
      "#catalogNotice",
      source === "inventory"
        ? "El catálogo /api/products aún no publica productos. La lista sale de /api/inventory."
        : "",
    );
    return;
  }
  select.hidden = true;
  select.required = false;
  manual.hidden = false;
  manual.required = true;
  $("#productLabel").htmlFor = "productIdManual";
  text(
    "#catalogNotice",
    "Ni /api/products ni /api/inventory devolvieron un catálogo. Escribe el identificador; el alta usa POST /api/orders.",
  );
}

async function loadCatalog() {
  const products = await apiRequest(PATHS.products);
  const catalog = products.ok ? asList(products.data)?.map(normalizeProduct).filter(Boolean) : null;
  if (catalog?.length) {
    setCatalog(catalog, "products");
    return;
  }
  const inventory = await apiRequest(PATHS.inventory);
  const stock = inventory.ok ? asList(inventory.data)?.map(normalizeProduct).filter(Boolean) : null;
  setCatalog(stock || [], stock?.length ? "inventory" : "none");
}

function renderInventory(products, message) {
  text("#inventoryMessage", message);
  const grid = $("#inventoryGrid");
  grid.replaceChildren();
  if (!products?.length) return;
  for (const warehouse of ["NORTE", "SUR"]) {
    const card = document.createElement("article");
    card.className = "inventory-item";
    const title = document.createElement("h3");
    title.textContent = warehouse;
    card.append(title);
    for (const product of products) {
      const line = document.createElement("p");
      const quantity = Number(product.stock?.[warehouse] ?? 0);
      line.textContent = `${product.name}: ${Number.isFinite(quantity) ? quantity : 0}`;
      card.append(line);
    }
    grid.append(card);
  }
}

async function loadInventory() {
  const result = await apiRequest(PATHS.inventory);
  if (!result.ok) {
    renderInventory([], describeApiError(result.status, result.data));
    return;
  }
  const products = asList(result.data)?.map(normalizeProduct).filter(Boolean) || [];
  if (!products.length) {
    renderInventory([], "La API de inventario respondió sin existencias.");
    return;
  }
  if (!products.some((product) => product.stock)) {
    renderInventory([], "La API respondió productos, pero no incluye existencias por almacén.");
    return;
  }
  renderInventory(products, "");
}

function selectedProduct() {
  if (!$("#productId").hidden) {
    const productId = $("#productId").value.trim();
    const known = state.products.find((product) => product.product_id === productId);
    return { product_id: productId, name: known?.name || productId };
  }
  const productId = $("#productIdManual").value.trim();
  return { product_id: productId, name: productId };
}

function renderDraft() {
  const list = $("#draftItems");
  list.replaceChildren();
  for (const item of state.draft) {
    const row = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = `${item.name} × ${item.quantity}`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Quitar";
    remove.addEventListener("click", () => {
      state.draft = state.draft.filter((entry) => entry.product_id !== item.product_id);
      renderDraft();
    });
    row.append(label, remove);
    list.append(row);
  }
}

function addDraftItem() {
  const product = selectedProduct();
  const quantity = Number($("#quantity").value);
  text("#formError", "");
  if (!product.product_id) {
    text("#formError", "Indica el producto.");
    return;
  }
  if (!Number.isInteger(quantity) || quantity <= 0) {
    text("#formError", "La cantidad debe ser un entero mayor que cero.");
    return;
  }
  const existing = state.draft.find((item) => item.product_id === product.product_id);
  if (existing) {
    existing.quantity += quantity;
  } else {
    state.draft.push({ product_id: product.product_id, name: product.name, quantity });
  }
  renderDraft();
}

function orderPayload() {
  return {
    delivery_address: $("#address").value.trim(),
    items: state.draft.map((item) => ({
      product_id: item.product_id,
      quantity: item.quantity,
    })),
  };
}

async function submitOrder(event) {
  event.preventDefault();
  text("#formError", "");
  text("#formResult", "");
  const payload = orderPayload();
  if (!payload.delivery_address || payload.delivery_address.length > 200) {
    text("#formError", "La dirección debe tener entre 1 y 200 caracteres.");
    return;
  }
  if (!payload.items.length) {
    text("#formError", "Agrega al menos un producto.");
    return;
  }
  const submit = $("#orderForm button[type='submit']");
  submit.disabled = true;
  const result = await apiRequest(PATHS.orders, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  submit.disabled = false;
  if (result.ok) {
    const orderId = result.data?.order_id ? ` ${result.data.order_id}` : "";
    text("#formResult", `Pedido aceptado.${orderId}`);
    state.draft = [];
    renderDraft();
    $("#orderForm").reset();
    await loadOrders();
    return;
  }
  const detail = describeApiError(result.status, result.data);
  text("#formResult", `${detail} Cuerpo enviado: ${JSON.stringify(payload)}`);
}

function fillStatusFilter() {
  const filter = $("#statusFilter");
  const current = filter.value;
  const present = new Set(state.orders.map((order) => order.status).filter(Boolean));
  filter.replaceChildren();
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "Todos los estados";
  filter.append(all);
  for (const status of Object.keys(STATUS_CLASS)) {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = status;
    filter.append(option);
  }
  for (const status of present) {
    if (STATUS_CLASS[status]) continue;
    const option = document.createElement("option");
    option.value = status;
    option.textContent = status;
    filter.append(option);
  }
  filter.value = [...filter.options].some((option) => option.value === current) ? current : "";
}

function visibleOrders() {
  const query = $("#search").value.trim().toLowerCase();
  const status = $("#statusFilter").value;
  return state.orders.filter((order) => {
    const matchesStatus = !status || order.status === status;
    const haystack = `${order.order_id || ""} ${order.delivery_address || ""}`.toLowerCase();
    return matchesStatus && (!query || haystack.includes(query));
  });
}

function renderOrders() {
  const body = $("#ordersBody");
  body.replaceChildren();
  const orders = visibleOrders();
  if (!state.orders.length) return;
  if (!orders.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.textContent = "Ningún pedido coincide con el filtro.";
    row.append(cell);
    body.append(row);
    return;
  }
  for (const order of orders) {
    const row = document.createElement("tr");
    const id = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = order.order_id || "—";
    button.addEventListener("click", () => {
      $("#trackId").value = order.order_id || "";
      if (order.order_id) trackOrder(order.order_id);
    });
    id.append(button);
    const status = document.createElement("td");
    status.textContent = order.status || "—";
    status.className = STATUS_CLASS[order.status] || "";
    const total = document.createElement("td");
    total.textContent = money(order.total);
    const address = document.createElement("td");
    address.textContent = order.delivery_address || "—";
    const created = document.createElement("td");
    created.textContent = when(order.created_at);
    row.append(id, status, total, address, created);
    body.append(row);
  }
}

async function loadOrders() {
  const result = await apiRequest(PATHS.orders);
  if (!result.ok) {
    state.orders = [];
    renderOrders();
    text("#ordersMessage", describeApiError(result.status, result.data));
    return;
  }
  const orders = asList(result.data);
  if (!orders) {
    state.orders = [];
    renderOrders();
    text("#ordersMessage", "GET /api/orders respondió, pero el cuerpo no es una lista.");
    return;
  }
  state.orders = orders;
  fillStatusFilter();
  renderOrders();
  text("#ordersMessage", orders.length ? "" : "No hay pedidos guardados.");
}

function renderTracking(order) {
  const root = $("#trackingResult");
  root.replaceChildren();
  const title = document.createElement("h3");
  title.textContent = order.order_id || "Pedido";
  const summary = document.createElement("p");
  summary.textContent = `${order.status || "SIN ESTADO"} · ${order.delivery_address || "Sin dirección"} · ${money(order.total)}`;
  root.append(title, summary);
  const items = asList(order.items) || [];
  if (items.length) {
    const list = document.createElement("ul");
    list.className = "draft-list";
    for (const item of items) {
      const row = document.createElement("li");
      row.textContent = `${item.product_id || "producto"} × ${item.quantity ?? "—"}`;
      list.append(row);
    }
    root.append(list);
  }
  const history = asList(order.history) || [];
  const timeline = document.createElement("div");
  timeline.className = "timeline";
  const steps = history.length
    ? history
    : [{ status: order.status || "SIN HISTORIAL", created_at: order.created_at }];
  for (const step of steps) {
    const item = document.createElement("article");
    item.className = "timeline-item";
    const name = document.createElement("strong");
    name.textContent = step.status || "SIN ESTADO";
    name.className = STATUS_CLASS[step.status] || "";
    const time = document.createElement("p");
    time.textContent = when(step.created_at);
    item.append(name, time);
    timeline.append(item);
  }
  root.append(timeline);
}

async function trackOrder(orderId) {
  const result = await apiRequest(orderPath(orderId));
  if (!result.ok) {
    const root = $("#trackingResult");
    root.replaceChildren();
    const message = document.createElement("p");
    message.className = "field-error";
    message.textContent = describeApiError(result.status, result.data);
    root.append(message);
    return;
  }
  renderTracking(result.data || {});
}

async function refresh() {
  await Promise.all([loadPlatform(), loadServices(), loadCatalog(), loadInventory(), loadOrders()]);
}

$("#addItem").addEventListener("click", addDraftItem);
$("#orderForm").addEventListener("submit", submitOrder);
$("#search").addEventListener("input", renderOrders);
$("#statusFilter").addEventListener("change", renderOrders);
$("#trackForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const orderId = $("#trackId").value.trim();
  if (orderId) trackOrder(orderId);
});
$("#refresh").addEventListener("click", refresh);

for (const status of Object.keys(STATUS_CLASS)) {
  const option = document.createElement("option");
  option.value = status;
  option.textContent = status;
  $("#statusFilter").append(option);
}

refresh();
