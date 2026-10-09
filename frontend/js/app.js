const app = document.querySelector('#app');
const nav = document.querySelector('#navigation');
const $ = (selector, root = document) => root.querySelector(selector);
const state = { packageSizes: [], orders: [], inventory: null };

const routes = {
  '/acceso': { role: null, title: 'Bienvenido a Ray-o', eyebrow: 'ENVÍOS SENCILLOS', render: renderAccess },
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
  document.querySelector('.app-shell').classList.toggle('access-mode', !route.role);
  if (!route.role) { nav.innerHTML = ''; return; }
  const active = (location.hash.slice(1).split('?')[0]) || '/usuario/pedido';
  document.querySelectorAll('[data-role-link]').forEach(link => link.classList.toggle('active', link.dataset.roleLink === route.role));
  document.querySelector('#navLabel').textContent = route.role === 'admin' ? 'ADMINISTRACIÓN' : 'MI ESPACIO';
  nav.innerHTML = `${menus[route.role].map(([path, icon, label]) => `<a class="nav-link ${active === path ? 'active' : ''}" href="#${path}"><span class="nav-icon">${icon}</span>${label}</a>`).join('')}<button class="nav-link logout-link" id="logoutButton" type="button"><span class="nav-icon">↪</span>Cerrar sesión</button>`;
  $('#logoutButton').addEventListener('click', logout);
}
function resolveRoute() {
  let path = (location.hash.slice(1).split('?')[0]) || '/acceso';
  if (path === '/salud') path = '/admin/salud';
  if (path === '/pedido') path = '/usuario/pedido';
  if (path === '/tablero') path = '/admin/pedidos';
  if (path === '/seguimiento') path = '/usuario/seguimiento';
  if (path === '/inventario') path = '/admin/inventario';
  if (!routes[path]) { location.hash = '#/acceso'; return; }
  const route = routes[path];
  const user = getSessionUser();
  if (route.role && !user) { location.hash = '#/acceso'; return; }
  if (route.role && user.role !== route.role) {
    location.hash = user.role === 'admin' ? '#/admin/tablero' : '#/usuario/pedido';
    return;
  }
  if (!route.role && user) {
    location.hash = user.role === 'admin' ? '#/admin/tablero' : '#/usuario/pedido';
    return;
  }
  setPage(route);
  route.render();
}
function getSessionUser() {
  try { return JSON.parse(sessionStorage.getItem('rayOUser') || 'null'); }
  catch { sessionStorage.removeItem('rayOUser'); return null; }
}
function logout() {
  sessionStorage.removeItem('rayOUser');
  sessionStorage.removeItem('rayOToken');
  location.hash = '#/acceso';
  resolveRoute();
}
async function api(path, options = {}) {
  const token = sessionStorage.getItem('rayOToken');
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) }, ...options });
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
function renderAccess() {
  app.innerHTML = `<section class="access-card"><a class="access-brand" href="#/acceso"><span class="brand-mark">R</span><span>Ray-o<small>ENVÍOS SENCILLOS</small></span></a><p class="eyebrow access-eyebrow">BIENVENIDO</p><h2>¿Cómo quieres continuar?</h2><p class="access-intro">Elige tu tipo de cuenta para entrar a Ray-o.</p><div id="accessPanel"></div></section>`;
  renderRoleChoices();
}
function renderRoleChoices() {
  $('#accessPanel').innerHTML = `<div class="role-choices"><button class="role-card" id="chooseUser" type="button"><span class="role-card-icon">♙</span><strong>Soy usuario</strong><span>Crear y seguir mis envíos</span><span class="role-arrow">→</span></button><button class="role-card" id="chooseAdmin" type="button"><span class="role-card-icon admin-icon">▦</span><strong>Soy administrador</strong><span>Entrar al panel de operaciones</span><span class="role-arrow">→</span></button></div>`;
  $('#chooseUser').addEventListener('click', renderUserOptions);
  $('#chooseAdmin').addEventListener('click', () => renderEmailLogin('admin'));
}
function renderUserOptions() {
  $('#accessPanel').innerHTML = `<div class="auth-options"><button class="btn" id="createAccount" type="button">Crear cuenta</button><button class="btn secondary" id="existingAccount" type="button">Ya tengo una cuenta</button><button class="back-link" id="backToRoles" type="button">← Volver</button></div>`;
  $('#createAccount').addEventListener('click', renderRegistration);
  $('#existingAccount').addEventListener('click', () => renderEmailLogin('usuario'));
  $('#backToRoles').addEventListener('click', renderRoleChoices);
}
function renderEmailLogin(role) {
  const title = role === 'admin' ? 'Acceso de administrador' : 'Iniciar sesión';
  $('#accessPanel').innerHTML = `<form id="emailLoginForm" class="auth-form"><h3>${title}</h3><p>Ingresa el correo y la contraseña de tu cuenta. No enviaremos códigos temporales.</p><div class="field"><label for="loginEmail">Correo electrónico</label><input id="loginEmail" type="email" autocomplete="email" required placeholder="nombre@correo.com"></div><div class="field"><label for="loginPassword">Contraseña</label><input id="loginPassword" type="password" autocomplete="current-password" required placeholder="Tu contraseña"></div><div id="authNotice"></div><button class="btn auth-submit" type="submit">Continuar →</button><button class="back-link" id="authBack" type="button">← Volver</button></form>`;
  $('#emailLoginForm').addEventListener('submit', event => loginByEmail(event, role));
  $('#authBack').addEventListener('click', role === 'admin' ? renderRoleChoices : renderUserOptions);
}
function renderRegistration() {
  $('#accessPanel').innerHTML = `<form id="registerForm" class="auth-form"><h3>Crear cuenta de usuario</h3><p>Completa tus datos para preparar tus envíos.</p><div class="field"><label for="registerName">Nombre completo</label><input id="registerName" name="name" autocomplete="name" required placeholder="Tu nombre"></div><div class="field"><label for="registerEmail">Correo electrónico</label><input id="registerEmail" name="email" type="email" autocomplete="email" required placeholder="nombre@correo.com"></div><div class="field"><label for="registerPhone">Número de teléfono</label><input id="registerPhone" name="phone" type="tel" autocomplete="tel" required placeholder="+52 55 1234 5678"></div><div class="field"><label for="registerAddress">Dirección</label><input id="registerAddress" name="address" autocomplete="street-address" required placeholder="Calle, número, colonia y ciudad"></div><div class="field"><label for="registerPassword">Contraseña</label><input id="registerPassword" name="password" type="password" autocomplete="new-password" minlength="8" required placeholder="Mínimo 8 caracteres"></div><div class="field"><label for="confirmPassword">Confirmar contraseña</label><input id="confirmPassword" type="password" autocomplete="new-password" minlength="8" required placeholder="Repite tu contraseña"></div><div id="authNotice"></div><button class="btn auth-submit" type="submit">Crear cuenta →</button><button class="back-link" id="authBack" type="button">← Volver</button></form>`;
  $('#registerForm').addEventListener('submit', registerUser);
  $('#authBack').addEventListener('click', renderUserOptions);
}
async function loginByEmail(event, requestedRole) {
  event.preventDefault();
  const button = $('#emailLoginForm button[type="submit"]');
  button.disabled = true; button.textContent = 'Entrando…'; $('#authNotice').innerHTML = '';
  const email = $('#loginEmail').value.trim();
  const password = $('#loginPassword').value;
  try {
    const data = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password, requested_role: requestedRole === 'admin' ? 'admin' : 'user' }) });
    const user = data.user || data;
    const role = normalizeRole(user.role || data.role);
    if (role !== requestedRole) throw new Error('El correo no tiene acceso a esta interfaz.');
    establishSession(user, role, email, data.token || data.access_token);
  } catch (error) {
    $('#authNotice').innerHTML = notice(error.message || 'No fue posible iniciar sesión.', 'error');
    button.disabled = false; button.textContent = 'Continuar →';
  }
}
async function registerUser(event) {
  event.preventDefault();
  const button = $('#registerForm button[type="submit"]');
  button.disabled = true; button.textContent = 'Creando cuenta…'; $('#authNotice').innerHTML = '';
  const password = $('#registerPassword').value;
  if (password !== $('#confirmPassword').value) {
    $('#authNotice').innerHTML = notice('Las contraseñas no coinciden.', 'error');
    button.disabled = false; button.textContent = 'Crear cuenta →';
    return;
  }
  const account = { name: $('#registerName').value.trim(), email: $('#registerEmail').value.trim(), phone: $('#registerPhone').value.trim(), address: $('#registerAddress').value.trim(), password };
  try {
    const data = await api('/api/auth/register', { method: 'POST', body: JSON.stringify(account) });
    const user = data.user || { ...account, ...(data.profile || {}) };
    establishSession(user, 'usuario', account.email, data.token || data.access_token);
  } catch (error) {
    $('#authNotice').innerHTML = notice(error.message || 'No fue posible crear la cuenta.', 'error');
    button.disabled = false; button.textContent = 'Crear cuenta →';
  }
}
function normalizeRole(role = '') {
  const value = String(role).toLowerCase();
  return ['admin', 'administrator', 'administrador'].includes(value) ? 'admin' : ['user', 'usuario', 'customer'].includes(value) ? 'usuario' : '';
}
function establishSession(user, role, email, token) {
  if (!role) throw new Error('La API no devolvió el rol de la cuenta.');
  sessionStorage.setItem('rayOUser', JSON.stringify({ ...user, email: user.email || email, role }));
  if (token) sessionStorage.setItem('rayOToken', token);
  location.hash = role === 'admin' ? '#/admin/tablero' : '#/usuario/pedido';
}
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
  app.innerHTML = `${pageHeading('Estado de servicios', 'Disponibilidad de los componentes de Ray-o.', '<button class="btn secondary" id="refreshHealth">↻ Actualizar</button>')}<section class="panel"><div class="panel-head"><div><h3>Monitor de plataforma</h3><p>El estado se consulta directamente a cada servicio.</p></div><span class="pill info">EN VIVO</span></div><div id="healthList" class="health-list"><div class="loading-card">Consultando servicios…</div></div></section><section class="callout"><span class="callout-icon">i</span>Un servicio no disponible puede limitar algunas operaciones. El panel muestra su respuesta actual.</section>`;
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
  app.innerHTML = `${pageHeading('Crea tu envío', 'Elige el tamaño del paquete y agrega la dirección de entrega.')}<div class="hero"><div><h2>Tu envío empieza aquí</h2><p>Selecciona el paquete que mejor se adapte a lo que vas a enviar.</p></div><a class="btn" href="#/usuario/seguimiento">⌖ Seguir pedido</a></div><section class="panel"><div class="panel-head"><div><h3>1. Elige el tamaño</h3><p>El precio mostrado corresponde al tamaño seleccionado.</p></div><span class="pill info">ENVÍO</span></div><div id="orderNotice"></div><form id="orderForm"><div id="packageSizes" class="size-options"><div class="loading-card">Cargando tamaños disponibles…</div></div><div class="form-grid order-address"><div class="field full"><label for="deliveryAddress">2. Dirección de entrega</label><input id="deliveryAddress" name="delivery_address" required minlength="5" placeholder="Calle, número, colonia, ciudad"></div></div><div class="price-summary"><span>Precio del envío</span><strong id="selectedPrice">Selecciona un tamaño</strong></div><div class="form-footer"><span class="form-hint">El precio final se confirma al crear el pedido.</span><button type="submit" class="btn" id="submitOrder" disabled>Crear pedido →</button></div></form></section>`;
  loadPackageSizes();
  $('#orderForm').addEventListener('submit', submitOrder);
}
async function loadPackageSizes() {
  try {
    const data = await api('/api/package-sizes');
    const sizes = Array.isArray(data) ? data : (data.package_sizes || data.sizes || []);
    state.packageSizes = sizes.filter(size => (size.is_active ?? size.active) !== false);
    if (!state.packageSizes.length) {
      $('#packageSizes').innerHTML = '<div class="empty-state"><strong>No hay tamaños disponibles</strong>Vuelve a intentarlo más tarde.</div>';
      return;
    }
    renderPackageSizes();
  } catch (error) {
    $('#packageSizes').innerHTML = notice(`No se pudo cargar el catálogo de tamaños: ${error.message}.`, 'error');
  }
}
function packageDimensions(size) {
  const dimensions = size.dimensions ?? size.measurements ?? size.measures ?? size.medidas;
  if (typeof dimensions === 'string') return dimensions;
  if (dimensions && typeof dimensions === 'object') {
    const { length, width, height, unit = 'cm' } = dimensions;
    if (length != null && width != null && height != null) return `${length} × ${width} × ${height} ${unit}`;
    return Object.values(dimensions).join(' × ');
  }
  return 'Medidas no especificadas';
}
function renderPackageSizes() {
  $('#packageSizes').innerHTML = state.packageSizes.map((size, index) => {
    const id = size.id ?? size.package_size_id;
    const maxWeight = size.max_weight_kg ?? size.max_weight ?? size.weight_limit_kg;
    const name = size.name ?? size.nombre ?? `Tamaño ${index + 1}`;
    return `<label class="size-option" for="packageSize${index}"><input id="packageSize${index}" type="radio" name="package_size_id" value="${escapeHtml(id)}" required><span class="size-check" aria-hidden="true"></span><span class="size-name">${escapeHtml(name)}</span><span class="size-dimensions">${escapeHtml(packageDimensions(size))}</span><span class="size-weight">Hasta ${escapeHtml(maxWeight ?? '—')} kg</span><strong class="size-price">${money(size.price)}</strong></label>`;
  }).join('');
  $('#packageSizes').querySelectorAll('input[name="package_size_id"]').forEach(input => input.addEventListener('change', updateSelectedPackagePrice));
  $('#submitOrder').disabled = true;
}
function updateSelectedPackagePrice() {
  const selectedId = $('input[name="package_size_id"]:checked')?.value;
  const selected = state.packageSizes.find(size => String(size.id ?? size.package_size_id) === selectedId);
  $('#selectedPrice').textContent = selected ? money(selected.price) : 'Selecciona un tamaño';
  $('#submitOrder').disabled = !selected;
}
async function submitOrder(event) {
  event.preventDefault(); const button = $('#submitOrder'); button.disabled = true; button.textContent = 'Enviando…'; $('#orderNotice').innerHTML = '';
  const selectedId = $('input[name="package_size_id"]:checked')?.value;
  const selectedSize = state.packageSizes.find(size => String(size.id ?? size.package_size_id) === selectedId);
  try {
    if (!selectedSize) throw new Error('Selecciona un tamaño para el paquete.');
    const result = await api('/api/orders', { method: 'POST', body: JSON.stringify({ package_size_id: selectedSize.id ?? selectedSize.package_size_id, delivery_address: $('#deliveryAddress').value.trim() }) });
    const confirmedPrice = result.confirmed_price ?? result.price ?? result.total ?? selectedSize.price;
    $('#orderNotice').innerHTML = notice(`Pedido creado correctamente. Identificador: ${result.order_id}. Precio confirmado: ${money(confirmedPrice)}.`, 'success');
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
