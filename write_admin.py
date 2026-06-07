#!/usr/bin/env python3
import pathlib

content = open('/dev/stdin').read()
pathlib.Path('/home/Jun/safe_box/private-cloud/frontend/src/pages/AdminManagement/AdminManagement.tsx').write_text(content)
print("Written successfully")