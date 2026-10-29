# Professional UI/UX Design Playbook for Codex

> Reusable design and engineering instructions for distinctive, polished, accessible production interfaces. Copy this file to a project as `DESIGN_GUIDELINES.md`, reference it from `AGENTS.md`, or paste the **Master Codex Prompt** into Codex. Adapt the placeholders before each project.

## 1. The core idea

Design for a specific audience, product, and brand—not for a generic screenshot. Professional quality comes from content hierarchy, taste, consistency, interaction clarity, restraint, and repeated visual review. Animation, 3D, and visual effects are optional tools, not proof of quality.

### Non-negotiable principles

1. **Clarity first:** The user understands what this product does, where they are, and what to do next in five seconds.
2. **Strong hierarchy:** One dominant message/action per view; supporting details progressively disclosed.
3. **Recognizable character:** Choose one cohesive visual concept informed by the domain, not a random trend.
4. **Restraint:** Prefer a few deliberate moments over constant gradients, glows, shadows, and animations.
5. **Content is design:** Use realistic, specific copy, examples, data, and meaningful empty states. Never invent testimonials or fake metrics.
6. **Accessibility by default:** Keyboard, semantics, contrast, legibility, zoom, reduced motion, and screen-reader experience are part of the design.
7. **Performance is UX:** Fast, responsive, stable layouts matter more than effects.
8. **Visual QA:** Inspect at mobile, tablet, and desktop widths; iterate based on actual renders.

## 2. Avoid the recognizable “AI-generated UI” look

Avoid these defaults unless the brief explicitly warrants them:

- Purple/blue aurora gradients, blurred neon blobs, glassmorphism everywhere, and uniform giant rounded cards.
- Centered headline + generic subtitle + two pill buttons + three feature cards for every product.
- Random decorative 3D spheres, particle fields, scroll hijacking, parallax on every section, and excessive entrance animations.
- Identical section padding throughout, excessive whitespace without hierarchy, stock-sounding copy, repetitive icon tiles.
- Every surface having a border, drop shadow, colored background, and hover transform simultaneously.
- Overly tiny uppercase labels, low-contrast gray body text, and thin font weights on complex backgrounds.

Instead, establish an intentional design thesis: e.g. “editorial financial dashboard with dense but calm data,” “warm tactile creative portfolio with one interactive 3D artifact,” or “precise technical tool with crisp type and visible system state.” Use asymmetry where meaningful; vary section rhythm; give important content room and secondary content less weight.

## 2A. Apply this playbook proportionately (mandatory, token-efficient)

**Default: implement the requested change, not a design workshop.** Apply core principles silently, keeping explanations short. Use the smallest relevant set of guidance:

| Task scope | Design effort | Verification |
|---|---|---|
| **Small change** — button, copy, spacing, bug fix | Preserve existing system; check affordance, readability, and consistency. No personas or alternative concepts. | Relevant focused tests and viewport if affected. |
| **Feature** — form, search, navigation, table, workflow | Map intended task and main states; apply relevant UX laws; select patterns that minimize mistakes. | Test happy path, errors, keyboard, and key breakpoints. |
| **New page/product or redesign** | Establish audience/goals, page structure, visual direction, interaction model, tokens. Ask questions only when blocked. | Full visual, responsive, accessibility, and flow QA. |
| **Immersive/3D request** | Add scene design, purpose, fallback, performance budget, and alternative controls. | Test reduced motion, device capability, touch, and graceful failure. |

Do **not** output verbose principle-by-principle analysis or read every reference for each edit. Consult specialist guidance only when relevant. Never demand a full UX study for a minor change. Do not invent research results or assert real user testing occurred.

## 3. The design workflow

### Discovery before code

Record:

