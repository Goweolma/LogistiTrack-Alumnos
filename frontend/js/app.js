const app = document.querySelector('#app');
const nav = document.querySelector('#navigation');
const $ = (selector, root = document) => root.querySelector(selector);
const state = { products: [], orders: [], inventory: null };

const routes = {
  '/usuario/pedido': { role: 'usuario', title: 'Crear un pedido', eyebrow: 'ESPACIO DE USUARIO', render: renderNewOrder },
  '/usuario/seguimiento': { role: 'usuario', title: 'Seguimiento', eyebrow: 'ESPACIO DE USUARIO', render: renderTracking },
  '/admin/tablero': { role: 'admin', title: 'Panel de operaciones', eyebrow: 'CENTRO DE CONTROL', render: renderDashboard },
  '/admin/pedidos': { role: 'admin', title: 'Gestión de pedidos', eyebrow: 'CENTRO DE CONTROL', render: renderOrders },
  '/admin/inventario': { role: 'admin', title: 'Inventario', eyebrow: 'CENTRO DE CONTROL', render: renderInventory },
  '/admin/salud': { role: 'admin', title: 'Salud de servicios', eyebrow: 'CENTRO DE CONTROL', render: renderHealth }
};
const menus = {
  usuario: [['/usuario/pedido', '＋', 'Nuevo pedido'], ['/usuario/seguimiento', '⌖', 'Seguir pedido']],
  admin: [['/admin/tablero', '▦', 'Resumen'], ['/admin/pedidos', '☷', 'Pedidos'], ['/admin/inventario', '▤', 'Inventario'], ['/admin/salud', '◉', 'Servicios']]
};

