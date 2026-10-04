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


def replace_hunk_exactly_once(
    contents: str, old_header: str, new_hunk: str, description: str
) -> str:
    """Replace one unified-diff hunk, while allowing a repaired input."""
    new_hunk = new_hunk.replace("\n<CONTEXT-BLANK>\n", "\n \n")
    old_count = contents.count(old_header)
    new_header = new_hunk.partition("\n")[0]
    new_count = contents.count(new_header)

    if old_count == 1 and new_count == 0:
        start = contents.index(old_header)
        end_candidates = [
            position
            for marker in ("\n@@ ", "\n--- ")
            if (position := contents.find(marker, start + len(old_header))) >= 0
        ]
        end = min(end_candidates, default=len(contents))
        return contents[:start] + new_hunk.rstrip("\n") + contents[end:]
    if old_count == 0 and new_count == 1:
        return contents

    raise RuntimeError(
        f"cannot repair {description}: "
        f"found old hunk {old_count} times and repaired hunk {new_count} times"
    )


def replace_hunk_sequence_exactly_once(
    contents: str, old_headers: tuple[str, ...], new_hunk: str, description: str
) -> str:
    """Replace adjacent unified-diff hunks with one current-context hunk."""
    new_hunk = new_hunk.replace("\n<CONTEXT-BLANK>\n", "\n \n")
    old_counts = tuple(contents.count(header) for header in old_headers)
    new_header = new_hunk.partition("\n")[0]
    new_count = contents.count(new_header)

    if all(count == 1 for count in old_counts) and new_count == 0:
        starts = tuple(contents.index(header) for header in old_headers)
        if starts != tuple(sorted(starts)):
            raise RuntimeError(
                f"cannot repair {description}: source hunks are out of order"
            )

        start = starts[0]
        last_start = starts[-1]
        end_candidates = [
            position
            for marker in ("\n@@ ", "\n--- ")
            if (
                position := contents.find(
                    marker, last_start + len(old_headers[-1])
                )
            )
            >= 0
        ]
        end = min(end_candidates, default=len(contents))
        return contents[:start] + new_hunk.rstrip("\n") + contents[end:]
    if all(count == 0 for count in old_counts) and new_count == 1:
        return contents

    raise RuntimeError(
        f"cannot repair {description}: "
        f"found source hunks {old_counts} and repaired hunk {new_count} times"
    )


def remove_patch_file_exactly_once(
    contents: str, file_index: str, next_file_index: str, description: str
) -> str:
    """Remove one obsolete file section while allowing an already-repaired input."""
    file_count = contents.count(file_index)
    if file_count == 0:
        return contents
    if file_count != 1:
        raise RuntimeError(
            f"cannot repair {description}: found file section {file_count} times"
        )

    start = contents.index(file_index)
    end = contents.find(next_file_index, start + len(file_index))
    if end < 0:
        raise RuntimeError(
            f"cannot repair {description}: next file section is missing"
        )
    return contents[:start] + contents[end:]


def has_complete_repair(
    contents: str, signatures: tuple[str, ...], description: str
) -> bool:
    """Recognize a fully repaired patch and reject a partial repair."""
    counts = tuple(contents.count(signature) for signature in signatures)
    if all(count == 1 for count in counts):
        return True
    if all(count == 0 for count in counts):
        return False

    raise RuntimeError(
        f"cannot repair {description}: found repaired signatures {counts}"
    )


