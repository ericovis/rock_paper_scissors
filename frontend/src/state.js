export function createStore(initial) {
  let state = initial;
  const listeners = new Set();
  return {
    get: () => state,
    set: (patch) => {
      state = { ...state, ...patch };
      listeners.forEach((fn) => fn(state));
    },
    subscribe: (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}

export function isMobile() {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(pointer: coarse)').matches &&
    window.innerWidth < 768
  );
}
