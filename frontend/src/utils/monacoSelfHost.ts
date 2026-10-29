// Self-hosted Monaco (no CDN): fixes CSP style-src breakage AND removes the
// third-party runtime supply-chain dependency identified in the security plan.
import * as monaco from 'monaco-editor';
import { loader } from '@monaco-editor/react';
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';
import jsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker';
import cssWorker from 'monaco-editor/esm/vs/language/css/css.worker?worker';
import htmlWorker from 'monaco-editor/esm/vs/language/html/html.worker?worker';
import tsWorker from 'monaco-editor/esm/vs/language/typescript/ts.worker?worker';

// only need the languages we preview/edit; the default full build already
// includes them via the workers above.

let configured = false;
export function ensureMonaco() {
  if (configured) return;
  configured = true;
  (self as unknown as { MonacoEnvironment: unknown }).MonacoEnvironment = {
    getWorker(_workerId: string, label: string) {
      switch (label) {
        case 'json': return new jsonWorker();
        case 'css': case 'scss': case 'less': return new cssWorker();
        case 'html': case 'handlebars': case 'razor': return new htmlWorker();
        case 'typescript': case 'javascript': return new tsWorker();
        default: return new editorWorker();
      }
    },
  };
  loader.config({ monaco });
}