- Product and target user; their top three jobs-to-be-done.
- Page objective and one primary call to action.
- Brand attributes (choose 3): e.g. trustworthy, playful, precise, luxurious, rebellious, warm.
- Existing brand assets, logo, fonts, images, product screenshots, colors, and content.
- Reference websites and *specific* traits to emulate (typographic scale, density, transition, navigation), not wholesale cloning.
- Required pages, states, breakpoints, internationalization, accessibility, loading/performance constraints.

### Produce a small design direction before implementation

Document 2–3 possible directions, each with:

- A one-sentence visual concept; palette; display/body fonts; layout system; image/illustration treatment.
- Navigation and page anatomy; a signature moment; accessibility/performance risks.
- Why it fits the product and what it sacrifices.

Choose one direction and build a compact system: tokens, 5–8 core components, and responsive page wireframes. Do not mix unrelated aesthetics.

## 3A. Essential UX psychology and interaction rules

Grounded in **Don't Make Me Think**, **The Design of Everyday Things**, **About Face**, **Laws of UX**, and the tactical approach of **Refactoring UI**. Apply by relevance, not as a checklist that must be discussed on every request.

### Understand goals before screens (especially for new features)

- Identify **who**, **what goal**, **what context**, and **what success looks like**. For complex products, create lightweight goal-based personas/scenarios **only from supplied research or explicitly marked assumptions**.
- Outline the shortest primary user flow, likely alternate path, and the failure/recovery path before designing elaborate screens.
- Organize information by users' mental models and vocabulary rather than implementation architecture. Make current location, next action, and back/undo affordances apparent.
- Use familiar conventions unless deviation delivers a clear benefit. Make interface copy scannable: descriptive headings, concise labels, front-loaded key information, and relevant grouping.

### Psychology-to-design rules

| Principle | Practical application | Avoid |
|---|---|---|
| **Jakob's Law / familiarity** | Familiar navigation, recognizable controls, standard terminology. | Reinventing common interactions solely for novelty. |
| **Hick's Law / decision complexity** | Prioritize choices, chunk long menus, progressively reveal advanced options. | Hiding necessary options or imposing arbitrary choice limits. |
| **Fitts's Law / target acquisition** | Comfortable targets, adequate spacing, reachable frequent actions, especially on touch. | Tiny adjacent hit areas or gesture-only essentials. |
| **Gestalt proximity / chunking** | Space related elements closer and separate unrelated groups; structure dense information. | Equally spaced elements with ambiguous relationships. |
| **Von Restorff / hierarchy** | Give the primary action distinct treatment; keep competing accents subdued. | Multiple equally loud CTAs. |
| **Tesler's Law / necessary complexity** | Use good defaults and contextual help; simplify the user's work without hiding consequential decisions. | Removing required controls or obscuring critical details. |
| **Doherty threshold / feedback** | Respond to actions promptly; use appropriate pending indicators, optimistic UI only when safe. | Dead clicks, frozen screens, fake instant success. |

These are *heuristics*, not universal quantitative guarantees. Avoid rigid memory or timing claims derived from popular summaries of psychology research.

### Affordances, error prevention, recovery

- Every actionable control needs a visible **signifier** and a label that predicts its outcome. Interaction should not depend on hover alone.
- Use natural **mapping** between a control and its effect; show system status and feedback.
- Prevent invalid actions with constraints, defaults, inline guidance, and validation where useful.
- Distinguish slips from misunderstandings: offer undo for reversible actions; confirm destructive/irreversible actions in proportion to risk.
- Keep draft state when appropriate; preserve entered information after errors; use actionable, respectful error messages.
- For forms, search, tables, filters, and multi-step flows, design empty/loading/error/success states and keyboard behavior before decorative polish.

### Tiny usability review (appropriate to task scope)

For a new page or substantial flow, evaluate these questions: **Can a new visitor tell what this is? Can they find the next action? Can they recover from a mistake? Can they complete the primary task without needless choices?** Test representative real users when available; code review or a simulated walkthrough is **not** actual user testing. Never report fabricated success rates.

### Tactical UI refinements

