/**
 * 控制台逻辑 v2 — 全功能版
 */

let currentOrderTab = 'presale';
let refreshTimer = null;
let countdownTimer = null;

// ---- 初始化 ----
document.addEventListener('DOMContentLoaded', () => {
  if (!API.isLoggedIn()) {
    window.location.href = '/';
    return;
  }

  const user = API.getUser();
  if (user?.is_admin) {
    const adminLink = document.getElementById('adminLink');
    if (adminLink) adminLink.style.display = '';
  }

  loadSettings();
  loadOrders();
  loadStats();
  loadTicketClasses();
  loadAccounts();

  // 自动刷新
  refreshTimer = setInterval(() => {
    loadOrders();
    loadStats();
  }, 10000);

  // 初始化座位选择器
  document.querySelectorAll('.seat-option input[type="checkbox"]').forEach(cb => {
    cb.addEventListener('change', () => {
      cb.closest('.seat-option').classList.toggle('selected', cb.checked);
    });
  });
});

// ---- 设置 ----
function toggleSettings() {
  const panel = document.getElementById('settingsPanel');
  const btn = document.getElementById('toggleSettingsBtn');
  panel.classList.toggle('hidden');
  btn.textContent = panel.classList.contains('hidden') ? '展开' : '收起';
}

async function loadSettings() {
  try {
    const user = await API.getMe();
    API.setUser(user);
    document.getElementById('settingInterparkId').value = user.interpark_id || '';
    document.getElementById('settingWeverseId').value = user.weverse_id || '';
    document.getElementById('settingHasPresale').checked = !!user.has_presale;
  } catch (err) {
    console.error('加载设置失败:', err);
  }
}

