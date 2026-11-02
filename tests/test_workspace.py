import base64
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aA1cAAAAASUVORK5CYII=")


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="photomaker-test-")
        self.original = app.DATA
        app.DATA = Path(self.directory.name)
        app.init()
        self.project = app.new_project({"title": "测试作品", "brief": "保持真实", "platform": "小红书"})

    def tearDown(self):
        app.DATA = self.original
        self.directory.cleanup()

    def upload(self, raw=PNG, **kwargs):
        return app.upload(self.project["id"], {"data": base64.b64encode(raw).decode(), "name": "原片.png", "features": {"width": 1, "height": 1, "contrast": 25}, **kwargs})

    def latest(self):
        return app.get("projects", self.project["id"])

    def test_originals_persist_and_exact_duplicates_are_skipped(self):
        first = self.upload()
        second = self.upload()
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(len(self.latest()["assets"]), 1)
        self.assertEqual((app.DATA / "assets" / first["asset"]["file"]).read_bytes(), PNG)
        app.init()
        self.assertEqual(len(self.latest()["assets"]), 1)

    def test_import_rejects_invalid_and_oversized_images(self):
        for raw in (b"not an image", b"", b"x" * (app.MAX_IMAGE + 1)):
            with self.assertRaises(app.Problem):
                app.store_image(raw)
        with self.assertRaises(app.Problem):
            app.upload(self.project["id"], {"data": "invalid@@"})

    def test_late_background_asset_not_lost_by_stale_editor(self):
        first = self.upload()["asset"]
        stale = self.latest()
        second = self.upload(PNG + b"second")["asset"]
        updated = app.update_project(self.project["id"], {"assets": [{"id": first["id"], "selected": False, "role": "细节"}]})
        self.assertEqual([a["id"] for a in updated["assets"]], [first["id"], second["id"]])
        self.assertFalse(updated["assets"][0]["selected"])

    def test_order_update_rejects_foreign_and_duplicate_asset_ids(self):
        asset = self.upload()["asset"]
        with self.assertRaises(app.Problem):
            app.update_project(self.project["id"], {"assets": [{"id": "unknown"}]})
        with self.assertRaises(app.Problem):
            app.update_project(self.project["id"], {"assets": [{"id": asset["id"]}, {"id": asset["id"]}]})

    def test_local_plan_is_labeled_and_generates_checkpoint(self):
        self.upload()
        job, project = app.create_job(self.project["id"], "plan", "local")
        app.run_plan(job["id"], project, "local")
        result = self.latest()
        self.assertEqual(app.get("jobs", job["id"])["status"], "completed")
        self.assertEqual([v["source"] for v in result["versions"]], ["checkpoint", "local"])
        self.assertIn("本地规则草案", result["story"]["notes"])
        self.assertEqual(result["story"]["body"], "保持真实")

    def test_model_plan_rejects_unknown_ids_and_missing_fields(self):
        self.upload()
        project = self.latest()
        valid = app.local_plan(project)
        app.validate_plan(valid, project)
        invalid = copy.deepcopy(valid)
        invalid["selection"][0]["id"] = "fabricated"
        with self.assertRaises(app.Problem):
            app.validate_plan(invalid, project)
        invalid = copy.deepcopy(valid)
        invalid["story"].pop("body")
        with self.assertRaises(app.Problem):
            app.validate_plan(invalid, project)

    def test_ai_never_overwrites_concurrent_edits(self):
        self.upload()
        job, snapshot = app.create_job(self.project["id"], "plan", "ai")
        def edited_plan(project, job_id):
            app.update_project(project["id"], {"brief": "用户的新要求"})
            return app.local_plan(project)
        with patch.object(app, "ai_plan", side_effect=edited_plan):
            app.run_plan(job["id"], snapshot, "ai")
        self.assertEqual(app.get("jobs", job["id"])["status"], "failed")
        self.assertEqual(self.latest()["brief"], "用户的新要求")
        self.assertEqual(self.latest()["versions"], [])

    def test_ai_specialists_really_call_model_and_save_provenance(self):
        self.upload()
        app.save_settings({"ai_base_url": "http://127.0.0.1:9999/v1", "ai_model": "test-model"})
        asset = self.latest()["assets"][0]
        def model(config, role, payload, images=None):
            if role == "选片师":
                return {"selection": [{"id": asset["id"], "role": "开场"}], "reason": "测量指标草案"}
            if role == "艺术指导":
                return {"name": "蓝调", "description": "柔和蓝色", "positive_prompt": "muted blue", "negative_prompt": "oversaturated"}
            return {"title": "测试标题", "body": "测试文案", "notes": "待确认"}
        job, project = app.create_job(self.project["id"], "plan", "ai")
        with patch.object(app, "call_model", side_effect=model) as mock:
            app.run_plan(job["id"], project, "ai")
        result = self.latest()
        self.assertEqual(mock.call_count, 3)
        self.assertEqual(app.get("jobs", job["id"])["status"], "completed")
        self.assertEqual(result["story"]["title"], "测试标题")
        self.assertEqual(result["versions"][-1]["details"]["provider"]["model"], "test-model")
        self.assertEqual(app.get("recipes", result["recipe_id"])["name"], "蓝调")

    def test_invalid_ai_plan_keeps_project_untouched(self):
        self.upload()
        job, project = app.create_job(self.project["id"], "plan", "ai")
        with patch.object(app, "ai_plan", return_value={"selection": []}):
            app.run_plan(job["id"], project, "ai")
        self.assertEqual(self.latest(), project)
        self.assertEqual(app.get("jobs", job["id"])["status"], "failed")

    def test_version_snapshot_is_independent_and_export_contains_originals(self):
        first = self.upload()["asset"]
        project = self.latest()
        version = app.add_version(project, "初版")
        project["story"]["title"] = "后来的标题"
        project["assets"][0]["role"] = "细节"
        self.assertEqual(version["story"]["title"], "")
        self.assertEqual(version["assets"][0]["role"], "环境")
        archive = zipfile.ZipFile(io.BytesIO(app.export_project(project)))
        self.assertIn("project.json", archive.namelist())
        self.assertIn("发布文案.md", archive.namelist())
        self.assertEqual(archive.read("originals/" + first["file"]), PNG)
        self.assertIn("publish/01_细节.png", archive.namelist())

    def test_duplicate_has_separate_history_and_shared_immutable_originals(self):
        self.upload()
        app.add_version(self.latest(), "原作初稿")
        clone = app.duplicate(self.project["id"])
        self.assertNotEqual(clone["id"], self.project["id"])
        self.assertEqual(clone["assets"][0]["file"], self.latest()["assets"][0]["file"])
        self.assertEqual(clone["versions"][0]["source"], "duplicate")
        self.assertEqual(clone["publications"], [])

    def test_three_targets_are_not_claimed_connected(self):
        self.assertEqual([p["id"] for p in app.PLATFORMS], ["xiaohongshu", "douyin", "weibo"])
        self.assertTrue(all(not target["account_connected"] for target in app.PLATFORMS))
        for invalid in ([], ["unknown"], [None], [["xiaohongshu"]], "xiaohongshu"):
            with self.assertRaises(app.Problem):
                app.valid_platforms(invalid)

    def test_multiplatform_export_keeps_exact_originals_and_only_selected_targets(self):
        asset = self.upload()["asset"]
        project = app.update_project(self.project["id"], {"platforms": ["douyin", "weibo", "douyin"]})
        self.assertEqual(project["platforms"], ["douyin", "weibo"])
        self.assertEqual(project["platform"], "抖音")
        with zipfile.ZipFile(io.BytesIO(app.export_project(project))) as archive:
            for target in ("douyin", "weibo"):
                self.assertEqual(archive.read("platforms/" + target + "/images/01_环境.png"), PNG)
                self.assertIn("platforms/" + target + "/发布文案.md", archive.namelist())
            self.assertFalse(any(name.startswith("platforms/tiktok/") for name in archive.namelist()))
            self.assertEqual(archive.read("originals/" + asset["file"]), PNG)

    def test_legacy_platform_mapping_does_not_change_existing_record(self):
        project = self.latest()
        project.pop("platforms")
        project["platform"] = "朋友圈"
        app.put("projects", project)
        self.assertEqual(self.latest()["platforms"], ["xiaohongshu"])
        self.assertEqual(self.latest()["legacy_platforms"], ["moments"])
        self.assertEqual(app.records("projects")[0]["platform"], "朋友圈")

    def test_publication_validates_targets_before_creating_version(self):
        self.upload()
        handler = object.__new__(app.Handler)
        with self.assertRaises(app.Problem):
            handler.api("POST", ["projects", self.project["id"], "publish"], {"platform_ids": []})
        with self.assertRaises(app.Problem):
            handler.api("POST", ["projects", self.project["id"], "publish"], {"platform_ids": ["weibo", "douyin"], "url": "https://example.com/post"})
        self.assertEqual(self.latest()["versions"], [])
        project = handler.api("POST", ["projects", self.project["id"], "publish"], {"platform_ids": ["weibo"], "url": "https://example.com/post"})
        self.assertEqual(project["publications"][0]["platform_id"], "weibo")
        self.assertEqual(len(project["publications"]), 1)

    def test_api_key_is_never_returned(self):
        public = app.save_settings({"ai_api_key": "secret-test-only", "ai_base_url": "http://localhost:8000/v1", "ai_model": "local"})
        self.assertTrue(public["has_api_key"])
        self.assertNotIn("secret-test-only", json.dumps(public))
        self.assertEqual((app.DATA / "settings.json").stat().st_mode & 0o777, 0o600)

    def test_comfy_rejects_ui_workflow_and_replaces_all_tokens(self):
        with self.assertRaises(app.Problem):
            app.make_recipe({"workflow": {"nodes": []}})
        workflow = {"1": {"class_type": "LoadImage", "inputs": {"image": "{{input_image}}"}},
                    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "hello {{positive_prompt}}"}}}
        recipe = app.make_recipe({"workflow": workflow})
        replaced = app.replace_tokens(recipe["workflow"], {"input_image": "foo.png", "positive_prompt": "blue"})
        self.assertEqual(replaced["1"]["inputs"]["image"], "foo.png")
        self.assertEqual(replaced["2"]["inputs"]["text"], "hello blue")
        self.assertEqual(workflow["1"]["inputs"]["image"], "{{input_image}}")

    def test_comfy_execution_saves_output_and_actual_recipe(self):
        asset = self.upload()["asset"]
        app.save_settings({"comfy_url": "http://127.0.0.1:8188"})
        recipe = app.make_recipe({"name": "风格测试", "positive_prompt": "blue", "workflow": {"1": {"class_type": "SaveImage", "inputs": {"text": "{{positive_prompt}}"}}}})
        app.update_project(self.project["id"], {"recipe_id": recipe["id"]})
        job, project = app.create_job(self.project["id"], "comfyui")
        def response(url, body=None, **kwargs):
            if url.endswith("/prompt"):
                self.assertEqual(body["prompt"]["1"]["inputs"]["text"], "blue")
                return {"prompt_id": "fake-prompt"}
            return {"fake-prompt": {"outputs": {"1": {"images": [{"filename": "output.png"}]}}, "status": {"status_str": "success"}}}
        with patch.object(app, "remote", side_effect=response), patch.object(app.urllib.request, "urlopen", return_value=io.BytesIO(PNG + b"generated")):
            app.run_comfy(job["id"], project, recipe, asset)
        result = self.latest()
        self.assertEqual(app.get("jobs", job["id"])["status"], "completed")
        self.assertEqual(len(result["assets"]), 2)
        output = result["assets"][-1]
        self.assertFalse(output["selected"])
        self.assertEqual(output["parent_asset_id"], asset["id"])
        self.assertEqual(output["generation"]["workflow"]["1"]["inputs"]["text"], "blue")
        self.assertEqual(result["versions"][-1]["source"], "comfyui")

    def test_restart_marks_unfinished_jobs_failed(self):
        self.upload()
        job, _ = app.create_job(self.project["id"], "plan", "local")
        app.init()
        self.assertEqual(app.get("jobs", job["id"])["status"], "failed")


if __name__ == "__main__":
    unittest.main()