- Start with layout, content hierarchy, and grayscale if brand styling obscures structural problems.
- Use a small consistent spacing scale; create **larger gaps between groups** than within groups.
- Deliberately distinguish primary, secondary, and tertiary actions. Use border/shadow/color only when they establish hierarchy.
- Prioritize before/after screenshot comparison and fixes to real visual defects rather than arbitrary aesthetic tweaking.

### Engagement only when genuinely relevant

For products with meaningful repeat usage, help users resume work, see progress, save preferences, and receive **opt-in useful reminders**. The Hooked framework (trigger, action, variable reward, investment) is optional analytical context, **not** an instruction to maximize compulsion. Never add manipulative streaks, misleading rewards, dark patterns, deceptive urgency, or excessive notifications.

## 4. Typography: treat it as the visual foundation

- Use one high-character display typeface and one highly legible text face **only if they complement each other**; a single family with multiple weights is often stronger.
- Consider Geist, Inter, IBM Plex Sans, Manrope, DM Sans, Instrument Sans, Source Sans 3 for UI; Fraunces, Newsreader, Instrument Serif, or a distinctive licensed display face for editorial accents. Verify licensing and support before use.
- Use a modular type scale and fluid sizes with `clamp()`, rather than arbitrary sizes per section.
- Set body copy around 16–18 CSS px with approximately 1.45–1.7 line-height; adjust by font, language, and context. Body text should remain readable at 200% zoom.
- Aim for 45–75 characters per line for extended prose; keep headlines visually balanced, and manually check wraps on small screens.
- Tighten tracking selectively on large headings; avoid aggressive negative letter spacing in paragraph text.
- Define typographic roles: display, h1–h4, body, small, label, caption, numeric/data. Use tabular numerals for aligned values.
- Avoid fake type hierarchies based solely on color or weight; use size, placement, and whitespace.

## 5. Theme, color, and surfaces

- Start with neutrals and one meaningful accent; optionally add a second functional/accent color. Do not distribute every brand color equally.
- Define semantic CSS variables, not hard-coded component colors: `--background`, `--foreground`, `--surface`, `--surface-raised`, `--muted`, `--border`, `--primary`, `--primary-foreground`, `--danger`, `--success`, `--focus-ring`.
- Support light/dark themes only if warranted; test **each independently** for contrast, not by naively inverting values.
- Use an 8px-ish spacing rhythm with deliberate exceptions, consistent radii, sensible border/shadow hierarchy, and a clear elevation system.
- Reserve gradients, textures, glass, and blur for art direction and separation—not as default decoration.
- Color must not be the sole carrier of state. Ensure non-text UI elements and focus indicators remain discernible.

## 6. Layout and visual composition

- Design for content: choose an appropriate max content width; combine a consistent grid with deliberate editorial breaks.
- Use scale, position, contrast, and whitespace to direct attention. A product screenshot or a useful data visualization may be the hero instead of a decorative illustration.
- Group related actions and information through proximity. Limit the number of simultaneously competing CTAs.
- Build real responsive variants: columns stack intentionally, navigation collapses accessibly, tables remain usable, touch targets stay comfortable, and no horizontal overflow is introduced.
- Prefer CSS Grid for large compositions and Flexbox for local alignment. Use container queries when component layout depends on available container width.
- Design all interaction states: default, hover, focus-visible, pressed, selected, disabled, pending, success, error, empty, and offline where relevant.

## 7. Motion and micro-interactions

Use a motion hierarchy:

1. **Feedback**: 100–200ms for hover/press/focus and toggle feedback.
2. **State transition**: approximately 180–350ms for tabs, accordions, dialogs, and content changes.
3. **Storytelling**: longer, sparing transitions for a distinctive hero or scrollytelling sequence.

These timings are guidelines, not laws. Favor opacity and transform animations; avoid animating large layout properties or expensive paint effects. Keep easing coherent. Never delay essential actions for an animation. Support `prefers-reduced-motion` by disabling nonessential movement and providing an equivalent static presentation. Avoid automatic moving content that users cannot pause or control.

