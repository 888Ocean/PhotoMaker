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


def solid_png(red, green, blue, width=8, height=8):
    import struct
    import zlib
    raw = b"".join(b"\x00" + bytes((red, green, blue)) * width for _ in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class GroupingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="photomaker-group-")
        self.original = app.DATA
        app.DATA = Path(self.directory.name)
        app.init()
        self.project = app.new_project({"title": "潮汐", "brief": "安静的蓝色", "platform": "小红书"})

    def tearDown(self):
        app.DATA = self.original
        self.directory.cleanup()

    def upload(self, raw, **kwargs):
        body = {"data": base64.b64encode(raw).decode(), "name": "原片.png", "features": {"width": 1, "height": 1, "contrast": 25}}
        body.update(kwargs)
        return app.upload(self.project["id"], body)

    def test_png_sample_fills_missing_metrics_without_replacing_client_palette(self):
        sampled = self.upload(solid_png(20, 40, 180), features={})["asset"]["features"]
        self.assertEqual(sampled["width"], 8)
        self.assertGreater(sampled["brightness"], 0)
        self.assertTrue(sampled["palette"])
        kept = self.upload(solid_png(200, 20, 20), name="kept.png", features={"width": 4, "height": 4, "brightness": 10, "contrast": 11, "palette": ["#112233"]})
        self.assertEqual(kept["asset"]["features"]["palette"], ["#112233"])
        self.assertEqual(kept["asset"]["features"]["brightness"], 10)

    def test_color_groups_split_warm_and_blue_and_local_review_is_labeled(self):
        warm = {"width": 8, "height": 8, "brightness": 60, "contrast": 20, "palette": ["#c06030", "#d07040"]}
        warm_b = {"width": 8, "height": 8, "brightness": 62, "contrast": 30, "palette": ["#c86838", "#cc7048"]}
        blue = {"width": 8, "height": 8, "brightness": 40, "contrast": 12, "palette": ["#204080", "#183868"]}
        self.upload(solid_png(1, 1, 1), name="a.png", features=warm)
        self.upload(solid_png(2, 2, 2), name="b.png", features=warm_b)
        self.upload(solid_png(3, 3, 3), name="c.png", features=blue)
        job, project = app.create_job(self.project["id"], "groups", "local")
        with patch.object(app, "remote", side_effect=AssertionError("local grouping must not use the network")):
            app.run_groups(job["id"], project, "local")
        result = self.latest()
        self.assertEqual(app.get("jobs", job["id"])["status"], "completed")
        self.assertEqual(len(result["groups"]), 2)
        warm_ids = {asset["id"] for asset in result["assets"] if asset["name"] in ("a.png", "b.png")}
        blue_ids = {asset["id"] for asset in result["assets"] if asset["name"] == "c.png"}
        self.assertIn(warm_ids, [set(group["asset_ids"]) for group in result["groups"]])
        self.assertIn(blue_ids, [set(group["asset_ids"]) for group in result["groups"]])
        for group in result["groups"]:
            self.assertIn(group["cover_asset_id"], group["asset_ids"])
            self.assertEqual(group["review"]["label"], "本地规则草案")
            self.assertEqual(group["review"]["origin"], "local")
            self.assertFalse(group["review"]["photos_sent"])
            self.assertIn("不是", group["reason"])
        self.assertTrue(any("暖调" in group["title"] or "蓝调" in group["title"] for group in result["groups"]))
        self.assertEqual(result["versions"][-1]["source"], "group-local")
        self.assertIn("groups", result["versions"][-2])

    def test_filename_series_stays_together_when_colors_match(self):
        blob = solid_png(80, 140, 180)
        self.upload(blob, name="aegean-cover.png", features={})
        self.upload(blob + b"\x00", name="aegean-vessel.png", features={})
        self.upload(blob + b"\x00\x00", name="nostos-cover.png", features={})
        groups = app.build_groups(self.latest())
        names = {asset["name"]: asset["id"] for asset in self.latest()["assets"]}
        aegean = next(group for group in groups if names["aegean-cover.png"] in group["asset_ids"])
        self.assertIn(names["aegean-vessel.png"], aegean["asset_ids"])
        self.assertNotIn(names["nostos-cover.png"], aegean["asset_ids"])
        self.assertEqual(aegean["signal"], "filename")
        titles = [group["title"] for group in groups]
        self.assertIn("潮汐 · 蓝调", titles)
        self.assertIn("潮汐 · 蓝调 2", titles)
        self.assertNotIn("潮汐 · 蓝调 3", titles)

    def test_design_output_series_are_separate_groups(self):
        root = Path(__file__).resolve().parents[1] / "design_output"
        names = [
            "starburst-series/jeju-diffraction-01.png",
            "starburst-series/jeju-diffraction-cover.png",
            "odyssey-nostos/nostos-cover-1080x1350.png",
            "odyssey-nostos/nostos-vessel-1080x1350.png",
            "odyssey-aegean-afterlight/aegean-cover-1080x1350.png",
            "odyssey-aegean-afterlight/aegean-vessel-clean-2048x1365.png",
        ]
        for name in names:
            self.upload((root / name).read_bytes(), name=Path(name).name, features={})
        result = self.latest()
        groups = app.build_groups(result)
        def group_for(*filenames):
            ids = {asset["id"] for asset in result["assets"] if asset["name"] in filenames}
            return next(group for group in groups if ids <= set(group["asset_ids"]))
        diffraction = group_for("jeju-diffraction-01.png", "jeju-diffraction-cover.png")
        nostos = group_for("nostos-cover-1080x1350.png", "nostos-vessel-1080x1350.png")
        aegean = group_for("aegean-cover-1080x1350.png", "aegean-vessel-clean-2048x1365.png")
        self.assertEqual(len({diffraction["id"], nostos["id"], aegean["id"]}), 3)
        color = next(item for item in aegean["review"]["items"] if item["aspect"] == "色彩")
        self.assertEqual(color["level"], "warn")
        self.assertEqual(aegean["review"]["style_name"], "未指定风格")

    def test_manual_title_cover_and_apply_leave_the_decision_with_the_user(self):
        warm = {"width": 8, "height": 8, "brightness": 55, "contrast": 15, "palette": ["#c06030"]}
        warm_b = {"width": 8, "height": 8, "brightness": 58, "contrast": 35, "palette": ["#c86838"]}
        blue = {"width": 8, "height": 8, "brightness": 40, "contrast": 12, "palette": ["#204080"]}
        self.upload(solid_png(1, 1, 1), name="a.png", features=warm)
        self.upload(solid_png(2, 2, 2), name="b.png", features=warm_b)
        self.upload(solid_png(3, 3, 3), name="c.png", features=blue)
        job, project = app.create_job(self.project["id"], "groups", "local")
        app.run_groups(job["id"], project, "local")
        result = self.latest()
        self.assertEqual(result["story"]["title"], "")
        group = next(item for item in result["groups"] if len(item["asset_ids"]) == 2)
        other = next(item for item in result["groups"] if item["id"] != group["id"])
        replacement = next(asset_id for asset_id in group["asset_ids"] if asset_id != group["cover_asset_id"])
        revised = app.update_project(self.project["id"], {"groups": [{"id": group["id"], "title": "老板定的标题", "cover_asset_id": replacement}]})
        saved = next(item for item in revised["groups"] if item["id"] == group["id"])
        self.assertEqual(saved["title"], "老板定的标题")
        self.assertEqual(saved["title_origin"], "manual")
        self.assertEqual(saved["cover_asset_id"], replacement)
        self.assertEqual(saved["cover_origin"], "manual")
        self.assertEqual(revised["story"]["title"], "")
        with self.assertRaises(app.Problem):
            app.update_project(self.project["id"], {"groups": [{"id": group["id"], "cover_asset_id": "missing"}]})
        applied = app.apply_group(self.project["id"], {"group_id": group["id"], "use_title": True, "use_cover": True, "use_set": True})
        selected = [asset["id"] for asset in applied["assets"] if asset["selected"]]
        self.assertEqual(selected, [replacement] + [asset_id for asset_id in group["asset_ids"] if asset_id != replacement])
        self.assertEqual(applied["story"]["title"], "老板定的标题")
        self.assertTrue(all(not asset["selected"] for asset in applied["assets"] if asset["id"] in set(other["asset_ids"])))

    def test_ai_review_is_labeled_and_does_not_send_photos(self):
        self.upload(solid_png(1, 2, 3), name="a.png", features={"width": 8, "height": 8, "brightness": 30, "contrast": 10, "palette": ["#102030"]})
        self.upload(solid_png(4, 5, 6), name="b.png", features={"width": 8, "height": 8, "brightness": 70, "contrast": 20, "palette": ["#e0c0a0"]})
        app.save_settings({"ai_base_url": "http://127.0.0.1:9999/v1", "ai_model": "test-model", "ai_vision": True})
        recipe = app.make_recipe({"name": "潮汐蓝", "description": "柔和的蓝", "positive_prompt": "muted blue"})
        app.update_project(self.project["id"], {"recipe_id": recipe["id"]})
        job, project = app.create_job(self.project["id"], "groups", "ai")
        groups = app.build_groups(project)

        def model(config, role, payload, images=None):
            self.assertEqual(role, "风格核对")
            self.assertIsNone(images)
            self.assertFalse(payload["photos_sent"])
            self.assertEqual(payload["style"]["name"], "潮汐蓝")
            encoded = json.dumps(payload)
            self.assertNotIn("base64", encoded)
            self.assertNotIn("image_url", encoded)
            return {"groups": [{"asset_ids": group["asset_ids"], "title": "夜航 %s" % index, "cover_id": group["cover_asset_id"],
                                "summary": "只根据采样指标。", "items": [{"aspect": "色彩", "level": "note", "detail": "未见照片"}]} for index, group in enumerate(groups, 1)]}

        with patch.object(app, "call_model", side_effect=model) as mock:
            app.run_groups(job["id"], project, "ai")
        result = self.latest()
        self.assertEqual(mock.call_count, 1)
        self.assertEqual(app.get("jobs", job["id"])["status"], "completed")
        self.assertEqual(result["groups"][0]["review"]["label"], "AI 风格核对")
        self.assertEqual(result["groups"][0]["review"]["provider"]["model"], "test-model")
        self.assertNotIn("ai_api_key", json.dumps(result["groups"]))
        self.assertIn("未发送照片", result["groups"][0]["review"]["limit"])
        self.assertTrue(result["groups"][0]["title"].startswith("夜航"))
        self.assertEqual([asset["selected"] for asset in result["assets"]], [True, True])

    def test_invalid_ai_review_and_late_import_do_not_write_groups(self):
        self.upload(solid_png(9, 9, 9), name="a.png", features={"width": 4, "height": 4, "brightness": 40, "contrast": 10, "palette": ["#888888"]})
        app.save_settings({"ai_base_url": "http://127.0.0.1:9999/v1", "ai_model": "test-model"})
        job, project = app.create_job(self.project["id"], "groups", "ai")
        with patch.object(app, "call_model", return_value={"groups": []}):
            app.run_groups(job["id"], project, "ai")
        self.assertEqual(app.get("jobs", job["id"])["status"], "failed")
        self.assertFalse(self.latest().get("groups"))
        job, snapshot = app.create_job(self.project["id"], "groups", "local")
        self.upload(solid_png(8, 8, 8), name="late.png", features={"width": 4, "height": 4, "brightness": 41, "contrast": 10, "palette": ["#808080"]})
        app.run_groups(job["id"], snapshot, "local")
        self.assertEqual(app.get("jobs", job["id"])["status"], "failed")
        self.assertEqual(len(self.latest()["assets"]), 2)
        self.assertFalse(self.latest().get("groups"))
        handler = object.__new__(app.Handler)
        with self.assertRaises(app.Problem):
            handler.api("POST", ["projects", self.project["id"], "groups"], {"mode": "sideways"})

    def latest(self):
        return app.get("projects", self.project["id"])


if __name__ == "__main__":
    unittest.main()
