#!/usr/bin/env python3
"""Regression tests for the SideTree patch repair helper."""

import importlib.util
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("repair_sidetree_patches.py")
SPEC = importlib.util.spec_from_file_location("repair_sidetree_patches", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
REPAIR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPAIR)


VERTICAL_SHELL_PATCH = """\
--- a/chrome/browser/ui/views/frame/vertical_tab_strip_region_view.cc
+++ b/chrome/browser/ui/views/frame/vertical_tab_strip_region_view.cc
@@ -70,14 +70,17 @@
 #include "ui/views/background.h"
 #include "ui/views/controls/button/label_button.h"
 #include "ui/views/controls/focus_ring.h"
+#include "ui/views/controls/label.h"
 #include "ui/views/controls/resize_area.h"
 #include "ui/views/controls/scroll_view.h"
 #include "ui/views/controls/separator.h"
 #include "ui/views/focus/focus_manager.h"
 #include "ui/views/interaction/element_tracker_views.h"
+#include "ui/views/layout/box_layout.h"
 #include "ui/views/layout/flex_layout.h"
 #include "ui/views/layout/flex_layout_types.h"
 #include "ui/views/layout/layout_types.h"
+#include "ui/views/style/typography.h"
 #include "ui/views/view.h"
 #include "ui/views/view_class_properties.h"
 #include "ui/views/view_utils.h"
@@ -98,6 +101,36 @@ constexpr ShadowFrameView::ShadowAlpha k
      .light_ambient = 0.0,
      .dark_key = 0.6,
      .dark_ambient = 0.0});
+
+std::unique_ptr<views::View> CreateSideTreeNativeShellView() {
+  auto shell = std::make_unique<views::View>();
+  auto* const layout =
+      shell->SetLayoutManager(std::make_unique<views::BoxLayout>(
+          views::BoxLayout::Orientation::kVertical,
+          gfx::Insets::TLBR(12, 10, 8, 10), 6));
+  layout->set_cross_axis_alignment(
+      views::BoxLayout::CrossAxisAlignment::kStretch);
+  shell->SetFocusBehavior(views::View::FocusBehavior::ALWAYS);
+  shell->GetViewAccessibility().SetRole(ax::mojom::Role::kGroup);
+  shell->GetViewAccessibility().SetName(u"SideTree");
+
+  auto title = std::make_unique<views::Label>(u"SideTree");
+  title->SetHorizontalAlignment(gfx::ALIGN_LEFT);
+  title->SetTextStyle(views::style::STYLE_BODY_3_MEDIUM);
+  shell->AddChildView(std::move(title));
+
+  auto stage = std::make_unique<views::Label>(u"C1 native shell");
+  stage->SetHorizontalAlignment(gfx::ALIGN_LEFT);
+  stage->SetTextStyle(views::style::STYLE_BODY_4);
+  shell->AddChildView(std::move(stage));
+
+  auto backing = std::make_unique<views::Label>(u"Tab model stays live");
+  backing->SetHorizontalAlignment(gfx::ALIGN_LEFT);
+  backing->SetTextStyle(views::style::STYLE_BODY_4);
+  shell->AddChildView(std::move(backing));
+
+  return shell;
+}
 }  // namespace
<CONTEXT-BLANK>
 DEFINE_CLASS_CUSTOM_ELEMENT_EVENT_TYPE(VerticalTabStripRegionView,
@@ -211,6 +244,14 @@ VerticalTabStripRegionView::VerticalTabS
                                    views::MinimumFlexSizeRule::kPreferred,
                                    views::MaximumFlexSizeRule::kPreferred));
<CONTEXT-BLANK>
+  sidetree_shell_view_ = AddChildView(CreateSideTreeNativeShellView());
+  sidetree_shell_view_->SetProperty(
+      views::kFlexBehaviorKey,
+      views::FlexSpecification(views::MinimumFlexSizeRule::kScaleToMinimum,
+                               views::MaximumFlexSizeRule::kPreferred));
+  sidetree_shell_view_->SetProperty(
+      views::kMarginsKey, gfx::Insets::TLBR(0, 0, kBottomContainerGap, 0));
+
   bottom_button_container_ =
       AddChildView(std::make_unique<VerticalTabStripBottomContainer>(
           state_controller_, root_action_item, browser_view->browser(),
@@ -519,6 +560,10 @@ void VerticalTabStripRegionView::Layout(
 }
<CONTEXT-BLANK>
 views::View* VerticalTabStripRegionView::GetDefaultFocusableChild() {
+  if (sidetree_shell_view_) {
+    return sidetree_shell_view_;
+  }
+
   const int active_index = tab_strip_model_->active_index();
   if (active_index != TabStripModel::kNoTab) {
     return GetTabAnchorViewAt(active_index);
@@ -1062,6 +1107,8 @@ views::View* VerticalTabStripRegionView:
<CONTEXT-BLANK>
   tab_strip_view_ =
       static_cast<VerticalTabStripView*>(AddChildView(std::move(view)));
+  tab_strip_view_->SetVisible(false);
+  tab_strip_view_->SetProperty(views::kViewIgnoredByLayoutKey, true);
   tab_strip_view_->SetProperty(
       views::kFlexBehaviorKey,
       views::FlexSpecification(views::MinimumFlexSizeRule::kScaleToMinimum,
@@ -1141,6 +1188,12 @@ void VerticalTabStripRegionView::OnColla
                            !state_controller_->IsExpandOnHoverEnabled() ||
                            resize_area_->is_resizing());
<CONTEXT-BLANK>
+  if (sidetree_shell_view_) {
+    sidetree_shell_view_->SetProperty(
+        views::kMarginsKey,
+        gfx::Insets::TLBR(0, padding, kBottomContainerGap, padding));
+  }
+
   resize_area_width_ = collapsed ? kCollapsedResizeAreaWidth : kResizeAreaWidth;
<CONTEXT-BLANK>
   if (tab_strip_view_) {
--- a/chrome/browser/ui/views/frame/vertical_tab_strip_region_view.h
+++ b/chrome/browser/ui/views/frame/vertical_tab_strip_region_view.h
@@ -303,6 +303,7 @@ class VerticalTabStripRegionView final
   bool zen_mode_floating_style_ = false;
<CONTEXT-BLANK>
   raw_ptr<VerticalTabStripView> tab_strip_view_ = nullptr;
+  raw_ptr<views::View> sidetree_shell_view_ = nullptr;
   raw_ptr<VerticalTabStripBottomContainer> bottom_button_container_ = nullptr;
   raw_ptr<views::View> gemini_button_ = nullptr;
   raw_ptr<views::ResizeArea> resize_area_ = nullptr;
""".replace("\n<CONTEXT-BLANK>\n", "\n \n")