## 8. 3D: when and how

Use 3D if users benefit from understanding a real object, spatial relationship, product detail, or a purposeful brand artifact. Do not introduce 3D just to fill empty space.

- **Best use cases:** product configurator, interactive object inspection, architecture/spatial demonstrations, focused hero sculpture, education, data/spatial storytelling.
- **Prefer CSS transforms** for lightweight perspective cards. Use **Spline** for art-directed scenes, **Three.js / React Three Fiber** for engineered real-time interactions, **Drei** for R3F helpers, and **GSAP** or **Motion** for choreographed surrounding UI as appropriate.
- Establish camera framing, lighting, shadows, materials, object scale, and composition. A carefully lit simple model outperforms a cluttered complex scene.
- Provide mouse, touch, and keyboard-accessible equivalent controls where object manipulation matters. Avoid relying solely on drag/hover instructions.
- Provide alt text or an adjacent accessible textual summary and a static poster/backup view if canvas fails, WebGL is unavailable, data saver is active, or reduced-motion is requested.
- Lazy-load heavy scenes; defer until visible or requested, minimize textures and polygons, compress models/textures, cap device pixel ratio when appropriate, clean up resources, and avoid perpetual rendering when idle.
- Avoid making an essential form or navigation depend on WebGL.

## 9. Accessibility and simplicity checklist

Target **WCAG 2.2 AA** and verify rather than merely claiming compliance.

- Semantic landmarks, logical heading order, true buttons and links, associated labels, useful alt text.
- All actions operable by keyboard, visible focus, no keyboard traps, sensible focus return after dialogs.
- Minimum contrast generally 4.5:1 for normal text, 3:1 for large text; check active controls and non-text contrast requirements too.
- Touch targets ideally at least 44×44 CSS px; WCAG 2.2 AA has specific 24×24 minimum/spacing exceptions. Do not treat 44×44 as a universal compliance rule.
- Never disable zoom; ensure layout and functionality at 200% zoom and 320 CSS px reflow, where applicable.
- Reduced motion and no forced smooth-scrolling. Make autoplay motion pausable if necessary.
- Form errors described in text, associated with inputs; accessible validation; clear recovery instructions.
- Accessible icon-only labels; legible placeholders (but never placeholders as the only labels); distinguish links from plain text.
- Test with keyboard-only, screen reader, high contrast/forced colors, and browser zoom—not just automated scans.

## 10. Curated library and tool directory

Choose the *fewest* dependencies that satisfy the brief. These are alternatives and complements, **not** an instruction to install all of them. Check package documentation and compatibility with the project's exact React/framework versions.

