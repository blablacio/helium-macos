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
    if has_complete_repair(
        contents,
        (
            "@@ -599,6 +615,31 @@",
            "@@ -701,6 +742,10 @@",
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
@@ -714,6 +759,13 @@
 }
<CONTEXT-BLANK>
 void VerticalTabStripRegionView::RequestCollapse(bool collapse) {
+  if (IsSideTreeShellActive()) {
+    ForceSideTreeExpandedState();
+    OnCollapseStateChanged(tabs::VerticalTabStripCollapseState::kExpanded);
+    InvalidateLayout();
+    return;
+  }
+
   target_collapse_state_.collapsed = collapse;
   // Do not trigger the animation before tab_strip_view() is set, as the region
   // view only subscribes to animation updates once tab_strip_view() has been""",
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
        (
            "@@ -46,6 +46,7 @@\n"
            " #include \"chrome/browser/ui/toasts/api/toast_id.h\"\n"
            " #include \"chrome/browser/ui/toasts/toast_controller.h\"\n"
            " #include \"chrome/browser/ui/views/frame/browser_view.h\"\n"
            "+#include \"chrome/browser/ui/views/tabs/sidetree/sidetree_container_tab_state.h\"\n"
            " #include \"chrome/browser/ui/web_applications/app_browser_controller.h\"\n"
            " #include \"chrome/browser/ui/web_applications/web_app_tabbed_utils.h\"\n"
            " #include \"chrome/browser/web_applications/web_app_helpers.h\"",
            "@@ -48,9 +48,10 @@\n"
            " #include \"chrome/browser/ui/toasts/api/toast_id.h\"\n"
            " #include \"chrome/browser/ui/toasts/toast_controller.h\"\n"
            " #include \"chrome/browser/ui/views/frame/browser_view.h\"\n"
            "+#include \"chrome/browser/ui/views/tabs/sidetree/sidetree_container_tab_state.h\"\n"
            " #include \"chrome/browser/ui/web_applications/app_browser_controller.h\"\n"
            " #include \"chrome/browser/ui/web_applications/"
            "navigation_capturing_process.h\"\n"
            " #include \"chrome/browser/ui/web_applications/"
            "web_app_launch_navigation_handle_user_data.h\"\n"
            " #include \"chrome/browser/ui/web_applications/web_app_launch_utils.h\"\n"
            " #include \"chrome/browser/ui/web_applications/web_app_tabbed_utils.h\"\n"
            " #include \"chrome/browser/web_applications/web_app_helpers.h\"",
            "browser_navigator include context",
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
        """@@ -62,13 +62,16 @@
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
 #include "ui/views/view_utils.h""",
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
            "   const int active_index = tab_strip_model_->active_index();",
            "   const int active_index = tab_strip_model()->active_index();",
            "GetDefaultFocusableChild tab model context",
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
+views::View* VerticalTabStripRegionView::GetTabAnchorViewAt(int tab_index) {
+  if (sidetree_shell_view_) {
+    if (views::View* sidetree_anchor =
+            sidetree_shell_view_->GetTabAnchorViewAt(tab_index)) {
+      return sidetree_anchor;
+    }
+  }
+
+  return BaseTabStripRegionView::GetTabAnchorViewAt(tab_index);
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
            """@@ -49,6 +49,7 @@
 #include "chrome/browser/ui/views/tabs/common/tab_strip_view.h"
 #include "chrome/browser/ui/views/tabs/common/tab_view.h"
 #include "chrome/browser/ui/views/tabs/common/unpinned_tab_container_view.h"
 #include "chrome/browser/ui/views/tabs/shared/drop_arrow.h"
+#include "chrome/browser/ui/views/tabs/sidetree/sidetree_tab_strip_view.h"
 #include "chrome/browser/ui/views/tabs/vertical/vertical_tab_strip_bottom_container.h"
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
 #include "ui/views/view_utils.h""",
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
            """@@ -35,6 +35,7 @@
 class BrowserView;
+class SideTreeTabStripView;
 class VerticalTabStripBottomContainer;
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
+  views::View* GetTabAnchorViewAt(int tab_index) override;
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