class RepairVerticalShellPatchTest(unittest.TestCase):
    def test_retargets_focus_hunk_to_get_active_tab_implementation(self) -> None:
        repaired = REPAIR.repair_vertical_strip_native_shell(VERTICAL_SHELL_PATCH)

        self.assertIn("@@ -375,6 +416,10 @@", repaired)
        self.assertIn(
            " views::View* VerticalTabStripRegionView::GetDefaultFocusableChild() {\n"
            "+  if (sidetree_shell_view_) {\n"
            "+    return sidetree_shell_view_;\n"
            "+  }\n"
            "+\n"
            "   tabs::TabInterface* active_tab = "
            "tab_strip_model()->GetActiveTab();",
            repaired,
        )
        self.assertNotIn("const int active_index", repaired)
        self.assertIn(' #include "ui/views/view_utils.h"\n', repaired)
        self.assertIn("   if (tab_strip_view()) {\n", repaired)
        self.assertNotIn("   if (tab_strip_view_) {\n", repaired)
        self.assertEqual(
            repaired,
            REPAIR.repair_vertical_strip_native_shell(repaired),
        )


class RepairNativeTabBridgePatchTest(unittest.TestCase):
    def test_emits_current_include_context(self) -> None:
        captured_hunks: dict[str, str] = {}
        captured_sequences: dict[str, str] = {}
        captured_replacements: dict[str, tuple[str, str]] = {}

        def capture_hunk(
            contents: str,
            _old_header: str,
            new_hunk: str,
            description: str,
        ) -> str:
            captured_hunks[description] = new_hunk
            return contents

        def capture_sequence(
            contents: str,
            _old_headers: tuple[str, ...],
            new_hunk: str,
            description: str,
        ) -> str:
            captured_sequences[description] = new_hunk
            return contents

        def capture_replacement(
            contents: str,
            old: str,
            new: str,
            description: str,
        ) -> str:
            captured_replacements[description] = (old, new)
            return contents

        with (
            mock.patch.object(REPAIR, "has_complete_repair", return_value=False),
            mock.patch.object(
                REPAIR,
                "replace_hunk_sequence_exactly_once",
                side_effect=capture_sequence,
            ),
            mock.patch.object(
                REPAIR,
                "replace_hunk_exactly_once",
                side_effect=capture_hunk,
            ),
            mock.patch.object(
                REPAIR,
                "replace_exactly_once",
                side_effect=capture_replacement,
            ),
        ):
            REPAIR.repair_native_tab_bridge("")

        bridge_include_hunk = captured_hunks["native tab bridge include context"]
        self.assertIn(
            ' #include "chrome/browser/ui/views/tabs/vertical/'
            'vertical_tab_strip_focus_swipe_controller.h"\n',
            bridge_include_hunk,
        )

        obsolete_shell_include_hunk = captured_hunks[
            "native tab bridge obsolete shell includes"
        ]
        self.assertIn(
            ' #include "ui/views/view_utils.h"\n',
            obsolete_shell_include_hunk,
        )

        bridge_source_hunk = captured_hunks[
            "native tab bridge source list context"
        ]
        self.assertIn("@@ -2607,6 +2607,10 @@", bridge_source_hunk)
        self.assertIn(
            '       "views/frame/vertical_tab_strip_region_view.h",\n'
            '+      "views/tabs/sidetree/sidetree_tab_row_view.cc",\n'
            '+      "views/tabs/sidetree/sidetree_tab_row_view.h",\n'
            '+      "views/tabs/sidetree/sidetree_tab_strip_view.cc",\n'
            '+      "views/tabs/sidetree/sidetree_tab_strip_view.h",\n'
            '       "views/helium/frame_corner_radius.cc",\n',
            bridge_source_hunk,
        )

        bridge_methods_hunk = captured_sequences[
            "native tab bridge base-class method relocation"
        ]
        self.assertIn("@@ -711,15 +691,44 @@", bridge_methods_hunk)
        self.assertIn(
            "+views::View* VerticalTabStripRegionView::GetTabAnchorView(\n"
            "+    const tabs::TabHandle& tab) {\n",
            bridge_methods_hunk,
        )
        self.assertIn(
            "+  return BaseTabStripRegionView::GetTabAnchorView(tab);\n",
            bridge_methods_hunk,
        )
        self.assertNotIn(
            "BaseTabStripRegionView::GetTabAnchorViewAt", bridge_methods_hunk
        )

        _, observer_definition = captured_replacements[
            "native tab bridge observer definition"
        ]
        self.assertIn(
            "+void SideTreeTabStripView::OnTabChangedAt(\n"
            "+    tabs::TabInterface* tab,\n"
            "+    TabChangeType change_type) {\n",
            observer_definition,
        )

        _, observer_declaration = captured_replacements[
            "native tab bridge observer declaration"
        ]
        self.assertIn(
            "+  void OnTabChangedAt(\n"
            "+      tabs::TabInterface* tab,\n"
            "+      TabChangeType change_type) override;",
            observer_declaration,
        )


