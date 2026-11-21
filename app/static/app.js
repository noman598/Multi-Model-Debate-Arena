/**
 * Integrated Client-Side Script
 * Handles Authentication (Signup, Login, Refresh, Logout, Profile)
 * + PicShare Photo Gallery (Upload, 200x200 Thumbnail view, Delete)
 * Uses `credentials: 'include'` for all requests.
 */

let isUserLoggedIn = false;

document.addEventListener('DOMContentLoaded', () => {
  checkStatus();
});

// 1. Check current session status
async function checkStatus() {
  try {
    const res = await sendRequest('/api/auth/status', 'GET');
    const statusEl = document.getElementById('session-status');
    const redisEl = document.getElementById('redis-status');
    const photosHint = document.getElementById('photos-hint');

    if (res.authenticated && res.user) {
      isUserLoggedIn = true;
      statusEl.innerHTML = `<span style="color: green; font-weight: bold;">Logged in as: ${res.user.username} (ID: ${res.user.id}, Email: ${res.user.email})</span>`;
      if (photosHint) photosHint.textContent = `Showing photos for ${res.user.username}:`;
      await loadPhotos();
    } else {
      isUserLoggedIn = false;
      statusEl.innerHTML = `<span style="color: #666;">Not logged in (Guest)</span>`;
      if (photosHint) photosHint.textContent = 'Please log in to view and upload your photos.';
      document.getElementById('photos-grid').innerHTML = '';
    }

    if (res.redis_mode) {
      redisEl.textContent = `| Redis Store: ${res.redis_mode}`;
    }
  } catch (err) {
    document.getElementById('session-status').textContent = 'Error checking status';
  }
}

// 2. Handle User Signup
async function handleSignup(e) {
  e.preventDefault();
  const username = document.getElementById('signup-username').value.trim();
  const email = document.getElementById('signup-email').value.trim();
  const fullName = document.getElementById('signup-fullname').value.trim();
  const password = document.getElementById('signup-password').value;

  const payload = {
    username: username,
    email: email,
    full_name: fullName || null,
    password: password
  };

  const res = await sendRequest('/api/auth/signup', 'POST', payload);
  if (res.id) {
    document.getElementById('signup-form').reset();
    document.getElementById('login-username').value = res.username;
    alert(`Account created successfully for '${res.username}'. You can now log in!`);
  }
}

// 3. Handle User Login
async function handleLogin(e) {
  e.preventDefault();
  const identifier = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;

  const payload = {
    username_or_email: identifier,
    password: password
  };

  const res = await sendRequest('/api/auth/login', 'POST', payload);
  if (res.user) {
    document.getElementById('login-form').reset();
    await checkStatus();
  }
}

// 4. Fetch Protected Profile (/api/auth/me)
async function handleGetProfile() {
  const res = await sendRequest('/api/auth/me', 'GET');
  if (res.id) {
    await checkStatus();
  }
}

// 5. Refresh Tokens (/api/auth/refresh)
async function handleRefreshToken() {
  const res = await sendRequest('/api/auth/refresh', 'POST');
  if (res.message) {
    await checkStatus();
  }
}

// 6. Logout (/api/auth/logout)
async function handleLogout() {
  await sendRequest('/api/auth/logout', 'POST');
  await checkStatus();
}

// --- PICSHARE GALLERY ACTIONS ---

// 7. Load user photos (/api/photos)
async function loadPhotos() {
  if (!isUserLoggedIn) return;
  try {
    const photos = await sendRequest('/api/photos', 'GET');
    renderPhotos(photos);
  } catch (err) {
    console.error('Failed to load photos:', err);
  }
}

function renderPhotos(photos) {
  const grid = document.getElementById('photos-grid');
  const hint = document.getElementById('photos-hint');

  if (!photos || photos.length === 0) {
    hint.textContent = 'No photos uploaded yet. Upload your first image above!';
    grid.innerHTML = '';
    return;
  }

  hint.textContent = `You have ${photos.length} uploaded photo(s):`;
  grid.innerHTML = photos.map(p => `
    <div class="photo-card">
      <a href="${p.original_url}" target="_blank" title="Click to view full size original">
        <img src="${p.thumbnail_url}" alt="Thumbnail #${p.id}">
      </a>
      <div class="photo-meta">ID: #${p.id} &bull; ${new Date(p.created_at).toLocaleDateString()}</div>
      <button type="button" class="btn-delete" onclick="handleDeletePhoto(${p.id})">Delete</button>
    </div>
  `).join('');
}

// 8. Upload photo (/api/photos/upload)
async function handleUploadPhoto(e) {
  e.preventDefault();
  if (!isUserLoggedIn) {
    alert('Please log in first to upload photos.');
    return;
  }

  const fileInput = document.getElementById('photo-file');
  if (!fileInput.files || fileInput.files.length === 0) {
    alert('Please select a file.');
    return;
  }

  const file = fileInput.files[0];
  if (file.size > 5 * 1024 * 1024) {
    alert('File is too large! Maximum allowed size is 5 MB.');
    return;
  }

  const formData = new FormData();
  formData.append('file', file);

  const metaEl = document.getElementById('output-meta');
  const boxEl = document.getElementById('output-box');
  metaEl.textContent = `Uploading ${file.name} to /api/photos/upload...`;

  try {
    const response = await fetch('/api/photos/upload', {
      method: 'POST',
      body: formData,
      credentials: 'include' // Sends HTTP-only JWT cookie
    });

    const data = await response.json();
    const time = new Date().toLocaleTimeString();
    metaEl.innerHTML = `[${time}] <strong>POST /api/photos/upload</strong> &bull; Status: <strong>${response.status} ${response.statusText}</strong>`;
    boxEl.textContent = JSON.stringify(data, null, 2);

    if (response.ok) {
      fileInput.value = '';
      await loadPhotos();
    } else {
      alert(data.detail || 'Upload failed');
    }
  } catch (err) {
    metaEl.textContent = 'Upload failed';
    boxEl.textContent = err.toString();
  }
}

// 9. Delete photo (/api/photos/{id})
async function handleDeletePhoto(photoId) {
  if (!confirm(`Delete photo #${photoId}?`)) return;
  const res = await sendRequest(`/api/photos/${photoId}`, 'DELETE');
  if (res) {
    await loadPhotos();
  }
}

// Clear Output Box
function clearOutput() {
  document.getElementById('output-meta').textContent = 'Output cleared.';
  document.getElementById('output-box').textContent = '';
}

// Central Request Function
async function sendRequest(url, method = 'GET', body = null) {
  const metaEl = document.getElementById('output-meta');
  const boxEl = document.getElementById('output-box');

  metaEl.textContent = `Sending ${method} ${url}...`;

  const options = {
    method: method,
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    },
    // CRITICAL: Include cookies in requests so access_token and refresh_token are sent
    credentials: 'include'
  };

  if (body) {
    options.body = JSON.stringify(body);
  }

  try {
    const response = await fetch(url, options);
    let data;
    try {
      data = await response.json();
    } catch (e) {
      data = { text: await response.text() };
    }

    const time = new Date().toLocaleTimeString();
    metaEl.innerHTML = `[${time}] <strong>${method} ${url}</strong> &bull; Status: <strong>${response.status} ${response.statusText}</strong>`;
    boxEl.textContent = JSON.stringify(data, null, 2);

    return data;
  } catch (err) {
    metaEl.textContent = `Error during ${method} ${url}`;
    boxEl.textContent = err.toString();
    throw err;
  }
}
