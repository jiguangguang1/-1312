/**
 * 首页逻辑
 */

function handleGetStarted() {
  if (API.isLoggedIn()) {
    window.location.href = '/dashboard';
  } else {
    showLoginModal();
  }
}

function handleFeatureClick(type) {
  if (API.isLoggedIn()) {
    window.location.href = `/dashboard?action=${type}`;
  } else {
    showLoginModal();
    showToast('请先登录后使用', 'info');
  }
}