| Need | Recommended default | Alternatives / specialized tools | Guidance |
|---|---|---|---|
| Framework | Next.js (React) | Astro for content-heavy sites, Vite + React for SPAs, Remix/React Router framework | Preserve an existing framework. |
| Styling | Tailwind CSS + CSS custom properties | CSS Modules, vanilla-extract, Panda CSS | Design tokens before utility sprawl. |
| Accessible components | shadcn/ui (customizable components) | Radix UI, Base UI, React Aria Components, Headless UI | Customize visual language; test behaviors. |
| Icons | Lucide | Phosphor, Heroicons, Tabler Icons | Pick one visual family. |
| UI motion | Motion (`motion/react`) | CSS transitions, React Spring | Use one main UI animation approach. |
| Timeline/scroll motion | GSAP + ScrollTrigger | Native CSS scroll-driven animation where supported | For genuinely complex sequencing. |
| Smooth scroll | Native browser scrolling | Lenis (selective) | Do not hijack natural scrolling by default. |
| 3D WebGL | Three.js + `@react-three/fiber` + `@react-three/drei` | Babylon.js, TresJS (Vue) | React Three Fiber version must match React major. |
| 3D authoring | Blender + glTF/GLB | Spline, Cinema 4D | Optimize asset output for the web. |
| 3D asset compression | glTF Transform, Draco, Meshopt, KTX2/Basis | `gltfjsx` for R3F component generation | Validate compressed asset support and visual fidelity. |
| Lightweight animation | CSS, SVG, Motion | Rive, Lottie / dotLottie | Prefer vector/state-machine animation for lightweight UI illustration. |
| Typography | Self-hosted variable webfonts, `next/font` in Next.js | Google Fonts, Fontsource | Respect license, language coverage, font loading. |
| Theme management | CSS variables + `prefers-color-scheme` | `next-themes` | Avoid theme flashes and untested dark mode. |
| Charts/data | Recharts | Visx, Apache ECharts, Nivo, D3 | Choose on complexity and accessibility needs. |
| Forms | React Hook Form + Zod | Formik, native HTML validation | Clear inline errors and accessible messages. |
| Notifications | Sonner | React Aria patterns, custom live-region toasts | Avoid unnecessary blocking modals. |
| Image optimization | Next Image or framework-native pipeline | Sharp, responsive `srcset` | Responsive sizes, reserved aspect ratios, formats. |
| UI documentation | Storybook | Ladle, component playground | Show interactive states and variants. |
| Accessibility audits | axe-core / jest-axe | Accessibility Insights, Lighthouse, WAVE | Manual checks remain mandatory. |
| E2E / visual testing | Playwright | Cypress, Chromatic, Percy | Screenshot at target viewport sizes; test keyboard flows. |
| Design & inspiration | Figma, real product screenshots | Mobbin, Awwwards, Godly, Behance, Dribbble | Understand patterns; do not blindly copy a showcase. |

### Suggested dependency profiles

**Editorial marketing site:** Astro or Next.js + Tailwind/CSS variables + Motion or CSS + minimal accessible primitives. Avoid WebGL unless it expresses the concept.

**SaaS/dashboard:** Next.js + Tailwind + shadcn/ui/Radix + Lucide + Recharts or Visx + React Hook Form/Zod + Playwright. Bias toward clear information density, states, and speed.

**Immersive portfolio/product:** Next.js or Vite React + Tailwind/CSS Modules + Three.js/R3F/Drei + Motion; add GSAP only for complex choreography. Keep text, navigation, and actions in semantic DOM.

## 11. Implementation discipline

1. Inspect the repository, README, design files, dependencies, and existing conventions. Avoid rewriting unrelated code.
2. Write a compact design brief and inventory of required screens/states. State assumptions explicitly.
3. Create tokens for colors, typography, spacing, radii, shadows, breakpoints, and motion.
4. Implement typography, shell, navigation, and responsive layout **before** decorative effects.
5. Build reusable but not overabstracted components, with semantic HTML and clear variants.
6. Use realistic copy and data only where sourced; mark demo data clearly.
7. Add animation and 3D after static UX is complete. Preserve a useful fallback.
8. Run typecheck/lint/tests/build where configured; use automated accessibility checks and manual keyboard checks.
9. Inspect screenshots at approximately 375, 768, 1280, and 1440 CSS px (plus actual target devices). Fix wrapping, contrast, focus, overflow, spacing, image cropping, and gesture discoverability.
10. Report what shipped, major design decisions, tests performed, known limitations, and any remaining choices.

## 11A. Scope-aware validation and concise reporting

- **Small edit:** run the relevant check; report the file/change and any blocker in 1–3 sentences.
- **Feature:** validate the user flow, error states, keyboard operation, and affected viewport(s). Mention remaining limitations concisely.
- **New page/redesign:** perform deeper visual and accessibility review as resources permit, prioritizing meaningful fixes.
- **3D/advanced motion:** test fallback and reduced motion as essential quality gates.
- Only claim checks that actually ran. Don't require artifacts, detailed design rationale, or broad dependency installations for small changes.
- Before accepting a design, ask whether it serves the primary task; visual polish cannot compensate for confusing task flows.

