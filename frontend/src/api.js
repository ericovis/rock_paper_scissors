const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
export const WS_BASE = import.meta.env.VITE_WS_BASE || 'ws://localhost:8000';

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  createUser: (username) =>
    request('/api/users', { method: 'POST', body: JSON.stringify({ username }) }),
  me: () => request('/api/users/me'),
  listRooms: () => request('/api/rooms'),
  createRoom: () => request('/api/rooms', { method: 'POST' }),
  leaderboard: () => request('/api/leaderboard'),
};
