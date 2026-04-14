import { WS_BASE } from './api.js';

export function openGameSocket(roomId, handlers) {
  const ws = new WebSocket(`${WS_BASE}/ws/game/${roomId}`);

  ws.addEventListener('message', (ev) => {
    let msg;
    try {
      msg = JSON.parse(ev.data);
    } catch {
      return;
    }
    const fn = handlers[msg.event];
    if (fn) fn(msg.data || {});
    else if (handlers._unknown) handlers._unknown(msg);
  });

  ws.addEventListener('open', () => handlers._open?.());
  ws.addEventListener('close', () => handlers._close?.());
  ws.addEventListener('error', (e) => handlers._error?.(e));

  return {
    socket: ws,
    send(event, data = {}) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ event, data }));
      }
    },
    close() {
      ws.close();
    },
  };
}
