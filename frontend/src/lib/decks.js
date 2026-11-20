import { uid } from './api';
let current;
export function deckOwnerKey() {
  if (current) return current;
  try { current = localStorage.getItem('hh_deck_owner'); } catch (_) {}
  if (!current) {
    current = uid();
    try { localStorage.setItem('hh_deck_owner', current); } catch (_) {}
  }
  return current;
}
