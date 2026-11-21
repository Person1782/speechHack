# Latest user direction — original neon restored

The user explicitly reversed the playful-poster redesign: “keep neon lights theme” and “revert to the original with the swinging sign.” Preserve the original Be Vietnam Pro typography, uppercase glowing wordmark, squared corners and animated swinging landing sign. Do not reintroduce the warm-paper/Fredoka/Montserrat redesign. Keep the previously removed marquee ticker absent.

The newly requested per-question Single choice / Open ended selector remains authorized. Use a two-option shadcn RadioGroup with the original dark surfaces and cyan selected border; map to existing classic/poll behavior. Preserve existing advanced decoy/caption modes and the You.com review gate.


{
  "VISUAL_POLISH_ADDENDUM_paper_examples_reference_only": {
    "intent": "Apply Paper-style workspace discipline (calm grid, dense lists, restrained controls) as VISUAL REFERENCE ONLY while preserving HH dark neon gig-poster identity. No new features; polish HostConsole.jsx, QuestionManager.jsx, Polls.jsx, BigScreen.jsx only.",
    "do_not": [
      "Do not change API behavior or nav labels/structure (Run / Radar / More)",
      "Do not add stock images",
      "Do not add new strings outside i18n",
      "Do not add glow everywhere—reserve neon for status + primary actions"
    ],

    "paper_inspired_principles_to_apply": {
      "composition": [
        "Narrow utility rail + dense content column (lists/tables) + secondary inspector column on desktop",
        "Controls live in a compact command strip; content gets the space",
        "Prefer thin separators + alignment over chunky card stacks"
      ],
      "density": "Replace repeated tall cards with compact rows (44–56px) and a single details panel (Dialog/Drawer) for editing.",
      "restraint": "Use hh-pink/hh-cyan/hh-yellow only for: primary CTA, active state, critical status. Everything else stays grayscale tokens (bg/surface/raised/line)."
    },

    "layout_changes_by_page": {
      "More_QuestionManager.jsx": {
        "goal": "Compact manager list (Paper-like) instead of chunky repeated cards.",
        "desktop_layout": {
          "grid": "lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-4",
          "left": "Dense list/table of questions (ScrollArea).",
          "right": "Inspector panel (selected question preview + quick actions). If no selection, show empty state with muted copy."
        },
        "mobile_layout": {
          "pattern": "Single column list; edit opens Drawer; add button sticky bottom.",
          "sticky": "sticky bottom-0 pb-[env(safe-area-inset-bottom)]"
        },
        "row_spec": {
          "height": "min-h-[52px]",
          "structure": "[drag] [question text (2 lines clamp)] [type badge] [meta: time limit] [actions]",
          "classes": "flex items-center gap-3 px-3 py-2 border-b border-[color:var(--hh-line)] hover:bg-[color:var(--hh-raised)]",
          "micro": "On hover: reveal action buttons (opacity transition). On active/selected: left 3px cyan spine (.hh-spine) + slightly raised background.",
          "testids": [
            "question-manager-list",
            "question-manager-row",
            "question-manager-row-select",
            "question-manager-row-actions"
          ]
        },
        "components": {
          "use": [
            "/app/frontend/src/components/ui/scroll-area.jsx",
            "/app/frontend/src/components/ui/table.jsx (desktop optional)",
            "/app/frontend/src/components/ui/dialog.jsx",
            "/app/frontend/src/components/ui/drawer.jsx",
            "/app/frontend/src/components/ui/badge.jsx",
            "/app/frontend/src/components/ui/separator.jsx"
          ]
        },
        "dialog_drawer_widths": {
          "dialog": "max-w-[720px] w-[92vw]",
          "drawer": "h-[92dvh]"
        }
      },

      "Run_Polls.jsx": {
        "goal": "Wider, calmer two-column host workspace: composer/moderation primary; sound dock + room/status secondary.",
        "desktop_layout": {
          "grid": "lg:grid lg:grid-cols-[minmax(0,1fr)_420px] lg:gap-6",
          "left_stack": [
            "Command strip (mode tabs + lock + send) compact",
            "Moderation queue (ScrollArea) dense rows",
            "Approved counter + limit messaging as small chips"
          ],
          "right_stack": [
            "Room card (session code, connected count) secondary",
            "Soundboard as a dock: sticky top-4, 4x2 grid, tighter gaps",
            "Top 5 preview panel (if present)"
          ]
        },
        "mobile_layout": {
          "pattern": "Single column; composer at top; moderation list; soundboard collapsible dock at bottom (Collapsible).",
          "sticky": "Primary action bar sticky bottom; soundboard opens as Drawer if needed."
        },
        "moderation_density": {
          "replace": "Ticket-stub cards remain allowed, but default view should be compact rows; expand row to show full ticket details.",
          "row": "min-h-[56px] px-3 py-2 border-b border-[color:var(--hh-line)]",
          "expand": "Use Collapsible: collapsed shows answer + dup count + 2 actions; expanded shows metadata + notes."
        },
        "soundboard_dock": {
          "grid": "grid grid-cols-4 gap-2",
          "button": "Use existing .hh-btn but apply hh-size-sm; keep labels 1 line, truncate.",
          "click_micro": "Add .hh-pop on click; do NOT add glow."
        },
        "testids": [
          "run-workspace",
          "run-command-strip",
          "run-moderation-list",
          "run-soundboard-dock"
        ]
      },

      "HostConsole.jsx": {
        "goal": "Make host controls feel like a deliberate workspace: clear stage labels, restrained accent, fewer giant blocks.",
        "structure": {
          "top": "Compact header row: wordmark left, language toggle + connection chip right.",
          "main": "Use a consistent section header pattern: .hh-meta label + thin Separator + content.",
          "spacing": "Prefer space-y-4 (mobile) / space-y-6 (desktop); avoid stacking multiple .hh-panel-raised back-to-back without breathing room."
        },
        "stage_labels": {
          "pattern": "Small uppercase labels (hh-meta) above each functional block: COMPOSE, MODERATE, SOUND, RESULTS.",
          "accent": "Only one accent spine per major block (cyan for active stage)."
        },
        "testids": [
          "host-console-header",
          "host-console-stage-compose",
          "host-console-stage-moderate",
          "host-console-stage-sound"
        ]
      },

      "BigScreen.jsx": {
        "goal": "Fix header overflow + improve TV safe-area composition; best possible mobile fallback for TV view.",
        "tv_safe_margins": {
          "outer": "px-[max(24px,3vw)] py-[max(18px,2.2vw)]",
          "rule": "Never pin text to edges; assume overscan."
        },
        "header": {
          "fix": "Use a 3-zone grid: left session/round, center timer, right status; allow wrapping with min-w-0 and truncate.",
          "classes": "grid grid-cols-[1fr_auto_1fr] items-center gap-4 min-w-0",
          "title": "Clamp wordmark size on narrow: text-[clamp(18px,3vw,34px)]"
        },
        "cards": {
          "layout": "2 columns only when >=1024px; otherwise 1 column; keep consistent gaps (gap-4).",
          "typography": "Answer text: text-[clamp(28px,4.2vw,56px)] leading-[1.05] font-extrabold"
        },
        "mobile_fallback": {
          "when": "If BigScreen is opened on a phone, switch to single-column with smaller header and hide non-essential chrome.",
          "rule": "Keep only: current prompt + approved cards; move Top5 to bottom sheet (Drawer) triggered by a small button."
        },
        "dialog_widths": {
          "any_overlay": "w-[92vw] max-w-[860px]"
        },
        "testids": [
          "tv-header",
          "tv-timer",
          "tv-approved-cards",
          "tv-top5-trigger"
        ]
      }
    },

    "shared_ui_recipes_to_add_(no_new_palette)": {
      "command_strip": {
        "purpose": "Paper-like compact control row used in Run + Manager.",
        "classes": "hh-panel flex flex-wrap items-center gap-2 px-3 py-2 border-2 border-[color:var(--hh-line)]",
        "controls": "Prefer small buttons (hh-size-sm) + Badge chips; keep primary CTA at far right on desktop.",
        "testid": "command-strip"
      },
      "dense_list": {
        "classes": "hh-panel overflow-hidden",
        "row_hover": "hover:bg-[color:var(--hh-raised)] transition-colors duration-150",
        "row_active": "bg-[color:var(--hh-raised)] relative before:content-[''] before:absolute before:left-0 before:top-0 before:bottom-0 before:w-[3px] before:bg-[color:var(--hh-cyan)]",
        "empty_state": "Use muted copy + a single hh-btn ghost; no illustrations."
      },
      "accent_budget": {
        "rule": "Per viewport: max 1 primary neon (pink OR cyan OR yellow) + 1 secondary chip. Everything else grayscale.",
        "why": "Prevents AI-looking glow overload; keeps workspace calm like Paper while retaining HH punch."
      }
    },

    "data_testid_reminder": {
      "rule": "All interactive + key informational elements must include data-testid (kebab-case).",
      "add_to_new_controls": [
        "command strip buttons",
        "row expand/collapse toggles",
        "TV top5 drawer trigger",
        "dialog close/save buttons"
      ]
    },

    "instructions_to_main_agent": [
      "This is an addendum: keep existing tokens and hh-* recipes; only adjust composition/density/restraint.",
      "Implement compact rows + inspector patterns using shadcn ScrollArea/Collapsible/Dialog/Drawer; no new libraries.",
      "Ensure BigScreen header uses 3-zone grid + truncation to prevent overflow; add TV safe margins.",
      "Keep everything in .js/.jsx; no .tsx guidance."
    ]
  },

  "General UI UX Design Guidelines": "    - You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms\n    - You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text\n   - NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json\n\n **GRADIENT RESTRICTION RULE**\nNEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc\nNEVER use dark gradients for logo, testimonial, footer etc\nNEVER let gradients cover more than 20% of the viewport.\nNEVER apply gradients to text-heavy content or reading areas.\nNEVER use gradients on small UI elements (<100px width).\nNEVER stack multiple gradient layers in the same viewport.\n\n**ENFORCEMENT RULE:**\n    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors\n\n**How and where to use:**\n   • Section backgrounds (not content backgrounds)\n   • Hero section header content. Eg: dark to light to dark color\n   • Decorative overlays and accent elements only\n   • Hero section with 2-3 mild color\n   • Gradients creation can be done for any angle say horizontal, vertical or diagonal\n\n- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc**\n\n</Font Guidelines>\n\n- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead. \n   \n- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.\n\n- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.\n   \n- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly\n    Eg: - if it implies playful/energetic, choose a colorful scheme\n           - if it implies monochrome/minimal, choose a black–white/neutral scheme\n\n**Component Reuse:**\n\t- Prioritize using pre-existing components from src/components/ui when applicable\n\t- Create new components that match the style and conventions of existing components when needed\n\t- Examine existing components to understand the project's component patterns before creating new ones\n\n**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component\n\n**Best Practices:**\n\t- Use Shadcn/UI as the primary component library for consistency and accessibility\n\t- Import path: ./components/[component-name]\n\n**Export Conventions:**\n\t- Components MUST use named exports (export const ComponentName = ...)\n\t- Pages MUST use default exports (export default function PageName() {...})\n\n**Toasts:**\n  - Use `sonner` for toasts\"\n  - Sonner component are located in `/app/src/components/ui/sonner.tsx`\n\nUse 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals."
}