function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
}
function money(value) { return new Intl.NumberFormat('es-MX', { style: 'currency', currency: 'MXN' }).format(Number(value) || 0); }
function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? escapeHtml(value) : date.toLocaleString('es-MX', { dateStyle: 'medium', timeStyle: 'short' });
}
function statusClass(status = '') {
  const normalized = status.toUpperCase();
  if (['DELIVERED', 'BASE_READY', 'HEALTHY', 'READY'].includes(normalized)) return 'success';
  if (['INVENTORY_REJECTED', 'FAILED', 'ERROR', 'UNAVAILABLE'].includes(normalized)) return 'danger';
  if (['DEGRADED', 'PREPARING', 'IN_TRANSIT', 'DRIVER_ASSIGNED'].includes(normalized)) return 'warning';
  return 'info';
}
function badge(status) { const value = status || 'SIN DATOS'; return `<span class="pill ${statusClass(value)}">${escapeHtml(value.replaceAll('_', ' '))}</span>`; }
function setPage(route) {
  document.querySelector('#pageTitle').textContent = route.title;
  document.querySelector('#pageEyebrow').textContent = route.eyebrow;
  const active = (location.hash.slice(1).split('?')[0]) || '/usuario/pedido';
  document.querySelectorAll('[data-role-link]').forEach(link => link.classList.toggle('active', link.dataset.roleLink === route.role));
  document.querySelector('#navLabel').textContent = route.role === 'admin' ? 'ADMINISTRACIÓN' : 'MI ESPACIO';
  nav.innerHTML = menus[route.role].map(([path, icon, label]) => `<a class="nav-link ${active === path ? 'active' : ''}" href="#${path}"><span class="nav-icon">${icon}</span>${label}</a>`).join('');
}
function resolveRoute() {
  let path = (location.hash.slice(1).split('?')[0]) || '/usuario/pedido';
  if (path === '/salud') path = '/admin/salud';
  if (path === '/pedido') path = '/usuario/pedido';
  if (path === '/tablero') path = '/admin/pedidos';
  if (path === '/seguimiento') path = '/usuario/seguimiento';
  if (path === '/inventario') path = '/admin/inventario';
  if (!routes[path]) { location.hash = '#/usuario/pedido'; return; }
  const route = routes[path];
  setPage(route);
  route.render();
}
async function api(path, options = {}) {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
  let data = {};
  try { data = await response.json(); } catch { data = {}; }
  if (!response.ok) {
    const error = new Error(data.detail || data.error || `Error HTTP ${response.status}`);
    error.status = response.status; error.data = data;
    throw error;
  }
  return data;
}
function pageHeading(title, subtitle, action = '') {
  return `<div class="page-heading"><div><h2>${title}</h2><p>${subtitle}</p></div>${action}</div>`;
}
function notice(text, type = '') { return `<div class="notice ${type}" role="status">${escapeHtml(text)}</div>`; }
function stat(label, value, note, icon, positive = false) {
  return `<article class="stat-card"><div class="stat-top"><span>${label}</span><span class="stat-icon">${icon}</span></div><strong>${value}</strong><span class="stat-note ${positive ? 'positive' : ''}">${note}</span></article>`;
}
function orderRows(orders) {
  if (!orders.length) return '<tr><td colspan="5"><div class="empty-state"><strong>No encontramos pedidos</strong>Prueba con otro filtro o búsqueda.</div></td></tr>';
  return orders.map(order => {
    const id = order.order_id || order.id || '—';
    return `<tr><td class="order-id">${escapeHtml(id)}</td><td>${escapeHtml(order.delivery_address || order.address || '—')}</td><td>${badge(order.status || 'UNKNOWN')}</td><td>${formatDate(order.created_at || order.updated_at)}</td><td><a class="btn secondary small" href="#/usuario/seguimiento?order_id=${encodeURIComponent(id)}">Ver detalle</a></td></tr>`;
  }).join('');
}
function renderDashboard() {
  app.innerHTML = `${pageHeading('Resumen de operaciones', 'Actividad reciente de pedidos y servicios.')}
    <section class="stats-grid" id="dashboardStats">${stat('PEDIDOS TOTALES', '—', 'Cargando información', '☷')}${stat('EN PROCESO', '—', 'Preparación y entrega', '↗')}${stat('ENTREGADOS', '—', 'Pedidos completados', '✓', true)}${stat('SERVICIOS', '—', 'Estado de la plataforma', '◉')}</section>
    <div class="quick-grid"><section class="panel"><div class="panel-head"><div><h3>Pedidos recientes</h3><p>Última actividad registrada</p></div><a class="btn secondary small" href="#/admin/pedidos">Ver todos →</a></div><div class="table-wrap"><table><thead><tr><th>Pedido</th><th>Dirección</th><th>Estado</th><th>Fecha</th><th></th></tr></thead><tbody id="recentOrders"><tr><td colspan="5" class="empty-state">Cargando pedidos…</td></tr></tbody></table></div></section>
    <section class="panel"><div class="panel-head"><div><h3>Servicios del sistema</h3><p>Disponibilidad general</p></div><a class="btn secondary small" href="#/admin/salud">Ver estado</a></div><div id="dashboardHealth" class="health-list"><div class="loading-card">Consultando…</div></div></section></div>`;
  Promise.allSettled([loadOrders(), loadHealth()]).then(([ordersResult, healthResult]) => {
    if (ordersResult.status === 'fulfilled') {
      const orders = state.orders;
      const inProgress = orders.filter(o => !['DELIVERED', 'INVENTORY_REJECTED'].includes((o.status || '').toUpperCase())).length;
      const delivered = orders.filter(o => (o.status || '').toUpperCase() === 'DELIVERED').length;
      $('#dashboardStats').innerHTML = `${stat('PEDIDOS TOTALES', orders.length, 'Pedidos registrados', '☷')}${stat('EN PROCESO', inProgress, 'Preparación y entrega', '↗')}${stat('ENTREGADOS', delivered, 'Pedidos completados', '✓', true)}${stat('SERVICIOS', healthResult.status === 'fulfilled' ? healthResult.value.length : '—', 'Estado de la plataforma', '◉')}`;
      $('#recentOrders').innerHTML = orderRows(orders.slice(0, 5));
    } else $('#recentOrders').innerHTML = `<tr><td colspan="5">${notice(`No se pudieron cargar pedidos: ${ordersResult.reason.message}`, 'error')}</td></tr>`;
    $('#dashboardHealth').innerHTML = healthResult.status === 'fulfilled' ? healthCards(healthResult.value) : notice('No se pudo consultar el estado de los servicios.', 'error');
  });
}
async function loadOrders() {
  const data = await api('/api/orders');
  state.orders = Array.isArray(data) ? data : (data.orders || data.items || []);
  return state.orders;
}
async function loadHealth() {
  const checks = [
    ['Pedidos', '/api/health'], ['Inventario', '/api/services/inventory/health'],
    ['Almacén', '/api/services/warehouse/health'], ['Reparto', '/api/services/delivery/health']
  ];
  return Promise.all(checks.map(async ([name, url]) => {
    try { const data = await api(url); return { name, status: data.status || 'HEALTHY', detail: data.message || 'Servicio disponible' }; }
    catch (error) { return { name, status: error.status === 503 ? (error.data.status || 'DEGRADED') : 'UNAVAILABLE', detail: error.message }; }
  }));
}
function healthCards(services) {
  return services.map(service => `<div class="health-item"><div><div class="health-name">${escapeHtml(service.name)}</div><div class="health-meta">${escapeHtml(service.detail)}</div></div>${badge(service.status)}</div>`).join('');
}
function renderHealth() {
  app.innerHTML = `${pageHeading('Estado de servicios', 'Disponibilidad de los componentes de LogistiTrack.', '<button class="btn secondary" id="refreshHealth">↻ Actualizar</button>')}<section class="panel"><div class="panel-head"><div><h3>Monitor de plataforma</h3><p>El estado se consulta directamente a cada servicio.</p></div><span class="pill info">EN VIVO</span></div><div id="healthList" class="health-list"><div class="loading-card">Consultando servicios…</div></div></section><section class="callout"><span class="callout-icon">i</span>Un servicio no disponible puede limitar algunas operaciones. El panel muestra su respuesta actual.</section>`;
  const refresh = async () => { $('#healthList').innerHTML = '<div class="loading-card">Consultando servicios…</div>'; $('#healthList').innerHTML = healthCards(await loadHealth()); };
  $('#refreshHealth').addEventListener('click', refresh); refresh();
}
function renderOrders() {
  app.innerHTML = `${pageHeading('Todos los pedidos', 'Busca por identificador o dirección y filtra por estado.', '<a class="btn" href="#/usuario/pedido">＋ Nuevo pedido</a>')}<section class="panel"><div class="toolbar"><div class="search-wrap"><input id="orderSearch" class="search-input" type="search" placeholder="Buscar pedido o dirección…" aria-label="Buscar pedido"></div><select id="statusFilter" class="filter-select" aria-label="Filtrar por estado"><option value="">Todos los estados</option><option>RECEIVED</option><option>INVENTORY_RESERVED</option><option>PREPARING</option><option>READY_FOR_DELIVERY</option><option>DRIVER_ASSIGNED</option><option>IN_TRANSIT</option><option>NEAR_DESTINATION</option><option>DELIVERED</option><option>INVENTORY_REJECTED</option></select><button id="refreshOrders" class="btn secondary">↻ Actualizar</button></div><div id="ordersNotice"></div><div class="table-wrap"><table><thead><tr><th>Pedido</th><th>Dirección de entrega</th><th>Estado</th><th>Fecha</th><th>Acción</th></tr></thead><tbody id="ordersBody"><tr><td colspan="5" class="empty-state">Cargando pedidos…</td></tr></tbody></table></div></section>`;
  const apply = () => { const query = $('#orderSearch').value.trim().toLowerCase(); const status = $('#statusFilter').value; const filtered = state.orders.filter(order => (!status || order.status === status) && (!query || `${order.order_id} ${order.delivery_address}`.toLowerCase().includes(query))); $('#ordersBody').innerHTML = orderRows(filtered); };
  $('#orderSearch').addEventListener('input', apply); $('#statusFilter').addEventListener('change', apply);
  const refresh = async () => { $('#ordersNotice').innerHTML = ''; try { await loadOrders(); apply(); } catch (error) { $('#ordersNotice').innerHTML = notice(`No se pudieron cargar los pedidos: ${error.message}`, 'error'); $('#ordersBody').innerHTML = ''; } };
  $('#refreshOrders').addEventListener('click', refresh); refresh();
}
function renderNewOrder() {
  app.innerHTML = `${pageHeading('¿Qué necesitas enviar?', 'Completa los datos y consulta el avance de tu entrega.')}<div class="hero"><div><h2>Tu entrega empieza aquí</h2><p>Crea un pedido y podrás seguir su recorrido en tiempo real.</p></div><a class="btn" href="#/usuario/seguimiento">⌖ Seguir pedido</a></div><section class="panel"><div class="panel-head"><div><h3>Datos del pedido</h3><p>Los campos marcados son necesarios para procesar la solicitud.</p></div><span class="pill info">NUEVO</span></div><div id="orderNotice"></div><form id="orderForm"><div class="form-grid"><div class="field full"><label for="deliveryAddress">Dirección de entrega</label><input id="deliveryAddress" name="delivery_address" required minlength="5" placeholder="Calle, número, colonia, ciudad"></div><div class="field full"><label>Productos</label><div id="orderItems"></div><button type="button" class="btn secondary small" id="addItem">＋ Agregar producto</button></div></div><div class="form-footer"><span class="form-hint">El total se confirma al procesar el pedido.</span><button type="submit" class="btn" id="submitOrder">Crear pedido →</button></div></form></section>`;
  loadProducts(); addOrderItem();
  $('#addItem').addEventListener('click', () => addOrderItem());
  $('#orderForm').addEventListener('submit', submitOrder);
}
async function loadProducts() {
  try {
    const data = await api('/api/products'); state.products = Array.isArray(data) ? data : (data.products || []);
    if (!state.products.length) { $('#orderItems').innerHTML = notice('El catálogo está vacío. No hay productos disponibles para agregar.', 'error'); return; }
    renderItemSelects();
  } catch (error) {
    $('#orderItems').innerHTML = notice(`No se pudo cargar el catálogo: ${error.message}. El pedido no puede enviarse hasta que el servicio esté disponible.`, 'error');
    $('#addItem').disabled = true; $('#submitOrder').disabled = true;
  }
}
function addOrderItem() {
  if (!state.products.length) { $('#orderItems').innerHTML = '<div class="loading-card">Cargando catálogo…</div>'; return; }
  const row = document.createElement('div'); row.className = 'item-row';
  row.innerHTML = `<div class="field"><label>Producto</label><select class="product-select" required>${state.products.map(product => `<option value="${escapeHtml(product.product_id)}">${escapeHtml(product.name)} · ${money(product.price)}</option>`).join('')}</select></div><div class="field"><label>Cantidad</label><input type="number" class="quantity-input" min="1" step="1" value="1" required></div><button type="button" class="item-remove" aria-label="Quitar producto">×</button>`;
  row.querySelector('.item-remove').addEventListener('click', () => { if ($('#orderItems').querySelectorAll('.item-row').length > 1) row.remove(); });
  $('#orderItems').append(row);
}
function renderItemSelects() { $('#orderItems').innerHTML = ''; addOrderItem(); }
async function submitOrder(event) {
  event.preventDefault(); const button = $('#submitOrder'); button.disabled = true; button.textContent = 'Enviando…'; $('#orderNotice').innerHTML = '';
  const items = [...document.querySelectorAll('.item-row')].map(row => ({ product_id: row.querySelector('.product-select').value, quantity: Number(row.querySelector('.quantity-input').value) }));
  try {
    const result = await api('/api/orders', { method: 'POST', body: JSON.stringify({ delivery_address: $('#deliveryAddress').value.trim(), items }) });
    $('#orderNotice').innerHTML = notice(`Pedido creado correctamente. Identificador: ${result.order_id}.`, 'success');
    if (result.order_id) { sessionStorage.setItem('lastOrderId', result.order_id); setTimeout(() => { location.hash = `#/usuario/seguimiento?order_id=${encodeURIComponent(result.order_id)}`; }, 1000); }
  } catch (error) {
    if (error.status === 503 && error.data.order_id) {
      $('#orderNotice').innerHTML = notice(`El pedido ${error.data.order_id} fue guardado, pero la confirmación está pendiente. Abriendo su seguimiento; no lo vuelvas a enviar.`, '');
      sessionStorage.setItem('lastOrderId', error.data.order_id);
      setTimeout(() => { location.hash = `#/usuario/seguimiento?order_id=${encodeURIComponent(error.data.order_id)}`; }, 1200);
    } else {
      const message = error.status === 400 ? error.data.detail : error.status === 501 ? 'La API todavía no implementa la creación de pedidos.' : error.message;
      $('#orderNotice').innerHTML = notice(`No se creó el pedido: ${message}`, 'error');
    }
  } finally { button.disabled = false; button.textContent = 'Crear pedido →'; }
}
function renderTracking() {
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  const initialId = params.get('order_id') || sessionStorage.getItem('lastOrderId') || '';
  app.innerHTML = `${pageHeading('Sigue tu entrega', 'Consulta el estado y el historial de un pedido.')}<section class="panel"><div class="panel-head"><div><h3>Buscar pedido</h3><p>Ingresa el identificador que recibiste al crear tu pedido.</p></div><span class="callout-icon">⌖</span></div><form id="trackingForm" class="tracking-search"><input id="trackingId" class="search-input" value="${escapeHtml(initialId)}" placeholder="Ej. ORD-12345" required aria-label="Identificador del pedido"><button class="btn" type="submit">Consultar →</button></form><div id="trackingResult"></div></section><section class="callout"><span class="callout-icon">i</span>El historial muestra los eventos conforme los procesa el sistema logístico.</section>`;
  $('#trackingForm').addEventListener('submit', event => { event.preventDefault(); fetchTracking($('#trackingId').value.trim()); });
  if (initialId) fetchTracking(initialId);
}
async function fetchTracking(id) {
  const result = $('#trackingResult'); result.innerHTML = '<div class="loading-card">Buscando pedido…</div>';
  try {
    const order = await api(`/api/orders/${encodeURIComponent(id)}`);
    const history = order.history || [];
    result.innerHTML = `<div class="panel-head tracking-summary"><div><p class="eyebrow">PEDIDO</p><h3 class="order-id">${escapeHtml(order.order_id || id)}</h3></div>${badge(order.status || 'UNKNOWN')}</div>${order.delivery_address ? `<p class="form-hint">Entrega en: ${escapeHtml(order.delivery_address)}</p>` : ''}<div class="timeline">${history.length ? history.map(event => `<div class="timeline-item done"><div class="timeline-title">${escapeHtml(event.status || event.event_type || event.event || 'Actualización')}</div><div class="timeline-time">${formatDate(event.timestamp || event.created_at || event.occurred_at)}${event.detail ? ` · ${escapeHtml(event.detail)}` : ''}</div></div>`).join('') : '<div class="empty-state">Aún no hay eventos registrados para este pedido.</div>'}</div>`;
  } catch (error) { result.innerHTML = notice(error.status === 404 ? 'No encontramos un pedido con ese identificador.' : `No se pudo consultar el pedido: ${error.message}`, 'error'); }
}
function renderInventory() {
  app.innerHTML = `${pageHeading('Existencias por almacén', 'Consulta disponibilidad de productos en las sedes Norte y Sur.', '<button class="btn secondary" id="refreshInventory">↻ Actualizar</button>')}<div id="inventoryNotice"></div><section id="inventoryContent" class="panel"><div class="loading-card">Cargando existencias…</div></section><section class="callout"><span class="callout-icon">i</span>La existencia se consulta desde el servicio de inventario. El precio del catálogo no representa stock.</section>`;
  const refresh = async () => {
    $('#inventoryNotice').innerHTML = ''; $('#inventoryContent').innerHTML = '<div class="loading-card">Cargando existencias…</div>';
    try {
      const data = await api('/api/inventory'); state.inventory = data;
      const products = data.products || data.items || (data.product_id ? [data] : []);
      $('#inventoryContent').innerHTML = products.length ? `<div class="product-grid">${products.map(product => `<article class="product-card"><h4>${escapeHtml(product.name || product.product_id)}</h4><p>${escapeHtml(product.description || product.product_id || '')}</p><div class="stock-line"><span>Norte</span><strong>${Number(product.stock?.NORTE ?? product.north ?? 0)}</strong></div><div class="stock-line"><span>Sur</span><strong>${Number(product.stock?.SUR ?? product.south ?? 0)}</strong></div><div class="stock-line"><span>Total</span><strong>${Number(product.total ?? (Number(product.stock?.NORTE || 0) + Number(product.stock?.SUR || 0)))}</strong></div></article>`).join('')}</div>` : '<div class="empty-state"><strong>Sin existencias para mostrar</strong>La API respondió, pero no devolvió productos.</div>';
    } catch (error) { $('#inventoryContent').innerHTML = ''; $('#inventoryNotice').innerHTML = notice(`No se pudo consultar inventario: ${error.message}`, 'error'); }
  };
  $('#refreshInventory').addEventListener('click', refresh); refresh();
}

document.querySelector('#today').textContent = new Date().toLocaleDateString('es-MX', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
window.addEventListener('hashchange', resolveRoute);
resolveRoute();