class RepairNativeTabPolishPatchTest(unittest.TestCase):
    def test_emits_current_sizing_and_collapse_context(self) -> None:
        captured_hunks: dict[str, str] = {}

        def capture_hunk(
            contents: str,
            _old_header: str,
            new_hunk: str,
            description: str,
        ) -> str:
            captured_hunks[description] = new_hunk
            return contents

        source = (
            "@@ -1048,12 +1089,23 @@ "
            "void VerticalTabStripRegionView::SetColl"
        )
        with (
            mock.patch.object(REPAIR, "has_complete_repair", return_value=False),
            mock.patch.object(
                REPAIR,
                "replace_hunk_exactly_once",
                side_effect=capture_hunk,
            ),
            mock.patch.object(
                REPAIR,
                "replace_exactly_once",
                side_effect=lambda contents, *_args: contents,
            ),
        ):
            REPAIR.repair_native_tab_polish(source)

        sizing_hunk = captured_hunks["native tab polish sizing context"]
        self.assertIn("@@ -412,5 +421,6 @@", sizing_hunk)
        self.assertIn("@@ -419,5 +429,11 @@", sizing_hunk)

        collapse_hunk = captured_hunks[
            "IsCollapsing and RequestCollapse base-class relocation"
        ]
        self.assertIn("@@ -715,2 +760,9 @@", collapse_hunk)
        self.assertIn(
            " void VerticalTabStripRegionView::RequestCollapse(bool collapse) {\n"
            "+  if (IsSideTreeShellActive()) {\n",
            collapse_hunk,
        )
        self.assertIn(
            "+\n"
            "   target_collapse_state_.collapsed = collapse;",
            collapse_hunk,
        )


