"""Headed, persistent, draft-only Xiaohongshu connection. Never submits posts."""
import copy
import importlib.util
import queue
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

from easel_xhs import SELECTORS, calc_title_length

HOME = "https://creator.xiaohongshu.com/new/home"
EDITOR = "https://creator.xiaohongshu.com/publish/publish?source=official&target=image"
IMAGE_INPUT = ', '.join('input[type="file"][accept*="%s" i]' % value
                        for value in ("image", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".avif"))


class ConnectionError(ValueError):
    pass


def validate_draft(project, data):
    assets = [asset for asset in project["assets"] if asset["selected"]]
    title = project["story"]["title"].strip() or project["title"].strip()
    body = project["story"]["body"].strip()
    if "xiaohongshu" not in project.get("platforms", ["xiaohongshu"]):
        raise ConnectionError("请先选择小红书作为发布目标。")
    if not assets or len(assets) > 18:
        raise ConnectionError("本版每次准备 1–18 张图片；请先调整选片。")
    if calc_title_length(title) > 20 or len(body.encode("utf-16-le")) // 2 > 1000:
        raise ConnectionError("标题需不超过 20 个全角字，正文需不超过 1000 个 UTF-16 字符。请先精简，不会自动截断。")
    paths = []
    root = (Path(data) / "assets").resolve()
    for asset in assets:
        path = (root / asset["file"]).resolve()
        if path.parent != root or not path.is_file():
            raise ConnectionError("选片文件缺失或路径无效，请重新导入。")
        paths.append(str(path))
    return {"project_id": project["id"], "title": title, "body": body, "images": paths}


def visible(page, selector):
    # Login and editor bundles can retain hidden copies of the same control.
    # Looking only at the first match misses the actual, visible one.
    return any(node.is_visible() for node in page.locator(selector).all())


def inspect_page(page):
    """Positive DOM evidence required. Cookies alone never mean connected."""
    url = urlsplit(page.url)
    if url.hostname != "creator.xiaohongshu.com":
        return "unknown"
    if visible(page, 'text=安全验证') or visible(page, 'text=操作频繁') or visible(page, 'text=访问受限'):
        return "verification_required"
    if (url.path.rstrip("/") == "/login"
            or visible(page, 'input[placeholder="验证码"], input[placeholder="手机号"], .login-container')):
        return "login_required"
    if (visible(page, SELECTORS["title_input"])
            or visible(page, '.user-info .user-name, .user-info .name, .creator-header .user-info, .user-name')
            or (visible(page, 'text=发布笔记') and visible(page, 'text=笔记管理'))
            or (url.path.startswith("/publish/publish")
                and visible(page, 'text=上传图文')
                and page.locator('input[type="file"]').count() > 0)):
        return "connected"
    return "unknown"


def publication_succeeded(page):
    """Only an explicit official success message counts, never a redirect."""
    if urlsplit(page.url).hostname != "creator.xiaohongshu.com":
        return False
    return any(node.is_visible() for label in ("发布成功", "笔记发布成功")
               for node in page.get_by_text(label, exact=True).all())


def editor_diagnostics(page):
    """Only inspect control structure; exclude account details and draft content."""
    return page.evaluate("""() => ({
        path: location.hostname === 'creator.xiaohongshu.com' ? location.pathname : null,
        inputs: [...document.querySelectorAll('input[type=file]')].map(n => ({
            accept: n.accept, multiple: n.multiple, disabled: n.disabled,
            visible: !!(n.offsetWidth || n.offsetHeight || n.getClientRects().length)
        })),
        tabs: [...document.querySelectorAll('.creator-tab')].map(n => ({
            label: ['上传图文','上传视频','写长文'].find(t => n.textContent.trim() === t) || 'other',
            visible: !!(n.offsetWidth || n.offsetHeight || n.getClientRects().length),
            x: Math.round(n.getBoundingClientRect().x), y: Math.round(n.getBoundingClientRect().y)
        })),
        titleControls: document.querySelectorAll('input[placeholder*=标题]').length,
        editors: document.querySelectorAll('[contenteditable=true]').length,
        previews: document.querySelectorAll('.img-preview-area .pr').length
    })""")


def select_image_mode(page, check=lambda: None):
    """Switch only a reachable image tab; never send images to a video input."""
    check()
    image_input = page.locator(IMAGE_INPUT)
    # The editor hydrates asynchronously after DOMContentLoaded; target=image
    # can render its file input later than the surrounding navigation.
    try:
        image_input.first.wait_for(state="attached", timeout=10000)
        return image_input
    except Exception:
        check()
    if image_input.count() == 0:
        tabs = page.get_by_text("上传图文", exact=True)
        tabs.first.wait_for(state="attached", timeout=15000)
        clicked = False
        for tab in tabs.all():
            box = tab.bounding_box()
            if not (tab.is_visible() and box and box["x"] >= 0 and box["y"] >= 0):
                continue
            check()
            tab.click(timeout=15000)
            clicked = True
            try:
                image_input.first.wait_for(state="attached", timeout=2500)
                break
            except Exception:
                continue
        if not clicked:
            raise ConnectionError("没有找到可点击的「上传图文」标签；请在官方窗口手动切换后重新连接。")
    if image_input.count() == 0:
        raise ConnectionError("已点击「上传图文」，但官方页面仍未提供图片上传控件；未上传任何内容。")
    return image_input


