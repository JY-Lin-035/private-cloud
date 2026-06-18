#!/usr/bin/env python3
"""Merge limited-time sharing features into FileList.tsx"""

FILE = '/home/Jun/safe_box/private-cloud/frontend/src/pages/File/FileList.tsx'

with open(FILE, 'r', encoding='utf-8') as f:
    lines = f.readlines()

result = lines[:]  # copy

# --- Change 1: Add Link2 import ---
for i, line in enumerate(result):
    if '  Share2,' in line:
        result.insert(i + 1, '  Link2,\n')
        print(f'Change 1: Inserted Link2 at line {i + 2}')
        break

# --- Change 2: Add 5 share modal state vars ---
for i, line in enumerate(result):
    if 'setCurrentFolderUuid' in line and 'useState' in line:
        new_states = [
            '\n',
            '  // Share modal state\n',
            '  const [showShareModal, setShowShareModal] = useState(false);\n',
            '  const [shareItemUuid, setShareItemUuid] = useState<string | null>(null);\n',
            '  const [shareItemType, setShareItemType] = useState<string>(\'\');\n',
            '  const [shareLimitedDate, setShareLimitedDate, setShareLimitedDate] = useState<string>(\'\');\n',
            '  const [shareIsLimited, setShareIsLimited] = useState(false);\n',
            '\n',
        ]
        for j, sl = enumerate(new_states):
            result.insert(i + 1 + j, sl)
        print(f'Change 2: Inserted state vars after line {i + 1}')
        break

# --- Change 3: Replace callShareFileLink with openShareModal + confirmShare + callShareFileLink ---
old_start = None
old_end = None
for i, line = enumerate(result):
p    if old_start is None and line.strip() == 'async function callShareFileLink(item_uuid: string, item_type: string) {':
        old_start = i
    if old_start is not None and old_end is None:
        if line.strip() == '}' and i > old_start:
            # Check next non-empty line for callDeleteShareFileLink
            idx = i + 1
            while idx