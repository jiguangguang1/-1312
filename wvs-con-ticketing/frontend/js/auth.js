/**
 * 认证逻辑
 */

let isRegisterMode = false;

function updateNavbarAuth() {
  const navAuth = document.getElementById('navAuth');
  const adminLink = document.getElementById('adminLink');
  if (!navAuth) return;

  if (API.isLoggedIn()) {
    const user = API.getUser();
    const initial = (user?.username || 'U')[0].toUpperCase();
    navAuth.innerHTML = `
      <div class="navbar-user" onclick="window.location.href='/dashboard'">
        <div class="navbar-avatar">${initial}</div>
        <span style="font-size:0.9rem; font-weight:500;">${user?.username || '用户'}</span>
      </div>
    `;
    if (adminLink && user?.is_admin) {
      adminLink.style.display = '';
    }
  } else {
    navAuth.innerHTML = `<a href="#" class="btn btn-primary btn-sm" onclick="showLoginModal()">登录</a>`;
    if (adminLink) adminLink.style.display = 'none';
  }
}

function showLoginModal() {
  isRegisterMode = false;
  document.getElementById('authModalTitle').textContent = '登录';
  document.getElementById('emailGroup').style.display = 'none';
  document.getElementById('authSubmitBtn').textContent = '登录';
  document.getElementById('toggleAuthMode').textContent = '没有账号？注册';
  openModal('loginModal');
}

function toggleAuthMode() {
  isRegisterMode = !isRegisterMode;
  if (isRegisterMode) {
    document.getElementById('authModalTitle').textContent = '注册';
    document.getElementById('emailGroup').style.display = '';
    document.getElementById('authSubmitBtn').textContent = '注册';
    document.getElementById('toggleAuthMode').textContent = '已有账号？登录';
  } else {
    document.getElementById('authModalTitle').textContent = '登录';
    document.getElementById('emailGroup').style.display = 'none';
    document.getElementById('authSubmitBtn').textContent = '登录';
    document.getElementById('toggleAuthMode').textContent = '没有账号？注册';
  }
}

async function handleAuth(event) {
  event.preventDefault();
  const username = document.getElementById('authUsername').value.trim();
  const password = document.getElementById('authPassword').value;
  const btn = document.getElementById('authSubmitBtn');

  btn.disabled = true;
  btn.textContent = '处理中...';

  try {
    let data;
    if (isRegisterMode) {
      const email = document.getElementById('authEmail').value.trim();
      if (!email) throw new Error('请填写邮箱');
      data = await API.register(username, email, password);
    } else {
      data = await API.login(username, password);
    }

    API.setToken(data.token);
    API.setUser(data.user);
    updateNavbarAuth();
    closeModal('loginModal');
    showToast(data.message || '操作成功', 'success');

    // 清空表单
    document.getElementById('authForm').reset();
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = isRegisterMode ? '注册' : '登录';
  }
}

function logout() {
  API.clearToken();
  updateNavbarAuth();
  window.location.href = '/';
}

// 页面加载时检查登录状态
document.addEventListener('DOMContentLoaded', () => {
  updateNavbarAuth();
});