class RepairNativeTabTreePatchTest(unittest.TestCase):
    def test_emits_current_ui_source_list_context(self) -> None:
        captured_hunks: dict[str, str] = {}
        captured_replacements: dict[str, tuple[str, str]] = {}

        def capture_hunk(
            contents: str,
            _old_header: str,
            new_hunk: str,
            description: str,
        ) -> str:
            captured_hunks[description] = new_hunk
            return contents

        def capture_replacement(
            contents: str,
            old: str,
            new: str,
            description: str,
        ) -> str:
            captured_replacements[description] = (old, new)
            return contents

        with (
            mock.patch.object(REPAIR, "has_complete_repair", return_value=False),
            mock.patch.object(
                REPAIR,
                "replace_hunk_exactly_once",
                side_effect=capture_hunk,
            ),
            mock.patch.object(
                REPAIR,
                "replace_exactly_once",
                side_effect=capture_replacement,
            ),
        ):
            REPAIR.repair_native_tab_tree("->GetProfile()" * 69)

        tree_source_hunk = captured_hunks["native tab tree source list context"]
        self.assertIn("@@ -2607,10 +2608,26 @@", tree_source_hunk)
        self.assertIn(
            '       "views/frame/vertical_tab_strip_region_view.h",\n'
            '+      "views/tabs/sidetree/sidetree_container_tab_state.cc",\n',
            tree_source_hunk,
        )
        self.assertIn(
            '+      "views/tabs/sidetree/sidetree_workspace_menu_model.h",\n'
            '       "views/helium/frame_corner_radius.cc",\n',
            tree_source_hunk,
        )

        _, test_target_header = captured_replacements[
            "native tab tree test target header"
        ]
        self.assertEqual("@@ -3953,6 +3970,84 @@", test_target_header)

        _, test_target_owner = captured_replacements[
            "native tab tree test target owner context"
        ]
        self.assertIn(" if (toolkit_views) {\n", test_target_owner)
        self.assertIn('   source_set("idle_dialog") {\n', test_target_owner)

        browser_view_hunk = captured_hunks["BrowserView SideTree state context"]
        self.assertIn("@@ -1569,6 +1569,11 @@", browser_view_hunk)
        self.assertIn(
            " bool BrowserView::IsVerticalTabStripRightAligned() const {\n",
            browser_view_hunk,
        )
        self.assertNotIn("browser_->GetType()", browser_view_hunk)
        self.assertNotIn("ShouldDrawTabStrip()", browser_view_hunk)

        _, navigator_hunk = captured_replacements[
            "browser_navigator include context"
        ]
        self.assertIn("@@ -49,11 +49,12 @@", navigator_hunk)
        self.assertIn(
            ' #include "chrome/browser/ui/window_feature_controller/'
            'window_feature_controller.h"\n',
            navigator_hunk,
        )
        self.assertIn(
            ' #include "chrome/browser/web_applications/web_app_tab_helper.h"',
            navigator_hunk,
        )

        _, persistence_browser = captured_replacements[
            "session persistence browser interface"
        ]
        self.assertEqual(
            "+  BrowserWindowInterface* browser = browser_view->browser();",
            persistence_browser,
        )

        _, new_tab_browser = captured_replacements[
            "new-tab browser interface"
        ]
        self.assertEqual(
            "+  BrowserWindowInterface* browser = browser_view_->browser();",
            new_tab_browser,
        )

        _, session_id_accessor = captured_replacements[
            "browser window session ID accessor"
        ]
        self.assertEqual(
            "+  const SessionID window_id = browser->GetSessionID();",
            session_id_accessor,
        )

        _, observer_hunk_header = captured_replacements[
            "native tab tree observer hunk size"
        ]
        self.assertEqual("@@ -238,16 +3166,29 @@", observer_hunk_header)

        _, observer_definition = captured_replacements[
            "native tab tree observer definition"
        ]
        self.assertIn(
            " void SideTreeTabStripView::OnTabChangedAt(\n"
            "     tabs::TabInterface* tab,\n"
            "     TabChangeType change_type) {\n"
            "+  const int index = tab_strip_model_->GetIndexOfTab(tab);\n",
            observer_definition,
        )


class RemovePatchFileTest(unittest.TestCase):
    def test_removes_obsolete_patch_section_idempotently(self) -> None:
        obsolete_index = "Index: src/chrome/test/BUILD.gn\n"
        next_index = "Index: src/chrome/browser/ui/next.cc\n"
        contents = (
            "prefix\n"
            + obsolete_index
            + "================================\n"
            + "--- src.orig/chrome/test/BUILD.gn\n"
            + "+++ src/chrome/test/BUILD.gn\n"
            + "@@ -1 +1,2 @@\n"
            + " context\n"
            + "+addition\n"
            + next_index
            + "suffix\n"
        )

        repaired = REPAIR.remove_patch_file_exactly_once(
            contents,
            obsolete_index,
            next_index,
            "obsolete test registration",
        )

        self.assertNotIn(obsolete_index, repaired)
        self.assertIn(next_index, repaired)
        self.assertEqual(
            repaired,
            REPAIR.remove_patch_file_exactly_once(
                repaired,
                obsolete_index,
                next_index,
                "obsolete test registration",
            ),
        )


if __name__ == "__main__":
    unittest.main()
