#!/usr/bin/env python3
"""Repair published SideTree patches for the macOS patch ordering."""

import sys
from pathlib import Path


def replace_exactly_once(
    contents: str, old: str, new: str, description: str
) -> str:
    """Apply one known repair, while allowing an already-repaired input."""
    old_count = contents.count(old)
    new_count = contents.count(new)

    if old_count == 1 and new_count == 0:
        return contents.replace(old, new, 1)
    if old_count == 0 and new_count == 1:
        return contents

    raise RuntimeError(
        f"cannot repair {description}: "
        f"found old context {old_count} times and repaired context {new_count} times"
    )


def repair_native_tab_polish(contents: str) -> str:
    repairs = (
        (
            "@@ -1048,12 +1089,23 @@ void VerticalTabStripRegionView::SetColl",
            "@@ -1048,13 +1089,24 @@ void VerticalTabStripRegionView::SetColl",
            "RequestCollapse hunk length",
        ),
        (
            "   target_collapse_state_.collapsed = collapse;\n"
            "   const auto motion =",
            "   target_collapse_state_.collapsed = collapse;\n"
            "   CHECK(tab_strip_view_);\n"
            "   const auto motion =",
            "RequestCollapse CHECK context",
        ),
        (
            " void VerticalTabStripRegionView::OnExpandOnHoverEnabledChanged(bool enabled) {\n"
            "+  if (IsSideTreeShellActive()) {\n"
            "+    resize_area_->SetVisible(true);\n"
            "+    ForceSideTreeExpandedState();\n"
            "+    return;\n"
            "+  }\n"
            "+\n"
            "   resize_area_->SetVisible(!state_controller_->IsCollapsed() || !enabled ||\n"
            "                            resize_area_->is_resizing());\n"
            "   UpdateExpandOnHoverState();",
            " void VerticalTabStripRegionView::OnExpandOnHoverEnabledChanged(\n"
            "     bool /*enabled*/) {\n"
            "+  if (IsSideTreeShellActive()) {\n"
            "+    resize_area_->SetVisible(true);\n"
            "+    ForceSideTreeExpandedState();\n"
            "+    return;\n"
            "+  }\n"
            "+\n"
            "   UpdateResizeAreaVisibility();\n"
            "   UpdateExpandOnHoverState();",
            "OnExpandOnHoverEnabledChanged context",
        ),
    )

    for old, new, description in repairs:
        contents = replace_exactly_once(contents, old, new, description)
    return contents


def repair_native_tab_tree(contents: str) -> str:
    repairs = (
        (
            "   resize_area_->SetVisible(!collapsed ||",
            "   UpdateResizeAreaVisibility();",
            "OnCollapseStateChanged resize helper context",
        ),
        (
            "@@ -1267,9 +1276,10 @@",
            "@@ -1267,8 +1276,9 @@",
            "OnCollapseStateChanged compact-mode hunk length",
        ),
        (
            "@@ -1267,8 +1276,9 @@\n"
            "                            resize_area_->is_resizing());\n"
            " \n"
            "   if (sidetree_shell_view_) {",
            "@@ -1267,8 +1276,9 @@\n"
            " \n"
            "   if (sidetree_shell_view_) {",
            "OnCollapseStateChanged compact-mode context",
        ),
        (
            "@@ -1336,7 +1356,7 @@\n"
            " \n"
            " void VerticalTabStripRegionView::OnExpandOnHoverEnabledChanged(bool enabled) {",
            "@@ -1336,8 +1356,8 @@\n"
            " \n"
            " void VerticalTabStripRegionView::OnExpandOnHoverEnabledChanged(\n"
            "     bool /*enabled*/) {",
            "OnExpandOnHoverEnabledChanged compact-mode context",
        ),
        (
            "@@ -240,6 +241,7 @@\n"
            " \n"
            "   void OnCollapseStateChanged(\n"
            "       tabs::VerticalTabStripCollapseState collapse_state);\n"
            "+  void ForceSideTreeExpandedState();\n"
            " \n"
            "   void UpdateColors();",
            "@@ -240,7 +241,8 @@\n"
            " \n"
            "   void OnCollapseStateChanged(\n"
            "       tabs::VerticalTabStripCollapseState collapse_state);\n"
            "+  void ForceSideTreeExpandedState();\n"
            "   void UpdateResizeAreaVisibility();\n"
            " \n"
            "   void UpdateColors();",
            "ForceSideTreeExpandedState declaration context",
        ),
        (
            "@@ -46,6 +46,7 @@\n"
            " #include \"chrome/browser/ui/toasts/api/toast_id.h\"\n"
            " #include \"chrome/browser/ui/toasts/toast_controller.h\"\n"
            " #include \"chrome/browser/ui/views/frame/browser_view.h\"\n"
            "+#include \"chrome/browser/ui/views/tabs/sidetree/sidetree_container_tab_state.h\"\n"
            " #include \"chrome/browser/ui/web_applications/app_browser_controller.h\"\n"
            " #include \"chrome/browser/ui/web_applications/web_app_tabbed_utils.h\"\n"
            " #include \"chrome/browser/web_applications/web_app_helpers.h\"",
            "@@ -46,7 +46,8 @@\n"
            " #include \"chrome/browser/ui/toasts/api/toast_id.h\"\n"
            " #include \"chrome/browser/ui/toasts/toast_controller.h\"\n"
            " #include \"chrome/browser/ui/views/frame/browser_view.h\"\n"
            "+#include \"chrome/browser/ui/views/tabs/sidetree/sidetree_container_tab_state.h\"\n"
            " #include \"chrome/browser/ui/web_applications/app_browser_controller.h\"\n"
            " #include \"chrome/browser/ui/web_applications/"
            "web_app_launch_navigation_handle_user_data.h\"\n"
            " #include \"chrome/browser/ui/web_applications/web_app_tabbed_utils.h\"\n"
            " #include \"chrome/browser/web_applications/web_app_helpers.h\"",
            "browser_navigator include context",
        ),
    )

    for old, new, description in repairs:
        contents = replace_exactly_once(contents, old, new, description)
    return contents


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} <patches-dir>", file=sys.stderr)
        return 64

    patches_dir = Path(sys.argv[1])
    repairs = (
        ("sidetree/ui/native-tab-polish.patch", repair_native_tab_polish),
        ("sidetree/ui/native-tab-tree.patch", repair_native_tab_tree),
    )
    for relative_path, repair in repairs:
        patch_path = patches_dir / relative_path
        original = patch_path.read_text(encoding="utf-8")
        repaired = repair(original)
        if repaired != original:
            patch_path.write_text(repaired, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
