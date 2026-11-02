import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from xhs_connection import XHSConnection, ConnectionError, validate_draft, fill_draft, inspect_page, select_image_mode, IMAGE_INPUT, publication_succeeded


class XHSTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="photomaker-xhs-test-")
        self.root = Path(self.directory.name)
        (self.root / "assets").mkdir()
        (self.root / "assets" / "a.png").write_bytes(b"test-image")
        self.project = {"id": "project-test", "title": "测试标题", "story": {"title": "", "body": "正文", "notes": "不上传"}, "platforms": ["xiaohongshu"], "assets": [{"file": "a.png", "selected": True}]}

    def tearDown(self):
        self.directory.cleanup()

    def test_snapshot_is_exact_and_excludes_private_notes(self):
        draft = validate_draft(self.project, self.root)
        self.project["story"]["body"] = "新正文"
        self.assertEqual(draft["body"], "正文")
        self.assertNotIn("notes", draft)
        self.assertEqual(draft["images"], [str((self.root / "assets" / "a.png").resolve())])

    def test_invalid_inputs_are_rejected_without_truncation(self):
        for change in ({"assets": []}, {"platforms": ["douyin"]}, {"story": {"title": "长" * 21, "body": ""}}, {"assets": [{"file": "../secret", "selected": True}]}):
            project = copy.deepcopy(self.project)
            project.update(change)
            with self.assertRaises(ConnectionError):
                validate_draft(project, self.root)

    def test_requires_live_connection_and_rejects_duplicate_prepare(self):
        connection = XHSConnection(self.root)
        with self.assertRaises(ConnectionError):
            connection.prepare(self.project)
        connection.set_state("connected", "test", True)
        result = connection.prepare(self.project)
        self.assertEqual(result["state"], "preparing")
        self.assertFalse(result["automatic_submit"])
        with self.assertRaises(ConnectionError):
            connection.prepare(self.project)
        fresh = XHSConnection(self.root)
        self.assertFalse(fresh.status()["account_connected"])

    def test_fill_uploads_and_edits_but_never_submits(self):
        page = MagicMock()
        page.url = "https://creator.xiaohongshu.com/publish/publish?source=official"
        page.locator.return_value.first.input_value.return_value = "测试标题"
        page.locator.return_value.first.inner_text.return_value = "正文"
        with patch("xhs_connection.visible", return_value=False):
            fill_draft(page, validate_draft(self.project, self.root))
        page.locator.assert_any_call(IMAGE_INPUT)
        page.get_by_text.assert_not_called()
        page.locator.return_value.first.click.assert_not_called()
        page.keyboard.press.assert_not_called()
        self.assertEqual(page.locator.return_value.first.fill.call_count, 2)
        page.locator.return_value.first.set_input_files.assert_called_once()

    def test_image_mode_skips_offscreen_duplicates_and_waits_for_image_input(self):
        page, image_input, tabs = MagicMock(), MagicMock(), MagicMock()
        offscreen, active = MagicMock(), MagicMock()
        offscreen.bounding_box.return_value = {"x": -9999, "y": 0}
        active.bounding_box.return_value = {"x": 100, "y": 120}
        active.is_visible.return_value = True
        tabs.all.return_value = [offscreen, active]
        image_input.count.side_effect = [0, 1]
        image_input.first.wait_for.side_effect = [TimeoutError(), None]
        page.locator.return_value = image_input
        page.get_by_text.return_value = tabs
        self.assertIs(select_image_mode(page), image_input)
        offscreen.click.assert_not_called()
        active.click.assert_called_once()
        self.assertEqual(image_input.first.wait_for.call_count, 2)
        image_input.first.wait_for.assert_any_call(state="attached", timeout=2500)
        image_input.first.set_input_files.assert_not_called()

    def test_cancel_before_upload_prevents_all_browser_actions(self):
        page = MagicMock()
        def cancelled():
            raise ConnectionError("cancelled")
        with self.assertRaises(ConnectionError):
            fill_draft(page, validate_draft(self.project, self.root), cancelled)
        self.assertEqual(page.mock_calls, [])

    def test_fill_draft_reports_failed_stage_without_publishing(self):
        page = MagicMock()
        page.url = "https://creator.xiaohongshu.com/new/home"
        page.goto.side_effect = TimeoutError("sensitive URL details")
        with self.assertRaisesRegex(ConnectionError, "打开官方发布编辑页失败（TimeoutError）") as error:
            fill_draft(page, validate_draft(self.project, self.root))
        self.assertNotIn("sensitive URL", str(error.exception))
        page.get_by_text.assert_not_called()

    def test_login_requires_host_and_positive_dom_not_cookies(self):
        page = MagicMock()
        page.url = "https://example.com/new/home"
        self.assertEqual(inspect_page(page), "unknown")
        page.url = "https://creator.xiaohongshu.com/new/home"
        with patch("xhs_connection.visible", return_value=False):
            self.assertEqual(inspect_page(page), "unknown")
        with patch("xhs_connection.visible", side_effect=lambda _page, selector: "placeholder" in selector):
            self.assertEqual(inspect_page(page), "login_required")

    def test_editor_upload_controls_are_positive_login_evidence(self):
        page = MagicMock()
        page.url = "https://creator.xiaohongshu.com/publish/publish?source=official"
        page.locator.return_value.count.return_value = 1
        with patch("xhs_connection.visible", side_effect=lambda _page, selector: selector == 'text=上传图文'):
            self.assertEqual(inspect_page(page), "connected")

    def test_login_route_is_not_mistaken_for_connected(self):
        page = MagicMock()
        page.url = "https://creator.xiaohongshu.com/login?redirect=/publish/publish"
        with patch("xhs_connection.visible", side_effect=lambda _page, selector: selector == 'text=上传图文'):
            self.assertEqual(inspect_page(page), "login_required")

    def test_current_workbench_navigation_is_recognized_without_username_class(self):
        page = MagicMock()
        page.url = "https://creator.xiaohongshu.com/new/home"
        with patch("xhs_connection.visible", side_effect=lambda _page, selector: selector in ('text=发布笔记', 'text=笔记管理')):
            self.assertEqual(inspect_page(page), "connected")

    def test_security_verification_blocks_editor_detection(self):
        page = MagicMock()
        page.url = "https://creator.xiaohongshu.com/publish/publish"
        with patch("xhs_connection.visible", return_value=True):
            self.assertEqual(inspect_page(page), "verification_required")

    def test_hidden_first_match_does_not_mask_visible_control(self):
        from xhs_connection import visible
        page, hidden, shown = MagicMock(), MagicMock(), MagicMock()
        hidden.is_visible.return_value = False
        shown.is_visible.return_value = True
        page.locator.return_value.all.return_value = [hidden, shown]
        self.assertTrue(visible(page, "test-selector"))

    def test_prepare_endpoint_requires_confirmation_and_does_not_publish(self):
        import app
        handler = object.__new__(app.Handler)
        with self.assertRaises(app.Problem):
            handler.api("POST", ["projects", "unused", "xhs-draft"], {})
        with patch.object(app, "get", return_value=self.project), patch.object(app, "add_version") as version, patch.object(app, "xhs_connection") as connection:
            connection.return_value.prepare.return_value = {"state": "preparing"}
            handler.api("POST", ["projects", "unused", "xhs-draft"], {"confirm_upload": True})
            version.assert_called_once_with(self.project, "准备小红书草稿（未发布）", "draft_prepare")
            self.assertNotIn("publications", self.project)

    def test_publication_requires_explicit_visible_official_success(self):
        page, message = MagicMock(), MagicMock()
        page.url = "https://creator.xiaohongshu.com/new/manage"
        page.get_by_text.return_value.all.return_value = []
        self.assertFalse(publication_succeeded(page))
        page.get_by_text.return_value.all.return_value = [message]
        message.is_visible.return_value = False
        self.assertFalse(publication_succeeded(page))
        message.is_visible.return_value = True
        self.assertTrue(publication_succeeded(page))
        page.url = "https://example.com/success"
        self.assertFalse(publication_succeeded(page))

    def test_manual_archive_does_not_complete_another_project_or_pending_upload(self):
        connection = XHSConnection(self.root)
        connection.set_state("ready_for_review", "test", True, project_id="first")
        connection.acknowledge_publication("other")
        self.assertEqual(connection.status()["state"], "ready_for_review")
        connection.acknowledge_publication("first")
        self.assertEqual(connection.status()["state"], "published")
        self.assertEqual(connection.status()["confirmation_source"], "user")
        connection.set_state("preparing", "uploading", True)
        connection.acknowledge_publication("first")
        self.assertEqual(connection.status()["state"], "preparing")

    def test_saved_xhs_archive_updates_status_but_failed_archive_does_not(self):
        import app
        handler = object.__new__(app.Handler)
        project = copy.deepcopy(self.project)
        project["publications"] = []
        connection = XHSConnection(self.root)
        connection.set_state("ready_for_review", "test", True, project_id=project["id"])
        with patch.object(app, "get", return_value=project), patch.object(app, "add_version", return_value={"id": "version"}), patch.object(app, "put", return_value=project), patch.object(app, "xhs_connection", return_value=connection):
            handler.api("POST", ["projects", project["id"], "publish"], {"platform_ids": ["weibo"]})
            self.assertEqual(connection.status()["state"], "ready_for_review")
            with patch.object(app, "put", side_effect=OSError("failed write")):
                with self.assertRaises(OSError):
                    handler.api("POST", ["projects", project["id"], "publish"], {"platform_ids": ["xiaohongshu"]})
                self.assertEqual(connection.status()["state"], "ready_for_review")
            handler.api("POST", ["projects", project["id"], "publish"], {"platform_ids": ["xiaohongshu"]})
            self.assertEqual(connection.status()["state"], "published")


if __name__ == "__main__":
    unittest.main()