## 12. Master Codex Prompt (copy and adapt)

```text
You are acting as a senior product designer, art director, interaction designer,
accessibility specialist, and staff-level frontend engineer.

PROJECT
- Product: [describe product]
- Audience: [primary users]
- Primary job/user outcome: [the thing a user wants to achieve]
- Required pages and functionality: [list]
- Brand personality: [three adjectives]
- Existing design assets / URLs / constraints: [list]
- Preferred framework: [existing stack, or recommend one]
- Desired visual references: [URLs and SPECIFIC traits to borrow]
- Desired use of 3D: [none / optional focal point / functional interactive model]
- Deployment/performance constraints: [list]

DESIGN DIRECTIVE
Build a distinctive, production-quality UI that looks designed for this exact
product by a skilled human team. Aim for restraint, strong typography, clear
hierarchy, thoughtful negative space, grounded content, and consistent details.
Do not fall back to a generic AI landing-page template.

Before writing code:
1. Inspect existing code, dependencies, assets, and project conventions.
2. Summarize user goals, information architecture, primary task flow, error recovery, and risks. Do not invent personas or research.
3. Only for meaningful new-page/redesign tasks, consider 1-3 coherent art directions in concise terms: typographic system,
   palette, grid, density, key imagery, motion, and why each fits.
4. Select the strongest direction based on product/user goals (or ask if a choice
   would materially change the deliverable). State the design thesis.
5. For new components or redesigns, make a compact design system: semantic color tokens, font roles, spacing,
   widths, radii, surfaces, interactive states, and motion rules.

VISUAL REQUIREMENTS
- Create a deliberate composition, not a uniform template of pill buttons,
  giant headline, gradient blobs, and three equal feature cards.
- Prioritize readable, expressive typography with proper line breaks and scale.
- Give each section a reason to exist; vary hierarchy and rhythm while keeping
  alignment systematic. Make the primary CTA obvious.
- Use a limited color palette and semantic design tokens. Support light/dark
  themes only when useful, with contrast checked in each.
- Use one consistent icon language. Don't add meaningless decoration.
- Design mobile, tablet, and desktop layouts intentionally, not only by stacking.
- Implement real loading, error, empty, success, disabled and focus states.
- Use genuine project data/assets, or visibly labeled placeholders; never invent
  testimonials, clients, ratings, growth metrics, or business claims.

MOTION + 3D
- Every animation must explain state, guide attention, or express brand.
- Prefer lightweight CSS/Motion for micro-interactions; GSAP for complex
  timelines only; R3F/Three.js for purposeful 3D only.
- If using 3D, plan camera, lighting, materials, pointer/touch interaction,
  responsive framing, loading poster, failure fallback, and performance budget.
- Keep critical content/controls in accessible HTML, not only inside canvas.
- Support prefers-reduced-motion and avoid scroll hijacking and distracting loops.
- Lazy-load heavy assets, minimize render work, and preserve fast input response.

ACCESSIBILITY + UX
- Target WCAG 2.2 AA. Use semantic HTML, labels, alt text, correct heading order,
  visible keyboard focus, accessible dialogs, and operable controls.
- Maintain appropriate text/non-text contrast, readable type, sensible targets,
  useful error messages, zoom/reflow, and keyboard navigation.
- Favor progressive disclosure and predictable navigation over visual gimmicks.
- Test keyboard interaction, mobile touch interaction, reduced motion and zoom.

IMPLEMENTATION
- Preserve existing stack and established code patterns where practical.
- Install only necessary, compatible dependencies; confirm current official docs.
- Favor reusable components, semantic markup, CSS variables, and maintainable code.
- No dead buttons, fake interactivity, broken links, console warnings, or hidden
  critical functionality. Clarify any backend-dependent feature before claiming
  that it works.
- Do not alter unrelated files. Do not deploy or publish without authorization.

VALIDATE AND ITERATE
- Run configured build/typecheck/lint/test commands when available.
- Visually inspect at 375, 768, 1280, and 1440 CSS px, or relevant device sizes.
- Check horizontal overflow, type wraps, responsive images, layout shifts,
  consistency, loading states, contrast, focus order, and motion preferences.
- For new pages/redesigns, perform a visual refinement pass after observing the actual UI. For small edits, focus on the requested area.
- If browser preview is unavailable, explicitly say visual verification remains.

DELIVERABLE
Provide: (1) design thesis and key decisions; (2) implemented UI;
(3) dependency choices and rationale; (4) verification results;
(5) remaining caveats. Optimize for user experience and product credibility,
not visual spectacle.
```

