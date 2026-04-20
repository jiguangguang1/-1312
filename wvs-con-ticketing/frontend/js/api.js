/**
 * API 客户端
 */
const API = {
  BASE: window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? `http://${window.location.hostname}:5000`
    : '',

  getToken() {
    return localStorage.getItem('wvs_token');
  },

  setToken(token) {
    localStorage.setItem('wvs_token', token);
  },

  clearToken() {
    localStorage.removeItem('wvs_token');
    localStorage.removeItem('wvs_user');
  },

  getUser() {
    const u = localStorage.getItem('wvs_user');
    return u ? JSON.parse(u) : null;
  },

  setUser(user) {
    localStorage.setItem('wvs_user', JSON.stringify(user));
  },

  isLoggedIn() {
    return !!this.getToken();
  },

  async request(path, options = {}) {
    const url = `${this.BASE}${path}`;
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    const token = this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    try {
      const res = await fetch(url, { ...options, headers });
      const data = await res.json();

      if (!res.ok) {
        if (res.status === 401) {
          this.clearToken();
          window.location.href = '/';
        }
        throw new Error(data.error || `请求失败 (${res.status})`);
      }

      return data;
    } catch (err) {
      if (err.message === 'Failed to fetch') {
        throw new Error('无法连接到服务器，请确认后端已启动');
      }
      throw err;
    }
  },

  // Auth
  login(username, password) {
    return this.request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  },

  register(username, email, password) {
    return this.request('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, email, password }),
    });
  },

  getMe() {
    return this.request('/api/auth/me');
  },

  updateProfile(data) {
    return this.request('/api/auth/profile', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  // Orders
  getOrders(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.request(`/api/orders?${qs}`);
  },

  getOrder(id) {
    return this.request(`/api/orders/${id}`);
  },

  createOrder(data) {
    return this.request('/api/orders', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  updateOrder(id, data) {
    return this.request(`/api/orders/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  deleteOrder(id) {
    return this.request(`/api/orders/${id}`, {
      method: 'DELETE',
    });
  },

  startGrabber(id) {
    return this.request(`/api/orders/${id}/start`, {
      method: 'POST',
    });
  },

  getOrderLogs(id, params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.request(`/api/orders/${id}/logs?${qs}`);
  },

  // Admin
  getAdminDashboard() {
    return this.request('/api/admin/dashboard');
  },

  getAdminUsers(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.request(`/api/admin/users?${qs}`);
  },

  getAdminOrders(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.request(`/api/admin/orders?${qs}`);
  },

  updateOrderStatus(id, data) {
    return this.request(`/api/admin/orders/${id}/status`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  // Ticket Classes
  getTicketClasses(orderId) {
    const qs = orderId ? `?order_id=${orderId}` : '';
    return this.request(`/api/ticket-classes${qs}`);
  },

  createTicketClass(data) {
    return this.request('/api/ticket-classes', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  updateTicketClass(id, data) {
    return this.request(`/api/ticket-classes/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  deleteTicketClass(id) {
    return this.request(`/api/ticket-classes/${id}`, {
      method: 'DELETE',
    });
  },

  getAdminTicketClasses() {
    return this.request('/api/admin/ticket-classes');
  },

  updateTicketClassStatus(id, data) {
    return this.request(`/api/admin/ticket-classes/${id}/status`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  // Accounts (多账号)
  getAccounts(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.request(`/api/accounts?${qs}`);
  },

  createAccount(data) {
    return this.request('/api/accounts', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  updateAccount(id, data) {
    return this.request(`/api/accounts/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  deleteAccount(id) {
    return this.request(`/api/accounts/${id}`, {
      method: 'DELETE',
    });
  },

  batchCreateAccounts(data) {
    return this.request('/api/accounts/batch', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // GetBlock
  getBlockNo(orderId, data) {
    return this.request(`/api/orders/${orderId}/get-block`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // 钉钉
  dingInit(orderId, webhook) {
    return this.request(`/api/orders/${orderId}/ding/init`, {
      method: 'POST',
      body: JSON.stringify({ webhook }),
    });
  },

  dingPush(orderId, message) {
    return this.request(`/api/orders/${orderId}/ding/push`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
  },
};

// Toast 通知
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add('show'));

  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// 模态框
function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('active');
}

// 状态标签
function statusBadge(status) {
  const labels = {
    pending: '待启动',
    waiting: '等待中',
    grabbing: '抢票中',
    success: '✅ 成功',
    failed: '❌ 失败',
    sold_out: '😢 售罄',
    error: '⚠️ 异常',
  };
  return `<span class="badge badge-${status}">${labels[status] || status}</span>`;
}

// 座位标签
const SEAT_LABELS = {
  0: 'VIP 站席',
  1: 'VIP 坐席',
  2: 'SR',
  3: 'R',
  4: 'S',
  5: 'A',
};