def fill_draft(page, draft, check=lambda: None):
    """Uses Easel editor selectors; intentionally has no submit operation."""
    stage = "打开官方发布编辑页"
    try:
        check()
        page.goto(EDITOR, wait_until="domcontentloaded", timeout=30000)
        check()
        page.locator('.creator-tab').first.wait_for(state="attached", timeout=15000)
        page_state = inspect_page(page)
        if page_state == "verification_required":
            raise ConnectionError("小红书要求安全验证，请在官方窗口完成验证后重新连接。")
        if page_state == "login_required":
            raise ConnectionError("发布页跳转到登录页，请重新登录后再准备草稿。")
        if not urlsplit(page.url).path.startswith("/publish/publish"):
            raise ConnectionError("打开发布页后被跳转；请在官方窗口确认账号登录状态。")

        stage = "选择图文发布模式"
        image_input = select_image_mode(page, check)
        for index, path in enumerate(draft["images"], 1):
            stage = f"上传第 {index} 张图片"
            check()
            image_input.first.set_input_files(path, timeout=15000)
            page.locator(SELECTORS["img_preview"]).nth(index - 1).wait_for(state="visible", timeout=60000)
        stage = "填写标题和正文"
        check()
        title = page.locator(SELECTORS["title_input"]).first
        title.wait_for(state="visible", timeout=15000)
        title.fill(draft["title"], timeout=15000)
        editor = page.locator(SELECTORS["content_quill"] + ', ' + SELECTORS["content_editable"]).first
        editor.wait_for(state="visible", timeout=15000)
        editor.fill(draft["body"], timeout=15000)
        stage = "核对填写结果"
        if title.input_value() != draft["title"] or editor.inner_text().strip() != draft["body"].strip():
            raise ConnectionError("网页内容与当前稿件不一致，请在官方窗口中检查。")
        if visible(page, SELECTORS["title_overflow"]) or visible(page, SELECTORS["content_overflow"]):
            raise ConnectionError("平台提示字数超限，请在官方窗口中修改。")
    except ConnectionError as exc:
        raise ConnectionError(f"{stage}：{exc}") from exc
    except Exception as exc:
        # Expose stage and exception type, but not URL, local paths, or browser internals.
        raise ConnectionError(f"{stage}失败（{type(exc).__name__}）。请查看官方窗口当前页面。") from exc
    # No click of any publish button, no Enter key submission, no success claim.


