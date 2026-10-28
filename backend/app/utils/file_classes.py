"""File classification shared by preview/edit endpoints (single source of truth
for what may be created, edited inline, streamed or converted).

Categories drive capability:
  editable   -> GET/PUT /api/files/content, /api/files/create
  sandbox    -> rendered ONLY through the CSP-sandboxed raw endpoint (html/svg)
  inline     -> allowed for the (P2) Range stream endpoint
  office     -> (P3) LibreOffice -> PDF conversion preview
  other      -> download only
"""
import os

MAX_EDIT_BYTES = 2 * 1024 * 1024

_MD = {"md", "markdown", "mdx"}
_JSON = {"json", "jsonc", "map"}
_CODE = {
    "txt", "log", "csv", "tsv", "ini", "cfg", "conf", "env", "properties",
    "yaml", "yml", "toml", "xml", "xsd", "xsl", "plist",
    "c", "h", "cpp", "cc", "cxx", "hpp", "hh", "hxx", "cs", "java", "go",
    "rs", "rb", "php", "swift", "kt", "kts", "lua", "pl", "pm", "r", "dart",
    "vue", "svelte", "sql", "sh", "bash", "zsh", "fish", "ps1", "psm1",
    "bat", "cmd", "mk", "gradle", "groovy", "scala", "clj", "ex", "exs",
    "erl", "hs", "ml", "nim", "zig", "jl", "tf", "dockerfile", "makefile",
    "gitignore", "dockerignore", "editorconfig", "babelrc", "eslintrc",
    "css", "scss", "sass", "less", "styl",
    "js", "jsx", "ts", "tsx", "mjs", "cjs", "py", "pyi", "ipynb",
}
_HTML = {"html", "htm", "xhtml"}
_SANDBOX = _HTML | {"svg"}
_IMAGE = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "avif", "ico"}
_VIDEO = {"mp4", "m4v", "webm", "ogv", "mov"}
_AUDIO = {"mp3", "m4a", "aac", "wav", "flac", "ogg", "oga", "opus"}
_PDF = {"pdf"}
_DOCX = {"docx"}
_OFFICE = {"doc", "odt", "rtf", "ppt", "pptx", "pps", "ppsx", "xls", "xlsx", "ods", "odp", "csv_office"}
# macro carriers: never converted server-side, download only
_MACRO_EXT = {"docm", "pptm", "xlsm", "dotm", "xltm"}

EDITABLE_CATEGORIES = {"text", "markdown", "json", "code", "html", "svg"}


def ext_of(filename: str) -> str:
    base = os.path.basename(filename or "")
    if "." not in base:
        return base.lower()  # dockerfile, makefile ...
    return base.rsplit(".", 1)[-1].lower()


def classify(filename: str) -> str:
    e = ext_of(filename)
    if e in _MD:
        return "markdown"
    if e in _JSON:
        return "json"
    if e in _HTML:
        return "html"
    if e == "svg":
        return "svg"
    if e in _CODE:
        return "code" if e not in {"txt", "log", "csv", "tsv"} else "text"
    if e in _IMAGE:
        return "image"
    if e in _VIDEO:
        return "video"
    if e in _AUDIO:
        return "audio"
    if e in _PDF:
        return "pdf"
    if e in _DOCX:
        return "docx"
    if e in _OFFICE:
        return "office"
    return "other"


def is_editable(filename: str) -> bool:
    return classify(filename) in EDITABLE_CATEGORIES


def is_sandbox_preview(filename: str) -> bool:
    return ext_of(filename) in _SANDBOX


def is_streamable(filename: str) -> bool:
    return classify(filename) in {"image", "video", "audio", "pdf"}


def is_office(filename: str) -> bool:
    e = ext_of(filename)
    return e in _OFFICE or e in _DOCX or classify(filename) == "docx"


def is_macro_doc(filename: str) -> bool:
    return ext_of(filename) in _MACRO_EXT