def repair_native_tab_polish(contents: str) -> str:
    contents = replace_hunk_exactly_once(
        contents,
        "@@ -554,15 +563,22 @@ views::View* VerticalTabStripRegionView:",
        """@@ -412,5 +421,6 @@ gfx::Size VerticalTabStripRegionView::GetMinimumSize() const {
   auto min_size = BaseTabStripRegionView::GetMinimumSize();
-  min_size.set_width((state_controller_->IsCollapsed() || IsAnimatingSize())
-                         ? kCollapsedWidth
-                         : kUncollapsedMinWidth);
+  const bool collapsed =
+      !IsSideTreeShellActive() &&
+      (state_controller_->IsCollapsed() || IsAnimatingSize());
+  min_size.set_width(collapsed ? kCollapsedWidth : kUncollapsedMinWidth);
   return min_size;
@@ -419,5 +429,11 @@ gfx::Size VerticalTabStripRegionView::CalculatePreferredSize(
 gfx::Size VerticalTabStripRegionView::CalculatePreferredSize(
     const views::SizeBounds& available_size) const {
   auto size = BaseTabStripRegionView::CalculatePreferredSize(available_size);
+  if (IsSideTreeShellActive()) {
+    size.set_width(std::clamp(target_collapse_state_.uncollapsed_width,
+                              kUncollapsedMinWidth, kUncollapsedMaxWidth));
+    return size;
+  }
+
   const auto* controller =
       BrowserAnimationController::From(browser_view()->browser());""",
        "native tab polish sizing context",
    )

    legacy_request_collapse_header = "@@ -714,6 +759,13 @@"
    current_request_collapse_hunk = """@@ -715,2 +760,9 @@
 void VerticalTabStripRegionView::RequestCollapse(bool collapse) {
+  if (IsSideTreeShellActive()) {
+    ForceSideTreeExpandedState();
+    OnCollapseStateChanged(tabs::VerticalTabStripCollapseState::kExpanded);
+    InvalidateLayout();
+    return;
+  }
+
   target_collapse_state_.collapsed = collapse;"""
    if legacy_request_collapse_header in contents:
        contents = replace_hunk_exactly_once(
            contents,
            legacy_request_collapse_header,
            current_request_collapse_hunk,
            "RequestCollapse current body context",
        )

    if has_complete_repair(
        contents,
        (
            "@@ -599,6 +615,31 @@",
            "@@ -701,6 +742,10 @@",
            "@@ -715,2 +760,9 @@",
            "@@ -758,6 +810,27 @@",
        ),
        "native tab polish patch",
    ):
        return contents

    repairs = (
        (
            "   auto min_size = TabStripRegionView::GetMinimumSize();",
            "   auto min_size = BaseTabStripRegionView::GetMinimumSize();",
            "GetMinimumSize base-class context",
        ),
        (
            "   auto size = TabStripRegionView::CalculatePreferredSize("
            "available_size);",
            "   auto size = BaseTabStripRegionView::CalculatePreferredSize("
            "available_size);",
            "CalculatePreferredSize base-class context",
        ),
        (
            "   CHECK(views::IsViewClass<VerticalTabStripView>(view.get()));",
            "   CHECK(views::IsViewClass<TabStripView>(view.get()));",
            "SetTabStripView class context",
        ),
        (
            "   CHECK(tab_strip_view_);\n"
            "   tab_strip_view_->SetIsAnimatingSize(!done_resizing);",
            "   CHECK(tab_strip_view());\n"
            "   tab_strip_view()->SetIsAnimatingSize(!done_resizing);",
            "OnResize native tab strip accessor",
        ),
        (
            "       sidetree_shell_view_ ? sidetree_shell_view_->GetBoundsInScreen()\n"
            "                            : tab_strip_view_->GetBoundsInScreen();",
            "       sidetree_shell_view_ ? sidetree_shell_view_->GetBoundsInScreen()\n"
            "                            : tab_strip_view()->GetBoundsInScreen();",
            "polish drag bounds accessor",
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

    contents = replace_hunk_exactly_once(
        contents,
        "@@ -967,6 +983,31 @@ "
        "void VerticalTabStripRegionView::HandleD",
        """@@ -599,6 +615,31 @@
<CONTEXT-BLANK>
 void VerticalTabStripRegionView::OnResize(int resize_amount,
                                           bool done_resizing) {
+  if (IsSideTreeShellActive()) {
+    if (!starting_width_on_resize_.has_value()) {
+      starting_width_on_resize_ = width();
+    }
+
+    const int resize_delta = state_controller_->IsTabStripRightAligned()
+                                 ? -resize_amount
+                                 : resize_amount;
+    const int proposed_width = starting_width_on_resize_.value() + resize_delta;
+    target_collapse_state_.collapsed = false;
+    target_collapse_state_.uncollapsed_width =
+        std::clamp(proposed_width, kUncollapsedMinWidth, kUncollapsedMaxWidth);
+
+    if (done_resizing) {
+      starting_width_on_resize_ = std::nullopt;
+      resize_area_->SetVisible(true);
+      state_controller_->SetUncollapsedWidth(
+          target_collapse_state_.uncollapsed_width);
+    }
+
+    ForceSideTreeExpandedState();
+    InvalidateLayout();
+    return;
+  }
+
   CHECK(tab_strip_view());
   tab_strip_view()->SetIsAnimatingSize(!done_resizing);
   if (!starting_width_on_resize_.has_value()) {""",
        "SideTree resize base-class accessor context",
    )

    final_header = "@@ -701,6 +742,10 @@"
    if final_header not in contents:
        old_headers = (
            "@@ -1048,12 +1089,23 @@ "
            "void VerticalTabStripRegionView::SetColl",
            "@@ -1048,13 +1089,24 @@ "
            "void VerticalTabStripRegionView::SetColl",
        )
        matches = [header for header in old_headers if contents.count(header) == 1]
        if len(matches) != 1:
            raise RuntimeError(
                "cannot repair IsCollapsing and RequestCollapse relocation: "
                f"found {len(matches)} source hunks"
            )
        contents = replace_hunk_exactly_once(
            contents,
            matches[0],
            """@@ -701,6 +742,10 @@
 }
<CONTEXT-BLANK>
 bool VerticalTabStripRegionView::IsCollapsing() {
+  if (IsSideTreeShellActive()) {
+    return false;
+  }
+
   return BrowserAnimationController::From(browser_view()->browser())
              ->GetCurrentMotion(TabStripAnimations::kVerticalTabStrip) ==
          TabStripAnimations::kCollapse;
@@ -715,2 +760,9 @@
 void VerticalTabStripRegionView::RequestCollapse(bool collapse) {
+  if (IsSideTreeShellActive()) {
+    ForceSideTreeExpandedState();
+    OnCollapseStateChanged(tabs::VerticalTabStripCollapseState::kExpanded);
+    InvalidateLayout();
+    return;
+  }
+
   target_collapse_state_.collapsed = collapse;""",
            "IsCollapsing and RequestCollapse base-class relocation",
        )

    contents = replace_hunk_exactly_once(
        contents,
        "@@ -1098,6 +1150,27 @@ "
        "void VerticalTabStripRegionView::ClickEv",
        """@@ -758,6 +810,27 @@
   }
 }
<CONTEXT-BLANK>
+bool VerticalTabStripRegionView::IsSideTreeShellActive() const {
+  return sidetree_shell_view_ != nullptr;
+}
+
+void VerticalTabStripRegionView::ForceSideTreeExpandedState() {
+  if (!IsSideTreeShellActive()) {
+    return;
+  }
+
+  // C2 replaces the native vertical tab strip with SideTree, so Chromium's
+  // collapsed-strip mode is disabled until SideTree has its own collapse model.
+  target_collapse_state_.collapsed = false;
+  ResetExpandOnHoverTimers();
+  is_expanded_on_hover_ = false;
+
+  if (!update_state_controller_collapsed_callback_.is_null() &&
+      state_controller_->IsCollapsed()) {
+    update_state_controller_collapsed_callback_.Run(false);
+  }
+}
+
 void VerticalTabStripRegionView::OnTabStripViewSet() {
   // C2 keeps Chromium's native vertical tab view alive for controller/drag
   // plumbing, while public visible tab-strip queries point at SideTree.""",
        "SideTree shell helpers hook context",
    )
    return contents


def repair_native_tab_tree(contents: str) -> str:
    legacy_profile_calls = contents.count("->profile()")
    current_profile_calls = contents.count("->GetProfile()")
    if legacy_profile_calls == 65 and current_profile_calls == 4:
        # Chromium 152 renamed Browser::profile() to Browser::GetProfile().
        # Every legacy call in this SideTree patch is on an added source line.
        contents = contents.replace("->profile()", "->GetProfile()")
    elif legacy_profile_calls != 0 or current_profile_calls != 69:
        raise RuntimeError(
            "cannot repair SideTree Browser profile accessors: "
            f"found {legacy_profile_calls} legacy and "
            f"{current_profile_calls} current calls"
        )

    contents = replace_exactly_once(
        contents,
        "+  Browser* browser = browser_view->browser();",
        "+  BrowserWindowInterface* browser = browser_view->browser();",
        "session persistence browser interface",
    )
    contents = replace_exactly_once(
        contents,
        "+  Browser* browser = browser_view_->browser();",
        "+  BrowserWindowInterface* browser = browser_view_->browser();",
        "new-tab browser interface",
    )
    contents = replace_exactly_once(
        contents,
        "+  const SessionID window_id = browser->session_id();",
        "+  const SessionID window_id = browser->GetSessionID();",
        "browser window session ID accessor",
    )
    contents = replace_exactly_once(
        contents,
        "@@ -238,16 +3166,28 @@",
        "@@ -238,16 +3166,29 @@",
        "native tab tree observer hunk size",
    )
    contents = replace_exactly_once(
        contents,
        " void SideTreeTabStripView::OnTabChangedAt(tabs::TabInterface* tab,\n"
        "                                           int index,\n"
        "                                           TabChangeType change_type) {\n"
        "+  if (ContainsIndex(index) && MaybeRunWorkspaceHarnessCommand(\n"
        "+                                  tab_strip_model_->GetWebContentsAt(index))) {",
        " void SideTreeTabStripView::OnTabChangedAt(\n"
        "     tabs::TabInterface* tab,\n"
        "     TabChangeType change_type) {\n"
        "+  const int index = tab_strip_model_->GetIndexOfTab(tab);\n"
        "+  if (ContainsIndex(index) && MaybeRunWorkspaceHarnessCommand(\n"
        "+                                  tab_strip_model_->GetWebContentsAt(index))) {",
        "native tab tree observer definition",
    )

    contents = replace_hunk_exactly_once(
        contents,
        "@@ -4686,10 +4687,26 @@",
        '''@@ -2607,10 +2608,26 @@
       "views/frame/vertical_tab_strip_background_blur_backdrop.cc",
       "views/frame/vertical_tab_strip_background_blur_backdrop.h",
       "views/frame/vertical_tab_strip_region_view.cc",
       "views/frame/vertical_tab_strip_region_view.h",
+      "views/tabs/sidetree/sidetree_container_tab_state.cc",
+      "views/tabs/sidetree/sidetree_container_tab_state.h",
+      "views/tabs/sidetree/sidetree_profile_service.cc",
+      "views/tabs/sidetree/sidetree_profile_service.h",
+      "views/tabs/sidetree/sidetree_workspace_controller.cc",
+      "views/tabs/sidetree/sidetree_workspace_controller.h",
+      "views/tabs/sidetree/sidetree_tab_order.cc",
+      "views/tabs/sidetree/sidetree_tab_order.h",
       "views/tabs/sidetree/sidetree_tab_row_view.cc",
       "views/tabs/sidetree/sidetree_tab_row_view.h",
+      "views/tabs/sidetree/sidetree_tab_restore_state.cc",
+      "views/tabs/sidetree/sidetree_tab_restore_state.h",
       "views/tabs/sidetree/sidetree_tab_strip_view.cc",
       "views/tabs/sidetree/sidetree_tab_strip_view.h",
+      "views/tabs/sidetree/sidetree_tree_model.cc",
+      "views/tabs/sidetree/sidetree_tree_model.h",
+      "views/tabs/sidetree/sidetree_workspace_state.cc",
+      "views/tabs/sidetree/sidetree_workspace_state.h",
+      "views/tabs/sidetree/sidetree_workspace_menu_model.cc",
+      "views/tabs/sidetree/sidetree_workspace_menu_model.h",
       "views/helium/frame_corner_radius.cc",
       "views/helium/frame_corner_radius.h",''',
        "native tab tree source list context",
    )

    contents = replace_exactly_once(
        contents,
        "@@ -5743,6 +5760,84 @@",
        "@@ -3953,6 +3970,84 @@",
        "native tab tree test target header",
    )
    contents = replace_exactly_once(
        contents,
        "+}\n"
        "+\n"
        " if (use_aura) {\n"
        '   source_set("overscroll_pref_manager") {\n'
        "     sources = [",
        "+}\n"
        "+\n"
        " if (toolkit_views) {\n"
        '   source_set("idle_dialog") {\n'
        '     public = [ "idle_dialog.h" ]',
        "native tab tree test target owner context",
    )
    contents = replace_hunk_exactly_once(
        contents,
        "@@ -1492,6 +1492,11 @@",
        # Keep the context below ShouldDrawVerticalTabStrip(). GNU Patch 2.8,
        # which quilt uses on macOS, rejects the larger function-body context.
        """@@ -1569,6 +1569,11 @@
 }
<CONTEXT-BLANK>
+bool BrowserView::IsSideTreeVerticalTabStripActive() const {
+  return ShouldDrawVerticalTabStrip() && vertical_tab_strip_region_view_ &&
+         vertical_tab_strip_region_view_->IsSideTreeShellActive();
+}
+
 bool BrowserView::IsVerticalTabStripRightAligned() const {
   auto* controller = tabs::VerticalTabStripStateController::From(browser_);
   return controller && controller->IsTabStripRightAligned();
 }""",
        "BrowserView SideTree state context",
    )
    contents = replace_exactly_once(
        contents,
        "@@ -46,6 +46,7 @@\n"
        ' #include "chrome/browser/ui/toasts/api/toast_id.h"\n'
        ' #include "chrome/browser/ui/toasts/toast_controller.h"\n'
        ' #include "chrome/browser/ui/views/frame/browser_view.h"\n'
        '+#include "chrome/browser/ui/views/tabs/sidetree/sidetree_container_tab_state.h"\n'
        ' #include "chrome/browser/ui/web_applications/app_browser_controller.h"\n'
        ' #include "chrome/browser/ui/web_applications/web_app_tabbed_utils.h"\n'
        ' #include "chrome/browser/web_applications/web_app_helpers.h"',
        "@@ -49,11 +49,12 @@\n"
        ' #include "chrome/browser/ui/toasts/api/toast_id.h"\n'
        ' #include "chrome/browser/ui/toasts/toast_controller.h"\n'
        ' #include "chrome/browser/ui/views/frame/browser_view.h"\n'
        '+#include "chrome/browser/ui/views/tabs/sidetree/sidetree_container_tab_state.h"\n'
        ' #include "chrome/browser/ui/web_applications/app_browser_controller.h"\n'
        ' #include "chrome/browser/ui/web_applications/navigation_capturing_process.h"\n'
        ' #include "chrome/browser/ui/web_applications/web_app_launch_navigation_handle_user_data.h"\n'
        ' #include "chrome/browser/ui/web_applications/web_app_launch_utils.h"\n'
        ' #include "chrome/browser/ui/web_applications/web_app_tabbed_utils.h"\n'
        ' #include "chrome/browser/ui/window_feature_controller/window_feature_controller.h"\n'
        ' #include "chrome/browser/web_applications/web_app_helpers.h"\n'
        ' #include "chrome/browser/web_applications/web_app_tab_helper.h"',
        "browser_navigator include context",
    )

    contents = remove_patch_file_exactly_once(
        contents,
        "Index: src/chrome/test/BUILD.gn\n",
        "Index: src/chrome/browser/ui/views/tabs/sidetree/"
        "sidetree_container_tab_state.cc\n",
        "obsolete monolithic unit-test source list",
    )

    if has_complete_repair(
        contents,
        (
            "@@ -162,5 +163,9 @@",
            "@@ -749,6 +749,33 @@",
            "@@ -130,8 +132,8 @@",
        ),
        "native tab tree patch",
    ):
        return contents

    repairs = (
        (
            "   auto min_size = TabStripRegionView::GetMinimumSize();",
            "   auto min_size = BaseTabStripRegionView::GetMinimumSize();",
            "GetMinimumSize compact-mode context",
        ),
        (
            "   auto size = TabStripRegionView::CalculatePreferredSize("
            "available_size);",
            "   auto size = BaseTabStripRegionView::CalculatePreferredSize("
            "available_size);",
            "CalculatePreferredSize compact-mode context",
        ),
        (
            " // and VerticalTabView.\n class HoverCardAnchorTarget {",
            " // and TabView.\n class HoverCardAnchorTarget {",
            "HoverCardAnchorTarget comment context",
        ),
        (
            '+    "//components/tabs",',
            '+    "//components/tabs:public",',
            "SideTree unit-test tabs dependency",
        ),
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
    )

    for old, new, description in repairs:
        contents = replace_exactly_once(contents, old, new, description)

    contents = replace_hunk_exactly_once(
        contents,
        "@@ -153,6 +154,10 @@",
        """@@ -162,5 +163,9 @@
   registry->RegisterBooleanPref(prefs::kShowMediaButton, true);
   registry->RegisterBooleanPref(prefs::kShowVerticalTabsCollapseButton, true);
   registry->RegisterBooleanPref(prefs::kShowDynamicNewTabButton, true);
+  registry->RegisterBooleanPref(prefs::kSideTreeShowInlineTabActions, false);
+  registry->RegisterBooleanPref(prefs::kSideTreeShowHoverPreviews, false);
+  registry->RegisterBooleanPref(prefs::kSideTreeShowTabMuteButton, false);
+  sidetree::SideTreeProfileService::RegisterProfilePrefs(registry);
<CONTEXT-BLANK>
   registry->RegisterBooleanPref(prefs::kWebAppCreateOnDesktop, true);""",
        "SideTree profile preference registration context",
    )
    contents = replace_hunk_exactly_once(
        contents,
        "@@ -106,6 +106,7 @@",
        """@@ -93,4 +93,5 @@ class VerticalTabStripRegionView final
   void UpdateInteriorMargin();
<CONTEXT-BLANK>
+  bool IsSideTreeShellActive() const;
   // views::View:
   void AddedToWidget() override;""",
        "IsSideTreeShellActive declaration context",
    )
    contents = replace_hunk_exactly_once(
        contents,
        "@@ -856,6 +856,33 @@",
        """@@ -749,6 +749,33 @@
 inline constexpr char kShowDynamicNewTabButton[] =
     "helium.browser.show_dynamic_new_tab_button";
<CONTEXT-BLANK>
+// A boolean pref set to true if native SideTree rows expose inline tab actions.
+inline constexpr char kSideTreeShowInlineTabActions[] =
+    "sidetree.show_inline_tab_actions";
+
+// A boolean pref set to true if native SideTree rows show tab hover previews.
+inline constexpr char kSideTreeShowHoverPreviews[] =
+    "sidetree.show_hover_previews";
+
+// A boolean pref set to true if native SideTree rows expose a row-local mute
+// button for tabs with audio state.
+inline constexpr char kSideTreeShowTabMuteButton[] =
+    "sidetree.show_tab_mute_button";
+
+// A list pref containing native SideTree workspace metadata records.
+inline constexpr char kSideTreeWorkspaces[] = "sidetree.workspaces.v1.items";
+
+// A string pref containing the default native SideTree workspace id.
+inline constexpr char kSideTreeDefaultWorkspaceId[] =
+    "sidetree.workspaces.v1.default_id";
+
+// A list pref containing native SideTree container metadata records.
+inline constexpr char kSideTreeContainers[] = "sidetree.containers.v1.items";
+
+// A string pref containing the default native SideTree container id.
+inline constexpr char kSideTreeDefaultContainerId[] =
+    "sidetree.containers.v1.default_id";
+
 // An int pref that controls the voice typing feature. This is managed by
 // enterprise policy.
 inline constexpr char kVoiceTypingSettings[] = "browser.voice_typing_settings";""",
        "SideTree preference constants context",
    )
    contents = replace_hunk_exactly_once(
        contents,
        "@@ -218,8 +220,8 @@",
        """@@ -130,8 +132,8 @@
                                    views::MinimumFlexSizeRule::kPreferred,
                                    views::MaximumFlexSizeRule::kPreferred));
<CONTEXT-BLANK>
-  sidetree_shell_view_ = AddChildView(
-      CreateSideTreeNativeShellView(browser_view, tab_strip_model()));
+  sidetree_shell_view_ = AddChildView(CreateSideTreeNativeShellView(
+      browser_view, tab_strip_model(), hover_card_controller()));
   sidetree_shell_view_->SetProperty(
       views::kFlexBehaviorKey,
       views::FlexSpecification(views::LayoutOrientation::kVertical,""",
        "native tree shell constructor accessors",
    )
    return contents


def repair_vertical_strip_native_shell(contents: str) -> str:
    contents = replace_hunk_exactly_once(
        contents,
        "@@ -519,6 +560,10 @@ "
        "void VerticalTabStripRegionView::Layout(",
        """@@ -375,6 +416,10 @@
 }
<CONTEXT-BLANK>
 views::View* VerticalTabStripRegionView::GetDefaultFocusableChild() {
+  if (sidetree_shell_view_) {
+    return sidetree_shell_view_;
+  }
+
   tabs::TabInterface* active_tab = tab_strip_model()->GetActiveTab();
   if (active_tab) {
     return GetTabAnchorView(active_tab->GetHandle());""",
        "GetDefaultFocusableChild active-tab context",
    )

    if has_complete_repair(
        contents,
        (
            "@@ -62,13 +62,16 @@",
            "@@ -705,6 +750,8 @@",
            "@@ -234,6 +234,7 @@ class VerticalTabStripRegionView final",
        ),
        "vertical strip native shell patch",
    ):
        return contents

    contents = replace_hunk_exactly_once(
        contents,
        "@@ -70,14 +70,17 @@",
        '''@@ -62,13 +62,16 @@
 #include "ui/views/background.h"
 #include "ui/views/controls/button/label_button.h"
 #include "ui/views/controls/focus_ring.h"
+#include "ui/views/controls/label.h"
 #include "ui/views/controls/resize_area.h"
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
 #include "ui/views/view_utils.h"''',
        "native shell include context",
    )
    contents = replace_hunk_exactly_once(
        contents,
        "@@ -1062,6 +1107,8 @@ views::View* VerticalTabStripRegionView:",
        """@@ -705,6 +750,8 @@
 }
<CONTEXT-BLANK>
 void VerticalTabStripRegionView::OnTabStripViewSet() {
+  tab_strip_view()->SetVisible(false);
+  tab_strip_view()->SetProperty(views::kViewIgnoredByLayoutKey, true);
   tab_strip_view()->SetProperty(
       views::kFlexBehaviorKey,
       views::FlexSpecification(views::MinimumFlexSizeRule::kScaleToMinimum,""",
        "hidden native tab strip context",
    )

    repairs = (
        (
            "   if (tab_strip_view_) {",
            "   if (tab_strip_view()) {",
            "OnCollapseStateChanged tab strip accessor context",
        ),
        (
            "@@ -1141,6 +1188,12 @@ "
            "void VerticalTabStripRegionView::OnColla",
            "@@ -809,7 +809,13 @@ "
            "void VerticalTabStripRegionView::OnCollapseStateChanged(",
            "OnCollapseStateChanged hunk context",
        ),
        (
            "                            "
            "!state_controller_->IsExpandOnHoverEnabled() ||\n"
            "                            resize_area_->is_resizing());\n"
            " \n",
            "   bool collapsed = "
            "state != tabs::VerticalTabStripCollapseState::kExpanded;\n"
            " \n"
            "   UpdateResizeAreaVisibility();\n"
            " \n",
            "OnCollapseStateChanged resize context",
        ),
        (
            "@@ -303,6 +303,7 @@ class VerticalTabStripRegionView final",
            "@@ -234,6 +234,7 @@ class VerticalTabStripRegionView final",
            "SideTree shell member hunk context",
        ),
        (
            "   bool zen_mode_floating_style_ = false;\n"
            " \n"
            "   raw_ptr<VerticalTabStripView> tab_strip_view_ = nullptr;\n"
            "+  raw_ptr<views::View> sidetree_shell_view_ = nullptr;\n"
            "   raw_ptr<VerticalTabStripBottomContainer> "
            "bottom_button_container_ = nullptr;",
            "   bool has_leading_exclusion_ = false;\n"
            "   bool zen_mode_floating_style_ = false;\n"
            " \n"
            "+  raw_ptr<views::View> sidetree_shell_view_ = nullptr;\n"
            "   raw_ptr<VerticalTabStripBottomContainer> "
            "bottom_button_container_ = nullptr;",
            "SideTree shell member type context",
        ),
    )

    for old, new, description in repairs:
        contents = replace_exactly_once(contents, old, new, description)
    return contents


def repair_native_tab_bridge(contents: str) -> str:
    contents = replace_hunk_exactly_once(
        contents,
        '@@ -4686,6 +4686,10 @@ static_library("ui") {',
        '''@@ -2607,6 +2607,10 @@
       "views/frame/vertical_tab_strip_background_blur_backdrop.cc",
       "views/frame/vertical_tab_strip_background_blur_backdrop.h",
       "views/frame/vertical_tab_strip_region_view.cc",
       "views/frame/vertical_tab_strip_region_view.h",
+      "views/tabs/sidetree/sidetree_tab_row_view.cc",
+      "views/tabs/sidetree/sidetree_tab_row_view.h",
+      "views/tabs/sidetree/sidetree_tab_strip_view.cc",
+      "views/tabs/sidetree/sidetree_tab_strip_view.h",
       "views/helium/frame_corner_radius.cc",
       "views/helium/frame_corner_radius.h",''',
        "native tab bridge source list context",
    )

    contents = replace_exactly_once(
        contents,
        "+void SideTreeTabStripView::OnTabChangedAt(tabs::TabInterface* tab,\n"
        "+                                          int index,\n"
        "+                                          TabChangeType change_type) {",
        "+void SideTreeTabStripView::OnTabChangedAt(\n"
        "+    tabs::TabInterface* tab,\n"
        "+    TabChangeType change_type) {",
        "native tab bridge observer definition",
    )
    contents = replace_exactly_once(
        contents,
        "+  void OnTabChangedAt(tabs::TabInterface* tab,\n"
        "+                      int index,\n"
        "+                      TabChangeType change_type) override;",
        "+  void OnTabChangedAt(\n"
        "+      tabs::TabInterface* tab,\n"
        "+      TabChangeType change_type) override;",
        "native tab bridge observer declaration",
    )

    if has_complete_repair(
        contents,
        (
            "@@ -711,15 +691,44 @@",
            "@@ -94,6 +95,9 @@",
            "@@ -229,7 +233,7 @@",
        ),
        "native tab bridge patch",
    ):
        return contents

    contents = replace_hunk_sequence_exactly_once(
        contents,
        (
            "@@ -777,6 +757,13 @@ "
            "void VerticalTabStripRegionView::UpdateL",
            "@@ -811,6 +798,13 @@ "
            "const tabs::TabData& VerticalTabStripReg",
            "@@ -939,6 +933,9 @@ "
            "void VerticalTabStripRegionView::SetTabS",
        ),
        """@@ -711,15 +691,44 @@ void VerticalTabStripRegionView::OnResize(
   }
 }
<CONTEXT-BLANK>
+std::optional<int> VerticalTabStripRegionView::GetFocusedTabIndex() const {
+  if (sidetree_shell_view_) {
+    if (std::optional<int> sidetree_focused_index =
+            sidetree_shell_view_->GetFocusedTabIndex()) {
+      return sidetree_focused_index;
+    }
+  }
+
+  return BaseTabStripRegionView::GetFocusedTabIndex();
+}
+
 void VerticalTabStripRegionView::SetCollapsedStateUpdatedCallback(
     base::RepeatingCallback<void(bool)> callback) {
   update_state_controller_collapsed_callback_ = std::move(callback);
 }
<CONTEXT-BLANK>
+views::View* VerticalTabStripRegionView::GetTabAnchorView(
+    const tabs::TabHandle& tab) {
+  if (sidetree_shell_view_ && tab.Get()) {
+    if (views::View* sidetree_anchor = sidetree_shell_view_->GetTabAnchorViewAt(
+            tab_strip_model()->GetIndexOfTab(tab.Get()))) {
+      return sidetree_anchor;
+    }
+  }
+  return BaseTabStripRegionView::GetTabAnchorView(tab);
+}
+
 bool VerticalTabStripRegionView::IsCollapsing() {
   return BrowserAnimationController::From(browser_view()->browser())
              ->GetCurrentMotion(TabStripAnimations::kVerticalTabStrip) ==
          TabStripAnimations::kCollapse;
 }
<CONTEXT-BLANK>
+views::View* VerticalTabStripRegionView::GetTabStripView() {
+  if (sidetree_shell_view_) {
+    return sidetree_shell_view_;
+  }
+  return BaseTabStripRegionView::GetTabStripView();
+}
+
 void VerticalTabStripRegionView::RequestCollapse(bool collapse) {""",
        "native tab bridge base-class method relocation",
    )

    hunks = (
        (
            "@@ -42,6 +42,7 @@",
            """@@ -47,7 +47,8 @@
 #include "chrome/browser/ui/views/tabs/common/tab_strip_view.h"
 #include "chrome/browser/ui/views/tabs/common/tab_view.h"
 #include "chrome/browser/ui/views/tabs/common/unpinned_tab_container_view.h"
 #include "chrome/browser/ui/views/tabs/shared/drop_arrow.h"
+#include "chrome/browser/ui/views/tabs/sidetree/sidetree_tab_strip_view.h"
 #include "chrome/browser/ui/views/tabs/vertical/vertical_tab_strip_bottom_container.h"
 #include "chrome/browser/ui/views/tabs/vertical/vertical_tab_strip_focus_swipe_controller.h"
 #include "chrome/browser/ui/web_applications/app_browser_controller.h"
""",
            "native tab bridge include context",
        ),
        (
            "@@ -70,17 +71,14 @@",
            """@@ -62,16 +63,13 @@
 #include "ui/views/background.h"
 #include "ui/views/controls/button/label_button.h"
 #include "ui/views/controls/focus_ring.h"
-#include "ui/views/controls/label.h"
 #include "ui/views/controls/resize_area.h"
 #include "ui/views/controls/separator.h"
 #include "ui/views/focus/focus_manager.h"
 #include "ui/views/interaction/element_tracker_views.h"
-#include "ui/views/layout/box_layout.h"
 #include "ui/views/layout/flex_layout.h"
 #include "ui/views/layout/flex_layout_types.h"
 #include "ui/views/layout/layout_types.h"
-#include "ui/views/style/typography.h"
 #include "ui/views/view.h"
 #include "ui/views/view_class_properties.h"
 #include "ui/views/view_utils.h"
""",
            "native tab bridge obsolete shell includes",
        ),
        (
            "@@ -1107,6 +1104,8 @@ "
            "views::View* VerticalTabStripRegionView:",
            """@@ -750,6 +759,8 @@
 }
<CONTEXT-BLANK>
 void VerticalTabStripRegionView::OnTabStripViewSet() {
+  // C2 keeps Chromium's native vertical tab view alive for controller/drag
+  // plumbing, while public visible tab-strip queries point at SideTree.
   tab_strip_view()->SetVisible(false);
   tab_strip_view()->SetProperty(views::kViewIgnoredByLayoutKey, true);
   tab_strip_view()->SetProperty(""",
            "OnTabStripViewSet bridge context",
        ),
        (
            "@@ -34,6 +34,7 @@",
            """@@ -34,7 +34,8 @@
 class BrowserView;
+class SideTreeTabStripView;
 class VerticalTabStripBottomContainer;
 class VerticalTabStripFocusSwipeController;
 class ShadowFrameView;
<CONTEXT-BLANK>
 namespace tabs {
 class VerticalTabStripStateController;""",
            "SideTreeTabStripView forward declaration context",
        ),
        (
            "@@ -303,7 +304,7 @@ class VerticalTabStripRegionView final",
            """@@ -94,6 +95,9 @@
   void RemovedFromWidget() override;
   void Layout(PassKey) override;
   views::View* GetDefaultFocusableChild() override;
+  std::optional<int> GetFocusedTabIndex() const override;
+  views::View* GetTabAnchorView(const tabs::TabHandle& tab) override;
+  views::View* GetTabStripView() override;
   gfx::Size GetMinimumSize() const override;
   gfx::Size CalculatePreferredSize(
       const views::SizeBounds& available_size) const override;
@@ -229,7 +233,7 @@
   // Whether a leading exclusion exists due to window controls.
   bool has_leading_exclusion_ = false;
   bool zen_mode_floating_style_ = false;
<CONTEXT-BLANK>
-  raw_ptr<views::View> sidetree_shell_view_ = nullptr;
+  raw_ptr<SideTreeTabStripView> sidetree_shell_view_ = nullptr;
   raw_ptr<VerticalTabStripBottomContainer> bottom_button_container_ = nullptr;
   raw_ptr<views::View> gemini_button_ = nullptr;""",
            "native tab bridge declarations and member context",
        ),
    )

    for old_header, new_hunk, description in hunks:
        contents = replace_hunk_exactly_once(
            contents, old_header, new_hunk, description
        )

    repairs = (
        (
            "      CreateSideTreeNativeShellView(browser_view, tab_strip_model_));",
            "      CreateSideTreeNativeShellView(browser_view, tab_strip_model()));",
            "native shell tab model accessor",
        ),
        (
            "-  gfx::Rect tab_strip_draggable_bounds = "
            "tab_strip_view_->GetBoundsInScreen();",
            "-  gfx::Rect tab_strip_draggable_bounds = "
            "tab_strip_view()->GetBoundsInScreen();",
            "native drag bounds source accessor",
        ),
        (
            "+                           : tab_strip_view_->GetBoundsInScreen();",
            "+                           : tab_strip_view()->GetBoundsInScreen();",
            "native drag bounds fallback accessor",
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
        ("sidetree/ui/native-tab-bridge.patch", repair_native_tab_bridge),
        (
            "sidetree/ui/vertical-strip-native-shell.patch",
            repair_vertical_strip_native_shell,
        ),
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
