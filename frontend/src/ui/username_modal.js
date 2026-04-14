import { api } from '../api.js';

export function showUsernameModal(onReady) {
  const backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  backdrop.innerHTML = `
    <div class="modal">
      <h2>Choose a username</h2>
      <p style="color: var(--muted); margin-top: 0;">This is how other players will see you.</p>
      <input type="text" id="username-input" placeholder="e.g. sharp_dagger" maxlength="32" autofocus />
      <div style="display: flex; justify-content: flex-end; margin-top: 16px;">
        <button id="username-submit">Start playing</button>
      </div>
      <div id="username-error" style="color: var(--lose); margin-top: 12px; display: none;"></div>
    </div>
  `;
  document.body.appendChild(backdrop);

  const input = backdrop.querySelector('#username-input');
  const btn = backdrop.querySelector('#username-submit');
  const errEl = backdrop.querySelector('#username-error');

  const submit = async () => {
    const username = input.value.trim();
    if (!username) return;
    btn.disabled = true;
    errEl.style.display = 'none';
    try {
      const user = await api.createUser(username);
      backdrop.remove();
      onReady(user);
    } catch (e) {
      errEl.textContent = e.message;
      errEl.style.display = 'block';
      btn.disabled = false;
    }
  };

  btn.addEventListener('click', submit);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') submit();
  });
  input.focus();
}