,
  "NEWS_RESEARCH_PANEL_ADDENDUM_(You.com)_append_only": {
    "scope": "Add Newsroom tab under More > QuestionManager. This is a UI/UX + spacing addendum only; keep existing HH workspace palette/tokens/density. No new aesthetic system, no new assets, no Tier3+ expansion.",
    "primary_user": "Host-only",
    "core_jobs": [
      "Search last 7 days by topic via You.com",
      "Scan results (source, excerpt/highlight, date)",
      "Save source-linked draft questions",
      "Open draft in the existing QuestionManager editor",
      "Explicit host-reviewed publish flow (4 choices + correct answer)"
    ],
    "layout": {
      "desktop": {
        "grid": "lg:grid lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-4",
        "left": "Results/Drafts list in a dense ledger (ScrollArea).",
        "right": "Inspector panel: selected result/draft details + actions (Save draft / Open in editor / Publish).",
        "sticky": "Inspector header row sticky top-0 within panel; list header sticky top-0 within ScrollArea."
      },
      "mobile": {
        "pattern": "Single column list; selecting a row opens Drawer (Vaul via shadcn Drawer) as inspector.",
        "drawer": "h-[92dvh] with snap points optional; keep actions in a sticky bottom action bar inside drawer.",
        "safe_area": "pb-[env(safe-area-inset-bottom)] for bottom bars"
      }
    },
    "command_strip_(top_of_newsroom_tab)": {
      "use_existing_recipe": "shared_ui_recipes_to_add_(no_new_palette).command_strip",
      "controls_order": [
        "Query input (dominant)",
        "Last 7 days chip (fixed, non-editable label)",
        "Search button (primary)",
        "Optional: domain include/exclude popover (advanced)"
      ],
      "spacing": "gap-2; wrap on mobile; keep Search button full-width on xs.",
      "testids": [
        "newsroom-command-strip",
        "newsroom-query-input",
        "newsroom-search-button",
        "newsroom-freshness-chip"
      ]
    },
    "results_list_row_spec": {
      "row_height": "min-h-[56px] (dense, readable)",
      "row_classes": "flex items-start gap-3 px-3 py-2 border-b border-[color:var(--hh-line)] hover:bg-[color:var(--hh-raised)] transition-colors duration-150",
      "left_gutter": "16px favicon/avatar square OR source initial badge (no images beyond favicon_url if provided by API)",
      "content": [
        "Title (1 line, truncate)",
        "Excerpt/highlight (2 lines clamp, muted)",
        "Meta line: domain • publication date (tabular nums)"
      ],
      "selection": "Use the same selected treatment as QuestionManager rows: subtle raised bg + cyan 3px spine.",
      "right_side": "Save Draft icon button + external link icon button (hidden until hover on desktop; always visible on touch).",
      "testids": [
        "newsroom-results-list",
        "newsroom-result-row",
        "newsroom-result-row-select",
        "newsroom-result-save-draft-button",
        "newsroom-result-open-source-link"
      ]
    },
    "drafts_list": {
      "placement": "Second tab or segmented control inside Newsroom: Results | Drafts (Tabs component).",
      "draft_row": "Reuse QuestionManager compact row styling; add a small 'SOURCE' chip + date.",
      "empty_state": "Muted copy + one ghost button: 'Search news' or 'Clear filters'. No illustrations.",
      "testids": [
        "newsroom-drafts-tab",
        "newsroom-draft-row",
        "newsroom-open-draft-in-editor-button"
      ]
    },
    "inspector_panel": {
      "container": "hh-panel overflow-hidden",
      "header": "Compact: title + source chip + date; actions aligned right on desktop.",
      "sections": [
        "Source block: favicon + domain + full URL (truncate with copy button)",
        "Excerpt block: highlights rendered as bullet list or quoted paragraphs",
        "Draft linkage: show whether a draft exists for this source",
        "Actions: Save Draft / Open in Editor / Publish (Publish disabled until host reviewed)"
      ],
      "progressive_disclosure": "Put raw JSON / extra metadata behind Collapsible labeled 'Details'.",
      "testids": [
        "newsroom-inspector",
        "newsroom-inspector-source-url",
        "newsroom-inspector-copy-url-button",
        "newsroom-inspector-save-draft-button",
        "newsroom-inspector-open-editor-button",
        "newsroom-inspector-publish-button",
        "newsroom-inspector-details-collapsible"
      ]
    },
    "publish_review_gate": {
      "rule": "Publishing requires explicit host review: 4 choices present + correct answer selected + source attached.",
      "ui_pattern": "In editor, show a small 'REVIEW REQUIRED' stamp (hh-stamp) until conditions met; then enable Publish.",
      "feedback": "If blocked, show inline Alert (shadcn Alert) above Publish with i18n string; also Sonner toast on click.",
      "testids": [
        "newsroom-review-required-alert",
        "newsroom-publish-disabled-reason"
      ]
    },
    "loading_empty_error_states_(EN_only_strings_via_i18n)": {
      "loading": "Use shadcn Skeleton rows (6–8) matching row height; keep list header visible.",
      "empty": "No results: show muted message + tips (try broader topic) + keep query in input.",
      "error": "Use Alert with destructive accent; never show credentials; include 'Try again' ghost button.",
      "unavailable": "If You.com API unavailable: show a calm banner in inspector + disable Search button with tooltip."
    },
    "components_(must_reuse_existing_shadcn)_paths": {
      "list_and_structure": [
        "/app/frontend/src/components/ui/scroll-area.jsx",
        "/app/frontend/src/components/ui/separator.jsx",
        "/app/frontend/src/components/ui/tabs.jsx",
        "/app/frontend/src/components/ui/collapsible.jsx",
        "/app/frontend/src/components/ui/table.jsx (optional for desktop header alignment)"
      ],
      "overlays": [
        "/app/frontend/src/components/ui/drawer.jsx (mobile inspector)",
        "/app/frontend/src/components/ui/dialog.jsx (confirm publish / discard draft)",
        "/app/frontend/src/components/ui/popover.jsx (advanced filters)",
        "/app/frontend/src/components/ui/tooltip.jsx"
      ],
      "feedback": [
        "/app/frontend/src/components/ui/alert.jsx",
        "/app/frontend/src/components/ui/skeleton.jsx",
        "/app/frontend/src/components/ui/sonner.jsx"
      ],
      "inputs": [
        "/app/frontend/src/components/ui/input.jsx",
        "/app/frontend/src/components/ui/button.jsx",
        "/app/frontend/src/components/ui/badge.jsx"
      ]
    },
    "micro_interactions_(keep_calm)": {
      "row_hover": "Only background tint + reveal actions (opacity transition 150ms).",
      "save_draft": "On click: apply .hh-pop to icon button; toast 'Draft saved'.",
      "external_link": "Open in new tab; show subtle tooltip 'Open source'.",
      "scroll": "Sticky headers use backdrop blur via existing .hh-editor style only if already present; otherwise solid bg to avoid shimmer."
    },
    "data_integrity_messaging": {
      "rule": "Position a small disclaimer under results header: 'Search results are for research; verify before publishing.'",
      "style": "hh-meta + muted; no alarmist red."
    },
    "instructions_to_main_agent": [
      "Append-only: do not change existing palette/tokens; reuse hh-workspace density and row patterns.",
      "Newsroom should feel like a ledger: thin separators, sticky headers, master-detail inspector.",
      "Use You.com results fields (title/url/description/highlights/favicon/date) as the only content; do not scrape.",
      "All new interactive + key info elements must include data-testid (kebab-case).",
      "Keep implementation in .js/.jsx; no .tsx patterns."
    ]
  }
