const form = document.getElementById('loginForm');
const errorMsg = document.getElementById('errorMsg');
const loginBtn = document.getElementById('loginBtn');

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;

  errorMsg.classList.add('hidden');
  loginBtn.disabled = true;
  loginBtn.textContent = 'Logging in...';

  try {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    const data = await res.json();

    if (res.ok && data.success) {
      window.location.href = '/admin';
    } else {
      showError(data.message || 'Invalid credentials');
    }
  } catch (err) {
    showError('Could not reach server');
  } finally {
    loginBtn.disabled = false;
    loginBtn.textContent = 'Log In';
  }
});

function showError(message) {
  errorMsg.textContent = message;
  errorMsg.classList.remove('hidden');
}