## 13. Review scorecard (rate 1–5, fix anything below 4)

| Criterion | Review question |
|---|---|
| Product fit | Could this design belong to any brand, or is it specifically right here? |
| Hierarchy | Can a new user find the primary action quickly? |
| Typography | Are headline wraps, readability, weights, and information density polished? |
| Layout | Is alignment consistent while composition remains visually interesting? |
| Content | Is the language specific, honest, and useful? |
| Interaction | Do controls have clear affordances, state feedback, and recovery? |
| Accessibility | Does keyboard, screen reader, contrast, zoom, and reduced motion work? |
| Responsive | Are mobile and tablet experiences intentionally composed? |
| Performance | Are imagery, fonts, 3D, and animation justified and efficient? |
| Craft | Are spacing, borders, shadows, icon strokes, and details coherent? |
| Discoverability | Can users tell what is clickable and locate the next step? |
| Task success | Can users complete the main workflow without unnecessary decisions? |
| Error recovery | Can users understand, prevent, or reverse mistakes? |

## 14. Official documentation and standards

- [Tailwind CSS](https://tailwindcss.com/docs)
- [shadcn/ui](https://ui.shadcn.com/docs), [theming](https://ui.shadcn.com/docs/theming)
- [Radix UI](https://www.radix-ui.com/primitives), [React Aria](https://react-spectrum.adobe.com/react-aria/)
- [Motion for React](https://motion.dev/docs/react)
- [GSAP ScrollTrigger](https://gsap.com/docs/v3/Plugins/ScrollTrigger/)
- [Three.js](https://threejs.org/docs/), [React Three Fiber](https://r3f.docs.pmnd.rs/), [Drei](https://github.com/pmndrs/drei)
- [Lenis](https://github.com/darkroomengineering/lenis)
- [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/), [WAI tutorials](https://www.w3.org/WAI/tutorials/)
- [Playwright](https://playwright.dev/), [axe-core](https://github.com/dequelabs/axe-core)
- [web.dev performance](https://web.dev/performance)

_This is a design playbook, not a guarantee of conformance or a frozen version manifest. Recheck installation commands, package versions, framework compatibility, licenses, and browser support at implementation time._

## 15. Selected foundational design references (conceptual guidance)

- **Steve Krug, _Don't Make Me Think_** — scanning, conventional navigation, low-friction usability and realistic task observation.
- **Don Norman, _The Design of Everyday Things_** — conceptual models, signifiers, affordances, mapping, feedback, constraints, errors.
- **Adam Wathan & Steve Schoger, _Refactoring UI_** — tactical hierarchy, spacing, typography, color and depth.
- **Alan Cooper et al., _About Face_** — goal-directed design, research-backed personas, scenarios and complex interaction architecture.
- **Jon Yablonski, _Laws of UX_** — use relevant psychology as design heuristics rather than absolute laws; https://lawsofux.com/.
- **Nir Eyal, _Hooked_** — optional retention model only when aligned with genuine user value and ethical engagement.

This guide paraphrases high-level principles; it does not reproduce book text. Always favor observed user outcomes and accessibility requirements over rigid rules.
