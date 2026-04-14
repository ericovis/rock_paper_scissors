import { api } from '../api.js';

export function renderLobby(root, user, onJoinRoom) {
  root.innerHTML = `
    <div class="lobby">
      <div class="lobby-header">
        <h1>Rock Paper Scissors</h1>
        <div class="user">Playing as <strong>${escapeHtml(user.username)}</strong></div>
      </div>
      <div class="lobby-grid">
        <div class="panel" id="rooms-panel">
          <div class="rooms-header">
            <h2>Open rooms</h2>
            <button id="create-room-btn">Create room</button>
          </div>
          <div class="room-list" id="room-list"></div>
        </div>
        <div class="panel">
          <h2>Leaderboard</h2>
          <div class="leaderboard-list" id="leaderboard-list"></div>
        </div>
      </div>
    </div>
  `;

  const roomList = root.querySelector('#room-list');
  const leaderboardList = root.querySelector('#leaderboard-list');
  const createBtn = root.querySelector('#create-room-btn');

  async function refreshRooms() {
    try {
      const rooms = await api.listRooms();
      if (!rooms.length) {
        roomList.innerHTML = `<div class="empty">No open rooms. Create one to get started.</div>`;
        return;
      }
      roomList.innerHTML = rooms
        .map(
          (r) => `
            <div class="room-item">
              <div>
                <div class="creator">${escapeHtml(r.creator_username)}</div>
                <div class="meta">Room #${r.room_id}</div>
              </div>
              <button data-room="${r.room_id}">Join</button>
            </div>
          `,
        )
        .join('');
      roomList.querySelectorAll('button[data-room]').forEach((btn) => {
        btn.addEventListener('click', () => {
          onJoinRoom(Number(btn.dataset.room));
        });
      });
    } catch (e) {
      roomList.innerHTML = `<div class="empty">Failed to load rooms: ${escapeHtml(e.message)}</div>`;
    }
  }

  async function refreshLeaderboard() {
    try {
      const lb = await api.leaderboard();
      if (!lb.entries.length) {
        leaderboardList.innerHTML = `<div class="empty">No wins yet.</div>`;
        return;
      }
      leaderboardList.innerHTML = lb.entries
        .map(
          (e, i) => `
            <div class="lb-row">
              <span class="rank">#${i + 1}</span>
              <span class="name">${escapeHtml(e.username)}</span>
              <span class="wins">${e.wins}</span>
            </div>
          `,
        )
        .join('');
    } catch (e) {
      leaderboardList.innerHTML = `<div class="empty">Failed: ${escapeHtml(e.message)}</div>`;
    }
  }

  createBtn.addEventListener('click', async () => {
    createBtn.disabled = true;
    try {
      const res = await api.createRoom();
      onJoinRoom(res.room_id, res.share_url);
    } catch (e) {
      alert(`Could not create room: ${e.message}`);
      createBtn.disabled = false;
    }
  });

  refreshRooms();
  refreshLeaderboard();
  const interval = setInterval(() => {
    refreshRooms();
    refreshLeaderboard();
  }, 3000);

  return () => clearInterval(interval);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[c]);
}
