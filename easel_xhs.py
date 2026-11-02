# Adapted from ZJU-REAL/Easel, commit 5a597e5f3ef5b01098b53f36caf719dd9a32b7bf.
# Original: skills/shared/scripts/xhs_publish.py (Apache-2.0).
# Changes (2026-10-29): only editor selectors and title length helper retained.
# Upstream reference: xpzouying/xiaohongshu-mcp, Copyright 2025 xpzouying.
# See THIRD_PARTY_NOTICES.md and licenses/Easel-Apache-2.0.txt.

SELECTORS = {
    "creator_tab": "div.creator-tab",
    "upload_input_first": ".upload-input",
    "upload_input_more": "input[type=file]",
    "img_preview": ".img-preview-area .pr",
    "title_input": "div.d-input input, input[placeholder*='标题']",
    "content_quill": "div.ql-editor",
    "content_editable": "div.editor-container [contenteditable='true'], [contenteditable='true']",
    "title_overflow": "div.title-container div.max_suffix",
    "content_overflow": "div.edit-container div.length-error"
}


def calc_title_length(s: str) -> int:
    """小红书标题长度：UTF-16 码元非 ASCII 计 2、ASCII 计 1，再 (n+1)//2 上取整。
    REF pkg/xhsutil/title.go CalcTitleLength。20 全角字 → 20。"""
    utf16 = s.encode("utf-16-le")
    byte_len = 0
    for i in range(0, len(utf16), 2):
        code = utf16[i] | (utf16[i + 1] << 8)
        byte_len += 2 if code > 127 else 1
    return (byte_len + 1) // 2

