import Editor from '@monaco-editor/react';
import { monacoLanguage } from '../../utils/fileClass';
import { ensureMonaco } from '../../utils/monacoSelfHost';

ensureMonaco();

interface Props {
  filename: string;
  value: string;
  readOnly?: boolean;
  onChange: (v: string) => void;
  onSave?: () => void;
}

/** Monaco code/text editor. Language inferred from extension. */
function EditorPane({ filename, value, readOnly, onChange, onSave }: Props) {
  return (
    <div className="h-full w-full min-h-[60vh]">
      <Editor
        height="100%"
        language={monacoLanguage(filename)}
        value={value}
        theme="vs-dark"
        onChange={(v) => onChange(v ?? '')}
        onMount={(editor, monaco) => {
          editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => onSave?.());
        }}
        options={{
          readOnly: !!readOnly,
          minimap: { enabled: false },
          fontSize: 14,
          wordWrap: 'on',
          automaticLayout: true,
          scrollBeyondLastLine: false,
          renderWhitespace: 'selection',
        }}
      />
    </div>
  );
}

export default EditorPane;
