// PENDING READ (V9). Purpose: a pending owner read names what is being read, in the words its caller already uses,
// and says for how long it has waited. The code that issues the read calls pendingRead at the moment it issues it, so
// the start time is the read's own, not a guess from the page's wording. Owns: one timer per node. The timer stops
// when the node's text is no longer the words it was given (the read settled and its owner painted the result), when
// the node is not in the page, or when pendingRead is called on the node again. Public contract:
// pendingRead(node, words?) -> node. With words, the node's text is set to them; without, its current text is used.
// The seconds are written to data-pending-seconds and drawn by CSS; the node's text is never rewritten.
const timers = new WeakMap();

export function pendingRead(node, words) {
  if (!node || typeof node !== 'object') return node;
  if (words !== undefined) node.textContent = words;
  const previous = timers.get(node);
  if (previous) clearInterval(previous);
  timers.delete(node);
  node.removeAttribute?.('data-pending-seconds');
  if (typeof node.setAttribute !== 'function' || typeof setInterval !== 'function' || typeof WeakRef !== 'function') return node;
  // the timer holds the node only weakly, so a dialog that is closed and dropped is never kept alive by its clock
  const text = node.textContent, started = Date.now(), held = new WeakRef(node);
  const timer = setInterval(() => {
    const current = held.deref();
    if (!current || current.isConnected !== true || current.textContent !== text) {
      clearInterval(timer);
      if (current) { if (timers.get(current) === timer) timers.delete(current); current.removeAttribute?.('data-pending-seconds'); }
      return;
    }
    const seconds = Math.floor((Date.now() - started) / 1000);
    if (seconds >= 1) current.setAttribute('data-pending-seconds', String(seconds));
  }, 1000);
  timer?.unref?.();
  timers.set(node, timer);
  return node;
}