class XHSConnection:
    def __init__(self, data):
        self.data = Path(data)
        self.lock = threading.RLock()
        self.thread = None
        self.stop_event = threading.Event()
        self.commands = queue.Queue()
        self.state = {"state": "disconnected", "account_connected": False, "message": "尚未打开小红书登录窗口。", "project_id": None}

    def status(self):
        with self.lock:
            result = copy.deepcopy(self.state)
        result["available"] = importlib.util.find_spec("playwright") is not None
        result["automatic_submit"] = False
        return result

    def set_state(self, state, message, connected=False, **extra):
        with self.lock:
            self.state.update(state=state, message=message, account_connected=connected, **extra)

    def connect(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ConnectionError("连接窗口仍在运行，请使用现有窗口，或先关闭连接。")
            if not self.status()["available"]:
                raise ConnectionError("缺少 Playwright。请使用 .venv/bin/python app.py 启动，或按 README 安装连接依赖。")
            self.stop_event.clear()
            self.commands = queue.Queue()
            self.set_state("starting", "正在打开小红书官方登录窗口…", project_id=None, diagnostics=None)
            self.thread = threading.Thread(target=self.run, daemon=True, name="xiaohongshu-browser")
            self.thread.start()
        return self.status()

    def prepare(self, project):
        draft = validate_draft(project, self.data)
        with self.lock:
            if self.state["state"] != "connected":
                raise ConnectionError("请先连接小红书；已有草稿时请先完成或关闭窗口，避免覆盖。")
            self.set_state("preparing", "正在上传选片并填写草稿，请勿操作该窗口…", True, project_id=project["id"])
            self.commands.put(draft)
        return self.status()

    def acknowledge_publication(self, project_id):
        """Called only after the user saves a local publication record."""
        with self.lock:
            if self.state.get("project_id") not in (None, project_id):
                return
            if self.state["state"] in ("starting", "preparing", "closing"):
                return
            self.set_state("published", "已由你确认在小红书发布，发布档案已保存。平台审核状态请在官网查看。",
                           self.state["account_connected"], project_id=project_id, confirmation_source="user")

    def close(self):
        self.stop_event.set()
        self.set_state("closing", "正在关闭连接窗口；本机登录会话会保留。")
        if not self.thread or not self.thread.is_alive():
            self.set_state("disconnected", "连接窗口已关闭；下次连接会重新验证登录。", project_id=None)
        return self.status()

    def check(self):
        if self.stop_event.is_set():
            raise ConnectionError("操作已取消。")

    def run(self):
        context = None
        try:
            from playwright.sync_api import sync_playwright
            profile = self.data / "browser-profiles" / "xiaohongshu"
            profile.mkdir(parents=True, exist_ok=True, mode=0o700)
            profile.chmod(0o700)
            with sync_playwright() as runtime:
                options = {"headless": False, "locale": "zh-CN", "viewport": {"width": 1280, "height": 900}}
                if Path('/Applications/Google Chrome.app').exists():
                    options["channel"] = "chrome"
                context = runtime.chromium.launch_persistent_context(str(profile), **options)
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(EDITOR, wait_until="domcontentloaded", timeout=30000)
                    self.set_state("login_required", "请在官方窗口扫码或手动登录；验证码由你在该窗口完成。")
                    deadline = time.monotonic() + 600
                    login_probe_at = time.monotonic() + 8
                    editor_probe_done = False
                    while not self.stop_event.is_set() and not page.is_closed():
                        with self.lock:
                            # Expose only the official pathname for troubleshooting;
                            # never return URL queries, cookies, or account details.
                            location = urlsplit(page.url)
                            self.state["page_path"] = location.path if location.hostname == "creator.xiaohongshu.com" else None
                        current = inspect_page(page)
                        if current == "connected" and self.status().get("diagnostics") is None:
                            # Confirm the image uploader is actually available before
                            # enabling draft preparation. No files or text are supplied.
                            if urlsplit(page.url).path.startswith("/publish/publish"):
                                try:
                                    select_image_mode(page, self.check)
                                except Exception as exc:
                                    self.set_state("error", "检测图文上传控件失败（%s）；未上传任何内容。请检查官方窗口。" % type(exc).__name__)
                            with self.lock:
                                self.state["diagnostics"] = editor_diagnostics(page)
                        old = self.status()["state"]
                        if (old == "ready_for_review" and current not in ("login_required", "verification_required")
                                and publication_succeeded(page)):
                            self.set_state("published", "官网已显示发布成功。请登记发布链接留档；审核及可见性以小红书为准。",
                                           True, confirmation_source="official_page")
                            old = "published"
                        # The creator home page changes frequently; verify a logged-in
                        # session through the official editor once after giving QR login time.
                        if (current == "unknown" and old in ("login_required", "unknown")
                                and not editor_probe_done
                                and time.monotonic() >= login_probe_at):
                            page.goto(EDITOR, wait_until="domcontentloaded", timeout=30000)
                            editor_probe_done = True
                            current = inspect_page(page)
                        if current == "verification_required":
                            self.set_state("verification_required", "平台要求安全验证。自动操作已暂停，请在官方窗口处理。")
                        elif current == "login_required":
                            self.set_state("login_required", "尚未登录或登录已失效，请在官方窗口完成登录。")
                        elif current == "connected" and old in ("login_required", "unknown", "verification_required"):
                            self.set_state("connected", "已检测到官方创作工作台或发布控件；可从作品中准备草稿。", True)
                            deadline = time.monotonic() + 1800
                        elif current == "unknown" and old not in ("ready_for_review", "published", "error"):
                            message = ("暂未识别登录状态，请等待扫码登录完成。" if not editor_probe_done else
                                       "尚未识别官方发布控件；请在连接窗口点击「发布笔记」，确认没有验证提示。不会上传内容。")
                            self.set_state("unknown", message)
                        try:
                            draft = self.commands.get_nowait()
                        except queue.Empty:
                            draft = None
                        if draft:
                            if current != "connected":
                                raise ConnectionError("登录状态已变化。未继续上传，请关闭连接后重新登录。")
                            try:
                                fill_draft(page, draft, self.check)
                                self.set_state("ready_for_review", "草稿已填入官方窗口，尚未发布、未确认云端保存。请检查图片顺序、话题与正文，并亲自点击发布。", True)
                            except Exception as exc:
                                self.set_state("error", f"草稿准备中断：{exc} 不会自动重试或提交。", project_id=draft["project_id"])
                                try:
                                    with self.lock:
                                        self.state["diagnostics"] = editor_diagnostics(page)
                                except Exception:
                                    pass
                            deadline = time.monotonic() + 1800
                        if time.monotonic() > deadline:
                            break
                        page.wait_for_timeout(500)
                finally:
                    context.close()
            self.set_state("disconnected", "连接窗口已关闭。登录会话保存在本机，下次连接会重新验证。", project_id=None)
        except Exception:
            self.set_state("error", "浏览器连接中断。请检查 Chrome、网络及连接依赖，关闭后重试；不会自动重试发布。")
