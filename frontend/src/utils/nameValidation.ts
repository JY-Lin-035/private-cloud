// Frontend mirror of backend app/utils/name_validation.py denylist.
// Symbols, spaces and emoji are allowed; only control chars, path/Windows
// reserved characters, bidi/zero-width spoofing, hidden-file and trailing-dot
// names are rejected.

export const MAX_NAME_LENGTH = 255;

// eslint-disable-next-line no-control-regex
const FORBIDDEN = /[\x00-\x1f\x7f<>"|?*/\\:\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]/;

export function validateDisplayName(raw: string): string | null {
  const name = (raw ?? '').trim();
  if (name === '') return '名稱不可僅為空白字元';
  if (name.length > MAX_NAME_LENGTH) return `名稱不可超過 ${MAX_NAME_LENGTH} 字元`;
  if (FORBIDDEN.test(name)) return '名稱包含不允許的字元';
  if (name === '.' || name === '..' || name.startsWith('.')) return '名稱不可為隱藏檔格式（以 . 開頭）';
  if (name.endsWith('.')) return '名稱不可使用 . 結尾';
  return null;
}
