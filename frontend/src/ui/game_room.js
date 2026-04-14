import { openGameSocket } from '../ws.js';
import { createScene } from '../scene/scene.js';
import { isMobile } from '../state.js';

const CHOICE_ICONS = { rock: '✊', paper: '✋', scissors: '✌️' };
const ROUND_TIMEOUT_MS = 45000;

export function renderGameRoom(root, roomId, shareUrl, onLeave) {
  root.innerHTML = `
    <div class="game-root">
      <div class="game-header">
        <button class="back-btn" id="leave-btn">← Leave</button>
        <div class="game-score">
          <span class="you">You <span id="score-you">0</span></span>
          —
          <span class="opp"><span id="score-opp">0</span> <span id="opp-name">Opponent</span></span>
        </div>
        <div class="timer-bar-wrap"><div class="timer-bar" id="timer-bar"></div></div>
      </div>
      <div class="game-scene" id="scene-host">
        <div class="status-banner" id="status">Waiting for opponent…</div>
        <div class="result-overlay" id="result-overlay" style="display:none;">
          <div class="badge" id="result-badge"></div>
        </div>
      </div>
      <div class="game-controls">
        <button class="choice-btn" data-choice="rock">✊</button>
        <button class="choice-btn" data-choice="paper">✋</button>
        <button class="choice-btn" data-choice="scissors">✌️</button>
      </div>
    </div>
  `;

  const scoreYouEl = root.querySelector('#score-you');
  const scoreOppEl = root.querySelector('#score-opp');
  const oppNameEl = root.querySelector('#opp-name');
  const timerBar = root.querySelector('#timer-bar');
  const statusEl = root.querySelector('#status');
  const resultOverlay = root.querySelector('#result-overlay');
  const resultBadge = root.querySelector('#result-badge');
  const leaveBtn = root.querySelector('#leave-btn');
  const choiceBtns = root.querySelectorAll('.choice-btn');
  const sceneHost = root.querySelector('#scene-host');

  const scene = createScene(sceneHost, { mobile: isMobile() });

  let deadline = 0;
  let timerRaf = null;
  let submittedChoice = null;

  function setStatus(msg, show = true) {
    statusEl.textContent = msg;
    statusEl.style.display = show ? 'block' : 'none';
  }

  function showResult(kind, text) {
    resultBadge.className = `badge ${kind}`;
    resultBadge.textContent = text;
    resultOverlay.style.display = 'flex';
    setTimeout(() => {
      resultOverlay.style.display = 'none';
    }, 1800);
  }

  function clearSelection() {
    submittedChoice = null;
    choiceBtns.forEach((b) => {
      b.classList.remove('selected');
      b.disabled = false;
    });
  }

  function stopTimer() {
    if (timerRaf) cancelAnimationFrame(timerRaf);
    timerRaf = null;
    timerBar.style.width = '0%';
  }

  function startTimer(deadlineMs) {
    deadline = deadlineMs;
    const tick = () => {
      const remaining = Math.max(0, deadline - Date.now());
      const pct = Math.max(0, Math.min(100, (remaining / ROUND_TIMEOUT_MS) * 100));
      timerBar.style.width = pct + '%';
      timerBar.classList.toggle('low', pct < 25);
      if (remaining > 0) {
        timerRaf = requestAnimationFrame(tick);
      }
    };
    tick();
  }

  const handlers = {
    room_ready: ({ opponent_username }) => {
      oppNameEl.textContent = opponent_username;
      setStatus(`Playing vs ${opponent_username}`, false);
    },
    round_start: ({ round_number, deadline_unix_ms }) => {
      clearSelection();
      setStatus(`Round ${round_number} — pick your move`);
      scene.setPhase('select');
      startTimer(deadline_unix_ms);
    },
    opponent_submitted: () => {
      setStatus('Opponent locked in — your turn');
    },
    round_result: ({ your_choice, opponent_choice, winner, score }) => {
      stopTimer();
      scoreYouEl.textContent = score.you;
      scoreOppEl.textContent = score.opponent;
      scene.playReveal(your_choice, opponent_choice, winner);
      const yourText = your_choice ? CHOICE_ICONS[your_choice] : '⏱';
      const oppText = opponent_choice ? CHOICE_ICONS[opponent_choice] : '⏱';
      setStatus(`You ${yourText} vs ${oppText} Opponent`);
      if (winner === 'you') showResult('win', 'YOU WIN');
      else if (winner === 'opponent') showResult('lose', 'YOU LOSE');
      else showResult('draw', 'DRAW');
    },
    opponent_disconnected: ({ grace_seconds }) => {
      setStatus(`Opponent disconnected — waiting ${grace_seconds}s…`);
    },
    opponent_reconnected: () => {
      setStatus('Opponent reconnected.');
    },
    opponent_left: () => {
      setStatus('Opponent left. Returning to lobby…');
      stopTimer();
      setTimeout(onLeave, 1500);
    },
    error: ({ code, message }) => {
      setStatus(`Error: ${code} (${message || ''}). Returning to lobby…`);
      stopTimer();
      setTimeout(onLeave, 2000);
    },
    _close: () => {
      setStatus('Disconnected. Returning to lobby…');
      stopTimer();
      setTimeout(onLeave, 1500);
    },
  };

  const sock = openGameSocket(roomId, handlers);

  choiceBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      if (submittedChoice) return;
      const choice = btn.dataset.choice;
      submittedChoice = choice;
      choiceBtns.forEach((b) => (b.disabled = true));
      btn.classList.add('selected');
      sock.send('submit_choice', { choice });
      setStatus('Waiting for opponent…');
    });
  });

  leaveBtn.addEventListener('click', () => {
    sock.send('leave_room');
    sock.close();
    onLeave();
  });

  if (shareUrl) {
    setTimeout(() => {
      setStatus(`Waiting for opponent — share: ${shareUrl}`);
    }, 100);
  }

  return () => {
    stopTimer();
    scene.dispose();
    sock.close();
  };
}
