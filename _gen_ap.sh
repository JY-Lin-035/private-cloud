var/use/bin/bash
exec python3 << 'PYGEN'
import pathlib, sys

# Build AdminManagement.tsx content
L = []

L.append("import { useEffect, useState, useCallback } from 'react';")
L.append("import { useNavigate } from 'react-router-dom';")
L.append("import { adminApi } from '../../api/adminApi';")
L.append("import { authApi } from '../../api/authApi';")
...

# Fail - Too complicated. Use a very different approach: write the ENTIRE file via base64 encoded string, decoded in bash
print("Cannot do multi-line TSX in this script context")
sys.exit(1)
scriptGEN