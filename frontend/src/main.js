import { api } from './api.js';
import { renderLobby } from './ui/lobby.js';
import { renderGameRoom } from './ui/game_room.js';
import { showUsernameModal } from './ui/username_modal.js';

const root = document.getElementById('app');
let currentUser = null;
let teardownView = null;

async function boot() {
  try {
    currentUser = await api.me();
  } catch {
    currentUser = null;
  }

  if (!currentUser) {
    showUsernameModal((user) => {
      currentUser = user;
      route();
    });
    return;
  }
  route();
}

function route() {
  teardownView?.();
  teardownView = null;

  const params = new URLSearchParams(window.location.search);
  const roomParam = params.get('room');
  if (roomParam) {
    const roomId = Number(roomParam);
    openGameRoom(roomId, null);
    return;
  }
  openLobby();
}

function openLobby() {
  teardownView?.();
  teardownView = renderLobby(root, currentUser, (roomId, shareUrl) => {
    const url = new URL(window.location.href);
    url.searchParams.set('room', String(roomId));
    window.history.pushState({}, '', url);
    openGameRoom(roomId, shareUrl);
  });
}

function openGameRoom(roomId, shareUrl) {
  teardownView?.();
  teardownView = renderGameRoom(root, roomId, shareUrl, () => {
    const url = new URL(window.location.href);
    url.searchParams.delete('room');
    window.history.pushState({}, '', url);
    openLobby();
  });
}

window.addEventListener('popstate', route);

boot();