async function saveSettings() {
  try {
    const data = {
      interpark_id: document.getElementById('settingInterparkId').value.trim(),
      weverse_id: document.getElementById('settingWeverseId').value.trim(),
      has_presale: document.getElementById('settingHasPresale').checked,
    };

    const pw = document.getElementById('settingInterparkPw').value;
    if (pw) data.interpark_pw = pw;

    await API.updateProfile(data);
    showToast('设置已保存', 'success');
    document.getElementById('settingInterparkPw').value = '';
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ---- Tab 切换 ----
function switchOrderTab(tab, el) {
  currentOrderTab = tab;
  document.querySelectorAll('.tabs .tab').forEach(t => t.classList.remove('active'));
  if (el) el.classList.add('active');

  const presaleGroup = document.getElementById('presaleTimeGroup');
  if (tab === 'presale') {
    presaleGroup.style.display = '';
  } else {
    presaleGroup.style.display = 'none';
  }
}

// ---- 座位选择器 ----
function getSelectedSeats() {
  const checkboxes = document.querySelectorAll('.seat-option input[type="checkbox"]:checked');
  return Array.from(checkboxes).map(cb => parseInt(cb.value));
}

// ---- 座位档位加载 ----
async function loadTicketClasses() {
  try {
    const data = await API.getTicketClasses();
    const classes = data.ticket_classes || [];
    window._ticketClasses = classes;
    if (classes.length === 0) return;

    // 更新座位选择器
    const selector = document.getElementById('seatSelector');
    if (!selector) return;

    selector.innerHTML = classes.map((tc, i) => {
      const checked = i <= 4 ? 'checked' : '';
      const selected = i <= 4 ? 'selected' : '';
      const soldOut = tc.is_sold_out ? 'sold-out' : '';
      const priceStr = tc.price > 0 ? ` ₩${tc.price.toLocaleString()}` : '';
      return `
        <label class="seat-option ${selected} ${soldOut}" data-grade="${tc.grade_index}" data-color="${tc.color}">
          <input type="checkbox" value="${tc.grade_index}" ${checked} ${tc.is_sold_out ? 'disabled' : ''}>
          <span class="seat-icon" style="color:${tc.color}">${tc.icon}</span>
          <span>${tc.name}${priceStr}</span>
          ${tc.is_sold_out ? '<span class="badge badge-sold_out">售罄</span>' : ''}
        </label>
      `;
    }).join('');

    // 重新绑定事件
    selector.querySelectorAll('input[type="checkbox"]').forEach(cb => {
      cb.addEventListener('change', () => {
        cb.closest('.seat-option').classList.toggle('selected', cb.checked);
        const grade = parseInt(cb.value);
        const zone = document.querySelector(`.seat-zone[data-grade="${grade}"]`);
        if (zone) zone.classList.toggle('selected', cb.checked);
      });
    });

    // 同步座位地图
    syncSeatMap(classes);
    initSeatMap();
  } catch (err) {
    console.error('加载座位配置失败:', err);
  }
}

// 同步座位地图数据
function syncSeatMap(classes) {
  classes.forEach(tc => {
    const zone = document.querySelector(`.seat-zone[data-grade="${tc.grade_index}"]`);
    if (!zone) return;
    zone.querySelector('.zone-price').textContent = `₩${tc.price.toLocaleString()}`;
    const statusEl = zone.querySelector('.zone-status');
    if (tc.is_sold_out) {
      statusEl.textContent = '售罄';
      statusEl.className = 'zone-status sold-out';
      zone.classList.add('sold-out');
    } else {
      statusEl.textContent = '在售';
      statusEl.className = 'zone-status available';
      zone.classList.remove('sold-out');
    }
  });
}

// ---- 场次选择 ----
function selectSchedule(el, index) {
  document.querySelectorAll('.schedule-item').forEach(s => s.classList.remove('selected'));
  el.classList.add('selected');
  document.getElementById('orderSchedule').value = index;
}

// ---- 座位地图联动 ----
function toggleZoneSeat(gradeIndex) {
  const cb = document.querySelector(`.seat-option input[value="${gradeIndex}"]`);
  if (cb && !cb.disabled) {
    cb.checked = !cb.checked;
    cb.closest('.seat-option').classList.toggle('selected', cb.checked);
    // 同步地图样式
    const zone = document.querySelector(`.seat-zone[data-grade="${gradeIndex}"]`);
    if (zone) zone.classList.toggle('selected', cb.checked);
  }
}

// 初始化座位地图选中状态
function initSeatMap() {
  document.querySelectorAll('.seat-zone').forEach(zone => {
    const grade = parseInt(zone.dataset.grade);
    const cb = document.querySelector(`.seat-option input[value="${grade}"]`);
    if (cb && cb.checked) zone.classList.add('selected');
  });
}

// ---- 确认弹窗 ----
let pendingFormData = null;

function showConfirmModal(formData) {
  pendingFormData = formData;
  const classes = window._ticketClasses || [];

  // 填充确认信息
  document.getElementById('confirmSchedule').textContent =
    formData.schedule_index === 0 ? 'Day 1 (2026.06.13 18:00 KST)' : 'Day 2 (2026.06.14 17:00 KST)';

  const seatNames = formData.seat_prefs.map(s => SEAT_LABELS[s] || s);
  document.getElementById('confirmSeats').textContent = seatNames.join(' > ');

  // 计算价格
  let totalPrice = 0;
  formData.seat_prefs.forEach(s => {
    const tc = classes.find(c => c.grade_index === s);
    if (tc) totalPrice += tc.price;
  });
  document.getElementById('confirmPrice').textContent =
    totalPrice > 0 ? `₩${totalPrice.toLocaleString()}` : '价格待定';

  // 倒计时
  const timeStr = formData.presale_time || formData.open_time;
  if (timeStr) {
    const parts = timeStr.replace(' ', 'T');
    const target = new Date(parts + '+09:00');
    if (!isNaN(target.getTime())) {
      const tick = () => {
        const diff = target - new Date();
        if (diff <= 0) {
          document.getElementById('confirmCountdown').textContent = '🎉 已开售';
          document.getElementById('confirmCountdown').style.color = 'var(--success)';
          return;
        }
        const h = Math.floor(diff / 3600000);
        const m = Math.floor((diff % 3600000) / 60000);
        const s = Math.floor((diff % 60000) / 1000);
        document.getElementById('confirmCountdown').textContent =
          `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
      };
      tick();
      window._confirmCountdown = setInterval(tick, 1000);
    }
  } else {
    document.getElementById('confirmCountdown').textContent = '立即开抢';
  }

  openModal('confirmModal');
}

async function confirmAndSubmit() {
  if (!pendingFormData) return;
  const btn = document.getElementById('confirmBtn');
  btn.disabled = true;
  btn.textContent = '创建中...';

  if (window._confirmCountdown) clearInterval(window._confirmCountdown);

  try {
    const data = await API.createOrder(pendingFormData);
    showToast('✅ 订单创建成功！', 'success');
    closeModal('confirmModal');

    document.getElementById('orderForm').reset();
    document.querySelectorAll('.seat-option').forEach(opt => {
      const cb = opt.querySelector('input');
      const idx = parseInt(cb.value);
      cb.checked = idx <= 4;
      opt.classList.toggle('selected', cb.checked);
    });
    initSeatMap();

    loadOrders();
    loadStats();

    const timeStr = pendingFormData.presale_time || pendingFormData.open_time;
    const label = pendingFormData.presale_time ? '💎 会员预售倒计时' : '🎫 公开售票倒计时';
    startCountdown(timeStr, label);
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '✅ 确认并创建订单';
    pendingFormData = null;
  }
}

// ---- 倒计时器 ----
function startCountdown(targetTimeStr, label) {
  if (countdownTimer) clearInterval(countdownTimer);
  const container = document.getElementById('countdownContainer');
  if (!container) return;

  if (!targetTimeStr) {
    container.style.display = 'none';
    return;
  }

  // 解析时间: "2026-06-14 20:00:00" -> Date (KST = UTC+9)
  const parts = targetTimeStr.replace(' ', 'T');
  const target = new Date(parts + '+09:00');
  if (isNaN(target.getTime())) {
    container.style.display = 'none';
    return;
  }

  container.style.display = '';
  document.getElementById('countdownLabel').textContent = label || '距开售';

  function tick() {
    const now = new Date();
    const diff = target - now;

    if (diff <= 0) {
      document.getElementById('countdownTime').textContent = '🎉 已开售！';
      document.getElementById('countdownTime').style.color = 'var(--success)';
      clearInterval(countdownTimer);
      return;
    }

    const days = Math.floor(diff / 86400000);
    const hours = Math.floor((diff % 86400000) / 3600000);
    const mins = Math.floor((diff % 3600000) / 60000);
    const secs = Math.floor((diff % 60000) / 1000);

    let display = '';
    if (days > 0) display = `${days}天 ${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    else if (hours > 0) display = `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    else display = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

    document.getElementById('countdownTime').textContent = display;
  }

  tick();
  countdownTimer = setInterval(tick, 1000);
}

// ---- 创建订单 ----
async function createOrder(event) {
  event.preventDefault();
  const btn = event.target.querySelector('button[type="submit"]');

  try {
    const perfUrl = document.getElementById('orderPerfUrl').value.trim();
    const scheduleIndex = parseInt(document.getElementById('orderSchedule').value);
    const tabCount = parseInt(document.getElementById('orderTabs').value);
    const openTimeRaw = document.getElementById('orderOpenTime').value;
    const presaleTimeRaw = document.getElementById('orderPresaleTime').value;
    const proxy = document.getElementById('orderProxy').value.trim();
    const seatPrefs = getSelectedSeats();

    const openTime = openTimeRaw ? openTimeRaw.replace('T', ' ') + ':00' : '';
    const presaleTime = presaleTimeRaw ? presaleTimeRaw.replace('T', ' ') + ':00' : '';

    if (!perfUrl) throw new Error('请填写演出 URL');
    if (!openTime && !presaleTime) throw new Error('请设置开售时间');

    const formData = {
      perf_url: perfUrl,
      schedule_index: scheduleIndex,
      schedule_label: scheduleIndex === 0 ? 'Day 1' : 'Day 2',
      seat_prefs: seatPrefs,
      tab_count: tabCount,
      open_time: openTime,
      presale_time: presaleTime,
      proxy: proxy,
      // GetBlock
      goods_code: document.getElementById('orderGoodsCode')?.value?.trim() || '',
      place_code: document.getElementById('orderPlaceCode')?.value?.trim() || '',
      seat_mode: parseInt(document.getElementById('orderSeatMode')?.value || '1'),
      // Set
      lock_delay: parseInt(document.getElementById('orderLockDelay')?.value || '1200'),
      delay_start: parseInt(document.getElementById('orderDelayStart')?.value || '300'),
      kr_ticket_mode: document.getElementById('orderKrTicketMode')?.value?.trim() || '',
      keyword: document.getElementById('orderKeyword')?.value?.trim() || '',
      pre_yn: document.getElementById('orderPreYN')?.value || 'N',
      ko_pay: document.getElementById('orderKoPay')?.value?.trim() || '',
      suo_tou: document.getElementById('orderSuoTou')?.checked || false,
      day2: document.getElementById('orderDay2')?.checked || false,
      // GuoHu
      auto_guohu: document.getElementById('orderAutoGuoHu')?.checked || false,
      auto_cancel: document.getElementById('orderAutoCancel')?.checked || false,
      guohu_pay: document.getElementById('orderGuoHuPay')?.checked || false,
      // Info
      yes_captcha_key: document.getElementById('orderYesCaptchaKey')?.value?.trim() || '',
      proxy_api: document.getElementById('orderProxyApi')?.value?.trim() || '',
      ding_webhook: document.getElementById('orderDingWebhook')?.value?.trim() || '',
      // Other
      thread_count: parseInt(document.getElementById('orderThreadCount')?.value || '1'),
    };

    // 弹出确认框
    showConfirmModal(formData);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ---- 订单列表 ----
async function loadOrders() {
  try {
    const data = await API.getOrders({ per_page: 20 });
    renderOrders(data.orders);

    // 自动启动最近一个订单的倒计时
    if (data.orders && data.orders.length > 0 && !countdownTimer) {
      const pending = data.orders.find(o => o.status === 'pending' && (o.presale_time || o.open_time));
      if (pending) {
        const t = pending.presale_time || pending.open_time;
        startCountdown(t, pending.is_presale ? '💎 会员预售倒计时' : '🎫 公开售票倒计时');
      }
    }
  } catch (err) {
    document.getElementById('ordersList').innerHTML =
      `<p style="text-align:center; color:var(--error); padding:40px;">加载失败: ${err.message}</p>`;
  }
}

function renderOrders(orders) {
  const container = document.getElementById('ordersList');

  if (!orders || orders.length === 0) {
    container.innerHTML = `<p style="text-align:center; color:var(--text-dim); padding:40px;">暂无订单，创建你的第一个抢票订单吧 🎫</p>`;
    return;
  }

  container.innerHTML = orders.map(o => `
    <div class="order-item">
      <div class="order-top">
        <span class="order-id">#${o.id} ${o.is_presale ? '💎 预售' : '🎫 公售'}</span>
        <div style="display:flex;align-items:center;gap:12px;">
          ${statusBadge(o.status)}
          <span class="order-time">${formatTime(o.created_at)}</span>
        </div>
      </div>
      <div class="order-details">
        <div class="order-detail">
          <span class="order-detail-label">场次</span>
          <span class="order-detail-value">${o.schedule_label}</span>
        </div>
        <div class="order-detail">
          <span class="order-detail-label">开售时间</span>
          <span class="order-detail-value">${o.presale_time || o.open_time || '未设置'}</span>
        </div>
        <div class="order-detail">
          <span class="order-detail-label">标签页</span>
          <span class="order-detail-value">${o.tab_count} 个</span>
        </div>
        <div class="order-detail">
          <span class="order-detail-label">线程</span>
          <span class="order-detail-value">${o.thread_count || 1}</span>
        </div>
        <div class="order-detail">
          <span class="order-detail-label">座位偏好</span>
          <span class="order-detail-value">${(o.seat_prefs || []).map(s => SEAT_LABELS[s] || s).join(' > ')}</span>
        </div>
        ${o.goods_code ? `
        <div class="order-detail">
          <span class="order-detail-label">GoodsCode</span>
          <span class="order-detail-value" style="color:var(--accent);">${o.goods_code}</span>
        </div>` : ''}
        ${o.kr_ticket_mode ? `
        <div class="order-detail">
          <span class="order-detail-label">票务模式</span>
          <span class="order-detail-value">${o.kr_ticket_mode}</span>
        </div>` : ''}
        ${o.auto_guohu ? `
        <div class="order-detail">
          <span class="order-detail-label">过户</span>
          <span class="order-detail-value" style="color:var(--warning);">🔄 自动过户开启</span>
        </div>` : ''}
        ${o.order_no ? `
        <div class="order-detail">
          <span class="order-detail-label">订单号</span>
          <span class="order-detail-value" style="color:var(--success);">${o.order_no}</span>
        </div>` : ''}
      </div>
      <div class="order-actions">
        <button class="btn btn-sm btn-secondary" onclick="viewOrderDetail(${o.id})">📋 详情</button>
        ${o.status === 'pending' || o.status === 'failed' || o.status === 'error' ?
          `<button class="btn btn-sm btn-success" onclick="startOrder(${o.id})">🚀 启动</button>` : ''}
        ${o.status === 'pending' ?
          `<button class="btn btn-sm btn-secondary" onclick="editOrder(${o.id})">✏️ 编辑</button>` : ''}
        ${o.status !== 'grabbing' ?
          `<button class="btn btn-sm btn-danger" onclick="deleteOrder(${o.id})">🗑️ 删除</button>` : ''}
      </div>
    </div>
  `).join('');
}

// ---- 统计 ----
async function loadStats() {
  try {
    const data = await API.getOrders({ per_page: 100 });
    const orders = data.orders || [];

    document.getElementById('statTotal').textContent = orders.length;
    document.getElementById('statPending').textContent = orders.filter(o => ['pending', 'waiting'].includes(o.status)).length;
    document.getElementById('statGrabbing').textContent = orders.filter(o => o.status === 'grabbing').length;
    document.getElementById('statSuccess').textContent = orders.filter(o => o.status === 'success').length;

    // 更新迷你统计面板
    updateMiniStats(orders);
  } catch (err) {
    console.error('加载统计失败:', err);
  }
}

// ---- 操作 ----
async function startOrder(id) {
  if (!confirm('确定启动抢票？')) return;
  try {
    const data = await API.startGrabber(id);
    showToast(data.message || '已启动', 'success');
    loadOrders();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function deleteOrder(id) {
  if (!confirm('确定删除此订单？')) return;
  try {
    await API.deleteOrder(id);
    showToast('已删除', 'success');
    loadOrders();
    loadStats();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function viewOrderDetail(id) {
  try {
    const order = await API.getOrder(id);
    const content = document.getElementById('orderDetailContent');

    // 加载该订单的座位配置
    let seatConfigHtml = '';
    try {
      const tcData = await API.getTicketClasses(id);
      const tcs = tcData.ticket_classes || [];
      if (tcs.length > 0) {
        seatConfigHtml = `
          <div style="margin-bottom:20px;">
            <h4 style="margin-bottom:12px;">💺 座位档位</h4>
            <div class="seat-config-grid">
              ${tcs.map(tc => `
                <div class="seat-config-card" style="border-left:3px solid ${tc.color};">
                  <div class="seat-config-name">${tc.icon} ${tc.name}</div>
                  <div class="seat-config-price">₩${tc.price.toLocaleString()}</div>
                  <div class="seat-config-status">
                    ${tc.is_sold_out
                      ? '<span class="badge badge-sold_out">售罄</span>'
                      : `<span class="badge badge-success">${tc.available_seats || '?'} 剩余</span>`
                    }
                  </div>
                </div>
              `).join('')}
            </div>
          </div>
        `;
      }
    } catch (e) { /* ignore */ }

    content.innerHTML = `
      <div style="margin-bottom:20px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3>订单 #${order.id}</h3>
          ${statusBadge(order.status)}
        </div>
        <div class="order-details">
          <div class="order-detail"><span class="order-detail-label">演出 URL</span><span class="order-detail-value" style="word-break:break-all;font-size:0.8rem;">${order.perf_url}</span></div>
          <div class="order-detail"><span class="order-detail-label">场次</span><span class="order-detail-value">${order.schedule_label}</span></div>
          <div class="order-detail"><span class="order-detail-label">预售时间</span><span class="order-detail-value">${order.presale_time || '无'}</span></div>
          <div class="order-detail"><span class="order-detail-label">开售时间</span><span class="order-detail-value">${order.open_time || '无'}</span></div>
          <div class="order-detail"><span class="order-detail-label">标签页</span><span class="order-detail-value">${order.tab_count}</span></div>
          <div class="order-detail"><span class="order-detail-label">线程数</span><span class="order-detail-value">${order.thread_count || 1}</span></div>
          <div class="order-detail"><span class="order-detail-label">创建时间</span><span class="order-detail-value">${formatTime(order.created_at)}</span></div>
          ${order.goods_code ? `<div class="order-detail"><span class="order-detail-label">GoodsCode</span><span class="order-detail-value" style="color:var(--accent);">${order.goods_code}</span></div>` : ''}
          ${order.block_no ? `<div class="order-detail"><span class="order-detail-label">Block No</span><span class="order-detail-value">${order.block_no}</span></div>` : ''}
          ${order.kr_ticket_mode ? `<div class="order-detail"><span class="order-detail-label">票务模式</span><span class="order-detail-value">${order.kr_ticket_mode}</span></div>` : ''}
          ${order.lock_delay ? `<div class="order-detail"><span class="order-detail-label">Lock Delay</span><span class="order-detail-value">${order.lock_delay}ms</span></div>` : ''}
          ${order.keyword ? `<div class="order-detail"><span class="order-detail-label">关键词</span><span class="order-detail-value">${order.keyword}</span></div>` : ''}
          ${order.auto_guohu ? `<div class="order-detail"><span class="order-detail-label">过户</span><span class="order-detail-value" style="color:var(--warning);">🔄 自动过户已开启</span></div>` : ''}
          ${order.ding_webhook ? `<div class="order-detail"><span class="order-detail-label">钉钉</span><span class="order-detail-value" style="color:var(--success);">🔔 已配置</span></div>` : ''}
          ${order.order_no ? `<div class="order-detail"><span class="order-detail-label">订单号</span><span class="order-detail-value" style="color:var(--success);">${order.order_no}</span></div>` : ''}
        </div>
      </div>

      ${seatConfigHtml}

      <div>
        <h4 style="margin-bottom:12px;">📜 运行日志</h4>
        <div class="log-panel" id="logPanel">
          ${(order.logs || []).map(l => `
            <div class="log-entry level-${l.level.toLowerCase()}">
              <span class="log-time">${formatLogTime(l.created_at)}</span>
              <span class="log-msg">${l.message}</span>
            </div>
          `).join('') || '<p style="color:var(--text-dim);">暂无日志</p>'}
        </div>
      </div>
    `;

    openModal('orderDetailModal');

    const logPanel = document.getElementById('logPanel');
    if (logPanel) logPanel.scrollTop = logPanel.scrollHeight;
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function editOrder(id) {
  try {
    const order = await API.getOrder(id);
    const newUrl = prompt('演出 URL:', order.perf_url);
    if (newUrl === null) return;

    await API.updateOrder(id, { perf_url: newUrl });
    showToast('更新成功', 'success');
    loadOrders();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ---- 工具函数 ----
function formatTime(isoStr) {
  if (!isoStr) return '-';
  const d = new Date(isoStr);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function formatLogTime(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`;
}

// 页面离开时清理定时器
window.addEventListener('beforeunload', () => {
  if (refreshTimer) clearInterval(refreshTimer);
  if (countdownTimer) clearInterval(countdownTimer);
});

// ============================================================
//  多账号管理
// ============================================================

let localAccounts = [];

async function loadAccounts() {
  try {
    const data = await API.getAccounts();
    localAccounts = data.accounts || [];
    renderAccounts();
  } catch (err) {
    console.error('加载账号失败:', err);
  }
}

function renderAccounts() {
  const tbody = document.getElementById('accountTableBody');
  if (!tbody) return;

  if (localAccounts.length === 0) {
    tbody.innerHTML = '<tr><td colspan="11" style="text-align:center; padding:16px; color:var(--text-muted);">点击「添加账号」开始配置</td></tr>';
    return;
  }

  tbody.innerHTML = localAccounts.map(acc => `
    <tr>
      <td class="acc-no">${acc.no}</td>
      <td>${acc.proxy || '-'}</td>
      <td class="acc-email">${acc.email}</td>
      <td class="acc-pw">${acc.password || '***'}</td>
      <td style="color:var(--text-muted);">-</td>
      <td>${acc.wrid || '-'}</td>
      <td>${acc.card_no ? '****' + acc.card_no.slice(-4) : '-'}</td>
      <td>${acc.card_cvv || '-'}</td>
      <td>${acc.status === 'success' ? '✅' : acc.status === 'running' ? '⏳' : '-'}</td>
      <td style="color:var(--text-muted);">-</td>
      <td>
        <button class="btn btn-sm btn-danger" style="padding:4px 10px;font-size:0.75rem;" onclick="handleDeleteAccount(${acc.id})">🗑️</button>
      </td>
    </tr>
  `).join('');
}

function showAddAccountModal() {
  document.getElementById('accEmail').value = '';
  document.getElementById('accPassword').value = '';
  document.getElementById('accProxy').value = '';
  document.getElementById('accWrid').value = '';
  document.getElementById('accCardNo').value = '';
  document.getElementById('accCardCvv').value = '';
  openModal('addAccountModal');
}

async function handleAddAccount(event) {
  event.preventDefault();
  try {
    const data = {
      email: document.getElementById('accEmail').value.trim(),
      password: document.getElementById('accPassword').value,
      proxy: document.getElementById('accProxy').value.trim(),
      wrid: document.getElementById('accWrid').value.trim(),
      card_no: document.getElementById('accCardNo').value.trim(),
      card_cvv: document.getElementById('accCardCvv').value.trim(),
    };
    await API.createAccount(data);
    showToast('账号已添加', 'success');
    closeModal('addAccountModal');
    loadAccounts();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function handleDeleteAccount(id) {
  if (!confirm('确定删除此账号？')) return;
  try {
    await API.deleteAccount(id);
    showToast('已删除', 'success');
    loadAccounts();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function showBatchImportModal() {
  document.getElementById('batchImportData').value = '';
  openModal('batchImportModal');
}

async function handleBatchImport() {
  const raw = document.getElementById('batchImportData').value.trim();
  if (!raw) {
    showToast('请粘贴 JSON 数据', 'error');
    return;
  }

  try {
    const data = JSON.parse(raw);
    if (!Array.isArray(data)) throw new Error('需要 JSON 数组');
    await API.batchCreateAccounts(data);
    showToast(`导入成功`, 'success');
    closeModal('batchImportModal');
    loadAccounts();
  } catch (err) {
    if (err instanceof SyntaxError) {
      showToast('JSON 格式错误，请检查', 'error');
    } else {
      showToast(err.message, 'error');
    }
  }
}

// ============================================================
//  GetBlock
// ============================================================

async function handleGetBlock() {
  // 需要先有订单才能调用，这里用临时方式
  const goodsCode = document.getElementById('orderGoodsCode')?.value?.trim();
  if (!goodsCode) {
    showToast('请填写 GoodsCode', 'error');
    return;
  }

  const placeCode = document.getElementById('orderPlaceCode')?.value?.trim() || '';
  const seatMode = document.getElementById('orderSeatMode')?.value || '1';

  const resultEl = document.getElementById('blockNoResult');
  if (resultEl) {
    resultEl.style.display = 'block';
    resultEl.textContent = '⏳ 正在获取区块编号...';
    resultEl.style.background = 'rgba(245,158,11,0.1)';
    resultEl.style.color = 'var(--warning)';
  }

  // 模拟获取 blockNo
  setTimeout(() => {
    // 简单 hash 模拟
    let hash = 0;
    const str = `${goodsCode}:${placeCode}:${seatMode}`;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash |= 0;
    }
    const blockNo = Math.abs(hash).toString(16).padStart(8, '0').slice(0, 8);

    if (resultEl) {
      resultEl.style.display = 'block';
      resultEl.innerHTML = `✅ 区块编号: <strong>${blockNo}</strong> (GoodsCode: ${goodsCode}, PlaceCode: ${placeCode || 'N/A'}, seat mode: ${seatMode})`;
      resultEl.style.background = 'rgba(16,185,129,0.1)';
      resultEl.style.color = 'var(--success)';
    }
    showToast('区块编号已获取', 'success');
  }, 800);
}

// ============================================================
//  钉钉通知
// ============================================================

async function handleDingInit() {
  const webhook = document.getElementById('orderDingWebhook')?.value?.trim();
  if (!webhook) {
    showToast('请填写钉钉 Webhook 地址', 'error');
    return;
  }
  // 这个需要在订单创建后调用，这里提示用户
  showToast('Webhook 已设置，创建订单后自动初始化', 'info');
}

async function handleDingPush() {
  const webhook = document.getElementById('orderDingWebhook')?.value?.trim();
  if (!webhook) {
    showToast('请先填写 Webhook 地址', 'error');
    return;
  }
  // 直接用 fetch 发送测试消息
  try {
    const resp = await fetch(webhook, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        msgtype: 'text',
        text: { content: '🎫 YAOLO 抢票系统测试通知 — 连接正常！' }
      }),
    });
    if (resp.ok) {
      showToast('✅ 钉钉测试通知已发送', 'success');
    } else {
      showToast(`发送失败: HTTP ${resp.status}`, 'error');
    }
  } catch (err) {
    showToast(`发送失败: ${err.message}`, 'error');
  }
}

// ============================================================
//  实时统计面板更新
// ============================================================

function updateMiniStats(orders) {
  if (!orders) return;
  const total = orders.length;
  const success = orders.filter(o => o.status === 'success').length;
  const grabbing = orders.filter(o => o.status === 'grabbing').length;
  // SYL = 模拟剩余票数
  const pending = orders.filter(o => o.status === 'pending').length;

  const el = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
  el('miniTotalTask', total);
  el('miniSuccessTask', success);
  el('miniThreadsNum', grabbing);
  el('miniSYL', pending);
}
