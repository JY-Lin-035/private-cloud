// Frontend mirror of backend app/utils/file_classes.ts (keep in sync!).

const MD = new Set(['md', 'markdown', 'mdx']);
const JSON_EXT = new Set(['json', 'jsonc', 'map']);
const HTML = new Set(['html', 'htm', 'xhtml']);
const CODE = new Set([
  'txt', 'log', 'csv', 'tsv', 'ini', 'cfg', 'conf', 'env', 'properties',
  'yaml', 'yml', 'toml', 'xml', 'xsd', 'xsl', 'plist',
  'c', 'h', 'cpp', 'cc', 'cxx', 'hpp', 'hh', 'hxx', 'cs', 'java', 'go',
  'rs', 'rb', 'php', 'swift', 'kt', 'kts', 'lua', 'pl', 'pm', 'r', 'dart',
  'vue', 'svelte', 'sql', 'sh', 'bash', 'zsh', 'fish', 'ps1', 'psm1',
  'bat', 'cmd', 'mk', 'gradle', 'groovy', 'scala', 'clj', 'ex', 'exs',
  'erl', 'hs', 'ml', 'nim', 'zig', 'jl', 'tf', 'dockerfile', 'makefile',
  'gitignore', 'dockerignore', 'editorconfig', 'babelrc', 'eslintrc',
  'css', 'scss', 'sass', 'less', 'styl',
  'js', 'jsx', 'ts', 'tsx', 'mjs', 'cjs', 'py', 'pyi', 'ipynb',
]);
const IMAGE = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'avif', 'ico']);
const VIDEO = new Set(['mp4', 'm4v', 'webm', 'ogv', 'mov']);
const AUDIO = new Set(['mp3', 'm4a', 'aac', 'wav', 'flac', 'ogg', 'oga', 'opus']);
const PDF = new Set(['pdf']);
const OFFICE_CLIENT = new Set(['docx', 'pptx', 'odp', 'odt']);
const OFFICE_OTHER = new Set(['doc', 'rtf', 'pps', 'ppsx', 'xls', 'xlsx', 'ods']);

export type FileCategory =
  | 'text' | 'markdown' | 'json' | 'code' | 'html' | 'svg'
  | 'image' | 'video' | 'audio' | 'pdf' | 'office' | 'office-legacy' | 'other';

export function extOf(filename: string): string {
  const base = (filename || '').split('/').pop() || '';
  const i = base.lastIndexOf('.');
  return i < 0 ? base.toLowerCase() : base.slice(i + 1).toLowerCase();
}

export function classify(filename: string): FileCategory {
  const e = extOf(filename);
  if (MD.has(e)) return 'markdown';
  if (JSON_EXT.has(e)) return 'json';
  if (HTML.has(e)) return 'html';
  if (e === 'svg') return 'svg';
  if (CODE.has(e)) return (e === 'txt' || e === 'log' || e === 'csv' || e === 'tsv') ? 'text' : 'code';
  if (IMAGE.has(e)) return 'image';
  if (VIDEO.has(e)) return 'video';
  if (AUDIO.has(e)) return 'audio';
  if (PDF.has(e)) return 'pdf';
  if (OFFICE_CLIENT.has(e)) return 'office';
  if (OFFICE_OTHER.has(e)) return 'office-legacy';
  return 'other';
}

const EDITABLE: FileCategory[] = ['text', 'markdown', 'json', 'code', 'html', 'svg'];
export const isEditable = (f: string) => EDITABLE.includes(classify(f));
export const isStreamable = (f: string) => ['image', 'video', 'audio', 'pdf'].includes(classify(f));

const LANG: Record<string, string> = {
  py: 'python', js: 'javascript', jsx: 'javascript', mjs: 'javascript', cjs: 'javascript',
  ts: 'typescript', tsx: 'typescript', c: 'c', h: 'c', cpp: 'cpp', cc: 'cpp', cxx: 'cpp',
  hpp: 'cpp', hh: 'cpp', cs: 'csharp', rb: 'ruby', pl: 'perl', sh: 'shell', bash: 'shell',
  zsh: 'shell', ps1: 'powershell', bat: 'bat', yml: 'yaml', ini: 'ini', cfg: 'ini',
  conf: 'ini', env: 'ini', properties: 'ini', dockerfile: 'dockerfile', makefile: 'makefile',
  mk: 'makefile', md: 'markdown', markdown: 'markdown', json: 'json', jsonc: 'jsonc',
  html: 'html', htm: 'html', xhtml: 'html', css: 'css', scss: 'scss', less: 'less',
  xml: 'xml', svg: 'xml', sql: 'sql', go: 'go', rs: 'rust', java: 'java', php: 'php',
  swift: 'swift', kt: 'kotlin', lua: 'lua', vue: 'html', csv: 'plaintext', log: 'plaintext',
  txt: 'plaintext', toml: 'ini', gradle: 'groovy',
};
export const monacoLanguage = (filename: string): string => LANG[extOf(filename)] || 'plaintext';
