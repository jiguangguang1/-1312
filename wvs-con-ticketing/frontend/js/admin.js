/**
 * 管理后台逻辑 v2
 */

document.addEventListener('DOMContentLoaded', () => {
  if (!API.isLoggedIn()) {
    window.location.href = '/';
    return;
  }

  const user = API.getUser();
  if (!user?.is_admin) {
    showToast('需要管理员权限', 'error');
    window.location.href = '/dashboard';
    return;
  }

  loadAdminDashboard();
  loadAdminOrders();
});

// ---- Tab ----
function switchAdminTab(tab, btn) {
  document.querySelectorAll('.tabs .tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');

  document.getElementById('adminOrdersTab').classList.remove('active');
  document.getElementById('adminUsersTab').classList.remove('active');
  document.getElementById('adminSeatsTab').classList.remove('active');

  if (tab === 'orders') {
    document.getElementById('adminOrdersTab').classList.add('active');
    loadAdminOrders();
  } else if (tab === 'users') {
    document.getElementById('adminUsersTab').classList.add('active');
    loadAdminUsers();
  } else if (tab === 'seats') {
    document.getElementById('adminSeatsTab').classList.add('active');
    loadAdminTicketClasses();
  }
}

// ---- Dashboard ----
async function loadAdminDashboard() {
  try {
    const data = await API.getAdminDashboard();
    const s = data.stats;
    document.getElementById('adminTotalUsers').textContent = s.total_users;
    document.getElementById('adminTotalOrders').textContent = s.total_orders;
    document.getElementById('adminGrabbing').textContent = s.grabbing;
    document.getElementById('adminSuccess').textContent = s.success;
    document.getElementById('adminFailed').textContent = s.failed;
    document.getElementById('adminSoldOut').textContent = s.sold_out;
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ---- 订单列表 ----
async function loadAdminOrders() {
  const container = document.getElementById('adminOrdersList');
  const status = document.getElementById('orderStatusFilter').value;

  try {
    const data = await API.getAdminOrders({ status: status || undefined, per_page: 50 });
    const orders = data.orders || [];

    if (orders.length === 0) {
      container.innerHTML = '<p style="text-align:center; color:var(--text-dim); padding:40px;">暂无订单</p>';
      return;
    }

    container.innerHTML = `
      <div style="overflow-x:auto;">
        <table style="width:100%; border-collapse:collapse; font-size:0.85rem;">
          <thead>
            <tr style="text-align:left; border-bottom:1px solid rgba(255,255,255,0.1);">
              <th style="padding:8px;">ID</th>
              <th style="padding:8px;">用户</th>
              <th style="padding:8px;">类型</th>
              <th style="padding:8px;">场次</th>
              <th style="padding:8px;">时间</th>
              <th style="padding:8px;">状态</th>
              <th style="padding:8px;">订单号</th>
              <th style="padding:8px;">操作</th>
            </tr>
          </thead>
          <tbody>
            ${orders.map(o => `
              <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                <td style="padding:8px; font-weight:600;">#${o.id}</td>
                <td style="padding:8px;">用户${o.user_id}</td>
                <td style="padding:8px;">${o.is_presale ? '💎 预售' : '🎫 公售'}</td>
                <td style="padding:8px;">${o.schedule_label}</td>
                <td style="padding:8px; font-size:0.8rem; color:var(--text-dim);">${o.presale_time || o.open_time || '-'}</td>
                <td style="padding:8px;">${statusBadge(o.status)}</td>
                <td style="padding:8px; font-size:0.8rem; color:var(--success);">${o.order_no || '-'}</td>
                <td style="padding:8px;">
                  <select style="padding:4px 8px; border-radius:6px; background:var(--bg-card); border:1px solid rgba(255,255,255,0.1); color:var(--text); font-size:0.8rem;"
                          onchange="changeOrderStatus(${o.id}, this.value)">
                    <option value="">修改状态</option>
                    <option value="pending">待启动</option>
                    <option value="grabbing">抢票中</option>
                    <option value="success">成功</option>
                    <option value="failed">失败</option>
                    <option value="sold_out">售罄</option>
                    <option value="error">异常</option>
                  </select>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
      <p style="text-align:center; color:var(--text-muted); font-size:0.8rem; margin-top:12px;">
        共 ${data.total} 条 | 第 ${data.page}/${data.pages} 页
      </p>
    `;
  } catch (err) {
    container.innerHTML = `<p style="color:var(--error); padding:20px;">加载失败: ${err.message}</p>`;
  }
}

async function changeOrderStatus(id, newStatus) {
  if (!newStatus) return;
  if (!confirm(`将订单 #${id} 状态改为「${newStatus}」？`)) {
    loadAdminOrders();
    return;
  }

  try {
    await API.updateOrderStatus(id, { status: newStatus });
    showToast('状态已更新', 'success');
    loadAdminOrders();
    loadAdminDashboard();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ---- 用户列表 ----
async function loadAdminUsers() {
  const container = document.getElementById('adminUsersList');

  try {
    const data = await API.getAdminUsers({ per_page: 50 });
    const users = data.users || [];

    if (users.length === 0) {
      container.innerHTML = '<p style="text-align:center; color:var(--text-dim); padding:40px;">暂无用户</p>';
      return;
    }

    container.innerHTML = `
      <div style="overflow-x:auto;">
        <table style="width:100%; border-collapse:collapse; font-size:0.85rem;">
          <thead>
            <tr style="text-align:left; border-bottom:1px solid rgba(255,255,255,0.1);">
              <th style="padding:8px;">ID</th>
              <th style="padding:8px;">用户名</th>
              <th style="padding:8px;">邮箱</th>
              <th style="padding:8px;">管理员</th>
              <th style="padding:8px;">预售</th>
              <th style="padding:8px;">注册时间</th>
            </tr>
          </thead>
          <tbody>
            ${users.map(u => `
              <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                <td style="padding:8px; font-weight:600;">#${u.id}</td>
                <td style="padding:8px;">${u.username}</td>
                <td style="padding:8px; color:var(--text-dim);">${u.email}</td>
                <td style="padding:8px;">${u.is_admin ? '👑' : '-'}</td>
                <td style="padding:8px;">${u.has_presale ? '💎' : '-'}</td>
                <td style="padding:8px; color:var(--text-dim); font-size:0.8rem;">${formatTime(u.created_at)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<p style="color:var(--error); padding:20px;">加载失败: ${err.message}</p>`;
  }
}

// ---- 座位配置管理 ----
async function loadAdminTicketClasses() {
  const container = document.getElementById('adminSeatsList');

  try {
    const data = await API.getAdminTicketClasses();
    const tcs = data.ticket_classes || [];

    if (tcs.length === 0) {
      container.innerHTML = '<p style="text-align:center; color:var(--text-dim); padding:40px;">暂无座位配置，点击「添加档位」创建</p>';
      return;
    }

    container.innerHTML = `
      <div class="seat-config-grid" style="grid-template-columns:repeat(auto-fill, minmax(220px, 1fr));gap:12px;">
        ${tcs.map(tc => `
          <div class="seat-config-card" style="border-left:3px solid ${tc.color};position:relative;">
            <div class="seat-config-name">${tc.icon} ${tc.name}</div>
            <div class="seat-config-price">₩${tc.price.toLocaleString()}</div>
            <div style="font-size:0.78rem;color:var(--text-muted);margin-bottom:8px;">
              每人限购 ${tc.ticket_per_person} 张 | 总计 ${tc.total_seats || '?'} 座
            </div>
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
              ${tc.is_sold_out
                ? '<span class="badge badge-sold_out" style="cursor:pointer" onclick="toggleSoldOut('+tc.id+',false)">售罄 ✕</span>'
                : '<span class="badge badge-success" style="cursor:pointer" onclick="toggleSoldOut('+tc.id+',true)">在售 ✕</span>'
              }
              <button class="btn btn-sm btn-secondary" style="padding:4px 10px;font-size:0.75rem;" onclick="deleteTicketClass(${tc.id})">🗑️</button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<p style="color:var(--error); padding:20px;">加载失败: ${err.message}</p>`;
  }
}

async function toggleSoldOut(id, soldOut) {
  try {
    await API.updateTicketClassStatus(id, { is_sold_out: soldOut });
    showToast(soldOut ? '已标记售罄' : '已标记在售', 'success');
    loadAdminTicketClasses();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function deleteTicketClass(id) {
  if (!confirm('确定删除此座位档位？')) return;
  try {
    await API.deleteTicketClass(id);
    showToast('已删除', 'success');
    loadAdminTicketClasses();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function showAddTicketClassForm() {
  const name = prompt('座位名称（如 VIP站席、SR석）：');
  if (!name) return;
  const price = parseInt(prompt('票价（韩元，如 154000）：') || '0');
  const totalSeats = parseInt(prompt('总座位数（如 500）：') || '0');
  const icon = prompt('图标 emoji（如 🔥）：') || '🎫';
  const color = prompt('颜色 hex（如 #ef4444）：') || '#7c5cfc';

  API.createTicketClass({ name, price, total_seats: totalSeats, available_seats: totalSeats, icon, color })
    .then(() => {
      showToast('档位已添加', 'success');
      loadAdminTicketClasses();
    })
    .catch(err => showToast(err.message, 'error'));
}

// ---- 工具函数 ----
function formatTime(isoStr) {
  if (!isoStr) return '-';
  const d = new Date(isoStr);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
